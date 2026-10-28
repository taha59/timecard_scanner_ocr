const assert=require('node:assert/strict'),vm=require('node:vm');
const {build}=require('../frontend/node_modules/esbuild');
(async()=>{
 const messages=[],inputs=[];let tick=0,modelLoads=0,fetches=0,disposed=0;
 const ids=[1,2,3,0,3,4,5],classes=6,data=new Float32Array(ids.length*classes);
 ids.forEach((id,step)=>data[step*classes+id]=.99);
 const session={inputNames:['x'],outputNames:['y'],run:async values=>{inputs.push(values.x);return {y:{data,dims:[1,ids.length,classes],dispose:()=>disposed++}};},release:async()=>{}};
 const context={performance:{now:()=>++tick},navigator:{hardwareConcurrency:4},SharedArrayBuffer,ArrayBuffer,Float32Array,Uint8ClampedArray,
  __session:session,__modelLoaded:()=>modelLoads++,__inputDisposed:()=>disposed++,
  self:{crossOriginIsolated:true,postMessage:message=>messages.push({...message,inputCount:inputs.length})},
  fetch:async()=>{fetches++;return {blob:async()=>({})};},
  createImageBitmap:async()=>({width:120,height:30,close:()=>{}}),
  OffscreenCanvas:class{constructor(){}getContext(){return {drawImage:()=>{},getImageData:(_x,_y,width,height)=>({data:new Uint8ClampedArray(width*height*4).fill(255)})};}}};
 vm.createContext(context);
 const code=await build({entryPoints:['frontend/src/ocr.worker.ts'],bundle:true,write:false,format:'iife',define:{'import.meta.env':'{}'},plugins:[{name:'mock-runtime',setup(builder){
  builder.onResolve({filter:/^onnxruntime-web\//},args=>({path:args.path,namespace:'runtime'}));
  builder.onLoad({filter:/.*/,namespace:'runtime'},args=>({contents:args.path.endsWith('?url')?'export default "runtime-asset";':`export const env={wasm:{}};export class Tensor{constructor(type,data,dims){this.data=data;this.dims=dims;}dispose(){globalThis.__inputDisposed();}}export const InferenceSession={create:async()=>{globalThis.__modelLoaded();return globalThis.__session;}};`,loader:'js'}));
 }}]});
 vm.runInContext(code.outputFiles[0].text,context);
 const tasks=[{id:'original',image:'data:test',required:true},{id:'fallback',image:'data:unused',required:false,fallback_for:['original']}];
 await context.self.onmessage({data:{model:new ArrayBuffer(8),characters:['blank','9',':','0','a','m'],tasks}});
 const first=messages.find(message=>message.readings);
 assert.equal(first.readings.original.text,'9:00am');assert.equal(first.readings.original.confidence,.79);
 assert.equal(first.readings.fallback.skipped_reason,'original_valid');
 assert.equal(first.stats.processed,1);assert.equal(first.stats.skipped,1);assert.equal(first.stats.threads,4);
 const fields=['imageDecodeMs','inputPrepMs','inferenceMs','textDecodeMs','cleanupMs','otherMs'];
 assert.ok(fields.every(key=>Number.isFinite(first.stats[key])&&first.stats[key]>=0));
 assert.equal(fields.reduce((sum,key)=>sum+first.stats[key],0),first.stats.readMs);
 assert.deepEqual(Array.from(inputs[0].dims),[1,3,48,320]);assert.equal(inputs[0].data[0],1);assert.equal(inputs[0].data[319],0);
 messages.length=0;await context.self.onmessage({data:{tasks}});
 assert.equal(messages.find(message=>message.stats).stats.reused,true);
 assert.equal(modelLoads,1);assert.equal(fetches,2);assert.equal(disposed,4);
 messages.length=0;
 const liveTasks=[{id:'a',image:'data:a',required:true},{id:'b',image:'data:b',required:true},
  {id:'retry-a',image:'data:retry',required:false,fallback_for:['a']}];
 await context.self.onmessage({data:{tasks:liveTasks,cardTasks:[['a','retry-a'],['b']]}});
 const cards=messages.filter(message=>message.cardReadings);
 assert.equal(cards.length,2);assert.equal(cards[0].cardIndex,0);assert.equal(cards[1].cardIndex,1);
 assert.equal(cards[0].inputCount,3);assert.equal(cards[1].inputCount,4);
 assert.equal(cards[0].cardReadings.a.text,'9:00am');
 assert.equal(cards[0].cardReadings['retry-a'].skipped_reason,'original_valid');
 assert.equal(cards[0].cardReadings.b,undefined);
 assert.ok(messages.indexOf(cards[0])<messages.findIndex(message=>message.stats));
 console.log('PASS: worker timings account for reading stages while preserving input construction, decoded text, retries, cleanup and warm-session reuse.');
})().catch(error=>{console.error(error);process.exitCode=1;});
