"""Real-photo geometry and versioned replay; fixed text tests plumbing only."""
from io import BytesIO
from pathlib import Path
import cv2
import pytest
from backend.app import create_app
from backend.crop_policy import crop_policy, LEGACY_CROPS, ROBUST_CROPS
from backend.device_ocr import DeviceRecognizer
from backend.extractor import detect_cards, extract, clean_ink, photo_punch_crops

FIXTURES=Path(__file__).parents[1]/'fixtures'


def test_crop_version_selection_is_explicit():
    assert crop_policy() is LEGACY_CROPS
    assert crop_policy('1') is LEGACY_CROPS
    assert crop_policy(2) is ROBUST_CROPS
    for value in [True,False,2.0,[],{},'unknown']:
        with pytest.raises(ValueError):crop_policy(value)


def test_versioned_tasks_replay_on_a_new_server():
    client=create_app().test_client()
    response=client.post('/api/scan',data={'image':(BytesIO((FIXTURES/'october-single.jpg').read_bytes()),'card.jpg'),
                                        'device':'true','live':'true','crop_version':'2'})
    assert response.status_code==200
    job=response.json
    assert job['crop_version']==2 and len(job['card_tasks'])==1
    # OCR accuracy is measured separately with real browser inference.
    readings={task['id']:{'text':'OFF','confidence':.9} for task in job['tasks']}
    body={'layouts':job['layouts'],'readings':readings,'crop_version':job['crop_version']}
    checked=create_app().test_client().post('/api/device-result',json=body)
    assert checked.status_code==200
    assert all(day['status']=='off' for day in checked.json['cards'][0]['days'])
    body['crop_version']=99
    assert client.post('/api/device-result',json=body).status_code==400


def test_source_layout_and_review_images_do_not_change_with_crop_version():
    layouts=detect_cards(cv2.imread(str(FIXTURES/'october-single.jpg')))
    before=extract(None,DeviceRecognizer(),layouts=layouts,include_notes=False)
    after=extract(None,DeviceRecognizer(crop_policy=ROBUST_CROPS),layouts=layouts,include_notes=False)
    assert [c['image'] for c in before]==[c['image'] for c in after]
    assert [d['image'] for c in before for d in c['days']]==[d['image'] for c in after for d in c['days']]


@pytest.mark.parametrize('original,wide,expected',[
    ('1:45pm','11:45pm','11:45pm'),
    ('1:45pm','11:40pm','1:45pm'),
    ('6:35pm','5:35pm','6:35pm'),
    ('unreadable','10:10pm','10:10pm'),
])
def test_wider_photo_only_fills_missing_or_restores_matching_leading_one(original,wide,expected):
    from dataclasses import replace
    from backend.extractor import punch_crops, focused_punch_crops
    card=detect_cards(cv2.imread(str(FIXTURES/'october-single.jpg')))[0]
    cell=card.cells[0];ink=clean_ink(cell)
    collector=DeviceRecognizer(crop_policy=ROBUST_CROPS)
    punches=punch_crops(ink,ROBUST_CROPS)
    collector.read_punches(card,0,punches)
    readings={key:{'text':'unreadable','confidence':.7} for key in collector.tasks}
    originals=photo_punch_crops(cell,ink,ROBUST_CROPS)
    focused=focused_punch_crops(cell,ink,ROBUST_CROPS)
    wider=photo_punch_crops(cell,ink,replace(ROBUST_CROPS,preserve_original_width=True,original_out_limit=.52))
    for image in [originals[0],punches[0],focused[0]]:
        readings[collector._key(image,'time')]={'text':original,'confidence':.7}
    readings[collector._key(wider[0],'time')]={'text':wide,'confidence':.7}
    result=DeviceRecognizer(readings,crop_policy=ROBUST_CROPS).read_punches(card,0,punches)
    assert result[0].text==expected
