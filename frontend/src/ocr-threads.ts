// Keep one model session; this controls CPU threads inside its WASM runtime.
export function ocrThreadCount(configured:unknown,isolated:boolean,sharedMemory:boolean,cores:number){
 const requested=Number(configured??4);
 const limit=[1,2,4].includes(requested)?requested:2;
 return isolated&&sharedMemory&&Math.floor(cores)>=limit?limit:1;
}
