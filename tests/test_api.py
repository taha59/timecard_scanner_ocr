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
    monkeypatch.setenv('ENABLE_SERVER_OCR','true')
    return create_app(Reader()).test_client()

def test_scan_and_calculate_without_photo_storage(client):
    response=client.post('/api/scan',data={'image':(BytesIO((ROOT/'fixtures/timecards.jpg').read_bytes()),'photo.jpg')})
    assert response.status_code==200
    scan=response.get_json();assert len(scan['cards'])==5
    assert all(c['totals']['grand']['minutes'] is not None for c in scan['cards'])
    corrected=card_from_truth(GROUND[0]);corrected['days'][0]['reviewed']=True
    recalculated=client.post('/api/calculate',json={'cards':[corrected]})
    assert recalculated.status_code==200
    assert recalculated.json['cards'][0]['totals']['grand']['hm']==GROUND[0]['regular']
    assert client.post('/api/training',json={'cards':scan['cards']}).status_code==404
    assert client.get('/api/training/'+'a'*32).status_code==404

def test_manual_mode(client):
    r=client.post('/api/scan',data={'image':(BytesIO((ROOT/'fixtures/timecards.jpg').read_bytes()),'photo.jpg'),'manual':'true'})
    assert r.status_code==200 and r.json['manual']
    assert all(c['totals']['regular']['minutes']==0 for c in r.json['cards'])


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
    assert r.status_code==200 and r.json['cards'][0]['totals']['regular']['hm']==GROUND[0]['regular']


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_scan_applies_clockwise_quarter_turn_before_extraction(client,monkeypatch,rotation):
    import numpy as np
    from PIL import Image
    pixels=np.zeros((8,12,3),dtype=np.uint8)
    pixels[:4,:6]=(255,0,0);pixels[:4,6:]=(0,255,0)
    pixels[4:,:6]=(0,0,255);pixels[4:,6:]=(255,255,0)
    data=BytesIO();Image.fromarray(pixels).save(data,format='PNG');data.seek(0)
    captured=[]
    monkeypatch.setattr('backend.app.extract',lambda image,reader:captured.append(image.copy()) or [])
    response=client.post('/api/scan',data={'image':(data,'corners.png'),'rotation':str(rotation),'manual':'true'})
    assert response.status_code==200
    expected=np.rot90(pixels,k=-(rotation//90))[:,:,::-1]
    np.testing.assert_array_equal(captured[0],expected)


@pytest.mark.parametrize('rotation',['45','-90','360','invalid',''])
def test_scan_rejects_non_quarter_turns(client,rotation):
    response=client.post('/api/scan',data={
        'image':(BytesIO((ROOT/'fixtures/timecards.jpg').read_bytes()),'photo.jpg'),
        'rotation':rotation,'manual':'true'})
    assert response.status_code==400
    assert 'Rotation must be' in response.json['error']


def test_user_rotation_is_applied_after_camera_exif_orientation(client,monkeypatch):
    import numpy as np
    from PIL import Image
    pixels=np.zeros((8,12,3),dtype=np.uint8);pixels[:3,:4]=(255,0,0)
    photo=Image.fromarray(pixels);exif=photo.getexif();exif[274]=6
    data=BytesIO();photo.save(data,format='PNG',exif=exif);data.seek(0)
    captured=[]
    monkeypatch.setattr('backend.app.extract',lambda image,reader:captured.append(image.copy()) or [])
    response=client.post('/api/scan',data={'image':(data,'camera.png'),'rotation':'270','manual':'true'})
    assert response.status_code==200
    np.testing.assert_array_equal(captured[0],pixels[:,:,::-1])


@pytest.mark.parametrize('rotation',[90,180,270])
def test_sideways_real_photo_is_corrected_for_scan(client,rotation):
    from PIL import Image
    data=BytesIO()
    Image.open(ROOT/'fixtures/novel-five-cards.jpg').rotate(rotation,expand=True).save(data,format='PNG')
    data.seek(0)
    response=client.post('/api/scan',data={'image':(data,'sideways.png'),'rotation':str(rotation),'manual':'true'})
    assert response.status_code==200
    assert len(response.json['cards'])==5
