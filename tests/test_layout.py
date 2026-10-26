from pathlib import Path
import json
import cv2
import numpy as np
import pytest
from backend.extractor import detect_cards,classify_ink,extract,punch_crops
from backend.recognizer import Reading

ROOT=Path(__file__).parents[1]
class FakeRecognizer:
    def __init__(self): self.calls=[]
    def read(self,image,mode='text'):
        self.calls.append((image.size,mode))
        return Reading('10:00' if mode=='time' else '?',.1)

def test_sample_layout_and_every_cell():
    im=cv2.imread(str(ROOT/'fixtures/timecards.jpg')); cards=detect_cards(im)
    truth=json.loads((ROOT/'fixtures/ground_truth.json').read_text())
    assert len(cards)==5
    for card,expected in zip(cards,truth):
        assert len(card.cells)==7
        for cell,punch in zip(card.cells,expected['punches']):
            status,fraction,ink=classify_ink(cell)
            assert cell.shape[0]>=80 and cell.shape[1]==108
            if isinstance(punch,list): assert status=='worked', (expected['name'],punch,fraction)
            if punch=='blank': assert status=='blank'
            if punch=='off': assert status!='blank'
            assert len(punch_crops(ink))==2

def test_fake_recognizer_sample_no_download(tmp_path,monkeypatch):
    monkeypatch.setenv('DEBUG_CROPS_DIR',str(tmp_path))
    fake=FakeRecognizer();cards=extract(cv2.imread(str(ROOT/'fixtures/timecards.jpg')),fake)
    assert len(cards)==5 and sum(len(c['days']) for c in cards)==35
    assert len(list(tmp_path.glob('*_ink.png')))==35
    assert all(not d['adjustment_confirmed'] for c in cards for d in c['days'])
    assert all(d['status_guessed'] for c in cards for d in c['days'])
    assert any(mode=='time' for _,mode in fake.calls)

def test_detection_resized_and_rotated():
    image=cv2.imread(str(ROOT/'fixtures/timecards.jpg'))
    for scale in [.6,1.5]:
        resized=cv2.resize(image,None,fx=scale,fy=scale)
        assert len(detect_cards(resized))==5
    mat=cv2.getRotationMatrix2D((800,450),2,1)
    assert len(detect_cards(cv2.warpAffine(image,mat,(1600,900),borderValue=(255,255,255))))==5


@pytest.mark.parametrize('filename,expected',[('october-group.jpg',7),('october-single.jpg',1)])
@pytest.mark.parametrize('scale',[.6,1,1.5])
def test_crisp_green_rules_do_not_hide_or_duplicate_cards(filename,expected,scale):
    image=cv2.imread(str(ROOT/'fixtures'/filename))
    cards=detect_cards(cv2.resize(image,None,fx=scale,fy=scale))
    assert len(cards)==expected
    assert all(len(card.cells)==7 for card in cards)
    assert all(cell.shape[0]>=80 and cell.shape[1]==108 for card in cards for cell in card.cells)


def test_single_card_grid_starts_before_first_punch():
    image=cv2.imread(str(ROOT/'fixtures'/'october-single.jpg'))
    card=detect_cards(image)[0]
    # The first punch must remain in the upper part of day 1, with its tall
    # digits intact. Previously the fallback began at the first filled OUT
    # box and cropped the IN line at the upper cell boundary.
    ink=classify_ink(card.cells[0])[2]
    assert np.count_nonzero(ink[7:22])>30
    assert np.count_nonzero(ink[26:45])>30


@pytest.mark.parametrize('name,count',[('timecards',5),('october-group',7),
                                      ('october-single',1),('novel-five-cards',5)])
@pytest.mark.parametrize('transform',['shrink','enlarge','rotate','perspective'])
def test_measured_grid_generalizes_to_transformed_photos(name,count,transform):
    image=cv2.imread(str(ROOT/'fixtures'/f'{name}.jpg'))
    h,w=image.shape[:2]
    if transform in {'shrink','enlarge'}:
        scale=.6 if transform=='shrink' else 1.5
        image=cv2.resize(image,None,fx=scale,fy=scale)
    elif transform=='rotate':
        image=cv2.warpAffine(image,cv2.getRotationMatrix2D((w/2,h/2),2,1),(w,h),borderValue=(255,255,255))
    else:
        source=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
        target=np.float32([[w*.03,h*.03],[w*.94,0],[w-1,h*.94],[0,h-1]])
        image=cv2.warpPerspective(image,cv2.getPerspectiveTransform(source,target),(w,h),borderValue=(255,255,255))
    cards=detect_cards(image)
    assert len(cards)==count
    for card in cards:
        assert len(card.source_grid)==8
        assert np.all(np.diff(card.source_grid)>0)
        assert card.cell_padding>=6


def test_first_in_word_is_fully_inside_crop_and_separate_from_out():
    card=detect_cards(cv2.imread(str(ROOT/'fixtures'/'novel-five-cards.jpg')))[0]
    # Independently annotated source-image extents of Employee 01's first two words.
    # The old heuristic started the crop below y=257, chopping off the IN word.
    canonical=np.interp([257,269,275,286],card.source_grid,np.linspace(120,720,8))
    positions=canonical-120+card.cell_padding
    assert 0<=positions[0]<positions[1]<card.cell_padding+26
    assert 0<=positions[2]<positions[3]<card.cells[0].shape[0]
    assert np.mean(positions[2:])>card.cell_padding+26


def test_ocr_clock_evidence_overrides_low_ink_off_guess(monkeypatch):
    import backend.extractor as module
    class ClockReader(FakeRecognizer):
        def read_status(self,image,ink):
            return Reading('9:00am 5:00pm',.79,has_clock=True)
    monkeypatch.setattr(module,'classify_ink',lambda cell:('off',.02,module.clean_ink(cell)))
    cards=extract(cv2.imread(str(ROOT/'fixtures'/'timecards.jpg')),ClockReader())
    assert all(day['status']=='worked' and day['in'] and day['out'] for card in cards for day in card['days'])


def test_unreadable_ink_is_unknown_not_an_automatic_off_zero():
    from backend.recognizer import UnavailableRecognizer
    cards=extract(cv2.imread(str(ROOT/'fixtures'/'timecards.jpg')),UnavailableRecognizer())
    assert all(day['status'] in {'unknown','blank'} for card in cards for day in card['days'])


def test_unverified_green_rectangle_cannot_create_an_estimated_grid():
    image=np.full((700,500,3),255,dtype=np.uint8)
    cv2.rectangle(image,(240,110),(265,620),(60,145,70),-1)
    with pytest.raises(ValueError,match='align the seven printed day rows'):
        detect_cards(image)
