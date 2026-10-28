const KEY='timecard-debug-statistics';

export function loadDebugStats(){
 try{
  const saved=window.localStorage.getItem(KEY);
  if(saved==='true'||saved==='false')return saved==='true';
 }catch{}
 return import.meta.env?.VITE_DEBUG_STATS==='true';
}

export function saveDebugStats(enabled:boolean){
 try{window.localStorage.setItem(KEY,String(enabled));}catch{}
}
