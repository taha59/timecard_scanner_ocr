const assert=require('node:assert/strict'),vm=require('node:vm'),{buildSync}=require('../frontend/node_modules/esbuild');
const context={};vm.createContext(context);
vm.runInContext(buildSync({entryPoints:['frontend/src/ocr-batches.ts'],bundle:true,write:false,format:'iife',globalName:'batches'}).outputFiles[0].text,context);
const tasks=[{id:'a',required:true},{id:'b',required:true},{id:'c',required:true},
 {id:'shared',required:false,fallback_for:['a','b']},{id:'recover',required:false,recover_for:[['b','shared']]}];
const groups=[['a','shared'],['b','shared','recover','c']];
const batches=context.batches.cardTaskBatches(tasks,groups);
assert.deepEqual(Array.from(batches[0],t=>t.id),['a','b','shared']);
assert.deepEqual(Array.from(batches[1],t=>t.id),['c','recover']);
assert.equal(new Set(batches.flat().map(t=>t.id)).size,tasks.length);
assert.throws(()=>context.batches.cardTaskBatches(tasks,[['missing']]),/Missing timecard crop/);
assert.throws(()=>context.batches.cardTaskBatches(tasks,[['a']]),/Incomplete timecard crop groups/);
assert.deepEqual(Array.from(context.batches.cardTaskBatches(tasks)[0],t=>t.id),['a','b','c','shared','recover']);
console.log('PASS: per-card batches retain shared retry prerequisites, read each task once, and preserve legacy ordering without groups.');
