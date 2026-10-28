import type {CropReading} from './ocr-policy';
import {transientConnectionFailure} from './request-json';
export type CardResultJob={index:number;layout:string;readings:Record<string,CropReading>};

// Jobs and recognized text live only in page memory. A failed request never
// cancels OCR or invalidates the cards whose totals have already been checked.
export class LiveResults<T>{
 private queue=Promise.resolve();
 private jobs=new Map<number,CardResultJob>();
 private completed=new Map<number,T>();
 private paused=false;
 lastError='';
 constructor(private submit:(job:CardResultJob,signal:AbortSignal)=>Promise<T>){}
 get pendingCount(){return this.jobs.size;}
 get cards(){return [...this.completed].sort(([a],[b])=>a-b).map(([,card])=>card);}
 enqueue(job:CardResultJob,signal:AbortSignal,publish:(index:number,card:T)=>void){
  this.jobs.set(job.index,job);
  this.queue=this.queue.then(async()=>{
   if(signal.aborted||this.paused)return;
   try{
    const card=await this.submit(job,signal);if(signal.aborted)return;
    this.completed.set(job.index,card);this.jobs.delete(job.index);publish(job.index,card);
   }catch(error){
    if(!signal.aborted){this.lastError=error instanceof Error?error.message:String(error);this.paused=transientConnectionFailure(error);}
   }
  });
 }
 async drain(){await this.queue;}
 async retry(signal:AbortSignal,publish:(index:number,card:T)=>void){
  this.paused=false;this.lastError='';
  for(const job of [...this.jobs.values()].sort((a,b)=>a.index-b.index))this.enqueue(job,signal,publish);
  await this.drain();
 }
}
