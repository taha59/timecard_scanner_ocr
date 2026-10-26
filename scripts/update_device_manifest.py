"""Regenerate the browser model manifest after installing/updating OCR weights."""
import hashlib
import json
import os
from pathlib import Path
import onnxruntime as ort

root=Path(__file__).resolve().parents[1]
model=Path(os.getenv('RAPIDOCR_MODEL_DIR',str(root/'model_cache'/'rapidocr')))/'PP-OCRv6_rec_medium.onnx'
session=ort.InferenceSession(str(model))
characters=session.get_modelmeta().custom_metadata_map['character'].splitlines()
manifest={'version':'ppocrv6-rec-medium-v1','filename':model.name,'bytes':model.stat().st_size,
          'sha256':hashlib.sha256(model.read_bytes()).hexdigest(),'characters':['blank',*characters,' ']}
(root/'backend'/'device-model.json').write_text(json.dumps(manifest))
print('Updated browser model size, checksum, and vocabulary.')
