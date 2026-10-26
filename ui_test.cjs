// DOM-level integration with the real Flask API. This is not a browser layout test.
const server=require('node:child_process').spawn('python',['-m','backend.app'],{env:process.env,stdio:'ignore'});
const path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
const {JSDOM}=require('./frontend/node_modules/jsdom');
const {buildSync}=require('./frontend/node_modules/esbuild');
const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://127.0.0.1:5000',runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window;
w.AbortController=AbortController;w.AbortSignal=AbortSignal;
global.window=w;global.document=w.document;global.HTMLElement=w.HTMLElement;global.MutationObserver=w.MutationObserver;
w.URL.createObjectURL=()=> 'blob:sample';w.URL.revokeObjectURL=()=>{};
let errors=[],failCalculation=false;w.addEventListener('error',event=>errors.push(event.message));
w.fetch=async(url,options={})=>{
 if(failCalculation&&url==='/api/calculate')return new Response(JSON.stringify({error:'Simulated calculation outage'}),{status:503,headers:{'Content-Type':'application/json'}});
 let body=options.body;
 if(body instanceof w.FormData){const form=new FormData();for(const [key,value] of body.entries()){
   if(typeof value==='string')form.append(key,value);else{
    const buffer=await new Promise((resolve,reject)=>{const reader=new w.FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsArrayBuffer(value);});
    form.append(key,new Blob([buffer],{type:value.type}),value.name);
   }
 }body=form;}
 const r=await fetch(new URL(url,w.location.href),{...options,body});return r;
};
const bundle=buildSync({entryPoints:[path.resolve('frontend/src/main.tsx')],bundle:true,write:false,format:'iife',loader:{'.css':'empty'},define:{'process.env.NODE_ENV':'"test"'},jsx:'automatic'}).outputFiles[0].text;
w.eval(bundle);
const {within,waitFor}=require('./frontend/node_modules/@testing-library/dom');
const user=require('./frontend/node_modules/@testing-library/user-event').default.setup({document:w.document});
const screen=within(w.document.body);
(async()=>{
 for(let i=0;i<40;i++){try{const r=await fetch('http://127.0.0.1:5000/api/health');if(r.ok)break;}catch{}await new Promise(r=>setTimeout(r,250));}
 await waitFor(()=>screen.getByRole('heading',{name:/Read the card/}));
 const file=new w.File([fs.readFileSync('fixtures/timecards.jpg')],'timecards.jpg',{type:'image/jpeg'});
 await user.upload(w.document.querySelector('input[type=file]'),file);
 await user.click(screen.getByRole('button',{name:'Extract crops for manual entry'}));
 await waitFor(()=>screen.getByRole('heading',{name:'5 cards to review'}),{timeout:15000});
 assert.equal(w.document.querySelectorAll('tbody tr:not(.flags-row)').length,35);
 const card=w.document.querySelector('section.card'),c=within(card),truth=require('./fixtures/ground_truth.json')[0];
 const name=c.getByRole('textbox',{name:'Card 1 employee name'});await user.clear(name);await user.type(name,'Employee 06');
 const rows=card.querySelectorAll('tbody tr:not(.flags-row)');
 for(let i=0;i<7;i++){
  const row=within(rows[i]),p=truth.punches[i];
  await user.selectOptions(row.getByRole('combobox'),Array.isArray(p)?'worked':p);
  if(Array.isArray(p))for(const [j,key] of ['IN','OUT'].entries()){
   const input=row.getByRole('textbox',{name:`Employee 06 Day ${i+1} ${key}`});await user.clear(input);await user.type(input,p[j]);
  }
  await user.click(row.getByLabelText('Notes checked'));await user.click(row.getByLabelText('Reviewed',{exact:true}));
 }
 await waitFor(()=>assert.equal(card.querySelector('.grand strong').textContent,'51:53 · 51.88 h'),{timeout:6000});
 const written=c.getByRole('textbox',{name:'Employee 06 written total'});await user.type(written,'0:00');
 await waitFor(()=>c.getByText('Written total mismatch; review before paying'));
 assert.equal(card.querySelector('.grand strong').textContent,'51:53 · 51.88 h');
 await user.click(c.getByRole('button',{name:/Day 1 ↗/}));
 assert.equal(screen.getByRole('dialog').querySelectorAll('img').length,2);
 await user.keyboard('{Escape}');assert.equal(screen.queryByRole('dialog'),null);
 await user.click(screen.getByRole('button',{name:'Save corrected crops'}));
 await waitFor(()=>screen.getByRole('link',{name:'Download labeled crops ↓'}),{timeout:20000});
 failCalculation=true;const firstIn=c.getByRole('textbox',{name:'Employee 06 Day 1 IN'});await user.clear(firstIn);await user.type(firstIn,'9:00');
 await waitFor(()=>screen.getByText('Simulated calculation outage'),{timeout:10000});
 assert.equal(card.querySelector('.grand strong').textContent,'Awaiting calculation');
 failCalculation=false;await user.clear(firstIn);await user.type(firstIn,'10:10');
 await waitFor(()=>assert.equal(card.querySelector('.grand strong').textContent,'51:53 · 51.88 h'),{timeout:10000});
 assert.deepEqual(errors,[]);
 console.log('PASS: React DOM integration against Flask: upload, 35 rows, editable punches to 51:53, independent written total, inspect crops, Escape close, training save, failed calculations hide stale totals, retry recovers, no JS errors.');
 dom.window.close();server.kill();
})().catch(e=>{console.error(e.message?.slice(0,1200));console.log('UI error:',w.document.querySelector('[role=alert]')?.textContent);dom.window.close();server.kill();process.exitCode=1;});
