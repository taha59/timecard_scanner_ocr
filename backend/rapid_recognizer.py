"""CPU PaddleOCR via ONNX Runtime. No Apple APIs or hosted inference."""
import hashlib
import os
import re
from pathlib import Path
import threading

import cv2
import numpy as np

from .calculator import parse_time
from .ocr_common import clock_text
from .recognizer import Reading

MODEL_FILES = {'Det': 'PP-OCRv6_det_small.onnx', 'Rec': 'PP-OCRv6_rec_medium.onnx'}


def choose_reading(groups):
    """Prefer original row context; use broader context only on parse failure."""
    alternatives = [{'source': source, 'raw': line['text'],
                     'value': clock_text(line['text'])} for source, lines in groups for line in lines]
    selected = None
    for source, lines in groups:
        valid = [line for line in lines if clock_text(line['text'])]
        if len(valid) == 1:
            selected = valid[0]
            break
    clocks = {parse_time(item['value'])[0] % 720 for item in alternatives if item['value']}
    explicit_clocks = {parse_time(item['value'])[0] for item in alternatives
                       if item['value'] and parse_time(item['value'])[1]}
    return Reading(clock_text(selected['text']) if selected else '',
                   min(float(selected['confidence']), .79) if selected else 0,
                   selected['text'] if selected else ' | '.join(item['raw'] for item in alternatives),
                   alternatives, len(clocks) > 1 or len(explicit_clocks) > 1)


class RapidOCRRecognizer:
    def __init__(self, local_only=None):
        from rapidocr import RapidOCR, ModelType, OCRVersion
        root = Path(os.getenv('RAPIDOCR_MODEL_DIR', str(Path(__file__).parents[1] / 'model_cache' / 'rapidocr')))
        local_only = os.getenv('MODEL_LOCAL_ONLY', '1') != '0' if local_only is None else local_only
        params = {'Rec.ocr_version': OCRVersion.PPOCRV6, 'Rec.model_type': ModelType.MEDIUM,
                  'Rec.lang_type': 'en', 'Det.ocr_version': OCRVersion.PPOCRV6,
                  'Det.model_type': ModelType.SMALL, 'Global.use_cls': False,
                  'Global.model_root_dir': str(root), 'Global.log_level': 'error',
                  'EngineConfig.onnxruntime.intra_op_num_threads': int(os.getenv('OCR_CPU_THREADS', '2')),
                  'EngineConfig.onnxruntime.inter_op_num_threads': 1}
        if local_only:
            for stage, filename in MODEL_FILES.items():
                path = root / filename
                if not path.is_file():
                    raise RuntimeError('OCR weights are missing. Run python download_model.py before starting the app.')
                params[f'{stage}.model_path'] = str(path)
        self.full_engine = RapidOCR(params=params)
        self.row_engine = RapidOCR(params={**params, 'Det.limit_side_len': 736, 'Det.limit_type': 'max'})
        self.lock = threading.Lock()
        self.local = threading.local()

    def warm_up(self):
        """Load both stages, downloading public weights only when permitted."""
        image = np.full((64, 192, 3), 255, dtype=np.uint8)
        with self.lock:
            self.row_engine(image, use_det=False, use_cls=False)
            self.row_engine(image, use_det=True, use_cls=False, use_rec=True)

    @staticmethod
    def _key(image):
        return (image.size, hashlib.sha256(image.tobytes()).digest())

    def _detect(self, image, full=False):
        if not isinstance(image, np.ndarray):
            image = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2BGR)
        scale = 3
        enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        with self.lock:
            output = (self.full_engine if full else self.row_engine)(
                enlarged, use_det=True, use_cls=False, use_rec=True)
        if output.boxes is None:
            return []
        return [{'text': text, 'confidence': float(score),
                 'x': float(box[:, 0].mean()) / scale, 'y': float(box[:, 1].mean()) / scale}
                for text, score, box in zip(output.txts, output.scores, output.boxes)]

    def prepare(self, layouts):
        from PIL import Image
        self.local.rows = {}
        self.local.context = {}
        for layout in layouts:
            self.local.context[id(layout)] = self._detect(layout.image, full=True)
            for cell in layout.cells:
                image = Image.fromarray(cv2.cvtColor(cell, cv2.COLOR_BGR2RGB))
                self.local.rows[self._key(image)] = self._detect(cell)

    def _lines(self, image):
        cache = getattr(self.local, 'rows', {})
        key = self._key(image)
        return cache[key] if key in cache else self._detect(image)

    def read(self, image, mode='text'):
        lines = sorted(self._lines(image), key=lambda line: (line['y'], line['x']))
        text = ' '.join(line['text'] for line in lines)
        return Reading(clock_text(text) if mode == 'time' else text,
                       min([line['confidence'] for line in lines] + [.79]) if lines else 0, text)

    def _read_line(self, image):
        with self.lock:
            output = self.row_engine(image, use_det=False, use_cls=False)
        return [{'text': text, 'confidence': float(score)} for text, score in zip(output.txts or [], output.scores)]

    def read_status(self, image, ink):
        from .extractor import tight_white
        lines = self._lines(image)
        reading = self.read(image)
        if re.sub(r'[^a-z]', '', reading.text.lower()) == 'off':
            return reading
        if any(clock_text(line['text']) for line in lines):
            reading.has_clock=True
            return reading
        # A large single OFF word can be missed by the text detector. Try the
        # whole cleaned word only when detection found no valid clock reading.
        words = self._read_line(tight_white(ink))
        if len(words) == 1 and words[0]['text'].strip().lower() == 'off' and words[0]['confidence'] >= .8:
            return Reading('off', .79, words[0]['text'])
        return reading

    def read_punches(self, layout, day, punches):
        from PIL import Image
        from .extractor import clean_ink, photo_punch_crops
        cell = layout.cells[day]
        image = Image.fromarray(cv2.cvtColor(cell, cv2.COLOR_BGR2RGB))
        row = self._lines(image)
        context = self.local.context[id(layout)]
        originals = None
        values = []
        start = round(120 + day * 600 / 7)
        end = round(120 + (day + 1) * 600 / 7)
        for index in range(2):
            padding=getattr(layout,'cell_padding',0)
            row_height=cell.shape[0]-2*padding
            groups = [('row', [line for line in row if padding-3<=line['y']<padding+row_height*.64
                              and (line['y'] < padding+26) == (index == 0)]),
                      ('card', [line for line in context if line['x'] > 198 and start <= line['y'] < end
                                and line['y']-start<(end-start)*.64
                                and ((line['y'] - start) < 26) == (index == 0)])]
            reading = choose_reading(groups)
            if not reading.text:
                if originals is None:
                    originals = photo_punch_crops(cell, clean_ink(cell))
                groups.append(('original_punch', self._read_line(originals[index])))
                reading = choose_reading(groups)
            if not reading.text:
                groups.append(('cleaned_punch', self._read_line(punches[index])))
                reading = choose_reading(groups)
            values.append(reading)
        return values
