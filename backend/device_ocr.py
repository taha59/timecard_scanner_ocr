"""Prepare recognition tasks and combine device readings without server inference."""
import hashlib
from PIL import Image
import cv2
from .recognizer import Reading
from .ocr_common import clock_text
from .extractor import png_data, clean_ink, tight_white, photo_punch_crops, punch_crops
from .rapid_recognizer import choose_reading

class DeviceRecognizer:
    def __init__(self, readings=None):
        self.tasks={}
        self.readings=readings

    def prepare(self,layouts):
        if self.readings is None:
            # Even a visually blank row can produce text on the device. Record
            # both punches up front so replay never needs an unprepared task.
            for layout in layouts:
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
            if key not in self.tasks:self.tasks[key]={'id':key,'image':png_data(image),'required':required}
            elif required:self.tasks[key]['required']=True
            return Reading('',0)
        value=self.readings.get(key)
        if value is None:raise ValueError('Device readings are incomplete. Process the photo again.')
        raw=value['text'];text=clock_text(raw) if mode=='time' else raw
        return Reading(text,min(value['confidence'],.79),raw)

    def read_status(self,image,ink):
        return self.read(tight_white(ink))

    def read_punches(self,layout,day,punches):
        originals=photo_punch_crops(layout.cells[day],clean_ink(layout.cells[day]))
        result=[]
        for original,cleaned in zip(originals,punches):
            original_id=self._key(original,'time');cleaned_id=self._key(cleaned,'time')
            first=self.read(original,'time')
            second=self.read(cleaned,'time',required=False)
            if self.readings is None:
                if cleaned_id!=original_id:
                    parents=self.tasks[cleaned_id].setdefault('fallback_for',[])
                    if original_id not in parents:parents.append(original_id)
            skipped=self.readings is not None and self.readings.get(cleaned_id,{}).get('skipped_reason')=='original_valid'
            if skipped and not clock_text(first.raw_text):
                raise ValueError('A fallback crop can only be skipped after a valid original punch.')
            reading=choose_reading([('original_punch',[{'text':first.raw_text,'confidence':first.confidence}]),
                                    ('cleaned_punch',[{'text':second.raw_text,'confidence':second.confidence}])])
            reading.cross_check_skipped=bool(skipped)
            result.append(reading)
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
