import * as ort from 'onnxruntime-web/wasm';
import wasmUrl from 'onnxruntime-web/ort-wasm-simd-threaded.wasm?url';
import wasmModuleUrl from 'onnxruntime-web/ort-wasm-simd-threaded.mjs?url';
ort.env.wasm.numThreads=1;
ort.env.wasm.proxy=false;
ort.env.wasm.wasmPaths={wasm:wasmUrl,mjs:wasmModuleUrl};
const scope=self as unknown as {onmessage:((event:MessageEvent)=>void)|null;postMessage:(data:unknown)=>void};
scope.onmessage=async event=>{
 let session:ort.InferenceSession|undefined;
 try{
  const {model,tasks,characters}=event.data;
  session=await ort.InferenceSession.create(model,{executionProviders:['wasm'],graphOptimizationLevel:'all'});
  const readings:Record<string,{text:string;confidence:number}>={};
  for(let index=0;index<tasks.length;index++){
   const task=tasks[index];
   const bitmap=await createImageBitmap(await (await fetch(task.image)).blob());
   const height=48,width=Math.max(320,Math.min(1024,Math.ceil(height*bitmap.width/bitmap.height)));
   const resizedWidth=Math.min(width,Math.ceil(height*bitmap.width/bitmap.height));
   const canvas=new OffscreenCanvas(resizedWidth,height),context=canvas.getContext('2d');
   if(!context)throw new Error('Image processing is unavailable in this browser.');
   context.drawImage(bitmap,0,0,resizedWidth,height);bitmap.close();
   const rgba=context.getImageData(0,0,resizedWidth,height).data;
   const pixels=new Float32Array(3*height*width);
   for(let c=0;c<3;c++)for(let y=0;y<height;y++)for(let x=0;x<resizedWidth;x++)pixels[c*height*width+y*width+x]=rgba[(y*resizedWidth+x)*4+(2-c)]/127.5-1;
   const output=await session.run({[session.inputNames[0]]:new ort.Tensor('float32',pixels,[1,3,height,width])});
   const prediction=output[session.outputNames[0]],data=prediction.data as Float32Array;
   const classes=prediction.dims[2],steps=prediction.dims[1];let previous=-1,text='',score=0,count=0;
   if(classes!==characters.length)throw new Error('The OCR model vocabulary does not match. Download the latest model.');
   for(let t=0;t<steps;t++){
    let best=0;for(let c=1;c<classes;c++)if(data[t*classes+c]>data[t*classes+best])best=c;
    if(best!==0&&best!==previous){text+=characters[best];score+=data[t*classes+best];count++;}previous=best;
   }
   readings[task.id]={text:text.slice(0,500),confidence:count?Math.max(0,Math.min(.79,score/count)):0};
   for(const tensor of Object.values(output))tensor.dispose();
   scope.postMessage({progress:`Reading on this device: ${index+1} of ${tasks.length} crops`});
  }
  scope.postMessage({readings});
 }catch(error){scope.postMessage({error:`Device OCR failed: ${error instanceof Error?error.message:String(error)}. Try manual entry or a newer browser.`});}
 finally{await session?.release();}
};
