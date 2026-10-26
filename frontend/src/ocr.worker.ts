import * as ort from 'onnxruntime-web/wasm';
import wasmUrl from 'onnxruntime-web/ort-wasm-simd-threaded.wasm?url';
import wasmModuleUrl from 'onnxruntime-web/ort-wasm-simd-threaded.mjs?url';
import {skipFallback,type CropReading,type CropTask} from './ocr-policy';
const requestedThreads=import.meta.env.VITE_OCR_THREADS==='1'?1:2;
ort.env.wasm.numThreads=self.crossOriginIsolated&&typeof SharedArrayBuffer!=='undefined'?Math.min(2,Math.max(1,requestedThreads),navigator.hardwareConcurrency||1):1;
ort.env.wasm.proxy=false;
// These URLs previously had no COEP headers and may be cached indefinitely.
// A new cache key forces a header-correct fetch when enabling threaded workers.
ort.env.wasm.wasmPaths={wasm:`${wasmUrl}?ocrRuntime=2`,mjs:`${wasmModuleUrl}?ocrRuntime=2`};
const scope=self as unknown as {onmessage:((event:MessageEvent)=>void)|null;postMessage:(data:unknown)=>void};
let session:ort.InferenceSession|undefined;
let characters:string[]=[];
scope.onmessage=async event=>{
 try{
  const {model,tasks}=event.data as {model?:ArrayBuffer;tasks:CropTask[]};
  const started=performance.now(),reused=Boolean(session);
  if(!session){
   if(!model)throw new Error('The device model needs to be loaded again.');
   if(event.data.forceSingleThread)ort.env.wasm.numThreads=1;
   scope.postMessage({progress:`Starting OCR runtime (${ort.env.wasm.numThreads} thread${ort.env.wasm.numThreads===1?'':'s'})…`});
   characters=event.data.characters;
   session=await ort.InferenceSession.create(model,{executionProviders:['wasm'],graphOptimizationLevel:'all'});
  }
  scope.postMessage({initialized:true});
  const loaded=performance.now(),readings:Record<string,CropReading>={};
  // Originals always run before any shared fallback that depends on them.
  const ordered=[...tasks].sort((a,b)=>Number(a.required===false)-Number(b.required===false));
  let processed=0,skipped=0;
  const canvas=new OffscreenCanvas(1,48),context=canvas.getContext('2d');
  if(!context)throw new Error('Image processing is unavailable in this browser.');
  for(let index=0;index<ordered.length;index++){
   const task=ordered[index];
   if(skipFallback(task,readings)){
    readings[task.id]={text:'',confidence:0,skipped_reason:'original_valid'};skipped++;
   }else{
    const bitmap=await createImageBitmap(await (await fetch(task.image)).blob());
    const height=48,width=Math.max(320,Math.min(1024,Math.ceil(height*bitmap.width/bitmap.height)));
    const resizedWidth=Math.min(width,Math.ceil(height*bitmap.width/bitmap.height));
    canvas.width=resizedWidth;
    context.drawImage(bitmap,0,0,resizedWidth,height);bitmap.close();
    const rgba=context.getImageData(0,0,resizedWidth,height).data;
    const pixels=new Float32Array(3*height*width);
    for(let c=0;c<3;c++)for(let y=0;y<height;y++)for(let x=0;x<resizedWidth;x++)pixels[c*height*width+y*width+x]=rgba[(y*resizedWidth+x)*4+(2-c)]/127.5-1;
    const input=new ort.Tensor('float32',pixels,[1,3,height,width]);
    let output:ort.InferenceSession.ReturnType|undefined;
    try{
     output=await session.run({[session.inputNames[0]]:input});
     const prediction=output[session.outputNames[0]],data=prediction.data as Float32Array;
     const classes=prediction.dims[2],steps=prediction.dims[1];let previous=-1,text='',score=0,count=0;
     if(classes!==characters.length)throw new Error('The OCR model vocabulary does not match. Download the latest model.');
     for(let t=0;t<steps;t++){
      let best=0;for(let c=1;c<classes;c++)if(data[t*classes+c]>data[t*classes+best])best=c;
      if(best!==0&&best!==previous){text+=characters[best];score+=data[t*classes+best];count++;}previous=best;
     }
     const quality=count?Math.max(0,Math.min(1,score/count)):0;
     readings[task.id]={text:text.slice(0,500),confidence:Math.min(.79,quality),quality};processed++;
    }finally{input.dispose();if(output)for(const tensor of Object.values(output))tensor.dispose();}
   }
   scope.postMessage({progress:`Reading on this device: ${index+1} of ${ordered.length} crops${skipped?` (${skipped} fallback retries avoided)`:''}`});
  }
  scope.postMessage({readings,stats:{loadMs:loaded-started,readMs:performance.now()-loaded,total:tasks.length,processed,skipped,reused,threads:ort.env.wasm.numThreads}});
  // Only the model/vocabulary survive this request. Crops and readings do not.
 }catch(error){
  await session?.release();session=undefined;characters=[];
  scope.postMessage({error:`Device OCR failed: ${error instanceof Error?error.message:String(error)}. Try manual entry or a newer browser.`});
 }
};
