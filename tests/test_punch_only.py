from copy import deepcopy
from backend.calculator import calculate_card
from backend.app import create_app


def card_with(days):
    return {'name':'Example','days':days+[{'in':'','out':''} for _ in range(7-len(days))]}


def test_complete_punches_count_without_status_review_or_adjustments():
    card=card_with([{'status':'off','in':'9:00am','out':'5:00pm','reviewed':False,
                     'source':'ocr','note':'+5','adjustment_hours':'5','adjustment_confirmed':True}])
    original=deepcopy(card)
    result=calculate_card(card,punch_only=True)
    assert result['totals']['regular']['hm']=='8:00'
    assert result['totals']['grand']['hm']=='8:00'
    assert result['totals']['adjustments']['minutes']==0
    assert result['totals']['complete']
    assert not result['days'][0]['flags']
    assert card==original


def test_incomplete_and_invalid_pairs_are_excluded_from_visible_total():
    result=calculate_card(card_with([{'in':'9:00am','out':'5:00pm'},
                                    {'in':'9:00am','out':''},
                                    {'in':'','out':'5:00pm'},
                                    {'in':'nonsense','out':'5:00pm'}]),punch_only=True)
    assert result['totals']['regular']['hm']=='8:00'
    assert result['totals']['grand']['hm']=='8:00'
    assert not result['totals']['complete']
    assert all(day['computed']['minutes'] is None for day in result['days'][1:4])
    assert all(day['computed']['minutes']==0 for day in result['days'][4:])
    assert 'Missing punch' in result['days'][1]['flags']


def test_clearing_and_filling_times_changes_total_without_status_toggle():
    card=card_with([{'status':'blank','in':'9:00pm','out':'5:00am'}])
    assert calculate_card(card,punch_only=True)['totals']['regular']['hm']=='8:00'
    card['days'][0]['in']='';card['days'][0]['out']=''
    assert calculate_card(card,punch_only=True)['totals']['regular']['minutes']==0


def test_api_uses_punch_only_arithmetic():
    client=create_app().test_client()
    card=card_with([{'status':'off','in':'9:00am','out':'5:00pm'}])
    response=client.post('/api/calculate',json={'cards':[card]})
    assert response.status_code==200
    assert response.json['cards'][0]['totals']['regular']['hm']=='8:00'
