from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import json
import os
import threading
import zipfile
import cv2
import numpy as np
from flask import Flask,request,jsonify,send_file,send_from_directory
from PIL import Image,ImageOps,UnidentifiedImageError
from werkzeug.exceptions import HTTPException
from .calculator import calculate_cards,STATUSES
from .extractor import extract
from .recognizer import create_recognizer,UnavailableRecognizer


def validate_cards(cards):
    if not isinstance(cards,list) or not 1<=len(cards)<=20:raise ValueError('Provide 1–20 cards')
    for card in cards:
        if not isinstance(card,dict) or not isinstance(card.get('days'),list) or len(card['days'])!=7:raise ValueError('Each card needs exactly seven day rows')
        for key in ['name','written_total']:
            if not isinstance(card.get(key,''),str) or len(card.get(key,''))>200:raise ValueError(f'Invalid {key}')
        for day in card['days']:
            if not isinstance(day,dict) or day.get('status') not in STATUSES:raise ValueError('Invalid day status')
            for key in ['in','out','adjustment_hours','note']:
                if not isinstance(day.get(key,''),str) or len(day.get(key,''))>500:raise ValueError(f'Invalid {key}')
            for key in ['confidence','in_confidence','out_confidence','status_confidence']:
                value=day.get(key)
                if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<=value<=1):raise ValueError('Confidence must be between 0 and 1')
    return cards


def create_app(recognizer=None):
    app=Flask(__name__,static_folder=None)
    app.config['MAX_CONTENT_LENGTH']=20*1024*1024
    cache=OrderedDict();cache_lock=threading.Lock();reader_lock=threading.Lock()
    reader=recognizer
    training=Path(os.getenv('TRAINING_DATA_DIR','training_data'))

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc,HTTPException):return jsonify(error=exc.description),exc.code
        if isinstance(exc,(ValueError,UnidentifiedImageError,Image.DecompressionBombError)):return jsonify(error=str(exc)),400
        app.logger.exception('Request failed')
        return jsonify(error='Processing failed. Check the backend logs; no payroll result was produced.'),500

    @app.get('/api/health')
    def health():return jsonify(ok=True,ocr_loaded=reader is not None,
                               ocr_engine=type(reader).__name__ if reader is not None else None)

    @app.post('/api/calculate')
    def calculate():
        body=request.get_json()
        if not isinstance(body,dict):raise ValueError('Expected a JSON object with cards')
        return jsonify(cards=calculate_cards(validate_cards(body.get('cards'))))

    @app.post('/api/scan')
    def scan():
        nonlocal reader
        upload=request.files.get('image')
        if not upload:raise ValueError('Choose a JPG, PNG or other supported image')
        pil=Image.open(upload.stream)
        if pil.width*pil.height>24_000_000:raise ValueError('Image exceeds 24 megapixels. Resize and try again.')
        pil=ImageOps.exif_transpose(pil).convert('RGB')
        image=cv2.cvtColor(np.array(pil),cv2.COLOR_RGB2BGR)
        manual=request.form.get('manual')=='true'
        if manual:active=UnavailableRecognizer()
        else:
            with reader_lock:
                if reader is None:
                    try:reader=create_recognizer()
                    except Exception:
                        app.logger.exception('Local OCR model could not load')
                        return jsonify(error='The OCR reader is unavailable. Install requirements and run python download_model.py on the server, or choose manual entry.',ocr_unavailable=True),503
                active=reader
        cards=extract(image,active)
        token=uuid4().hex
        with cache_lock:
            cache[token]=cards
            while len(cache)>8:cache.popitem(last=False)
        return jsonify(scan_id=token,cards=calculate_cards(cards),manual=manual,message='Manual mode: no handwriting was recognized. Enter and verify every punch and inspect adjustment notes.' if manual else 'All OCR values require review. Inspect every crop and adjustment area.')

    @app.post('/api/training')
    def save_training():
        body=request.get_json()
        if not isinstance(body,dict):raise ValueError('Expected JSON')
        cards=validate_cards(body.get('cards'))
        with cache_lock:original=cache.get(body.get('scan_id',''))
        if original is None:raise ValueError('Scan expired. Upload again before saving corrected crops.')
        if len(cards)!=len(original):raise ValueError('Card count differs from the original scan')
        batch=training/uuid4().hex;batch.mkdir(parents=True,exist_ok=False)
        import base64
        records=[]
        for ci,card in enumerate(cards):
            for di,day in enumerate(card['days']):
                if day.get('reviewed') is not True:continue
                if day['status']=='worked':
                    from .calculator import parse_time
                    try:parse_time(day.get('in'));parse_time(day.get('out'))
                    except ValueError:continue
                images={}
                for key in ['image','note_image']:
                    filename=f'{ci}_{di}_{key}.png'
                    (batch/filename).write_bytes(base64.b64decode(original[ci]['days'][di][key].split(',')[1]))
                    images[key]=filename
                records.append({'card':ci,'day':di,'status':day['status'],'in':day.get('in',''),'out':day.get('out',''),'note':day.get('note',''),'adjustment_hours':day.get('adjustment_hours','0'),'adjustment_confirmed':day.get('adjustment_confirmed',False),'images':images})
        (batch/'labels.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        return jsonify(saved_rows=len(records),batch=batch.name)

    @app.get('/api/training/<batch_id>')
    def download_training(batch_id):
        if not len(batch_id)==32 or any(c not in '0123456789abcdef' for c in batch_id):raise ValueError('Invalid training batch')
        folder=training/batch_id
        if not folder.is_dir():return jsonify(error='Training batch not found'),404
        data=BytesIO()
        with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:
            for file in folder.iterdir():z.write(file,file.name)
        data.seek(0);return send_file(data,mimetype='application/zip',as_attachment=True,download_name='corrected-crops.zip')

    dist=Path(__file__).parents[1]/'frontend'/'dist'
    @app.get('/')
    def index():
        if not (dist/'index.html').exists():return jsonify(error='Frontend is not built. Run npm install and npm run build in frontend.'),503
        return send_from_directory(dist,'index.html')
    @app.get('/assets/<path:filename>')
    def asset(filename):return send_from_directory(dist/'assets',filename)
    return app

if __name__=='__main__':create_app().run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=False)
