const assert=require('node:assert/strict');
const {JSDOM}=require('../frontend/node_modules/jsdom');
const {buildSync}=require('../frontend/node_modules/esbuild');
const dom=new JSDOM('<div id="root"></div>',{url:'https://frontend.example',runScripts:'outside-only'}),w=dom.window;
global.window=w;global.document=w.document;global.HTMLElement=w.HTMLElement;global.MutationObserver=w.MutationObserver;
w.Headers=Headers;w.AbortController=AbortController;
const calls=[];w.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({version:'test'})};};
// A stale Vercel environment flag must not bring the removed sign-in screen back.
w.eval(buildSync({entryPoints:['frontend/src/main.tsx'],bundle:true,write:false,format:'iife',loader:{'.css':'empty'},define:{'process.env.NODE_ENV':'"test"','import.meta.env':JSON.stringify({VITE_REQUIRE_ACCESS_PASSWORD:'true',VITE_API_BASE_URL:'https://api.example/'})},jsx:'automatic',logLevel:'silent'}).outputFiles[0].text);
const {within,waitFor}=require('../frontend/node_modules/@testing-library/dom');
const screen=within(w.document.body);
(async()=>{
 await waitFor(()=>screen.getByText('Choose photo'));
 assert.equal(screen.queryByLabelText('Access password'),null);
 assert.equal(screen.queryByRole('button',{name:'Unlock app'}),null);
 assert.equal(screen.queryByRole('radio',{name:/Server OCR/}),null);
 assert.equal(w.localStorage.length,0);assert.equal(w.sessionStorage.length,0);
 const context={Headers,URL,fetch:(url,options)=>{calls.push({url,options});return Promise.resolve({ok:true});}};
 require('node:vm').createContext(context);
 require('node:vm').runInContext(buildSync({entryPoints:['frontend/src/api.ts'],bundle:true,write:false,format:'iife',globalName:'api',define:{'import.meta.env':JSON.stringify({VITE_API_BASE_URL:'https://api.example/'})}}).outputFiles[0].text,context);
 await context.api.apiFetch('/api/device-model');
 assert.equal(calls.at(-1).url,'https://api.example/api/device-model');
 assert.equal(calls.at(-1).options.headers.get('Authorization'),null);
 assert.equal(calls.at(-1).options.credentials,'omit');
 console.log('PASS: app opens without a password, ignores the old gate flag, and API requests require no injected credentials.');
 dom.window.close();
})().catch(e=>{console.error(e.message);dom.window.close();process.exitCode=1;});
