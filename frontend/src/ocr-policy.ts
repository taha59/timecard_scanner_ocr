export type CropReading={text:string;confidence:number;quality?:number;skipped_reason?:'original_valid'};
export type CropTask={id:string;image:string;required?:boolean;fallback_for?:string[]};
// Deliberately narrower than the backend's parser: ambiguous OCR characters,
// malformed suffixes, and low-quality readings still get both crop versions.
export function clearClock(reading:CropReading|undefined){
 if(!reading||!Number.isFinite(reading.quality)||(reading.quality??0)<.9)return false;
 const match=reading.text.trim().match(/^(\d{1,2})\s*[:.]\s*(\d{2})\s*(am|pm)?$/i);
 if(!match)return false;
 const hour=Number(match[1]),minute=Number(match[2]);
 return minute<=59&&(match[3]?hour>=1&&hour<=12:hour<=23);
}
export function skipFallback(task:CropTask,readings:Record<string,CropReading>){
 return task.required===false&&Boolean(task.fallback_for?.length)&&task.fallback_for!.every(id=>id!==task.id&&clearClock(readings[id]));
}
