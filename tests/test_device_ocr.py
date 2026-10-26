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
