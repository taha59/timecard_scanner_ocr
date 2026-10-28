export type RequestTiming={untilResponseMs:number;downloadMs:number;jsonParseMs:number;responseBytes:number|null;server:Record<string,number>};

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
