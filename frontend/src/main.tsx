import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {apiFetch,setAccessToken,serverOcrEnabled,passwordRequired} from './api';
import {deviceSupported,modelPresent,downloadModel,removeModel,recognizeOnDevice,type ModelManifest,type DeviceOcrStats} from './device-ocr';

type Amount={hm:string|null;decimal:string|null;minutes:number|null};
type Day={label:string;status:string;in:string;out:string;adjustment_hours:string;adjustment_confirmed:boolean;reviewed:boolean;note:string;image:string;note_image:string;punch_images:string[];computed:Amount;flags:string[]};
type Card={id:string;name:string;written_total:string;image:string;days:Day[];needs_review:boolean;totals:{regular:Amount;adjustments:Amount;grand:Amount;known_punch_subtotal:Amount;complete:boolean};cross_check:{message:string|null;candidates:{interpretation:string;hm:string;difference:Amount}[]}};
type Scan={cards:Card[];scan_id:string;message:string;manual:boolean};
async function api(path:string,options:RequestInit){
 let r:Response;try{r=await apiFetch(path,options);}catch(e){if((e as Error).name==='AbortError')throw e;throw new Error('Cannot reach the calculation service. Try again; totals are unavailable until the request succeeds.');}
 let data;try{data=await r.json();}catch{throw new Error('The service returned an unreadable response. Try again.');}
 if(!r.ok)throw new Error(data.error||`Request failed (${r.status})`);return data;
}
const amount=(a?:Amount)=>a?.hm==null?'Unresolved':`${a.hm} · ${a.decimal} h`;
function App(){
 const [file,setFile]=useState<File|null>(null),[preview,setPreview]=useState('');
 const [rotation,setRotation]=useState(0),[previewBusy,setPreviewBusy]=useState(false);
 const [cards,setCards]=useState<Card[]>([]),[scanId,setScanId]=useState(''),[busy,setBusy]=useState(false),[pending,setPending]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [ocrMode,setOcrMode]=useState<'server'|'device'>(serverOcrEnabled?'server':'device');
 const [manifest,setManifest]=useState<ModelManifest|null>(null),[modelReady,setModelReady]=useState(false),[modelBusy,setModelBusy]=useState(false),[progress,setProgress]=useState('');
 const [accessGranted,setAccessGranted]=useState(!passwordRequired),[password,setPassword]=useState(''),[accessBusy,setAccessBusy]=useState(false);
 const [scanTiming,setScanTiming]=useState('');
 const supported=deviceSupported();
 async function unlock(event:React.FormEvent){event.preventDefault();setAccessBusy(true);setError('');setAccessToken(password);try{await api('/api/access',{method:'GET'});setAccessGranted(true);setPassword('');}catch(e){setAccessToken('');setError((e as Error).message);}finally{setAccessBusy(false);}}
 useEffect(()=>{if(!supported||!accessGranted)return;let canceled=false;apiFetch('/api/device-model').then(r=>{if(!r.ok)throw new Error('Model information unavailable');return r.json();}).then(async m=>{const ready=await modelPresent(m);if(!canceled){setManifest(m);setModelReady(ready);}}).catch(()=>{if(!canceled)setManifest(null);});return()=>{canceled=true;};},[accessGranted]);
 useEffect(()=>{if(window.isSecureContext&&'serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});},[]);
 const [expandedCards,setExpandedCards]=useState<Record<string,boolean>>({});
 const [inspect,setInspect]=useState<{ci:number;di:number}|null>(null);
 useEffect(()=>{
  if(!inspect)return;
  const previous=document.activeElement as HTMLElement|null;
  const trap=(event:KeyboardEvent)=>{
   if(event.key==='Escape'){setInspect(null);return;}
   if(event.key!=='Tab')return;
   const nodes=Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"] button,[role="dialog"] input,[role="dialog"] a'));
   const first=nodes[0],last=nodes[nodes.length-1];
   if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
   else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  };
  document.addEventListener('keydown',trap);
  return()=>{document.removeEventListener('keydown',trap);previous?.focus();};
 },[inspect]);
 const revision=useRef(0),timer=useRef<ReturnType<typeof setTimeout>|null>(null),abort=useRef<AbortController|null>(null);
 useEffect(()=>{
  if(!file){setPreview('');setPreviewBusy(false);return;}
  const originalUrl=URL.createObjectURL(file);
  if(rotation===0){setPreview(originalUrl);setPreviewBusy(false);return()=>URL.revokeObjectURL(originalUrl);}
  let cancelled=false,rotatedUrl='';
  const image=new Image();
  setPreviewBusy(true);
  const failed=()=>{if(!cancelled){setPreviewBusy(false);setPreview('');setError('Could not rotate this photo. Choose another image or rotate back to the original orientation.');}};
  image.onerror=failed;
  image.onload=()=>{
   if(cancelled)return;
   // Only the display preview is resized. The server rotates the original
   // upload after EXIF correction, preserving its full resolution.
   const scale=Math.min(1,1600/Math.max(image.naturalWidth,image.naturalHeight));
   const width=Math.max(1,Math.round(image.naturalWidth*scale)),height=Math.max(1,Math.round(image.naturalHeight*scale));
   const canvas=document.createElement('canvas');
   const sideways=rotation===90||rotation===270;
   canvas.width=sideways?height:width;canvas.height=sideways?width:height;
   const context=canvas.getContext('2d');if(!context){failed();return;}
   context.translate(canvas.width/2,canvas.height/2);context.rotate(rotation*Math.PI/180);
   context.drawImage(image,-width/2,-height/2,width,height);
   canvas.toBlob(blob=>{if(cancelled)return;if(!blob){failed();return;}rotatedUrl=URL.createObjectURL(blob);setPreview(rotatedUrl);setPreviewBusy(false);},'image/png');
  };
  image.src=originalUrl;
  return()=>{cancelled=true;image.onload=null;image.onerror=null;URL.revokeObjectURL(originalUrl);if(rotatedUrl)URL.revokeObjectURL(rotatedUrl);};
 },[file,rotation]);
 useEffect(()=>()=>{if(timer.current)clearTimeout(timer.current);abort.current?.abort();},[]);
 function accept(f:File){if(!f.type.startsWith('image/')){setError('Choose an image file.');return;}setScanTiming('');setFile(f);setRotation(0);setPreviewBusy(false);setMessage('');setError('');setCards([]);setExpandedCards({});setScanId('');revision.current++;abort.current?.abort();if(timer.current)clearTimeout(timer.current);setPending(false);}
 function rotateSource(delta:number){
  if(!file||busy||previewBusy)return;
  setScanTiming('');setRotation(previous=>(previous+delta+360)%360);setPreviewBusy(true);
  setError('');setMessage('');setCards([]);setExpandedCards({});setScanId('');setInspect(null);
  revision.current++;abort.current?.abort();if(timer.current)clearTimeout(timer.current);setPending(false);
 }
 function cancelScan(){revision.current++;setModelBusy(false);setProgress('');abort.current?.abort();abort.current=null;setBusy(false);setError('');setMessage('Processing canceled. You can change the photo or try again.');}
 async function installModel(){
  if(!manifest||busy)return;
  const rev=++revision.current,controller=new AbortController();abort.current?.abort();abort.current=controller;
  setBusy(true);setModelBusy(true);setError('');setMessage('');setProgress('Starting model download…');
  try{await downloadModel(manifest,controller.signal,text=>{if(rev===revision.current)setProgress(text);});if(rev===revision.current){setModelReady(true);setMessage('Model saved on this device. You can now process with device OCR.');}}
  catch(e){if(rev===revision.current&&(e as Error).name!=='AbortError')setError((e as Error).message);}
  finally{if(rev===revision.current){setBusy(false);setModelBusy(false);setProgress('');abort.current=null;}}
 }
 async function forgetModel(){try{await removeModel();setModelReady(false);setMessage('Downloaded model removed from this browser.');}catch{setError('Could not remove the saved model. Try again.');}}
 async function scan(manual=false){if(busy||!file||previewBusy||!preview||(!manual&&ocrMode==='device'&&!modelReady))return;setCards([]);setExpandedCards({});setInspect(null);setScanId('');setScanTiming('');setProgress('');setBusy(true);setError('');setMessage('');const rev=++revision.current;
  abort.current?.abort();if(timer.current)clearTimeout(timer.current);setPending(false);
  const controller=new AbortController();abort.current=controller;
  const form=new FormData();form.append('image',file);form.append('rotation',String(rotation));if(manual)form.append('manual','true');
  try{
   let data:Scan;
   if(!manual&&ocrMode==='device'){
    if(!manifest||!supported)throw new Error('Device OCR needs a supported browser over HTTPS. You can still use manual entry.');
    if(!await modelPresent(manifest)){setModelReady(false);throw new Error('The saved model is no longer available. Download it again before scanning.');}
    const started=performance.now();let deviceStats:DeviceOcrStats|null=null;
    form.append('device','true');setProgress('Preparing crops on the server…');
    const prepared=await api('/api/scan',{method:'POST',body:form,signal:controller.signal});
    const cropped=performance.now();
    const readings=await recognizeOnDevice(manifest,prepared.tasks,controller.signal,text=>{if(rev===revision.current)setProgress(text);},stats=>{deviceStats=stats;});
    controller.signal.throwIfAborted();setProgress('Checking entries and calculating totals…');
    data=await api('/api/device-result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({layouts:prepared.layouts,readings}),signal:controller.signal});
    if(rev===revision.current&&deviceStats){const stats=deviceStats as DeviceOcrStats;setScanTiming(`Total ${((performance.now()-started)/1000).toFixed(2)}s · Crop preparation ${((cropped-started)/1000).toFixed(2)}s · Model startup ${(stats.loadMs/1000).toFixed(2)}s${stats.reused?' (reused)':''} · Reading ${(stats.readMs/1000).toFixed(2)}s${stats.threads?` (${stats.threads} thread${stats.threads===1?'':'s'})`:''} · ${stats.processed}/${stats.total} crops read · ${stats.skipped} fallback crops skipped`);}
   }else data=await api('/api/scan',{method:'POST',body:form,signal:controller.signal});
   if(rev!==revision.current)return;setCards(data.cards);setExpandedCards({});setScanId(data.scan_id);setMessage(data.message);
  }catch(e){if(rev===revision.current&&(e as Error).name!=='AbortError')setError((e as Error).message);}finally{if(rev===revision.current){setBusy(false);setProgress('');if(abort.current===controller)abort.current=null;}}

 }
 function update(next:Card[]){
  setCards(next);setPending(true);setError('');const rev=++revision.current;
  abort.current?.abort();if(timer.current)clearTimeout(timer.current);
  timer.current=setTimeout(async()=>{const controller=new AbortController();abort.current=controller;
   try{const data=await api('/api/calculate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cards:next}),signal:controller.signal});if(rev===revision.current){setCards(data.cards);setPending(false);}}
   catch(e){if((e as Error).name!=='AbortError'&&rev===revision.current){setError((e as Error).message);setPending(false);}}
  },350);
 }
 function editCard(ci:number,patch:Partial<Card>){update(cards.map((c,i)=>i===ci?{...c,...patch}:c));}
 function editDay(ci:number,di:number,patch:Partial<Day>){editCard(ci,{days:cards[ci].days.map((d,i)=>i===di?{...d,...patch}:d)});}
 const reviewed=cards.reduce((n,c)=>n+c.days.filter(d=>d.reviewed).length,0);
 const resultsBlocked=pending||Boolean(error);
 const current=inspect?cards[inspect.ci]?.days[inspect.di]:null;
 if(!accessGranted)return <main className="access-panel"><h1>Timecard access</h1><p>Enter the private app password. It stays in memory until you close or refresh this page.</p><form onSubmit={unlock}><label>Access password<input type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)}/></label><button className="primary" disabled={accessBusy}>{accessBusy?'Checking…':'Unlock app'}</button></form>{scanTiming&&<details className="scan-timing"><summary>Scan timing</summary><p>{scanTiming}</p></details>}
 <div role="alert">{error}</div></main>;
 return <><header><a className="brand" href="/">▦ <span>Timecard</span><span className="brand-sub">PAYROLL REVIEW</span></a><span className="local-pill">Local OCR · Human review</span></header>
 <main><div className="intro"><div className="eyebrow">FROM PAPER TO PUNCHES</div><h1>Read the card.<br/><span>Verify the hours.</span></h1><p>Extract handwritten punches, inspect the originals, and calculate every minute from the times you approve.</p></div>
 <section className="upload-panel" aria-label="Upload timecards"><div className="step">01 / SOURCE PHOTO</div><div className="upload-grid"><div className="drop" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy&&e.dataTransfer.files[0])accept(e.dataTransfer.files[0]);}}><span className="upload-icon">↥</span><strong>Drop your timecard photo here</strong><span>One photo, one or more TOPS 1256 cards</span><label className="file-button">Choose photo<input type="file" accept="image/*" disabled={busy} onChange={e=>e.target.files?.[0]&&accept(e.target.files[0])}/></label>{file&&<small>{file.name}</small>}</div><div className="source-column"><div className="source-preview" aria-busy={previewBusy}>{preview?<a href={preview} target="_blank" rel="noreferrer"><img src={preview} alt={`Uploaded timecard photograph, rotated ${rotation} degrees clockwise; open preview`}/></a>:<div><span>▤</span><p>Your source stays beside the results.<br/>No handwritten total drives the calculation.</p></div>}</div>{file&&<div className="rotation-controls" aria-label="Source photo rotation"><button type="button" onClick={()=>rotateSource(-90)} disabled={busy||previewBusy} aria-label="Rotate photo left 90 degrees">↶ Rotate left 90°</button><button type="button" onClick={()=>rotateSource(90)} disabled={busy||previewBusy} aria-label="Rotate photo right 90 degrees">↷ Rotate right 90°</button><span aria-live="polite">{previewBusy?'Updating preview…':`Rotation: ${rotation}°`}</span></div>}</div></div><fieldset className="ocr-choice" disabled={busy}><legend>Where should handwriting be read?</legend>{serverOcrEnabled&&<label><input type="radio" name="ocr-mode" checked={ocrMode==='server'} onChange={()=>{setOcrMode('server');setError('');}}/> Server OCR <small>Use the server’s existing local model.</small></label>}<label><input type="radio" name="ocr-mode" checked={ocrMode==='device'} onChange={()=>{setOcrMode('device');setError('');}}/> This device <small>Download once, then read handwriting on your phone or computer.</small></label></fieldset>
 {ocrMode==='device'&&<div className="device-options">
 <p>Photos are processed in server memory for cropping and totals, then discarded. No photos or scans are saved. Handwriting recognition runs on this device. Device mode is experimental and may read differently from server OCR. Always review every entry.</p>
 {!supported?<p>Device OCR requires HTTPS (or localhost) and a recent Safari or Chrome browser. Open this app over HTTPS to use device OCR. Manual entry is still available.</p>:!manifest?<p>Model information is unavailable. Check the server connection and access password, then refresh.</p>:modelReady?<><strong>Model ready on this device</strong><button type="button" onClick={forgetModel} disabled={busy}>Remove downloaded model</button></>:<><p>By choosing “Agree &amp; download”, you allow this site to download approximately {Math.ceil(manifest.bytes/1024/1024)} MB of model weights, plus the OCR runtime, and store the model in this browser. It uses device memory and battery. Browser cleanup may require another download.</p><button type="button" onClick={installModel} disabled={busy}>Agree &amp; download model</button></>}
 <details><summary>Add to your Home Screen</summary><p>iPhone: open in Safari, tap Share, then Add to Home Screen. Android: open the Chrome menu and choose Add to Home screen or Install app. HTTPS is required. The saved model can still be removed by browser storage cleanup.</p></details>
 </div>}
 <div className="actions"><button className="primary" onClick={()=>scan()} disabled={!file||busy||previewBusy||!preview||(ocrMode==='device'&&(!supported||!modelReady))}>{busy?(modelBusy?'Downloading model…':'Processing photo…'):ocrMode==='device'?'Scan on this device →':'Scan with local OCR →'}</button><button onClick={()=>scan(true)} disabled={!file||busy||previewBusy||!preview}>Extract crops for manual entry</button>{busy&&<button type="button" onClick={cancelScan}>Cancel processing</button>}<span>Notes are added only after confirmation.</span></div>{progress&&<p role="status" className="notice">{progress}</p>}</section>
 {scanTiming&&<details className="scan-timing"><summary>Scan timing</summary><p>{scanTiming}</p></details>}
 <div role="alert">{error&&<p className="error">{error}</p>}</div><div aria-live="polite">{message&&<p className="notice">{message}</p>}</div>
 {cards.length>0&&<><div className="review-heading"><div><div className="eyebrow">02 / VERIFY & CORRECT</div><h2>{cards.length} cards to review</h2><p>{reviewed} of {cards.length*7} day rows marked reviewed. Inspect both punches and notes.</p></div><span className={pending?'pill pending':'pill'} role="status">{pending?'Recalculating…':error?'Calculation requires attention':'Calculated by Python'}</span></div>
 {cards.map((card,ci)=>{const expanded=expandedCards[card.id]??ci===0;return <section className="card" key={`${scanId}-${card.id}`}><div className="card-heading"><span className="card-index">{String(ci+1).padStart(2,'0')}</span><label className="name-label">Employee name<input aria-label={`Card ${ci+1} employee name`} value={card.name} placeholder="Enter employee name" onChange={e=>editCard(ci,{name:e.target.value})}/></label><span className="pill">{card.needs_review?'Review required':'Rows reviewed'}</span><button className="card-toggle" aria-label={`${expanded?'Collapse':'Expand'} employee ${ci+1}`} aria-expanded={expanded} aria-controls={`card-body-${card.id}`} onClick={()=>setExpandedCards(previous=>({...previous,[card.id]:!expanded}))}><span aria-hidden="true">{expanded?'▾':'▸'}</span> {expanded?'Hide details':'Show details'}</button></div>
 <div className="card-body" id={`card-body-${card.id}`} hidden={!expanded}>
 <details className="card-source"><summary>View timecard</summary><div className="card-source-content"><img src={card.image} alt={`${card.name||`Employee ${ci+1}`} timecard from uploaded photo`} loading="lazy"/><a href={card.image} target="_blank" rel="noreferrer">Open full card ↗</a></div></details>
 <div className="table-scroll"><table><thead><tr><th>Day / source</th><th>Status</th><th>IN</th><th>OUT</th><th>Adjustment</th><th>Punch hours</th><th>Review</th></tr></thead><tbody>{card.days.map((day,di)=><React.Fragment key={di}><tr><td><button className="crop-button" onClick={()=>setInspect({ci,di})}><img src={day.image} alt={`${day.label} source crop`}/><span>{day.label} ↗</span></button></td><td><select aria-label={`${card.name} ${day.label} status`} value={day.status} onChange={e=>editDay(ci,di,{status:e.target.value,reviewed:false})}>{['worked','off','blank','crossed_out','unknown'].map(s=><option key={s} value={s}>{s.replace('_',' ')}</option>)}</select></td><td><input aria-label={`${card.name} ${day.label} IN`} value={day.in} placeholder="H:MM" onChange={e=>editDay(ci,di,{in:e.target.value,reviewed:false})}/></td><td><input aria-label={`${card.name} ${day.label} OUT`} value={day.out} placeholder="H:MM" onChange={e=>editDay(ci,di,{out:e.target.value,reviewed:false})}/></td><td><input className="adjust-input" aria-label={`${card.name} ${day.label} adjustment hours`} value={day.adjustment_hours} onChange={e=>editDay(ci,di,{adjustment_hours:e.target.value,adjustment_confirmed:false,reviewed:false})}/><label className="check"><input type="checkbox" checked={day.adjustment_confirmed} onChange={e=>editDay(ci,di,{adjustment_confirmed:e.target.checked,reviewed:false})}/>Notes checked</label></td><td className="hours">{resultsBlocked?'Unavailable':day.computed.hm??'Unresolved'}</td><td><label className="check"><input type="checkbox" checked={day.reviewed} onChange={e=>editDay(ci,di,{reviewed:e.target.checked})}/>Reviewed</label></td></tr><tr className="flags-row"><td colSpan={7}>{day.flags.length>0?<div className="flags">{day.flags.map((f,i)=><span key={i}>{f}</span>)}</div>:<span className="quiet">No calculation flags</span>}</td></tr></React.Fragment>)}</tbody></table></div>
 <div className="totals" aria-live="polite"><div><span>PUNCH TOTAL</span><strong>{resultsBlocked?'Awaiting calculation':amount(card.totals.regular)}</strong>{!resultsBlocked&&!card.totals.regular.hm&&<small>Known subtotal: {amount(card.totals.known_punch_subtotal)}</small>}</div><div><span>CONFIRMED ADJUSTMENTS</span><strong>{resultsBlocked?'Awaiting calculation':amount(card.totals.adjustments)}</strong></div><div className="grand"><span>GRAND TOTAL</span><strong>{resultsBlocked?'Awaiting calculation':amount(card.totals.grand)}</strong></div></div>
 <div className="crosscheck"><label>Written total · cross-check only<input aria-label={`${card.name} written total`} placeholder="e.g. 27.07" value={card.written_total} onChange={e=>editCard(ci,{written_total:e.target.value})}/></label><div><p>{resultsBlocked?'Comparison unavailable until calculation succeeds.':card.cross_check.message||'No written-total mismatch identified. Review every source row before paying.'}</p>{!resultsBlocked&&card.cross_check.candidates.map((c,i)=><small key={i}>{c.interpretation}: {c.hm} · difference: {c.difference.hm??'unresolved'} </small>)}</div></div></div></section>;})}
 </>}
 <footer>Punch arithmetic is computed on the backend. Unresolved entries block complete totals. Every scan needs human review.</footer></main>
 {current&&inspect&&<div className="modal-backdrop" onClick={()=>setInspect(null)}><div className="modal" role="dialog" aria-modal="true" aria-label="Inspect day crop" onClick={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key==='Escape')setInspect(null);}}><button autoFocus className="close" onClick={()=>setInspect(null)}>Close ×</button><h2>{cards[inspect.ci].name||`Card ${inspect.ci+1}`} · {current.label}</h2><p>Compare the handwriting with the editable row. Check the notes area even when OCR found nothing.</p><div className="crop-pair"><figure><img src={current.image} alt="Original punch area"/><figcaption>Punches</figcaption></figure><figure><img src={current.note_image} alt="Original adjustment and notes area"/><figcaption>Notes / adjustments</figcaption></figure></div><label>Recognized note <input value={current.note} onChange={e=>editDay(inspect.ci,inspect.di,{note:e.target.value,adjustment_confirmed:false,reviewed:false})}/></label><p className="quiet">OCR does not reliably detect crossing out. Set the status manually when appropriate.</p></div></div>}
 </>;
}
createRoot(document.getElementById('root')!).render(<App/>);
