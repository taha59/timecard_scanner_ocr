import {apiFetch} from './api';
import type {CropReading,CropTask} from './ocr-policy';
export type ModelManifest={version:string;bytes:number;sha256:string;url:string;characters:string[]};
export type DeviceOcrStats={loadMs:number;readMs:number;total:number;processed:number;skipped:number;reused:boolean;threads?:number;imageDecodeMs?:number;inputPrepMs?:number;inferenceMs?:number;textDecodeMs?:number;cleanupMs?:number;otherMs?:number};
export type DeviceTask=CropTask;
export const MODEL_CACHE='timecard-device-model-v1';
const modelKey=(m:ModelManifest)=>`/device-model-cache/${m.version}/${m.sha256}`;
export function deviceSupported(){return window.isSecureContext&&'caches' in window&&'Worker' in window&&'WebAssembly' in window&&'OffscreenCanvas' in window;}
export async function modelPresent(m:ModelManifest){return deviceSupported()&&Boolean(await (await caches.open(MODEL_CACHE)).match(modelKey(m)));}
export async function removeModel(){releaseDeviceModel();await caches.delete(MODEL_CACHE);}
export async function downloadModel(m:ModelManifest,signal:AbortSignal,progress:(text:string)=>void){
 const cache=await caches.open(MODEL_CACHE);
 const response=await apiFetch(m.url,{signal,cache:'no-store'});
 if(!response.ok||!response.body)throw new Error('Model download failed. The server may need its OCR models installed.');
 const reader=response.body.getReader(),chunks:Uint8Array[]=[];let received=0;
 try{while(true){const {done,value}=await reader.read();if(done)break;received+=value.length;if(received>m.bytes)throw new Error('Unexpected model size.');chunks.push(value);progress(`Downloading model: ${Math.floor(received/m.bytes*100)}%`);}}finally{reader.releaseLock();}
 signal.throwIfAborted();
 const bytes=new Uint8Array(received);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
 const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('');
 if(received!==m.bytes||hash!==m.sha256)throw new Error('Model verification failed. Try downloading again.');
 signal.throwIfAborted();
 await cache.put(modelKey(m),new Response(bytes,{headers:{'Content-Type':'application/octet-stream'}}));
 if(signal.aborted){await cache.delete(modelKey(m));signal.throwIfAborted();}
 // The browser decides whether persistence can be granted; denial is not an error.
 try{await navigator.storage?.persist?.();}catch{}
}
let currentWorker:Worker|null=null,workerKey='',workerReady=false,inFlight=false;
let idleTimer:ReturnType<typeof setTimeout>|undefined;
let cancelActive:(()=>void)|null=null;
function discardWorker(){
 if(idleTimer)clearTimeout(idleTimer);idleTimer=undefined;
 currentWorker?.terminate();currentWorker=null;workerKey='';workerReady=false;
}
export function releaseDeviceModel(){const cancel=cancelActive;cancelActive=null;cancel?.();discardWorker();}
window.addEventListener('pagehide',releaseDeviceModel);
function abortable<T>(work:Promise<T>,signal:AbortSignal){
 return new Promise<T>((resolve,reject)=>{
  const cancel=()=>{signal.removeEventListener('abort',cancel);reject(new DOMException('Canceled','AbortError'));};
  signal.addEventListener('abort',cancel,{once:true});
  if(signal.aborted){cancel();return;}
  work.then(value=>{signal.removeEventListener('abort',cancel);resolve(value);},error=>{signal.removeEventListener('abort',cancel);reject(error);});
 });
}
async function recognizeAttempt(m:ModelManifest,tasks:DeviceTask[],signal:AbortSignal,progress:(text:string)=>void,report:((stats:DeviceOcrStats)=>void)|undefined,forceSingleThread=false){
 if(inFlight)throw new Error('Another device scan is still running.');
 signal.throwIfAborted();inFlight=true;
 let worker:Worker|undefined;
 try{
  if(idleTimer)clearTimeout(idleTimer);idleTimer=undefined;
  const key=modelKey(m);
  const reuse=Boolean(currentWorker&&workerReady&&workerKey===key);
  let model:ArrayBuffer|undefined;
  if(!reuse){
   releaseDeviceModel();
   const cached=await (await caches.open(MODEL_CACHE)).match(key);
   if(!cached)throw new Error('The saved model is no longer available. Download it again before scanning.');
   model=await abortable(cached.arrayBuffer(),signal);signal.throwIfAborted();
   currentWorker=new Worker(new URL('./ocr.worker.ts',import.meta.url),{type:'module'});workerKey=key;
  }
  worker=currentWorker!;
  const active=worker;
  return await new Promise<Record<string,CropReading>>((resolve,reject)=>{
   let initialized=reuse,bootTimer:ReturnType<typeof setTimeout>|undefined;
   const startupError=(message:string)=>{const error=new Error(message);error.name='DeviceOcrStartupError';return error;};
   const finish=(discard:boolean)=>{
    if(bootTimer)clearTimeout(bootTimer);
    signal.removeEventListener('abort',cancel);cancelActive=null;active.onmessage=null;active.onerror=null;
    if(discard&&currentWorker===active)discardWorker();
   };
   const cancel=()=>{finish(true);reject(new DOMException('Canceled','AbortError'));};
   cancelActive=cancel;
   signal.addEventListener('abort',cancel,{once:true});
   if(signal.aborted){cancel();return;}
   active.onerror=()=>{finish(true);reject(initialized?new Error('Device OCR could not run. Try manual entry or a newer browser.'):startupError('The OCR runtime could not start.'));};
   active.onmessage=event=>{
    const data=event.data;
    if(data.initialized){initialized=true;if(bootTimer)clearTimeout(bootTimer);}
    else if(data.progress)progress(data.progress);
    else if(data.error){finish(true);reject(initialized?new Error(data.error):startupError(data.error));}
    else if(data.readings){workerReady=true;report?.(data.stats);finish(false);resolve(data.readings);}
   };
   progress(reuse?'Using the already loaded device model…':'Loading the model on this device…');
   if(!reuse)bootTimer=setTimeout(()=>{finish(true);reject(startupError('The OCR runtime took too long to start.'));},30_000);
   active.postMessage({model,tasks,characters:model?m.characters:undefined,forceSingleThread},model?[model]:[]);
  });
 }catch(error){if(worker&&currentWorker===worker)releaseDeviceModel();throw error;}
 finally{
  inFlight=false;
  // Retain only the loaded model, for at most five minutes between scans.
  if(currentWorker)idleTimer=setTimeout(releaseDeviceModel,5*60*1000);
 }
}

export async function recognizeOnDevice(m:ModelManifest,tasks:DeviceTask[],signal:AbortSignal,progress:(text:string)=>void,report?:(stats:DeviceOcrStats)=>void){
 try{return await recognizeAttempt(m,tasks,signal,progress,report);}
 catch(error){
  if(signal.aborted||(error as Error).name!=='DeviceOcrStartupError')throw error;
  progress('Threaded OCR could not start. Retrying with one CPU thread…');
  return await recognizeAttempt(m,tasks,signal,progress,report,true);
 }
}
