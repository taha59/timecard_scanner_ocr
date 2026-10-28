import type {DeviceOcrStats} from './device-ocr';
export type RequestTiming={untilResponseMs:number;downloadMs:number;jsonParseMs:number;responseBytes:number|null;server:Record<string,number>};
export function addRequestTiming(a:RequestTiming|null,b:RequestTiming):RequestTiming{
 if(!a)return b;
 const server={...a.server};for(const [key,value] of Object.entries(b.server))server[key]=(server[key]||0)+value;
 return {untilResponseMs:a.untilResponseMs+b.untilResponseMs,downloadMs:a.downloadMs+b.downloadMs,jsonParseMs:a.jsonParseMs+b.jsonParseMs,
  responseBytes:a.responseBytes===null||b.responseBytes===null?null:a.responseBytes+b.responseBytes,server};
}

export function parseServerTiming(header:string|null){
 const timings:Record<string,number>={};
 for(const entry of (header||'').split(',')){
  const name=entry.trim().match(/^([a-zA-Z][\w-]*)/),duration=entry.match(/;\s*dur=(\d+(?:\.\d+)?)(?:\s*;|\s*$)/);
  if(name&&duration&&Number.isFinite(Number(duration[1])))timings[name[1]]=Number(duration[1]);
 }
 return timings;
}

export async function readTimedJson(response:Response,started:number,headersReceived:number){
 const text=await response.text(),downloaded=performance.now();
 const data=JSON.parse(text),parsed=performance.now();
 const size=response.headers.get('X-Response-Bytes');
 const bytes=size!==null&&/^\d+$/.test(size)?Number(size):NaN;
 const timing:RequestTiming={untilResponseMs:headersReceived-started,downloadMs:downloaded-headersReceived,jsonParseMs:parsed-downloaded,responseBytes:Number.isSafeInteger(bytes)?bytes:null,server:parseServerTiming(response.headers.get('Server-Timing'))};
 return {data,timing};
}

const seconds=(ms:number|undefined)=>ms===undefined?'Not available':`${(ms/1000).toFixed(2)}s`;
export function PreparationTiming({timing}:{timing:RequestTiming}){
 return <div className="preparation-timing"><h3>Preparation breakdown</h3><dl>
  <dt>Until response starts</dt><dd>{seconds(timing.untilResponseMs)}</dd>
  <dt>Download response</dt><dd>{seconds(timing.downloadMs)}</dd>
  <dt>Parse JSON on this device</dt><dd>{seconds(timing.jsonParseMs)}</dd>
  <dt>Response size before compression</dt><dd>{timing.responseBytes===null?'Not available':`${(timing.responseBytes/1_000_000).toFixed(2)} MB`}</dd>
  <dt>Server processing</dt><dd>{seconds(timing.server.compute)}</dd>
  <dt>Server request read</dt><dd>{seconds(timing.server.request_read)}</dd>
  <dt>Image preparation</dt><dd>{seconds(timing.server.image)}</dd>
  <dt>Card detection</dt><dd>{seconds(timing.server.grid)}</dd>
  <dt>Crop creation</dt><dd>{seconds(timing.server.crops)}</dd>
  <dt>Build response</dt><dd>{seconds(timing.server.response_build)}</dd>
 </dl><p className="quiet">Until response starts includes upload, waiting, and server work. Download includes reading and decoding the response body. Server processing starts after the upload is read; server request read can include waiting for upload bytes. Server times are already included in preparation, not extra time.</p></div>;
}

export function ReadingTiming({stats}:{stats:DeviceOcrStats}){
 if(stats.inferenceMs===undefined)return null;
 return <div className="preparation-timing"><h3>Reading breakdown</h3><dl>
  <dt>Decode crop images</dt><dd>{seconds(stats.imageDecodeMs)}</dd>
  <dt>Prepare model inputs</dt><dd>{seconds(stats.inputPrepMs)}</dd>
  <dt>Model inference</dt><dd>{seconds(stats.inferenceMs)}</dd>
  <dt>Decode recognized text</dt><dd>{seconds(stats.textDecodeMs)}</dd>
  <dt>Release tensors</dt><dd>{seconds(stats.cleanupMs)}</dd>
  <dt>Other worker work</dt><dd>{seconds(stats.otherMs)}</dd>
 </dl><p className="quiet">These stages are included in Reading time. They measure elapsed time, including any device scheduling delays.</p></div>;
}

export function ResultsTiming({timing,live=false}:{timing:RequestTiming;live?:boolean}){
 return <div className="preparation-timing"><h3>Results check breakdown</h3><dl>
  <dt>Until results response starts</dt><dd>{seconds(timing.untilResponseMs)}</dd>
  <dt>Download results</dt><dd>{seconds(timing.downloadMs)}</dd>
  <dt>Parse results JSON</dt><dd>{seconds(timing.jsonParseMs)}</dd>
  <dt>Results server processing</dt><dd>{seconds(timing.server.compute)}</dd>
  <dt>Rebuild layouts</dt><dd>{seconds(timing.server.layouts)}</dd>
  <dt>Reconstruct entries and source images</dt><dd>{seconds(timing.server.reconstruct)}</dd>
  <dt>Calculate totals and build results</dt><dd>{seconds(timing.server.response_build)}</dd>
 </dl><p className="quiet">{live?'These are summed per-card requests, which run while other cards are being read and overlap Reading time. ':''}Server values overlap the results request time; do not add them again.</p></div>;
}
