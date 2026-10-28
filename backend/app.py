from functools import wraps
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit
import json
import os
import threading
from time import perf_counter
import cv2
import numpy as np
from flask import Flask,Request,request,jsonify,send_file,send_from_directory,g
from PIL import Image,ImageOps,UnidentifiedImageError
from werkzeug.exceptions import HTTPException
from .calculator import calculate_cards,STATUSES
from .extractor import extract,detect_cards
from .recognizer import create_recognizer,UnavailableRecognizer


class MemoryUploadRequest(Request):
    # Werkzeug normally spills larger file uploads to a temporary disk file.
    def _get_file_stream(self,total_content_length,content_type,filename=None,content_length=None):
        return BytesIO()

def validate_cards(cards):
    if not isinstance(cards,list) or not 1<=len(cards)<=20:raise ValueError('Provide 1–20 cards')
    for card in cards:
        if not isinstance(card,dict) or not isinstance(card.get('days'),list) or len(card['days'])!=7:raise ValueError('Each card needs exactly seven day rows')
        for key in ['name','written_total']:
            if not isinstance(card.get(key,''),str) or len(card.get(key,''))>200:raise ValueError(f'Invalid {key}')
        for day in card['days']:
            if not isinstance(day,dict) or day.get('status','unknown') not in STATUSES:raise ValueError('Invalid day status')
            for key in ['in','out','adjustment_hours','note']:
                if not isinstance(day.get(key,''),str) or len(day.get(key,''))>500:raise ValueError(f'Invalid {key}')
            for key in ['confidence','in_confidence','out_confidence','status_confidence']:
                value=day.get(key)
                if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<=value<=1):raise ValueError('Confidence must be between 0 and 1')
    return cards


def create_app(recognizer=None):
    app=Flask(__name__,static_folder=None)
    app.request_class=MemoryUploadRequest
    app.config['MAX_CONTENT_LENGTH']=20*1024*1024
    production=os.getenv('APP_ENV','development')=='production'
    server_ocr=os.getenv('ENABLE_SERVER_OCR','false').lower()=='true'
    origins={origin.strip().rstrip('/') for origin in os.getenv('ALLOWED_ORIGINS','').split(',') if origin.strip()}
    for origin in origins:
        parsed=urlsplit(origin)
        if parsed.scheme not in {'https','http'} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('ALLOWED_ORIGINS must contain exact origins, such as https://your-app.vercel.app')
        if production and parsed.scheme!='https':raise ValueError('Production ALLOWED_ORIGINS must use HTTPS')
    if production and not origins:
        raise ValueError('Production requires ALLOWED_ORIGINS')
    reader=recognizer;reader_lock=threading.Lock();image_slot=threading.BoundedSemaphore(1)
    model_manifest=json.loads((Path(__file__).parent/'device-model.json').read_text())

    @app.before_request
    def protect_api():
        if not request.path.startswith('/api/'):return None
        g.request_started=perf_counter()
        g.stage_timings=[]
        origin=request.headers.get('Origin')
        same_origin=request.host_url.rstrip('/')
        if origin and origin!=same_origin and origin not in origins:
            return jsonify(error='This website origin is not allowed to use the API.'),403
        if request.method=='OPTIONS':return '',204
        if request.path=='/api/health':return None

    @app.after_request
    def response_headers(response):
        origin=request.headers.get('Origin')
        if request.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
            response.headers['Vary']='Origin'
            if hasattr(g,'request_started'):
                finished=perf_counter()
                timings=list(g.stage_timings)
                if hasattr(g,'compute_started'):timings.append(('compute',(finished-g.compute_started)*1000))
                timings.append(('handler',(finished-g.request_started)*1000))
                response.headers['Server-Timing']=', '.join(f'{name};dur={duration:.3f}' for name,duration in timings)
            if response.mimetype=='application/json':
                length=response.calculate_content_length()
                if length is not None:response.headers['X-Response-Bytes']=str(length)
            if origin in origins:
                response.headers['Access-Control-Allow-Origin']=origin
                response.headers['Access-Control-Allow-Methods']='GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers']='Authorization, Content-Type'
                response.headers['Access-Control-Max-Age']='600'
                response.headers['Access-Control-Expose-Headers']='Server-Timing, X-Response-Bytes'
        if not request.path.startswith('/api/'):
            response.headers['Cross-Origin-Opener-Policy']='same-origin'
            response.headers['Cross-Origin-Embedder-Policy']='require-corp'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        return response

    def limited_image_work(function):
        @wraps(function)
        def wrapped(*args,**kwargs):
            if not image_slot.acquire(blocking=False):
                return jsonify(error='Another photo is being processed. Please try again shortly.'),429
            try:return function(*args,**kwargs)
            finally:image_slot.release()
        return wrapped

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc,HTTPException):return jsonify(error=exc.description),exc.code
        if isinstance(exc,(ValueError,UnidentifiedImageError,Image.DecompressionBombError)):return jsonify(error=str(exc)),400
        app.logger.exception('Request failed')
        return jsonify(error='Processing failed. Check the backend logs; no payroll result was produced.'),500

    @app.get('/api/health')
    def health():
        from .device_ocr import DEVICE_PNG_COMPRESSION
        return jsonify(ok=True,stateless=True,server_ocr_enabled=server_ocr,ocr_loaded=reader is not None,
                       ocr_engine=type(reader).__name__ if reader is not None else None,
                       device_crop_png_compression=DEVICE_PNG_COMPRESSION,scan_profile='punch-only-v2')

    @app.get('/api/access')
    def access():return jsonify(ok=True)

    @app.post('/api/calculate')
    def calculate():
        body=request.get_json()
        if not isinstance(body,dict):raise ValueError('Expected a JSON object with cards')
        return jsonify(cards=calculate_cards(validate_cards(body.get('cards')),punch_only=True))

    @app.post('/api/scan')
    @limited_image_work
    def scan():
        nonlocal reader
        device=request.form.get('device')=='true'
        manual=request.form.get('manual')=='true'
        if not device and not manual and not server_ocr:
            return jsonify(error='Server OCR is disabled. Choose device OCR or manual entry.'),403
        upload=request.files.get('image')
        if not upload:raise ValueError('Choose a JPG, PNG or other supported image')
        rotation=request.form.get('rotation','0')
        if rotation not in {'0','90','180','270'}:
            raise ValueError('Rotation must be 0, 90, 180, or 270 degrees clockwise')
        # Accessing request.form/files consumes multipart input and can include
        # waiting for upload bytes. Keep it separate from image processing.
        g.stage_timings.append(('request_read',(perf_counter()-g.request_started)*1000))
        g.compute_started=perf_counter()
        stage_started=perf_counter()
        with Image.open(upload.stream) as source:
            if source.width*source.height>24_000_000:raise ValueError('Image exceeds 24 megapixels. Resize and try again.')
            pil=ImageOps.exif_transpose(source).convert('RGB')
        if pil.width*pil.height>6_000_000:
            scale=(6_000_000/(pil.width*pil.height))**.5
            pil.thumbnail((int(pil.width*scale),int(pil.height*scale)),Image.Resampling.LANCZOS)
        if rotation!='0':pil=pil.rotate(-int(rotation),expand=True)
        image=cv2.cvtColor(np.array(pil),cv2.COLOR_RGB2BGR)
        g.stage_timings.append(('image',(perf_counter()-stage_started)*1000))
        if device:
            from .device_ocr import DeviceRecognizer,pack_layouts
            stage_started=perf_counter()
            layouts=detect_cards(image)
            g.stage_timings.append(('grid',(perf_counter()-stage_started)*1000))
            if len(layouts)>20:raise ValueError('Use at most 20 cards per photo')
            collector=DeviceRecognizer()
            stage_started=perf_counter()
            extract(None,collector,layouts=layouts,include_images=False,include_notes=False)
            g.stage_timings.append(('crops',(perf_counter()-stage_started)*1000))
            stage_started=perf_counter()
            response=jsonify(layouts=pack_layouts(layouts),tasks=list(collector.tasks.values()))
            g.stage_timings.append(('response_build',(perf_counter()-stage_started)*1000))
            return response
        if manual:active=UnavailableRecognizer()
        else:
            with reader_lock:
                if reader is None:
                    try:reader=create_recognizer()
                    except Exception:
                        app.logger.exception('Local OCR model could not load')
                        return jsonify(error='The optional server OCR reader is unavailable. Choose device OCR or manual entry.'),503
                active=reader
        cards=extract(image,active,include_notes=False,include_auxiliary_images=False)
        return jsonify(scan_id=uuid4().hex,cards=calculate_cards(cards,punch_only=True),manual=manual,message='Manual mode: no handwriting was recognized. Enter both times for each worked day.' if manual else 'All OCR values require review. Check the times against the source photo.')

    @app.get('/api/device-model')
    def device_model():return jsonify(**model_manifest,url='/api/device-model/weights')

    @app.get('/api/device-model/weights')
    def device_weights():
        root=Path(os.getenv('RAPIDOCR_MODEL_DIR',str(Path(__file__).parents[1]/'model_cache'/'rapidocr')))
        path=root/model_manifest['filename']
        if not path.is_file():return jsonify(error='Device model is missing on the server. Run scripts/download_device_model.py.'),503
        return send_file(path,mimetype='application/octet-stream',conditional=True)

    @app.post('/api/device-result')
    @limited_image_work
    def device_result():
        from .device_ocr import DeviceRecognizer,unpack_layouts
        body=request.get_json()
        if not isinstance(body,dict):raise ValueError('Expected device readings')
        g.stage_timings.append(('request_read',(perf_counter()-g.request_started)*1000))
        g.compute_started=perf_counter()
        stage_started=perf_counter()
        layouts=unpack_layouts(body.get('layouts'))
        g.stage_timings.append(('layouts',(perf_counter()-stage_started)*1000))
        readings=body.get('readings')
        if not isinstance(readings,dict) or len(readings)>1200:raise ValueError('Invalid device readings')
        for value in readings.values():
            if not isinstance(value,dict) or not isinstance(value.get('text'),str) or len(value['text'])>500:raise ValueError('Invalid device text')
            if value.get('skipped_reason') not in (None,'original_valid','standard_valid'):
                raise ValueError('Invalid skipped crop reason')
            if value.get('skipped_reason') and (value['text'] or value.get('confidence')!=0):
                raise ValueError('Skipped crops must not contain invented readings')
            score=value.get('confidence')
            if isinstance(score,bool) or not isinstance(score,(int,float)) or not 0<=score<=1:raise ValueError('Invalid device confidence')
        stage_started=perf_counter()
        cards=extract(None,DeviceRecognizer(readings),layouts=layouts,include_notes=False,include_auxiliary_images=False)
        g.stage_timings.append(('reconstruct',(perf_counter()-stage_started)*1000))
        stage_started=perf_counter()
        response=jsonify(scan_id=uuid4().hex,cards=calculate_cards(cards,punch_only=True),manual=False,message='Device OCR complete. Review every entry. Photos were processed in server memory only; no photos or scans were saved.')
        g.stage_timings.append(('response_build',(perf_counter()-stage_started)*1000))
        return response

    dist=Path(__file__).parents[1]/'frontend'/'dist'
    @app.get('/')
    def index():
        if not (dist/'index.html').exists():return jsonify(service='Timecard API',health='/api/health',stateless=True)
        return send_from_directory(dist,'index.html')
    @app.get('/manifest.webmanifest')
    @app.get('/sw.js')
    @app.get('/icon-192.png')
    @app.get('/icon-512.png')
    def install_asset():return send_from_directory(dist,request.path.lstrip('/'))
    @app.get('/assets/<path:filename>')
    def asset(filename):return send_from_directory(dist/'assets',filename)
    return app

if __name__=='__main__':create_app().run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=False)
