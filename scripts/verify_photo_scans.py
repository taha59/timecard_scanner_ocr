from pathlib import Path
from io import BytesIO
import json,time
from backend.app import create_app
from backend.recognizer import create_recognizer
reader=create_recognizer();client=create_app(reader).test_client();reports=[]
for name in ['october-single','october-group']:
 start=time.monotonic()
 response=client.post('/api/scan',data={'image':(BytesIO(Path('fixtures/'+name+'.jpg').read_bytes()),name+'.jpg')})
 body=response.get_json();result={'photo':name,'http_status':response.status_code,'seconds':round(time.monotonic()-start,2)}
 if response.status_code!=200:result['error']=body
 else:
  result['cards']=[{'name':c['name'],'days':[{k:d.get(k) for k in ['status','in','out','raw_in','raw_out','raw_status','computed']} for d in c['days']]} for c in body['cards']]
 reports.append(result);print(json.dumps(result,indent=2),flush=True)
 Path('new-photo-verification.json').write_text(json.dumps(reports,indent=2)+'\n')
