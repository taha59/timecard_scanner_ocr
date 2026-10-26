"""Download only the browser recognizer, verifying the pinned SHA-256."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.request import urlopen,Request

ROOT=Path(__file__).resolve().parents[1]
URL='https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv6/rec/PP-OCRv6_rec_medium.onnx'


def download():
    manifest=json.loads((ROOT/'backend'/'device-model.json').read_text())
    root=Path(os.getenv('RAPIDOCR_MODEL_DIR',str(ROOT/'model_cache'/'rapidocr')))
    root.mkdir(parents=True,exist_ok=True)
    target=root/manifest['filename']
    def valid(path):
        if not path.is_file() or path.stat().st_size!=manifest['bytes']:return False
        with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()==manifest['sha256']
    if valid(target):print('Verified device model already installed.');return
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=root,delete=False) as output:
            temporary=Path(output.name)
            with urlopen(Request(URL,headers={'User-Agent':'Timecard-model-installer/1.0'}),timeout=120) as response:
                while chunk:=response.read(1024*1024):output.write(chunk)
        if not valid(temporary):raise RuntimeError('Model checksum or size mismatch; refusing to install.')
        temporary.replace(target)
        print('Downloaded and verified device recognition weights. No server model was loaded.')
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)

if __name__=='__main__':download()
