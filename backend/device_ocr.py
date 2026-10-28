"""Prepare recognition tasks and combine device readings without server inference."""
import hashlib
import re
from PIL import Image
import cv2
from .recognizer import Reading
from .ocr_common import clock_text,tentative_clock_text
from .extractor import png_data, clean_ink, tight_white, photo_punch_crops, punch_crops, focused_punch_crops, label_edge_punch_crops
from .rapid_recognizer import choose_reading

# Task images prioritize fast, lossless encoding. Full cards and review images
# keep the normal compression level so later request payloads do not grow.
DEVICE_PNG_COMPRESSION=1

class DeviceRecognizer:
    def __init__(self, readings=None):
        self.tasks={}
        self.readings=readings
        self._prepared_punches={}
        self.card_tasks=[]
        self._card_index=None

    def begin_card(self,index):
        self._card_index=index

    def prepare(self,layouts):
        if self.readings is None:
            self._prepared_punches.clear()
            self.card_tasks=[{} for _ in layouts]
            # Even a visually blank row can produce text on the device. Record
            # both punches up front so replay never needs an unprepared task.
            for index,layout in enumerate(layouts):
                self.begin_card(index)
                for day,cell in enumerate(layout.cells):
                    self.read_punches(layout,day,punch_crops(clean_ink(cell)))

    @staticmethod
    def _key(image,mode):
        image=image.convert('RGB')
        return hashlib.sha256(mode.encode()+str(image.size).encode()+image.tobytes()).hexdigest()

    def read(self,image,mode='text',required=True):
        image=image.convert('RGB')
        key=self._key(image,mode)
        if self.readings is None:
            if self._card_index is not None and self._card_index<len(self.card_tasks):
                self.card_tasks[self._card_index][key]=None
            if key not in self.tasks:self.tasks[key]={'id':key,'image':png_data(image,compress_level=DEVICE_PNG_COMPRESSION),'required':required}
            elif required:self.tasks[key]['required']=True
            return Reading('',0)
        value=self.readings.get(key)
        if value is None:raise ValueError('Device readings are incomplete. Process the photo again.')
        raw=value['text'];text=clock_text(raw) if mode=='time' else raw
        return Reading(text,min(value['confidence'],.79),raw)

    def read_status(self,image,ink):
        return self.read(tight_white(ink))

    def read_punches(self,layout,day,punches):
        cache_key=(id(layout),day)
        if self.readings is None and cache_key in self._prepared_punches:
            return self._prepared_punches[cache_key]
        ink=clean_ink(layout.cells[day])
        originals=photo_punch_crops(layout.cells[day],ink)
        focused=focused_punch_crops(layout.cells[day],ink)
        edges=label_edge_punch_crops(layout,day)
        result=[];compact_repairs=[]
        for original,cleaned,focus,edge in zip(originals,punches,focused,edges):
            edge_id=self._key(edge,'time') if edge is not None else None
            edge_reading=(self.read(edge,'time',required=False) if edge_id is not None and
                          (self.readings is None or edge_id in self.readings) else Reading('',0))
            original_id=self._key(original,'time');cleaned_id=self._key(cleaned,'time')
            first=self.read(original,'time')
            second=self.read(cleaned,'time',required=False)
            focused_id=self._key(focus,'time')
            third=(Reading('',0) if self.readings is not None and focused_id not in self.readings
                   else self.read(focus,'time',required=False))
            if self.readings is None:
                if edge_id is not None and edge_id not in {original_id,cleaned_id,focused_id}:
                    self.tasks[edge_id]['edge_recovery']=True
                    groups=self.tasks[edge_id].setdefault('recover_for',[])
                    group=[original_id,cleaned_id,focused_id]
                    if group not in groups:groups.append(group)
                if cleaned_id!=original_id:
                    parents=self.tasks[cleaned_id].setdefault('fallback_for',[])
                    if original_id not in parents:parents.append(original_id)
                if focused_id not in {original_id,cleaned_id}:
                    groups=self.tasks[focused_id].setdefault('recover_for',[])
                    pair=[original_id,cleaned_id]
                    if pair not in groups:groups.append(pair)
            skipped=self.readings is not None and self.readings.get(cleaned_id,{}).get('skipped_reason') in {'original_valid','standard_valid'}
            if skipped and not clock_text(first.raw_text):
                raise ValueError('A fallback crop can only be skipped after a valid original punch.')
            focus_skipped=self.readings is not None and self.readings.get(focused_id,{}).get('skipped_reason')=='standard_valid'
            if focus_skipped and not (clock_text(first.raw_text) or clock_text(second.raw_text)):
                raise ValueError('A recovery crop can only be skipped after an ordinary time was read.')
            # A wide crop must not replace an established clock arbitrarily.
            # It may restore a missing leading 1 (1:45 -> 11:45), with the
            # minutes and meridiem unchanged, or fill an unreadable punch.
            normal=next((clock_text(v.raw_text) for v in (first,second,third) if clock_text(v.raw_text)), '')
            if not normal:
                normal=next((tentative_clock_text(v.raw_text) for v in (third,first,second) if tentative_clock_text(v.raw_text)), '')
            expanded=clock_text(edge_reading.raw_text)
            old_clock=re.fullmatch(r'([012])[:.]([0-5][0-9])(am|pm)?',normal)
            new_clock=re.fullmatch(r'1([012])[:.]([0-5][0-9])(am|pm)?',expanded)
            restore_leading_one=bool(old_clock and new_clock and old_clock.group(1,2)==new_clock.group(1,2)
                                     and (not old_clock.group(3) or old_clock.group(3)==new_clock.group(3)))
            edge_preferred=bool(expanded and (not normal or restore_leading_one))
            edge_group=('label_edge_punch',[{'text':edge_reading.raw_text,'confidence':edge_reading.confidence}])
            groups=[('original_punch',[{'text':first.raw_text,'confidence':first.confidence}]),
                                    ('cleaned_punch',[{'text':second.raw_text,'confidence':second.confidence}]),
                                    ('focused_punch',[{'text':third.raw_text,'confidence':third.confidence}])]
            reading=choose_reading(([edge_group]+groups) if edge_preferred else groups)
            ordinary=bool(clock_text(first.raw_text) or clock_text(second.raw_text))
            if reading.text and (not ordinary or edge_preferred):reading.recovered=True
            compact_repair=False
            if not reading.text and self.readings is not None:
                candidates=[(source,value,tentative_clock_text(value.raw_text)) for source,value in
                            [('focused_punch',third),('original_punch',first),('cleaned_punch',second)]]
                candidates=[item for item in candidates if item[2]]
                if candidates:
                    from .calculator import parse_time
                    chosen=candidates[0]
                    compact_repair=not bool(re.search(r'[:.;：]',chosen[1].raw_text))
                    alternatives=[{'source':source,'raw':value.raw_text,'value':candidate} for source,value,candidate in candidates]
                    parsed=[parse_time(item[2]) for item in candidates]
                    conflict=(len({value%720 for value,explicit in parsed})>1 or
                              len({value for value,explicit in parsed if explicit})>1)
                    reading=Reading(chosen[2],min(chosen[1].confidence,.65),chosen[1].raw_text,alternatives,conflict,recovered=True)
            if edge_reading.raw_text and not edge_preferred:
                reading.alternatives=(reading.alternatives or [])+[{'source':'label_edge_punch','raw':edge_reading.raw_text,'value':expanded}]
                if expanded and reading.text:
                    from .calculator import parse_time
                    left,left_explicit=parse_time(reading.text);right,right_explicit=parse_time(expanded)
                    if left%720!=right%720 or (left_explicit and right_explicit and left!=right):reading.conflict=True
            reading.cross_check_skipped=bool(skipped)
            result.append(reading);compact_repairs.append(compact_repair)
        # A bare digit sequence alone could be a written duration/total. Only
        # repair that format when the other punch provides a real clock anchor.
        if not any(value.text and not compact for value,compact in zip(result,compact_repairs)):
            for index,compact in enumerate(compact_repairs):
                if compact:result[index]=Reading('',0,result[index].raw_text,result[index].alternatives)
        if self.readings is None:self._prepared_punches[cache_key]=result
        return result


def pack_layouts(layouts):
    return [png_data(layout.image) for layout in layouts]


def unpack_layouts(payload):
    """Rebuild crops from browser-held normalized cards; no server scan cache."""
    import base64
    import binascii
    from io import BytesIO
    import numpy as np
    from .extractor import LayoutCard
    if not isinstance(payload,list) or not 1<=len(payload)<=20:
        raise ValueError('Provide 1–20 normalized cards')
    layouts=[]
    for value in payload:
        if not isinstance(value,str) or not value.startswith('data:image/png;base64,') or len(value)>2_000_000:
            raise ValueError('Invalid normalized card')
        try:
            data=base64.b64decode(value.split(',',1)[1],validate=True)
            with Image.open(BytesIO(data)) as image:
                if image.format!='PNG' or image.size!=(310,785):raise ValueError('Invalid normalized card dimensions')
                card=cv2.cvtColor(np.array(image.convert('RGB')),cv2.COLOR_RGB2BGR)
        except (binascii.Error,OSError) as exc:
            raise ValueError('Invalid normalized card image') from exc
        cells=[];notes=[]
        for day in range(7):
            a=round(120+day*600/7);b=round(120+(day+1)*600/7)
            cells.append(card[a-6:b+6,198:306].copy())
            notes.append(card[a-6:b+6,8:135].copy())
        layouts.append(LayoutCard(card,(0,0,0,0),cells,notes,card[65:112,20:290].copy(),card[721:766,185:309].copy(),6))
    return layouts
