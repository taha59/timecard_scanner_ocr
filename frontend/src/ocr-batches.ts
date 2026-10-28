import {cropStage,type CropTask} from './ocr-policy';

// Shared crops are still read once. Include every prerequisite before deciding
// whether a shared retry can be skipped, even if it belongs to another card.
export function cardTaskBatches(tasks:CropTask[],cards?:string[][]){
 if(!cards)return [[...tasks].sort((a,b)=>cropStage(a)-cropStage(b))];
 const byId=new Map(tasks.map(task=>[task.id,task])),scheduled=new Set<string>();
 const batches=cards.map(ids=>{
  const needed=new Set<string>();
  function include(id:string){
   if(scheduled.has(id)||needed.has(id))return;
   const task=byId.get(id);if(!task)throw new Error('Missing timecard crop. Process the photo again.');
   needed.add(id);
   if(task.required===false){for(const parent of task.fallback_for||[])include(parent);for(const group of task.recover_for||[])for(const parent of group)include(parent);}
  }
  for(const id of ids)include(id);
  const batch=tasks.filter(task=>needed.has(task.id)).sort((a,b)=>cropStage(a)-cropStage(b));
  for(const task of batch)scheduled.add(task.id);
  return batch;
 });
 if(scheduled.size!==tasks.length)throw new Error('Incomplete timecard crop groups. Process the photo again.');
 return batches;
}
