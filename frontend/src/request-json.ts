import {apiFetch} from './api';
import {readTimedJson,type RequestTiming} from './scan-timing';

export class ApiRequestError extends Error{
 constructor(message:string,public retryable=false,public status?:number,public retryAfter:string|null=null){super(message);this.name='ApiRequestError';}
}
export const transientConnectionFailure=(error:unknown)=>error instanceof ApiRequestError&&error.retryable&&error.status!==500;
export function retryDelayMs(header:string|null,attempt:number){
 const seconds=header!==null&&/^\d+(?:\.\d+)?$/.test(header)?Number(header)*1000:NaN;
 const date=header?Date.parse(header):NaN;
 const requested=Number.isFinite(seconds)?seconds:Number.isFinite(date)?Math.max(0,date-Date.now()):0;
 return Math.min(30_000,Math.max(1000*2**attempt,requested));
}
export function waitForRetry(ms:number,signal?:AbortSignal|null){
 return new Promise<void>((resolve,reject)=>{
  const abort=()=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);reject(new DOMException('Canceled','AbortError'));};
  const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},ms);
  signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();
 });
}
type Recovery={retry?:boolean;onRetry?:(attempt:number)=>void;wait?:typeof waitForRetry;timeoutMs?:number};
export async function requestJson(path:string,options:RequestInit,report?:(timing:RequestTiming)=>void,recovery:Recovery={}){
 const attempts=recovery.retry?3:1;
 for(let attempt=0;attempt<attempts;attempt++){
  options.signal?.throwIfAborted();
  const controller=new AbortController(),abort=()=>controller.abort();let timedOut=false;
  options.signal?.addEventListener('abort',abort,{once:true});
  const timeout=recovery.timeoutMs??(recovery.retry?30_000:undefined);
  const timer=timeout===undefined?undefined:setTimeout(()=>{timedOut=true;controller.abort();},timeout);
  try{
   const started=performance.now();let response:Response;
   try{response=await apiFetch(path,{...options,signal:controller.signal});}
   catch(e){
    if(options.signal?.aborted)throw new DOMException('Canceled','AbortError');
    throw new ApiRequestError(timedOut?'The calculation service took too long to respond.':'Cannot reach the calculation service. Try again; totals are unavailable until the request succeeds.',true);
   }
   const headersReceived=performance.now();
   const retryable=[408,425,429,500,502,503,504].includes(response.status);
   // Hosting/proxy failures can return HTML without JSON or CORS headers.
   // Preserve HTTP status where the browser exposes it instead of losing 429.
   if(!response.ok){
    let message=`Calculation service request failed (${response.status}).`;
    try{const data=await response.json();if(typeof data.error==='string')message=data.error;}catch{}
    throw new ApiRequestError(message,retryable,response.status,response.headers.get('Retry-After'));
   }
   try{
    if(report){const result=await readTimedJson(response,started,headersReceived);report(result.timing);return result.data;}
    return await response.json();
   }catch(e){
    if(options.signal?.aborted)throw new DOMException('Canceled','AbortError');
    throw new ApiRequestError('The service returned an incomplete or unreadable response. Try again.',true);
   }
  }catch(error){
   if(options.signal?.aborted)throw new DOMException('Canceled','AbortError');
   if(!(error instanceof ApiRequestError)||!error.retryable||attempt===attempts-1)throw error;
   recovery.onRetry?.(attempt+1);
   // Do not leave the per-attempt watchdog active during backoff.
   clearTimeout(timer);options.signal?.removeEventListener('abort',abort);
   await (recovery.wait??waitForRetry)(retryDelayMs(error.retryAfter,attempt),options.signal);
  }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',abort);}
 }
 throw new Error('The calculation service is unavailable.');
}
