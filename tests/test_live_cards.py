from io import BytesIO
from pathlib import Path
import pytest
from backend.app import create_app


@pytest.mark.parametrize('photo',['october-single.jpg','novel-five-cards.jpg','timecards.jpg','october-group.jpg'])
def test_live_groups_keep_existing_tasks_and_individual_results(photo):
    # Fixed clock readings exercise grouping/replay, not OCR accuracy.
    client=create_app().test_client()
    image=(Path(__file__).parents[1]/'fixtures'/photo).read_bytes()
    def prepare(live):
        response=client.post('/api/scan',data={'device':'true','live':live,'image':(BytesIO(image),photo)})
        assert response.status_code==200
        return response.json
    legacy=prepare('false');job=prepare('true')
    assert legacy=={key:job[key] for key in ['layouts','tasks']}
    assert len(job['card_tasks'])==len(job['layouts'])
    assert set().union(*map(set,job['card_tasks']))=={t['id'] for t in job['tasks']}
    readings={t['id']:{'text':'9:00am','confidence':.79} for t in job['tasks']}
    all_cards=client.post('/api/device-result',json={'layouts':job['layouts'],'readings':readings}).json['cards']
    for index,(layout,ids) in enumerate(zip(job['layouts'],job['card_tasks'])):
        result=client.post('/api/device-result',json={'layouts':[layout],'readings':{key:readings[key] for key in ids}})
        assert result.status_code==200,result.json
        card=result.json['cards'][0];card['id']=str(index)
        assert card==all_cards[index]
    assert client.get('/api/health').json['ocr_loaded'] is False
