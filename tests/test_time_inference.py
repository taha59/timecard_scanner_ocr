"""Policy examples and real-photo replay plumbing; no synthetic OCR accuracy claims."""
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import pytest
from backend.time_inference import DEFAULT_POLICY, infer_time_pair
from backend.calculator import calculate_day, calculate_card
from backend.app import create_app


@pytest.mark.parametrize('start,end,expected_start,expected_end,minutes',[
    ('9:00','5:00','9:00am','5:00pm',480),
    ('3:15','11:40','3:15pm','11:40pm',505),
    ('11:00','2:00','11:00am','2:00pm',180),
    ('9:00am','10:35','9:00am','10:35pm',815),
    ('8:55','11:45','8:55am','11:45pm',890),
    ('12:00','5:00','12:00pm','5:00pm',300),
    ('7:00pm','10:00','7:00pm','10:00pm',180),
    ('9:00','13:00','9:00am','13:00',240),
    ('13:00','23:59','13:00','23:59',659),
])
def test_schedule_pair_examples(start,end,expected_start,expected_end,minutes):
    result=infer_time_pair(start,end)
    assert (result.start,result.end,result.minutes)==(expected_start,expected_end,minutes)
    assert not result.conflict


@pytest.mark.parametrize('raw,suffix',[
    ('9:00a','am'),('9:00 A.','am'),('9:00 p','pm'),(' 9:00 P. ','pm'),
    ('9:00 p.m.','pm'),('9:00a m','am'),('O9:OOa','am'),
])
def test_selected_raw_suffix_is_stronger_than_schedule(raw,suffix):
    result=infer_time_pair('9:00','10:00pm',raw_start=raw)
    assert result.start=='9:00'+suffix
    assert result.annotations['in']['source'] in {'partial_suffix','raw_suffix'}
    assert 'schedule' not in result.annotations['in']['source']


@pytest.mark.parametrize('value,expected',[('9:00a','9:00am'),('9:00 A.','9:00am'),('4:30p','4:30pm')])
def test_partial_suffix_typed_in_field(value,expected):
    result=infer_time_pair(value,'11:00pm')
    assert result.start==expected
    assert result.annotations['in']['source']=='partial_suffix'


@pytest.mark.parametrize('raw',['a 9:00','9:00 apple','9:00 p total','4:00p','9:00a 10:00p','10/19/26','9:00a1'])
def test_unrelated_letters_different_times_and_multiple_clocks_are_not_suffix_evidence(raw):
    result=infer_time_pair('9:00','5:00',raw_start=raw)
    assert result.start=='9:00am'
    assert result.annotations['in']['source']=='schedule'


@pytest.mark.parametrize('start,end',[
    ('9:00pm','10:00pm'),('9:00AM','5:00PM'),('11:00pm','2:00am'),('9:00am','10:00am'),
])
def test_complete_suffixes_are_never_rewritten(start,end):
    result=infer_time_pair(start,end,raw_start='9:00a',raw_end='5:00p')
    assert result.start==start and result.end==end
    assert not result.annotations


def test_impossible_pair_is_not_turned_into_overnight_pay():
    day={'in':'11:00pm','out':'2:00am'}
    result=calculate_day(day,punch_only=True,time_policy=DEFAULT_POLICY)
    assert result['in']=='11:00pm' and result['out']=='2:00am'
    assert result['computed']['minutes'] is None
    assert any('same-day' in flag for flag in result['flags'])
    card={'days':[day]+[{'in':'','out':''} for _ in range(6)]}
    assert calculate_card(card,punch_only=True,time_policy=DEFAULT_POLICY)['totals']['regular']['minutes']==0


def test_missing_suffix_cannot_override_explicit_or_partial_overnight_conflict():
    result=infer_time_pair('11:00pm','2:00')
    assert result.conflict and result.end=='2:00'
    result=infer_time_pair('9:00','5:00',raw_start='9:00p',raw_end='5:00p')
    assert result.conflict and result.start=='9:00pm' and result.end=='5:00pm'


@pytest.mark.parametrize('value',['','?','OFF','1140','9:65','13:00p'])
def test_policy_never_fills_missing_or_invalid_clock_digits(value):
    result=infer_time_pair(value,'5:00pm',raw_start='9:00a')
    assert result.start==value and not result.annotations


def test_policy_rules_can_be_disabled_or_changed_independently():
    disabled=infer_time_pair('9:00','5:00',raw_start='9:00p',policy=replace(DEFAULT_POLICY,enabled=False))
    assert (disabled.start,disabled.end,disabled.annotations)==('9:00','5:00',{})
    no_schedule=infer_time_pair('9:00','5:00',policy=replace(DEFAULT_POLICY,schedule_biases=False))
    assert (no_schedule.start,no_schedule.end)==('9:00','5:00')
    partial_only=infer_time_pair('9:00a','5:00p',policy=replace(DEFAULT_POLICY,schedule_biases=False))
    assert partial_only.minutes==480
    no_partial=infer_time_pair('9:00','10:00pm',raw_start='9:00p',policy=replace(DEFAULT_POLICY,partial_suffixes=False))
    assert no_partial.start=='9:00am' and no_partial.annotations['in']['source']=='schedule'
    morning_end=infer_time_pair('9:00','10:00',policy=replace(DEFAULT_POLICY,preferred_out_suffix='am'))
    assert morning_end.end=='10:00am'
    early_close=infer_time_pair('9:00am','11:00pm',policy=replace(DEFAULT_POLICY,latest_out_minute=22*60))
    assert early_close.conflict
    overnight=infer_time_pair('11:00pm','2:00am',policy=replace(DEFAULT_POLICY,same_day_only=False))
    assert not overnight.conflict and overnight.minutes==180


def test_recalculation_preserves_provenance_and_ignores_stale_raw_ocr():
    day={'in':'9:00','out':'10:00pm','raw_in':'9:00p'};original=deepcopy(day)
    first=calculate_day(day,punch_only=True,time_policy=DEFAULT_POLICY,use_ocr_evidence=True)
    assert first['in']=='9:00pm' and first['computed']['minutes']==60
    assert first['time_inference']['in']['source']=='partial_suffix'
    again=calculate_day(first,punch_only=True,time_policy=DEFAULT_POLICY)
    assert first==again and day==original
    # A user has changed the field and cleared its old annotation.
    edited={**first,'in':'9:00','time_inference':{}}
    result=calculate_day(edited,punch_only=True,time_policy=DEFAULT_POLICY)
    assert result['in']=='9:00am' and result['computed']['minutes']==780
    assert result['time_inference']['in']['source']=='schedule'


def test_written_totals_never_drive_suffix_selection():
    card={'written_total':'13:35','days':[{'in':'9:00','out':'10:35'}]+[{'in':'','out':''} for _ in range(6)]}
    before=calculate_card(card,punch_only=True,time_policy=DEFAULT_POLICY)
    card['written_total']='1:35'
    after=calculate_card(card,punch_only=True,time_policy=DEFAULT_POLICY)
    assert before['days']==after['days'] and before['totals']==after['totals']
    assert before['totals']['regular']['hm']=='13:35'


def test_api_policy_can_be_disabled_with_one_environment_flag(monkeypatch):
    card={'days':[{'in':'9:00','out':'10:35'}]+[{'in':'','out':''} for _ in range(6)]}
    client=create_app().test_client()
    enabled=client.post('/api/calculate',json={'cards':[card]}).json['cards'][0]
    assert enabled['totals']['regular']['hm']=='13:35'
    monkeypatch.setenv('TIME_INFERENCE_ENABLED','false')
    disabled=create_app().test_client().post('/api/calculate',json={'cards':[card]}).json['cards'][0]
    assert disabled['days'][0]['in']=='9:00' and disabled['days'][0]['out']=='10:35'
    assert disabled['totals']['regular']['hm']=='1:35'


def test_real_photo_device_replay_uses_partial_raw_evidence_and_preserves_images():
    from backend.device_ocr import DeviceRecognizer,unpack_layouts
    from backend.extractor import clean_ink,photo_punch_crops
    client=create_app().test_client()
    photo=(Path(__file__).parents[1]/'fixtures/october-single.jpg').read_bytes()
    job=client.post('/api/scan',data={'device':'true','live':'true','image':(BytesIO(photo),'card.jpg')}).json
    layout=unpack_layouts(job['layouts'])[0]
    punches=photo_punch_crops(layout.cells[0],clean_ink(layout.cells[0]))
    readings={t['id']:{'text':'unreadable','confidence':.2} for t in job['tasks']}
    readings[DeviceRecognizer._key(punches[0],'time')]={'text':'10:25a','confidence':.7}
    readings[DeviceRecognizer._key(punches[1],'time')]={'text':'10:00p','confidence':.7}
    result=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings})
    assert result.status_code==200
    card=result.json['cards'][0];day=card['days'][0]
    assert (day['in'],day['out'],day['computed']['hm'])==('10:25am','10:00pm','11:35')
    assert day['raw_in']=='10:25a' and day['raw_out']=='10:00p'
    assert day['time_inference']['out']['source']=='partial_suffix'
    assert card['image']==job['layouts'][0] and day['image'].startswith('data:image/png;base64,')
