from io import BytesIO
from pathlib import Path
import builtins
import pytest
from backend.app import create_app

ORIGIN='https://timecards.example.com'
TOKEN='a-private-password-with-at-least-24-characters'

@pytest.fixture
def production(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('APP_ACCESS_TOKEN',TOKEN)
    monkeypatch.setenv('ALLOWED_ORIGINS',ORIGIN)
    monkeypatch.setenv('ENABLE_SERVER_OCR','false')
    return create_app().test_client()

def test_cross_origin_access_without_password(production):
    preflight=production.options('/api/device-result',headers={'Origin':ORIGIN,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
    assert preflight.status_code==204
    assert preflight.headers['Access-Control-Allow-Origin']==ORIGIN
    allowed=production.get('/api/device-model',headers={'Origin':ORIGIN})
    assert allowed.status_code==200 and allowed.headers['Cache-Control']=='no-store'
    assert allowed.headers['Access-Control-Allow-Origin']==ORIGIN
    blocked=production.post('/api/calculate',json={'cards':[]},headers={'Origin':'https://evil.example'})
    assert blocked.status_code==403 and 'Access-Control-Allow-Origin' not in blocked.headers
    # Old hosting password values and stale client headers no longer gate access.
    assert production.get('/api/access').status_code==200
    assert production.get('/api/access',headers={'Authorization':'Bearer wrong'}).status_code==200
    assert production.get('/api/health').status_code==200


def test_production_fails_without_origin_configuration(monkeypatch):
    monkeypatch.setenv('APP_ENV','production');monkeypatch.delenv('APP_ACCESS_TOKEN',raising=False)
    monkeypatch.delenv('ALLOWED_ORIGINS',raising=False)
    with pytest.raises(ValueError,match='Production requires'):create_app()

def test_production_starts_without_password(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('ALLOWED_ORIGINS',ORIGIN)
    monkeypatch.delenv('APP_ACCESS_TOKEN',raising=False)
    assert create_app().test_client().get('/api/device-model').status_code==200


def test_server_ocr_disabled_and_legacy_storage_removed(production):
    auth={'Authorization':f'Bearer {TOKEN}'}
    assert production.post('/api/scan',headers=auth).status_code==403
    assert production.post('/api/training',json={},headers=auth).status_code==404
    assert production.get('/api/health').json['stateless'] is True
    assert production.get('/api/health').json['server_ocr_enabled'] is False

def test_upload_never_spools_to_disk_or_creates_debug_crops(monkeypatch,tmp_path):
    monkeypatch.setenv('DEBUG_CROPS_DIR',str(tmp_path/'debug'))
    app=create_app()
    data=(Path(__file__).parents[1]/'fixtures/novel-five-cards.jpg').read_bytes()
    # Verify upload stream is BytesIO, including larger-than-spool-threshold data.
    @app.post('/test-upload')
    def upload_check():
        from flask import request
        assert isinstance(request.files['image'].stream,BytesIO)
        return '',204
    assert app.test_client().post('/test-upload',data={'image':(BytesIO(b'x'*700_000),'large.jpg')}).status_code==204
    original_open=builtins.open
    def no_writes(file,mode='r',*args,**kwargs):
        assert not any(c in mode for c in 'wax+'),f'Unexpected disk write: {file}'
        return original_open(file,mode,*args,**kwargs)
    monkeypatch.setattr(builtins,'open',no_writes)
    response=app.test_client().post('/api/scan',data={'image':(BytesIO(data),'photo.jpg'),'manual':'true'})
    assert response.status_code==200
    assert not (tmp_path/'debug').exists()


def test_browser_isolation_headers_keep_cors_intact(production):
    page=production.get('/')
    assert page.headers['Cross-Origin-Opener-Policy']=='same-origin'
    assert page.headers['Cross-Origin-Embedder-Policy']=='require-corp'
    api=production.get('/api/health',headers={'Origin':ORIGIN})
    assert api.headers['Access-Control-Allow-Origin']==ORIGIN
    assert api.headers['Cache-Control']=='no-store'


def test_busy_results_expose_cors_and_retry_after(production,monkeypatch):
    import threading
    import backend.app as module
    entered=threading.Event();release=threading.Event();completed=[]
    original=module.detect_cards
    def held(image):
        entered.set()
        assert release.wait(5)
        return original(image)
    monkeypatch.setattr(module,'detect_cards',held)
    photo=(Path(__file__).parents[1]/'fixtures/october-single.jpg').read_bytes()
    def prepare():
        with production.application.test_client() as client:
            completed.append(client.post('/api/scan',data={'device':'true','image':(BytesIO(photo),'card.jpg')}))
    worker=threading.Thread(target=prepare);worker.start()
    try:
        assert entered.wait(3)
        busy=production.post('/api/device-result',json={},headers={'Origin':ORIGIN})
        assert busy.status_code==429
        assert busy.headers['Retry-After']=='1'
        assert busy.headers['Access-Control-Allow-Origin']==ORIGIN
        assert 'Retry-After' in busy.headers['Access-Control-Expose-Headers']
    finally:
        release.set();worker.join(5)
    assert completed and completed[0].status_code==200
