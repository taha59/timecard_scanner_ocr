"""Evaluate real OCR; ground truth is used ONLY here and in tests, never extraction."""
import argparse
import json
from pathlib import Path
import sys
import cv2
from backend.extractor import extract
from backend.recognizer import create_recognizer
from backend.calculator import calculate_cards,parse_time


def same_time(a,b):
    try:return parse_time(a)[0]%720 == parse_time(b)[0]%720
    except (ValueError,TypeError):return False


def evaluate(cards,truth):
    counts={'status_correct':0,'status_total':0,'punch_correct':0,'punch_total':0,'regular_totals_matching':0,'grand_totals_matching':0,'cards_expected':len(truth),'cards_detected':len(cards)}
    for ci,t in enumerate(truth):
        card=cards[ci] if ci<len(cards) else {'days':[],'totals':{}}
        print(f"\n{t['name']} / OCR name: {card.get('name','MISSING CARD')}")
        for di,expected in enumerate(t['punches']):
            if di in t.get('exclude_scoring',[]):
                print(f'  Day {di+1}: excluded (crossed out)');continue
            got=card['days'][di] if di<len(card['days']) else {}
            status='worked' if isinstance(expected,list) else expected
            counts['status_total']+=1;counts['status_correct']+=got.get('status')==status
            if isinstance(expected,list):
                counts['punch_total']+=2
                counts['punch_correct']+=same_time(got.get('in'),expected[0])+same_time(got.get('out'),expected[1])
            print(f"  Day {di+1}: expected {expected!s:24} got {got.get('status','MISSING')} {got.get('in','')}/{got.get('out','')}")
        totals=card.get('totals',{})
        counts['regular_totals_matching']+=totals.get('regular',{}).get('hm')==t['regular']
        counts['grand_totals_matching']+=totals.get('grand',{}).get('hm')==t['grand']
        print(f"  Regular {totals.get('regular',{}).get('hm')} expected {t['regular']}; grand {totals.get('grand',{}).get('hm')} expected {t['grand']}")
    for kind in ['status','punch']:
        counts[f'{kind}_accuracy']=round(counts[f'{kind}_correct']/counts[f'{kind}_total'],4) if counts[f'{kind}_total'] else None
    print('\n'+json.dumps(counts,indent=2));return counts


def main():
    parser=argparse.ArgumentParser();parser.add_argument('image',nargs='?',default='fixtures/timecards.jpg');parser.add_argument('--download',action='store_true');parser.add_argument('--json-output');args=parser.parse_args()
    truth=json.loads(Path('fixtures/ground_truth.json').read_text())
    try:
        image=cv2.imread(args.image)
        if image is None:raise ValueError('Cannot read image')
        reader=create_recognizer(local_only=not args.download)
        cards=calculate_cards(extract(image,reader)); result=evaluate(cards,truth)
    except Exception as exc:
        result={'evaluation':'NOT RUN','reason':f'{type(exc).__name__}: {exc}'}
        print(json.dumps(result,indent=2))
        if args.json_output:Path(args.json_output).write_text(json.dumps(result,indent=2)+'\n')
        return 2
    if args.json_output:Path(args.json_output).write_text(json.dumps(result,indent=2)+'\n')
    return 0

if __name__=='__main__':sys.exit(main())
