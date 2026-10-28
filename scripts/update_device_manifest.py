"""Regenerate the browser model manifest after installing/updating OCR weights."""
import hashlib
import json
import os
import argparse
from pathlib import Path
import onnxruntime as ort

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--variant',choices=['medium','small'],default='medium')
variant=parser.parse_args().variant
root=Path(__file__).resolve().parents[1]
model=Path(os.getenv('RAPIDOCR_MODEL_DIR',str(root/'model_cache'/'rapidocr')))/f'PP-OCRv6_rec_{variant}.onnx'
session=ort.InferenceSession(str(model))
characters=session.get_modelmeta().custom_metadata_map['character'].splitlines()
manifest={'version':f'ppocrv6-rec-{variant}-v1','filename':model.name,'bytes':model.stat().st_size,
          'sha256':hashlib.sha256(model.read_bytes()).hexdigest(),'characters':['blank',*characters,' ']}
(root/'backend'/('device-model.json' if variant=='medium' else 'device-model-small.json')).write_text(json.dumps(manifest))
print('Updated browser model size, checksum, and vocabulary.')
