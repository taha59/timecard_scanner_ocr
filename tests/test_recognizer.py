import numpy as np
import pytest

from backend.ocr_common import clock_text
from backend.extractor import punch_crops
from backend.recognizer import time_token_trie


def test_default_reader_is_portable_on_every_os(monkeypatch):
    import backend.recognizer as module
    sentinel = object()
    monkeypatch.delenv('OCR_ENGINE', raising=False)
    import backend.rapid_recognizer as rapid
    monkeypatch.setattr(rapid, 'RapidOCRRecognizer', lambda local_only=None: sentinel)
    assert module.create_recognizer() is sentinel


@pytest.mark.parametrize('engine',['vision','unknown'])
def test_unsupported_reader_is_rejected(monkeypatch,engine):
    import backend.recognizer as module
    monkeypatch.setenv('OCR_ENGINE',engine)
    with pytest.raises(ValueError,match='auto, rapidocr, or trocr'):
        module.create_recognizer()


def test_ocr_conflicts_keep_provenance_and_prefer_original_row():
    from backend.rapid_recognizer import choose_reading
    value = choose_reading([
        ('row', [{'text': '11:00am', 'confidence': .82}]),
        ('card', [{'text': '1:00am', 'confidence': .98}]),
    ])
    assert value.text == '11:00am' and value.conflict
    assert value.raw_text == '11:00am'
    assert len(value.alternatives) == 2
    assert value.confidence < .8


def test_ambiguous_punches_remain_unresolved_without_repairing_digits():
    from backend.rapid_recognizer import choose_reading
    value = choose_reading([('row', [{'text': '10:350m', 'confidence': .99}])])
    assert value.text == '' and value.raw_text == '10:350m'
    assert value.alternatives[0]['value'] == ''


def test_am_pm_disagreement_is_flagged_even_when_clock_digits_agree():
    from backend.rapid_recognizer import choose_reading
    value=choose_reading([
        ('row',[{'text':'9:00pm','confidence':.95}]),
        ('card',[{'text':'9:00am','confidence':.99}]),
    ])
    assert value.conflict


def test_multiple_clock_readings_in_one_band_do_not_pick_arbitrarily():
    from backend.rapid_recognizer import choose_reading
    value = choose_reading([('row', [{'text': '9:45', 'confidence': .99},
                                    {'text': '6:00', 'confidence': .99}])])
    assert value.text == '' and value.conflict


def test_offline_reader_requires_cached_weights(tmp_path, monkeypatch):
    from backend.rapid_recognizer import RapidOCRRecognizer
    monkeypatch.setenv('RAPIDOCR_MODEL_DIR', str(tmp_path))
    with pytest.raises(RuntimeError, match='download_model.py'):
        RapidOCRRecognizer(local_only=True)


def test_detection_resets_mode_after_recognition_only_fallback():
    from types import SimpleNamespace
    import threading
    from backend.rapid_recognizer import RapidOCRRecognizer
    class Engine:
        def __init__(self):
            self.detect = False
        def __call__(self, image, **kwargs):
            self.detect = kwargs.get('use_det', self.detect)
            assert self.detect, 'Previous recognition-only call left detection disabled'
            return SimpleNamespace(boxes=None)
    reader = RapidOCRRecognizer.__new__(RapidOCRRecognizer)
    reader.lock = threading.Lock()
    reader.row_engine = Engine()
    assert reader._detect(np.full((85, 108, 3), 255, dtype=np.uint8)) == []


def test_off_word_fallback_never_overrides_detected_clock():
    from backend.rapid_recognizer import RapidOCRRecognizer
    from backend.recognizer import Reading
    reader = RapidOCRRecognizer.__new__(RapidOCRRecognizer)
    reader._lines = lambda image: [{'text': '10:10', 'confidence': .99}]
    reader.read = lambda image: Reading('10:10', .79)
    def unexpected(image):
        raise AssertionError('Do not try a word-only classifier on detected work')
    reader._read_line = unexpected
    assert reader.read_status(None, None).text == '10:10'


def test_off_word_fallback_requires_exact_word_and_high_confidence():
    from backend.rapid_recognizer import RapidOCRRecognizer
    from backend.recognizer import Reading
    reader = RapidOCRRecognizer.__new__(RapidOCRRecognizer)
    reader._lines = lambda image: []
    reader.read = lambda image: Reading('', 0)
    ink = np.zeros((85, 108), dtype=np.uint8)
    for raw, confidence, expected in [('OFE', .99, ''), ('off', .4, ''), ('off', .96, 'off')]:
        reader._read_line = lambda image: [{'text': raw, 'confidence': confidence}]
        assert reader.read_status(None, ink).text == expected


def test_daily_written_duration_below_punches_is_not_an_out_candidate():
    from types import SimpleNamespace
    from backend.rapid_recognizer import RapidOCRRecognizer
    reader=RapidOCRRecognizer.__new__(RapidOCRRecognizer)
    layout=SimpleNamespace(cells=[np.zeros((85,108,3),dtype=np.uint8)])
    reader.local=SimpleNamespace(context={id(layout):[]})
    reader._lines=lambda image:[
        {'text':'9:00am','confidence':.99,'y':14},
        {'text':'5:05pm','confidence':.99,'y':35},
        {'text':'8:05','confidence':.99,'y':72},
    ]
    values=reader.read_punches(layout,0,[])
    assert [value.text for value in values]==['9:00am','5:05pm']
    assert all(item['raw']!='8:05' for item in values[1].alternatives)


@pytest.mark.parametrize('raw,expected', [
    ('10:10 an', '10:10'), ('8:00p.m', '8:00pm'),
    ('11:49', '11:49'), ('6:00_', '6:00'), ('4:05', '4:05'),
    ('3:000-pa', ''), ('8:• 2 Pm', ''), ('9145', ''),
    ('9:95', ''), ('off', ''), ('1:18 5:10', ''),
    ('5:0SPM', '5:05pm'), ('S:50', '5:50'), ('hours', ''),
])
def test_ocr_clock_prefix_without_inventing_digits(raw, expected):
    assert clock_text(raw) == expected


def test_split_keeps_tall_first_line_out_of_second_crop():
    ink = np.zeros((85, 108), dtype=np.uint8)
    ink[6:23, 20:40] = 255
    ink[28:45, 60:80] = 255
    first, second = punch_crops(ink)
    # Both isolated lines have the same geometry. A midpoint between peaks
    # would cut the first line and carry its remaining strokes into OUT.
    def dark_bounds(image):
        ys, xs = np.where(np.asarray(image.convert('L')) < 128)
        return (xs.max() - xs.min(), ys.max() - ys.min())
    assert dark_bounds(first) == dark_bounds(second) == (59, 50)


def test_time_grammar_rejects_repeated_digits_and_invalid_minutes():
    class CharacterTokenizer:
        eos_token_id = -1
        def encode(self, text, add_special_tokens=False):
            return list(map(ord, text))
    trie = time_token_trie(CharacterTokenizer())
    def accepts(text):
        node = trie
        for token in list(map(ord, text)) + [-1]:
            if token not in node:
                return False
            node = node[token]
        return True
    assert accepts('10:35') and accepts('8.00 pm')
    assert not accepts('8.000000')
    assert not accepts('9:95')
    assert not accepts('23:10 pm')
