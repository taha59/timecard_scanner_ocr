from io import BytesIO
import json
from pathlib import Path
import pytest
from backend.app import create_app
from backend.recognizer import Reading
from tests.test_calculator import card_from_truth,GROUND

ROOT=Path(__file__).parents[1]
class Reader:
    def read(self,image,mode='text'):return Reading('10:00' if mode=='time' else '',.3)

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('TRAINING_DATA_DIR',str(tmp_path/'training'))
    return create_app(Reader()).test_client()

def test_scan_calculate_and_training(client):
    response=client.post('/api/scan',data={'image':(BytesIO((ROOT/'fixtures/timecards.jpg').read_bytes()),'photo.jpg')})
    assert response.status_code==200
    scan=response.get_json();assert len(scan['cards'])==5
    assert all(c['totals']['grand']['minutes'] is None for c in scan['cards'])
    corrected=card_from_truth(GROUND[0]);corrected['days'][0]['reviewed']=True
    recalculated=client.post('/api/calculate',json={'cards':[corrected]})
    assert recalculated.status_code==200
    assert recalculated.json['cards'][0]['totals']['grand']['hm']=='51:53'
    scan['cards'][0]['days'][0].update(status='worked',**{'in':'10:10','out':'8:00','reviewed':True})
    saved=client.post('/api/training',json={'scan_id':scan['scan_id'],'cards':scan['cards']})
    assert saved.status_code==200 and saved.json['saved_rows']==1
    download=client.get('/api/training/'+saved.json['batch'])
    assert download.status_code==200 and download.data[:2]==b'PK'
    import zipfile
    with zipfile.ZipFile(BytesIO(download.data)) as z:
        label=json.loads(z.read('labels.jsonl'))
        assert label['in']=='10:10' and 'image' in label['images']

def test_manual_mode(client):
    r=client.post('/api/scan',data={'image':(BytesIO((ROOT/'fixtures/timecards.jpg').read_bytes()),'photo.jpg'),'manual':'true'})
    assert r.status_code==200 and r.json['manual']
    assert all(not c['totals']['complete'] for c in r.json['cards'])


@pytest.mark.parametrize('filename,count',[('october-group.jpg',7),('october-single.jpg',1)])
def test_new_photos_scan_without_ocr_or_network(client,filename,count):
    response=client.post('/api/scan',data={
        'image':(BytesIO((ROOT/'fixtures'/filename).read_bytes()),filename),'manual':'true'})
    assert response.status_code==200
    assert len(response.json['cards'])==count
    assert sum(len(c['days']) for c in response.json['cards'])==count*7

@pytest.mark.parametrize('payload',[{}, {'cards':[]},{'cards':[{}]}, {'cards':[{'days':[None]*7}]}])
def test_bad_payload(client,payload):assert client.post('/api/calculate',json=payload).status_code==400

def test_invalid_image(client):
    assert client.post('/api/scan',data={}).status_code==400
    assert client.post('/api/scan',data={'image':(BytesIO(b'nonsense'),'bad.jpg')}).status_code==400

def test_malformed_confidence(client):
    card=card_from_truth(GROUND[0]);card['days'][0]['confidence']='bad'
    assert client.post('/api/calculate',json={'cards':[card]}).status_code==400

def test_written_total_cannot_break_calculation(client):
    card=card_from_truth(GROUND[0]);card['written_total']='9999.99'
    r=client.post('/api/calculate',json={'cards':[card]})
    assert r.status_code==200 and r.json['cards'][0]['totals']['regular']['hm']=='51:53'
