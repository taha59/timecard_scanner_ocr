import base64
from io import BytesIO
from pathlib import Path
import cv2
from PIL import Image
from backend import extractor,device_ocr
from backend.recognizer import UnavailableRecognizer


def layout():
    return extractor.detect_cards(cv2.imread(str(Path(__file__).parents[1]/'fixtures/october-single.jpg')))[0]


def pixels(data):
    with Image.open(BytesIO(base64.b64decode(data.split(',',1)[1]))) as image:
        return image.size,image.convert('RGB').tobytes()


def test_fast_task_png_preserves_pixels_and_task_id():
    card=layout();image=Image.fromarray(cv2.cvtColor(card.cells[0],cv2.COLOR_BGR2RGB))
    collector=device_ocr.DeviceRecognizer();collector.read(image,'time')
    task=next(iter(collector.tasks.values()))
    assert task['id']==collector._key(image,'time')
    assert pixels(task['image'])==pixels(extractor.png_data(image))
    # Full cards carried back to the API keep normal compression.
    assert device_ocr.pack_layouts([card])==[extractor.png_data(card.image)]


def test_collector_reuses_prepared_punches_only_within_request(monkeypatch):
    card=layout();calls=[];original=device_ocr.focused_punch_crops
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(device_ocr,'focused_punch_crops',counted)
    collector=device_ocr.DeviceRecognizer();collector.prepare([card])
    assert len(calls)==7
    punches=extractor.punch_crops(extractor.clean_ink(card.cells[0]))
    collector.read_punches(card,0,punches)
    assert len(calls)==7
    # A fresh request/collector must not reuse another scan's preparation.
    device_ocr.DeviceRecognizer().prepare([card])
    assert len(calls)==14


def test_device_collection_does_not_encode_discarded_review_images(monkeypatch):
    card=layout()
    def forbidden(*args,**kwargs):raise AssertionError('Discarded previews must not be PNG encoded')
    monkeypatch.setattr(extractor,'png_data',forbidden)
    collector=device_ocr.DeviceRecognizer()
    cards=extractor.extract(None,collector,layouts=[card],include_images=False)
    assert collector.tasks
    assert cards[0]['image']==''
    assert all(day['image']=='' and day['note_image']=='' and day['punch_images']==[] for day in cards[0]['days'])


def test_normal_extraction_keeps_visible_source_images():
    cards=extractor.extract(None,UnavailableRecognizer(),layouts=[layout()])
    assert cards[0]['image'].startswith('data:image/png;base64,')
    assert all(day['image'].startswith('data:image/png;base64,') for day in cards[0]['days'])
