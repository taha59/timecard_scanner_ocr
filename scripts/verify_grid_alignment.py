import cv2,json,time
from pathlib import Path
from backend.extractor import extract
from backend.recognizer import create_recognizer
from backend.calculator import calculate_cards
r=create_recognizer(); reports=[]
for name in ['novel-five-cards','timecards','october-single','october-group']:
 t=time.monotonic();cs=calculate_cards(extract(cv2.imread('fixtures/'+name+'.jpg'),r)); report={'photo':name,'seconds':round(time.monotonic()-t,2),'cards':[{k:c[k] for k in ['name','totals']}|{'days':[{k:d.get(k) for k in ['status','in','out','raw_in','raw_out','computed','flags']} for d in c['days']]} for c in cs]};reports.append(report);Path('grid-rewrite-evaluation.json').write_text(json.dumps(reports,indent=2)+'\n');print(name,report['seconds'],len(cs),flush=True)
 for c in report['cards']:print(c['name'],[(d['status'],d['in'],d['out']) for d in c['days']],flush=True)
