from io import BytesIO
from pathlib import Path
import re
from backend.app import create_app


def durations(response):
    return {name:float(value) for name,value in re.findall(r'([a-z_]+);dur=([0-9.]+)',response.headers['Server-Timing'])}


def test_device_preparation_exposes_non_overlapping_server_compute():
    client=create_app().test_client()
    photo=(Path(__file__).parents[1]/'fixtures/october-single.jpg').read_bytes()
    response=client.post('/api/scan',data={'image':(BytesIO(photo),'card.jpg'),'device':'true'})
    assert response.status_code==200
    assert set(response.json)=={'layouts','tasks'}
    timing=durations(response)
    assert set(timing)=={'request_read','image','grid','crops','response_build','compute','handler'}
    assert all(value>=0 for value in timing.values())
    assert sum(timing[name] for name in ['image','grid','crops','response_build'])<=timing['compute']+.01
    assert timing['request_read']+timing['compute']<=timing['handler']+.01
    assert int(response.headers['X-Response-Bytes'])==len(response.data)
    assert client.get('/api/health').json['ocr_loaded'] is False


def test_timing_headers_are_readable_only_by_allowed_origin(monkeypatch):
    monkeypatch.setenv('ALLOWED_ORIGINS','https://timecards.example')
    monkeypatch.setenv('APP_ACCESS_TOKEN','timing-test-token')
    client=create_app().test_client()
    allowed=client.get('/api/access',headers={'Origin':'https://timecards.example','Authorization':'Bearer timing-test-token'})
    assert allowed.status_code==200
    assert allowed.headers['Access-Control-Expose-Headers']=='Server-Timing, X-Response-Bytes'
    assert 'handler' in durations(allowed)
    assert allowed.headers['Cache-Control']=='no-store'
    blocked=client.get('/api/access',headers={'Origin':'https://other.example','Authorization':'Bearer timing-test-token'})
    assert blocked.status_code==403
    assert 'Access-Control-Expose-Headers' not in blocked.headers


def test_invalid_scan_still_has_handler_timing():
    client=create_app().test_client()
    response=client.post('/api/scan',data={'device':'true'})
    assert response.status_code==400
    assert durations(response)['handler']>=0


def test_device_results_have_processing_breakdown():
    client=create_app().test_client()
    photo=(Path(__file__).parents[1]/'fixtures/october-single.jpg').read_bytes()
    prepared=client.post('/api/scan',data={'image':(BytesIO(photo),'card.jpg'),'device':'true'}).json
    response=client.post('/api/device-result',json={'layouts':prepared['layouts'],'readings':{t['id']:{'text':'','confidence':0} for t in prepared['tasks']}})
    assert response.status_code==200
    timing=durations(response)
    assert {'request_read','layouts','reconstruct','response_build','compute','handler'}==set(timing)
    assert timing['layouts']+timing['reconstruct']+timing['response_build']<=timing['compute']+.01
    assert int(response.headers['X-Response-Bytes'])==len(response.data)
    assert client.get('/api/health').json['ocr_loaded'] is False
