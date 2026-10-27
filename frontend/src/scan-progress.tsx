export function ScanProgress({message}:{message:string}){
 const reading=message.match(/^Reading on this device: (\d+) of (\d+) crops/);
 const download=message.match(/^Downloading model: (\d+)%/);
 const percent=reading&&Number(reading[2])>0?Math.min(100,Math.floor(Number(reading[1])/Number(reading[2])*100)):download?Number(download[1]):undefined;
 const label=reading?'Reading handwriting':download?'Downloading model':message.startsWith('Preparing crops')?'Preparing your photo…':/runtime|Loading the model|already loaded|Retrying with one/.test(message)?'Starting handwriting reader…':message;
 return <div className="scan-progress notice" role="status"><div className="scan-progress-label"><span>{label}</span>{percent!==undefined&&<strong>{percent}%</strong>}</div><progress aria-label={label} max={100} value={percent}/></div>;
}
