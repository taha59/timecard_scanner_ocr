from io import BytesIO
from pathlib import Path
import pytest
from backend.app import create_app

class NeverRecognize:
    def read(self,*args,**kwargs):
        raise AssertionError('Device processing must not run server OCR')

@pytest.fixture
def client():return create_app(NeverRecognize()).test_client()

def prepare(client):
    return client.post('/api/scan',data={'image':(BytesIO((Path(__file__).parents[1]/'fixtures/novel-five-cards.jpg').read_bytes()),'cards.jpg'),'device':'true'})

def test_device_roundtrip_uses_no_server_model(client):
    prepared=prepare(client)
    assert prepared.status_code==200
    job=prepared.json
    assert len(job['tasks'])>100
    assert all(task['image'].startswith('data:image/png;base64,') for task in job['tasks'])
    readings={task['id']:{'text':'OFF','confidence':.99} for task in job['tasks']}
    response=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings})
    assert response.status_code==200
    assert len(response.json['cards'])==5
    assert all(d['status']=='off' and d['reviewed'] is False for c in response.json['cards'] for d in c['days'])
    assert all(d['status_confidence']<=.79 for c in response.json['cards'] for d in c['days'])
    # A new app instance can finish it: no scan cache or sticky worker needed.
    assert create_app(NeverRecognize()).test_client().post('/api/device-result',json={'layouts':job['layouts'],'readings':readings}).status_code==200

def test_device_readings_validation(client):
    job=prepare(client).json
    assert client.post('/api/device-result',json={'layouts':job['layouts'],'readings':{}}).status_code==400
    readings={task['id']:{'text':'OFF','confidence':2} for task in job['tasks']}
    assert client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings}).status_code==400
    assert client.post('/api/device-result',json={'layouts':[],'readings':{}}).status_code==400

def test_device_model_and_install_assets(client):
    manifest=client.get('/api/device-model').json
    assert manifest['bytes']>1_000_000 and len(manifest['sha256'])==64
    assert manifest['characters'][0]=='blank'
    assert client.get('/manifest.webmanifest').status_code==200
    assert client.get('/sw.js').status_code==200


def test_device_noisy_blank_rows_have_prepared_punches(client):
    job=prepare(client).json
    readings={task['id']:{'text':'10:00','confidence':.5} for task in job['tasks']}
    response=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings})
    assert response.status_code==200
    assert all(d['status']=='worked' for c in response.json['cards'] for d in c['days'])


def test_fallback_dependencies_and_skipped_readings(client):
    job=prepare(client).json
    tasks={task['id']:task for task in job['tasks']}
    fallbacks=[task for task in tasks.values() if task.get('required') is False]
    assert fallbacks
    assert all(task.get('fallback_for') or task.get('recover_for') for task in fallbacks)
    assert all(parent in tasks and parent!=task['id'] for task in fallbacks for parent in task.get('fallback_for',[]))
    full={key:{'text':'10:00','confidence':.79} for key in tasks}
    all_read=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':full}).json
    skipped={key:({'text':'','confidence':0,'skipped_reason':'original_valid'} if task.get('required') is False else full[key]) for key,task in tasks.items()}
    response=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':skipped})
    assert response.status_code==200
    for old,new in zip(all_read['cards'],response.json['cards']):
        assert [(d['in'],d['out'],d['status']) for d in old['days']]==[(d['in'],d['out'],d['status']) for d in new['days']]
        assert all(d['reviewed'] is False for d in new['days'])
    assert any('Alternate OCR crop not checked: verify original crop' in d['flags'] for c in response.json['cards'] for d in c['days'])
    for key,task in tasks.items():
        if task.get('required') is not False:skipped[key]={'text':'not a clock','confidence':.2}
    assert client.post('/api/device-result',json={'layouts':job['layouts'],'readings':skipped}).status_code==400


def test_low_score_valid_times_are_not_suppressed(client):
    job=prepare(client).json
    readings={task['id']:{'text':'9:00am','confidence':.02} for task in job['tasks']}
    response=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings})
    assert response.status_code==200
    for card in response.json['cards']:
        for day in card['days']:
            assert day['in']=='9:00am' and day['out']=='9:00am'
            assert day['reviewed'] is False
            assert 'Low OCR confidence: verify original crop' in day['flags']


def test_focused_out_retry_can_recover_low_score_time(client):
    import cv2
    from backend.device_ocr import DeviceRecognizer,unpack_layouts
    from backend.extractor import clean_ink,photo_punch_crops,focused_punch_crops,punch_crops
    job=prepare(client).json
    layout=unpack_layouts(job['layouts'])[0];ink=clean_ink(layout.cells[0])
    original=photo_punch_crops(layout.cells[0],ink);cleaned=punch_crops(ink);focused=focused_punch_crops(layout.cells[0],ink)
    readings={task['id']:{'text':'not readable','confidence':.2} for task in job['tasks']}
    key=DeviceRecognizer._key
    readings[key(original[0],'time')]={'text':'9:00am','confidence':.02}
    readings[key(original[1],'time')]={'text':'11:400 1','confidence':.99}
    readings[key(cleaned[1],'time')]={'text':'not readable','confidence':.9}
    readings[key(focused[1],'time')]={'text':'11:40pm','confidence':.02}
    response=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings})
    assert response.status_code==200
    day=response.json['cards'][0]['days'][0]
    assert day['out']=='11:40pm' and not day['reviewed']
    assert 'Tentative OCR recovery: verify digits against source crop' in day['flags']


def test_bare_numbers_without_another_clock_are_not_invented_times(client):
    job=prepare(client).json
    readings={task['id']:{'text':'1140','confidence':.99} for task in job['tasks']}
    response=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings})
    assert response.status_code==200
    assert all(not d['in'] and not d['out'] for c in response.json['cards'] for d in c['days'])


def test_previous_clients_without_optional_focus_tasks_still_work(client):
    job=prepare(client).json
    readings={task['id']:{'text':'9:00am','confidence':.3} for task in job['tasks']
              if not (task.get('recover_for') and not task.get('fallback_for') and task.get('required') is False)}
    response=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings})
    assert response.status_code==200
    assert all(d['in']=='9:00am' and d['out']=='9:00am' for c in response.json['cards'] for d in c['days'])


def test_tentative_recovery_keeps_meridiem_disagreement_flag(client):
    from backend.device_ocr import DeviceRecognizer,unpack_layouts
    from backend.extractor import clean_ink,photo_punch_crops,focused_punch_crops,punch_crops
    job=prepare(client).json;layout=unpack_layouts(job['layouts'])[0];ink=clean_ink(layout.cells[0])
    original=photo_punch_crops(layout.cells[0],ink);cleaned=punch_crops(ink);focused=focused_punch_crops(layout.cells[0],ink)
    readings={task['id']:{'text':'not readable','confidence':.3} for task in job['tasks']}
    key=DeviceRecognizer._key
    readings[key(original[0],'time')]={'text':'9:00am','confidence':.4}
    readings[key(original[1],'time')]={'text':'900am','confidence':.4}
    readings[key(cleaned[1],'time')]={'text':'900pm','confidence':.4}
    response=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings})
    assert response.status_code==200
    day=response.json['cards'][0]['days'][0]
    assert day['out']=='9:00am'
    assert 'OCR readings disagree: verify original crop' in day['flags']
    assert not day['reviewed']


def test_label_edge_crop_recovers_missing_and_clipped_valid_hours():
    import cv2
    from backend.device_ocr import DeviceRecognizer
    from backend.extractor import detect_cards,clean_ink,punch_crops,photo_punch_crops,focused_punch_crops,label_edge_punch_crops
    layout=detect_cards(cv2.imread(str(Path(__file__).parents[1]/'fixtures/october-group.jpg')))[2]
    for day,clipped,expected in [(1,'0:55pm','10:55pm'),(3,'0:45','10:45pm'),(5,'1:45pm','11:45pm')]:
        cell=layout.cells[day];ink=clean_ink(cell);punches=punch_crops(ink)
        edge=label_edge_punch_crops(layout,day)[1]
        assert edge is not None
        collector=DeviceRecognizer();collector.read_punches(layout,day,punches)
        readings={key:{'text':'unreadable','confidence':.1} for key in collector.tasks}
        for crops in [punches,photo_punch_crops(cell,ink),focused_punch_crops(cell,ink)]:
            readings[collector._key(crops[1],'time')]={'text':clipped,'confidence':.99}
        readings[collector._key(edge,'time')]={'text':expected,'confidence':.4}
        out=DeviceRecognizer(readings).read_punches(layout,day,punches)[1]
        assert out.text==expected and out.recovered
        if clipped=='1:45pm':assert out.conflict
        # A scan prepared before this update can still finish without edge tasks.
        del readings[collector._key(edge,'time')]
        DeviceRecognizer(readings).read_punches(layout,day,punches)
