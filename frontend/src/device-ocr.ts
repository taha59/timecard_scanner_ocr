import {apiFetch} from './api';
export type ModelManifest={version:string;bytes:number;sha256:string;url:string;characters:string[]};
export type DeviceTask={id:string;image:string};
export const MODEL_CACHE='timecard-device-model-v1';
const modelKey=(m:ModelManifest)=>`/device-model-cache/${m.version}/${m.sha256}`;
export function deviceSupported(){return window.isSecureContext&&'caches' in window&&'Worker' in window&&'WebAssembly' in window&&'OffscreenCanvas' in window;}
export async function modelPresent(m:ModelManifest){return deviceSupported()&&Boolean(await (await caches.open(MODEL_CACHE)).match(modelKey(m)));}
export async function removeModel(){await caches.delete(MODEL_CACHE);}
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
export async function recognizeOnDevice(m:ModelManifest,tasks:DeviceTask[],signal:AbortSignal,progress:(text:string)=>void){
 const cached=await (await caches.open(MODEL_CACHE)).match(modelKey(m));
 if(!cached)throw new Error('The saved model is no longer available. Download it again before scanning.');
 const model=await cached.arrayBuffer();signal.throwIfAborted();
 const worker=new Worker(new URL('./ocr.worker.ts',import.meta.url),{type:'module'});
 return await new Promise<Record<string,{text:string;confidence:number}>>((resolve,reject)=>{
  const stop=()=>{worker.terminate();signal.removeEventListener('abort',cancel);};
  const cancel=()=>{stop();reject(new DOMException('Canceled','AbortError'));};
  signal.addEventListener('abort',cancel,{once:true});
  if(signal.aborted){cancel();return;}
  worker.onerror=()=>{stop();reject(new Error('Device OCR could not run. Try manual entry or a newer browser.'));};
  worker.onmessage=event=>{const data=event.data;if(data.progress)progress(data.progress);else if(data.error){stop();reject(new Error(data.error));}else if(data.readings){stop();resolve(data.readings);}};
  progress('Loading the model on this device…');
  worker.postMessage({model,tasks,characters:m.characters},[model]);
 });
}
