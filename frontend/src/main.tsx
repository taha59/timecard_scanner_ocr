import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

type Amount={hm:string|null;decimal:string|null;minutes:number|null};
type Day={label:string;status:string;in:string;out:string;adjustment_hours:string;adjustment_confirmed:boolean;reviewed:boolean;note:string;image:string;note_image:string;punch_images:string[];computed:Amount;flags:string[]};
type Card={id:string;name:string;written_total:string;image:string;days:Day[];needs_review:boolean;totals:{regular:Amount;adjustments:Amount;grand:Amount;known_punch_subtotal:Amount;complete:boolean};cross_check:{message:string|null;candidates:{interpretation:string;hm:string;difference:Amount}[]}};
type Scan={cards:Card[];scan_id:string;message:string;manual:boolean};
async function api(path:string,options:RequestInit){
 let r:Response;try{r=await fetch(path,options);}catch(e){if((e as Error).name==='AbortError')throw e;throw new Error('Cannot reach the calculation service. Try again; totals are unavailable until the request succeeds.');}
 let data;try{data=await r.json();}catch{throw new Error('The service returned an unreadable response. Try again.');}
 if(!r.ok)throw new Error(data.error||`Request failed (${r.status})`);return data;
}
const amount=(a?:Amount)=>a?.hm==null?'Unresolved':`${a.hm} · ${a.decimal} h`;
function App(){
 const [file,setFile]=useState<File|null>(null),[preview,setPreview]=useState('');
 const [cards,setCards]=useState<Card[]>([]),[scanId,setScanId]=useState(''),[busy,setBusy]=useState(false),[pending,setPending]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[batch,setBatch]=useState('');
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
 useEffect(()=>{if(!file){setPreview('');return;}const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url);},[file]);
 useEffect(()=>()=>{if(timer.current)clearTimeout(timer.current);abort.current?.abort();},[]);
 function accept(f:File){if(!f.type.startsWith('image/')){setError('Choose an image file.');return;}setFile(f);setError('');setCards([]);setExpandedCards({});setBatch('');setScanId('');revision.current++;abort.current?.abort();if(timer.current)clearTimeout(timer.current);setPending(false);}
 async function scan(manual=false){if(!file)return;setBusy(true);setError('');setMessage('');setBatch('');const rev=++revision.current;
  abort.current?.abort();if(timer.current)clearTimeout(timer.current);setPending(false);
  const form=new FormData();form.append('image',file);if(manual)form.append('manual','true');
  try{const data:Scan=await api('/api/scan',{method:'POST',body:form});if(rev!==revision.current)return;setCards(data.cards);setExpandedCards({});setScanId(data.scan_id);setMessage(data.message);}catch(e){if(rev===revision.current)setError((e as Error).message);}finally{setBusy(false);}
 }
 function update(next:Card[]){
  setCards(next);setPending(true);setError('');setBatch('');const rev=++revision.current;
  abort.current?.abort();if(timer.current)clearTimeout(timer.current);
  timer.current=setTimeout(async()=>{const controller=new AbortController();abort.current=controller;
   try{const data=await api('/api/calculate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cards:next}),signal:controller.signal});if(rev===revision.current){setCards(data.cards);setPending(false);}}
   catch(e){if((e as Error).name!=='AbortError'&&rev===revision.current){setError((e as Error).message);setPending(false);}}
  },350);
 }
 function editCard(ci:number,patch:Partial<Card>){update(cards.map((c,i)=>i===ci?{...c,...patch}:c));}
 function editDay(ci:number,di:number,patch:Partial<Day>){editCard(ci,{days:cards[ci].days.map((d,i)=>i===di?{...d,...patch}:d)});}
 async function save(){setError('');try{const data=await api('/api/training',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scan_id:scanId,cards})});setBatch(data.batch);setMessage(`Saved ${data.saved_rows} reviewed rows as labeled crops. This saves data; it does not train a model.`);}catch(e){setError((e as Error).message);}}
 const reviewed=cards.reduce((n,c)=>n+c.days.filter(d=>d.reviewed).length,0);
 const resultsBlocked=pending||Boolean(error);
 const current=inspect?cards[inspect.ci]?.days[inspect.di]:null;
 return <><header><a className="brand" href="/">▦ <span>Timecard</span><span className="brand-sub">PAYROLL REVIEW</span></a><span className="local-pill">Local OCR · Human review</span></header>
 <main><div className="intro"><div className="eyebrow">FROM PAPER TO PUNCHES</div><h1>Read the card.<br/><span>Verify the hours.</span></h1><p>Extract handwritten punches, inspect the originals, and calculate every minute from the times you approve.</p></div>
 <section className="upload-panel" aria-label="Upload timecards"><div className="step">01 / SOURCE PHOTO</div><div className="upload-grid"><div className="drop" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy&&e.dataTransfer.files[0])accept(e.dataTransfer.files[0]);}}><span className="upload-icon">↥</span><strong>Drop your timecard photo here</strong><span>One photo, one or more TOPS 1256 cards</span><label className="file-button">Choose photo<input type="file" accept="image/*" disabled={busy} onChange={e=>e.target.files?.[0]&&accept(e.target.files[0])}/></label>{file&&<small>{file.name}</small>}</div><div className="source-preview">{preview?<a href={preview} target="_blank" rel="noreferrer"><img src={preview} alt="Uploaded timecard photograph; open full size"/></a>:<div><span>▤</span><p>Your source stays beside the results.<br/>No handwritten total drives the calculation.</p></div>}</div></div><div className="actions"><button className="primary" onClick={()=>scan()} disabled={!file||busy}>{busy?'Processing photo…':'Scan with local OCR →'}</button><button onClick={()=>scan(true)} disabled={!file||busy}>Extract crops for manual entry</button><span>Notes are added only after confirmation.</span></div></section>
 <div role="alert">{error&&<p className="error">{error}</p>}</div><div aria-live="polite">{message&&<p className="notice">{message}</p>}</div>
 {cards.length>0&&<><div className="review-heading"><div><div className="eyebrow">02 / VERIFY & CORRECT</div><h2>{cards.length} cards to review</h2><p>{reviewed} of {cards.length*7} day rows marked reviewed. Inspect both punches and notes.</p></div><span className={pending?'pill pending':'pill'} role="status">{pending?'Recalculating…':error?'Calculation requires attention':'Calculated by Python'}</span></div>
 {cards.map((card,ci)=>{const expanded=expandedCards[card.id]??ci===0;return <section className="card" key={`${scanId}-${card.id}`}><div className="card-heading"><span className="card-index">{String(ci+1).padStart(2,'0')}</span><label className="name-label">Employee name<input aria-label={`Card ${ci+1} employee name`} value={card.name} placeholder="Enter employee name" onChange={e=>editCard(ci,{name:e.target.value})}/></label><span className="pill">{card.needs_review?'Review required':'Rows reviewed'}</span><button className="card-toggle" aria-label={`${expanded?'Collapse':'Expand'} employee ${ci+1}`} aria-expanded={expanded} aria-controls={`card-body-${card.id}`} onClick={()=>setExpandedCards(previous=>({...previous,[card.id]:!expanded}))}><span aria-hidden="true">{expanded?'▾':'▸'}</span> {expanded?'Hide details':'Show details'}</button></div>
 <div className="card-body" id={`card-body-${card.id}`} hidden={!expanded}>
 <details className="card-source"><summary>View timecard</summary><div className="card-source-content"><img src={card.image} alt={`${card.name||`Employee ${ci+1}`} timecard from uploaded photo`} loading="lazy"/><a href={card.image} target="_blank" rel="noreferrer">Open full card ↗</a></div></details>
 <div className="table-scroll"><table><thead><tr><th>Day / source</th><th>Status</th><th>IN</th><th>OUT</th><th>Adjustment</th><th>Punch hours</th><th>Review</th></tr></thead><tbody>{card.days.map((day,di)=><React.Fragment key={di}><tr><td><button className="crop-button" onClick={()=>setInspect({ci,di})}><img src={day.image} alt={`${day.label} source crop`}/><span>{day.label} ↗</span></button></td><td><select aria-label={`${card.name} ${day.label} status`} value={day.status} onChange={e=>editDay(ci,di,{status:e.target.value,reviewed:false})}>{['worked','off','blank','crossed_out','unknown'].map(s=><option key={s} value={s}>{s.replace('_',' ')}</option>)}</select></td><td><input aria-label={`${card.name} ${day.label} IN`} value={day.in} placeholder="H:MM" onChange={e=>editDay(ci,di,{in:e.target.value,reviewed:false})}/></td><td><input aria-label={`${card.name} ${day.label} OUT`} value={day.out} placeholder="H:MM" onChange={e=>editDay(ci,di,{out:e.target.value,reviewed:false})}/></td><td><input className="adjust-input" aria-label={`${card.name} ${day.label} adjustment hours`} value={day.adjustment_hours} onChange={e=>editDay(ci,di,{adjustment_hours:e.target.value,adjustment_confirmed:false,reviewed:false})}/><label className="check"><input type="checkbox" checked={day.adjustment_confirmed} onChange={e=>editDay(ci,di,{adjustment_confirmed:e.target.checked,reviewed:false})}/>Notes checked</label></td><td className="hours">{resultsBlocked?'Unavailable':day.computed.hm??'Unresolved'}</td><td><label className="check"><input type="checkbox" checked={day.reviewed} onChange={e=>editDay(ci,di,{reviewed:e.target.checked})}/>Reviewed</label></td></tr><tr className="flags-row"><td colSpan={7}>{day.flags.length>0?<div className="flags">{day.flags.map((f,i)=><span key={i}>{f}</span>)}</div>:<span className="quiet">No calculation flags</span>}</td></tr></React.Fragment>)}</tbody></table></div>
 <div className="totals" aria-live="polite"><div><span>PUNCH TOTAL</span><strong>{resultsBlocked?'Awaiting calculation':amount(card.totals.regular)}</strong>{!resultsBlocked&&!card.totals.regular.hm&&<small>Known subtotal: {amount(card.totals.known_punch_subtotal)}</small>}</div><div><span>CONFIRMED ADJUSTMENTS</span><strong>{resultsBlocked?'Awaiting calculation':amount(card.totals.adjustments)}</strong></div><div className="grand"><span>GRAND TOTAL</span><strong>{resultsBlocked?'Awaiting calculation':amount(card.totals.grand)}</strong></div></div>
 <div className="crosscheck"><label>Written total · cross-check only<input aria-label={`${card.name} written total`} placeholder="e.g. 27.07" value={card.written_total} onChange={e=>editCard(ci,{written_total:e.target.value})}/></label><div><p>{resultsBlocked?'Comparison unavailable until calculation succeeds.':card.cross_check.message||'No written-total mismatch identified. Review every source row before paying.'}</p>{!resultsBlocked&&card.cross_check.candidates.map((c,i)=><small key={i}>{c.interpretation}: {c.hm} · difference: {c.difference.hm??'unresolved'} </small>)}</div></div></div></section>;})}
 <section className="training"><div><h3>Build a better reader from corrections.</h3><p>Save reviewed day crops and their corrected labels for future training. Saving does not fine-tune the model.</p></div><button disabled={resultsBlocked||busy||reviewed===0} onClick={save}>Save corrected crops</button>{batch&&<a href={`/api/training/${batch}`}>Download labeled crops ↓</a>}</section></>}
 <footer>Punch arithmetic is computed on the backend. Unresolved entries block complete totals. Every scan needs human review.</footer></main>
 {current&&inspect&&<div className="modal-backdrop" onClick={()=>setInspect(null)}><div className="modal" role="dialog" aria-modal="true" aria-label="Inspect day crop" onClick={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key==='Escape')setInspect(null);}}><button autoFocus className="close" onClick={()=>setInspect(null)}>Close ×</button><h2>{cards[inspect.ci].name||`Card ${inspect.ci+1}`} · {current.label}</h2><p>Compare the handwriting with the editable row. Check the notes area even when OCR found nothing.</p><div className="crop-pair"><figure><img src={current.image} alt="Original punch area"/><figcaption>Punches</figcaption></figure><figure><img src={current.note_image} alt="Original adjustment and notes area"/><figcaption>Notes / adjustments</figcaption></figure></div><label>Recognized note <input value={current.note} onChange={e=>editDay(inspect.ci,inspect.di,{note:e.target.value,adjustment_confirmed:false,reviewed:false})}/></label><p className="quiet">OCR does not reliably detect crossing out. Set the status manually when appropriate.</p></div></div>}
 </>;
}
createRoot(document.getElementById('root')!).render(<App/>);
