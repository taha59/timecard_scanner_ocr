export type CropReading={text:string;confidence:number;quality?:number;skipped_reason?:'original_valid'|'standard_valid'};
export type CropTask={id:string;image:string;required?:boolean;fallback_for?:string[];recover_for?:string[][];edge_recovery?:boolean};
// Deliberately narrower than the backend's parser: ambiguous OCR characters,
// malformed suffixes, and low-quality readings still get both crop versions.
export function clearClock(reading:CropReading|undefined){
 if(!reading||!Number.isFinite(reading.quality)||(reading.quality??0)<.9)return false;
 const match=reading.text.trim().match(/^(\d{1,2})\s*[:.]\s*(\d{2})\s*(am|pm)?$/i);
 if(!match)return false;
 const hour=Number(match[1]),minute=Number(match[2]);
 return minute<=59&&(match[3]?hour>=1&&hour<=12:hour<=23);
}
// Match the backend's normal clock acceptance. A recovery retry is needed only
// while neither ordinary crop contains a readable time, irrespective of score.
export function readableClock(reading:CropReading|undefined){
 if(!reading)return false;
 const match=reading.text.trim().match(/^([0-9OoIlISs]{1,2})\s*[:.]\s*([0-9OoIlISs]{2})([^0-9]*)$/);
 if(!match||/\p{Number}/u.test(match[3]))return false;
 const digits=(s:string)=>s.replace(/[Oo]/g,'0').replace(/[Il]/g,'1').replace(/[Ss]/g,'5');
 const hour=Number(digits(match[1])),minute=Number(digits(match[2]));
 const suffix=match[3].replace(/[\s.]/g,'').toLowerCase();
 return minute<=59&&((suffix==='am'||suffix==='pm')?hour>=1&&hour<=12:hour<=23);
}
export function skipFallback(task:CropTask,readings:Record<string,CropReading>){
 const ordinary=task.fallback_for||[],recover=task.recover_for||[];
 if(task.required!==false||(!ordinary.length&&!recover.length))return false;
 if(ordinary.includes(task.id)||recover.some(group=>!group.length||group.includes(task.id)))return false;
 return ordinary.every(id=>clearClock(readings[id]))&&recover.every(group=>group.some(id=>readableClock(readings[id])&&(!task.edge_recovery||!/^\s*[012]\s*[:.]/.test(readings[id].text))));
}
export function cropStage(task:CropTask){return task.required!==false?0:task.edge_recovery?3:task.recover_for?.length?2:1;}
