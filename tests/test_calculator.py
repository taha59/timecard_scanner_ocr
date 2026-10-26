import json
from pathlib import Path
from copy import deepcopy
import pytest
from backend.calculator import (parse_time, normalize_time, calculate_day, calculate_card,
                                written_total_candidates, adjustment_minutes)

GROUND = json.loads((Path(__file__).parents[1] / 'fixtures/ground_truth.json').read_text())

def card_from_truth(truth):
    days = []
    for index, punch in enumerate(truth['punches']):
        day = {'label': f'Day {index+1}', 'adjustment_hours': truth['adjustments'].get(str(index), '0')}
        day.update({'status':'worked', 'in':punch[0], 'out':punch[1]} if isinstance(punch,list) else {'status':punch})
        days.append(day)
    return {'name':truth['name'], 'days':days, 'written_total':truth.get('written_total','')}

@pytest.mark.parametrize('truth', GROUND, ids=lambda t:t['name'])
def test_ground_truth_totals(truth):
    result = calculate_card(card_from_truth(truth))
    assert result['totals']['regular']['hm'] == truth['regular']
    assert result['totals']['grand']['hm'] == truth['grand']
    if truth['name'] == 'Employee 08':
        assert 'mismatch' in result['cross_check']['message']
        assert [c['difference']['hm'] for c in result['cross_check']['candidates']] == ['0:05','0:08']

@pytest.mark.parametrize('written', ['', '0', '999:59', '27.07', 'unreadable', '51:53', '25:22 hrs'])
def test_written_total_never_changes_computation(written):
    card = card_from_truth(GROUND[0])
    before = calculate_card(card)
    card['written_total'] = written
    after = calculate_card(card)
    assert before['totals'] == after['totals']
    assert before['days'] == after['days']

@pytest.mark.parametrize('raw,minutes,explicit', [('10:10 a.m.',610,True),('8:0pm',1200,True),('I0;I0',610,False),('12:00am',0,True),('12:00 pm',720,True),('O8.05',485,False)])
def test_parser(raw, minutes, explicit):
    assert parse_time(raw) == (minutes,explicit)

@pytest.mark.parametrize('raw', ['garbage','10:60','25:00','0:30am','13:00pm','+2 storage','10:10+1','nan'])
def test_parser_rejects_bad_times(raw):
    with pytest.raises(ValueError): parse_time(raw)

@pytest.mark.parametrize('start,end,hm,flag', [('11:49','6:15','6:26','AM/PM inferred'),('8:00pm','6:00am','10:00',None),('6:00am','8:00pm','14:00','Shift over 12 hours'),('8:00','8:00','0:00','Zero-length'),('11:00am','1:00','2:00','AM/PM inferred')])
def test_duration(start,end,hm,flag):
    result=calculate_day({'status':'worked','in':start,'out':end})
    assert result['computed']['hm']==hm
    if flag: assert any(flag in f for f in result['flags'])

@pytest.mark.parametrize('status', ['off','blank','crossed_out'])
def test_excluded_status(status):
    result=calculate_day({'status':status})
    assert result['computed']['minutes']==0
    assert bool(result['flags'])==(status=='crossed_out')

@pytest.mark.parametrize('day', [{'status':'worked','in':'9:00'}, {'status':'worked','in':'?','out':'5:00'}, {'status':'unknown'}])
def test_unresolved_is_not_zero(day):
    card=card_from_truth(GROUND[0]); card['days'][0]=day
    result=calculate_card(card)
    assert result['days'][0]['computed']['minutes'] is None
    assert result['totals']['grand']['minutes'] is None
    assert not result['totals']['complete']


def test_low_confidence_and_purity():
    card=card_from_truth(GROUND[0]); card['days'][0]['confidence']=.2
    saved=deepcopy(card); result=calculate_card(card)
    assert card==saved
    assert 'Low OCR confidence' in ' '.join(result['days'][0]['flags'])

@pytest.mark.parametrize('raw,minutes', [('1',60),('+2',120),('1.5',90),('-0:30',-30),('0.125',8),('0',0)])
def test_adjustment(raw,minutes): assert adjustment_minutes(raw)==minutes

@pytest.mark.parametrize('raw', ['nan','inf','+2 storage','1:60','1001',''])
def test_bad_adjustment(raw):
    with pytest.raises(ValueError): adjustment_minutes(raw)


def test_unconfirmed_note_not_added():
    card=card_from_truth(GROUND[2]); card['days'][0]['adjustment_confirmed']=False
    result=calculate_card(card)
    assert result['totals']['regular']['hm']=='25:12'
    assert result['totals']['grand']['minutes'] is None


def test_normalization(): assert normalize_time(' 10:10 A. M. ' )=='10:10am'


def test_seven_days_required():
    with pytest.raises(ValueError): calculate_card({'days':[]})


@pytest.mark.parametrize('raw,expected',[('10.10.',(610,False)),('5.10 .',(310,False)),('10:10 a.m.',(610,True))])
def test_terminal_punctuation(raw,expected):assert parse_time(raw)==expected
