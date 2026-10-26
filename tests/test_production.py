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

def test_cross_origin_auth_and_preflight(production):
    preflight=production.options('/api/device-result',headers={'Origin':ORIGIN,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'})
    assert preflight.status_code==204
    assert preflight.headers['Access-Control-Allow-Origin']==ORIGIN
    assert 'Authorization' in preflight.headers['Access-Control-Allow-Headers']
    denied=production.get('/api/device-model',headers={'Origin':ORIGIN})
    assert denied.status_code==401 and denied.headers['Access-Control-Allow-Origin']==ORIGIN
    allowed=production.get('/api/device-model',headers={'Origin':ORIGIN,'Authorization':f'Bearer {TOKEN}'})
    assert allowed.status_code==200 and allowed.headers['Cache-Control']=='no-store'
    blocked=production.post('/api/calculate',json={'cards':[]},headers={'Origin':'https://evil.example','Authorization':f'Bearer {TOKEN}'})
    assert blocked.status_code==403 and 'Access-Control-Allow-Origin' not in blocked.headers
    assert production.get('/api/access',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert production.get('/api/access',headers={'Authorization':f'Bearer {TOKEN}'}).status_code==200
    assert production.get('/api/health').status_code==200

def test_production_fails_without_private_configuration(monkeypatch):
    monkeypatch.setenv('APP_ENV','production');monkeypatch.delenv('APP_ACCESS_TOKEN',raising=False)
    monkeypatch.delenv('ALLOWED_ORIGINS',raising=False)
    with pytest.raises(ValueError,match='Production requires'):create_app()

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
