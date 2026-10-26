"""Green-strip anchored TOPS 1256 extraction. Geometry is heuristic, always reviewed."""
from dataclasses import dataclass
from pathlib import Path
import os
import cv2
import numpy as np
from PIL import Image

@dataclass
class LayoutCard:
    image: np.ndarray
    anchor: tuple
    cells: list
    notes: list
    name: np.ndarray
    written: np.ndarray
    cell_padding: int = 0
    source_grid: np.ndarray | None = None


def bar_geometry(mask,anchor):
    """Recover seven row boundaries from fourteen filled OUT boxes."""
    x,y,w,h=anchor
    points=[];widths=[]
    for yy in range(y,y+h):
        row=mask[yy,x:x+w]>0
        edges=np.diff(np.r_[0,row,0].astype(int))
        starts=np.where(edges==1)[0];ends=np.where(edges==-1)[0]
        if len(starts):
            k=int(np.argmax(ends-starts));length=ends[k]-starts[k]
            if length>h*.012:
                points.append((yy,x+ends[k]-1));widths.append(length)
    if len(points)<10:
        return None
    bar_width=float(np.median(widths))
    fitted=np.array(points,dtype=float)
    slope,intercept=np.polyfit(*fitted.T,1)
    # Printed totals and attached rules may extend beyond the bar. Fit its
    # dominant straight edge rather than allowing those outliers to tilt it.
    for _ in range(3):
        residual=fitted[:,1]-(intercept+slope*fitted[:,0])
        keep=np.abs(residual-np.median(residual))<max(2,bar_width*.25)
        if np.count_nonzero(keep)<10:
            break
        slope,intercept=np.polyfit(*fitted[keep].T,1)
    ya=max(0,y-round(.1*h));yb=min(mask.shape[0],y+h+round(.1*h))
    ys=np.arange(ya,yb);right=np.round(intercept+slope*ys).astype(int)
    coverage=[]
    for yy,edge in zip(ys,right):
        a=max(0,min(mask.shape[1],int(edge-bar_width*.9)))
        b=max(0,min(mask.shape[1],edge+1))
        coverage.append(float(np.mean(mask[yy,a:b]>0)) if b>a else 0)
    coverage=np.array(coverage)
    filled=(coverage>.45).astype('uint8')[:,None]
    filled=cv2.morphologyEx(filled,cv2.MORPH_CLOSE,np.ones((max(3,round(h*.005)),1),np.uint8)).ravel()
    edges=np.diff(np.r_[0,filled,0].astype(int))
    starts=np.where(edges==1)[0];ends=np.where(edges==-1)[0]
    runs=[(int(a+ya),int(b+ya)) for a,b in zip(starts,ends) if b-a>h*.018]
    if len(runs)!=14:
        return None
    periods=np.diff([a for a,b in runs])
    if np.std(periods)/np.mean(periods)>.15:
        return None
    gap=float(np.median([runs[i+1][0]-runs[i][1] for i in range(13)]))
    boundaries=[runs[0][0]-gap]+[runs[i][1] for i in range(1,14,2)]
    return slope,intercept,np.array(boundaries)


def detect_cards(image):
    """Find and validate every strip; derive every grid from printed OUT boxes."""
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    base=cv2.inRange(hsv,(32,25,35),(100,255,255))
    height,width=image.shape[:2]
    blue,green,red=cv2.split(image.astype('int16'))
    printing=base.copy();printing[(green-red<12)|(green-blue<8)]=0
    solid=cv2.morphologyEx(printing,cv2.MORPH_OPEN,
                           np.ones((max(5,round(height/60)),3),np.uint8))
    fine=cv2.morphologyEx(printing,cv2.MORPH_OPEN,
                          np.ones((max(5,round(height/100)),3),np.uint8))
    validated=[]
    # Always combine passes. A partial detection must not disable recovery of
    # other cards. Coarse components propose strips; fourteen boxes validate them.
    for proposal in (base,printing,fine,solid):
        closed=cv2.morphologyEx(proposal,cv2.MORPH_CLOSE,
                                np.ones((max(9,round(height*.039)),3),np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(closed)
        for x,y,w,h,area in stats[1:]:
            if h<max(100,height*.12) or not .008<w/h<.6 or area/(w*h)<.12:
                continue
            anchor=tuple(map(int,(x,y,w,h)))
            geometry=bar_geometry(printing,anchor)
            if geometry is None:
                geometry=bar_geometry(base,anchor)
            if geometry is None:
                continue
            slope,intercept,boundaries=geometry
            middle=float(np.mean(boundaries[[0,-1]]))
            right=intercept+slope*middle
            duplicate=False
            for _,(other_slope,other_intercept,other_bounds) in validated:
                span=min(boundaries[-1]-boundaries[0],other_bounds[-1]-other_bounds[0])
                overlap=min(boundaries[-1],other_bounds[-1])-max(boundaries[0],other_bounds[0])
                if overlap>.7*span and abs(right-(other_intercept+other_slope*middle))<.08*span:
                    duplicate=True
                    break
            if not duplicate:
                validated.append((anchor,geometry))
    if not validated:
        raise ValueError('Could not align the seven printed day rows. Show the full green IN/OUT strip in a clear photo.')
    result=[]
    for anchor,(slope,intercept,boundaries) in sorted(validated,key=lambda item:item[1][1]+item[1][0]*np.mean(item[1][2])):
        grid=np.linspace(120,720,8)
        source_y=np.interp(np.arange(785),grid,boundaries)
        source_y[:120]=boundaries[0]+(np.arange(120)-120)*(boundaries[1]-boundaries[0])/(600/7)
        source_y[721:]=boundaries[-1]+(np.arange(721,785)-720)*(boundaries[-1]-boundaries[-2])/(600/7)
        xx,yy=np.meshgrid(np.arange(310,dtype=np.float32),np.arange(785,dtype=np.float32))
        sy=np.broadcast_to(source_y[:,None],yy.shape).astype('float32')
        scale=(boundaries[-1]-boundaries[0])/600
        sx=intercept+slope*sy+(xx-190)*scale
        card=cv2.remap(image,sx.astype('float32'),sy,cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT,borderValue=(255,255,255))
        cells=[];notes=[]
        padding=6
        for day in range(7):
            a=round(120+day*600/7);b=round(120+(day+1)*600/7)
            cells.append(card[a-padding:b+padding,198:306].copy())
            notes.append(card[a-padding:b+padding,8:135].copy())
        result.append(LayoutCard(card,anchor,cells,notes,card[65:112,20:290].copy(),
                                 card[721:766,185:309].copy(),padding,boundaries.copy()))
    return result


def clean_ink(cell):
    hsv=cv2.cvtColor(cell,cv2.COLOR_BGR2HSV)
    gray=cv2.cvtColor(cell,cv2.COLOR_BGR2GRAY)
    # Printed green ink is suppressed BEFORE measuring. No speck-removal step.
    green=cv2.inRange(hsv,(30,19,30),(105,255,255))
    gray=gray.copy();gray[green>0]=255
    ink=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,25,15)
    horizontal=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(24,cell.shape[1]//3)),np.uint8))
    vertical=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((max(22,cell.shape[0]//2),1),np.uint8))
    ink[cv2.dilate(horizontal|vertical,np.ones((2,1),np.uint8))>0]=0
    ink[:3]=0;ink[-3:]=0;ink[:,:3]=0;ink[:,-3:]=0
    return ink


def classify_ink(cell):
    ink=clean_ink(cell);fraction=float(np.count_nonzero(ink)/ink.size)
    blank=float(os.getenv('BLANK_INK_THRESHOLD','.015'))
    off=float(os.getenv('OFF_INK_THRESHOLD','.035'))
    return ('blank' if fraction<blank else 'off' if fraction<off else 'worked'),fraction,ink


def tight_white(ink):
    ys,xs=np.where(ink>0)
    if not len(xs): return Image.new('RGB',(192,64),'white')
    crop=255-ink[max(0,ys.min()-3):ys.max()+4,max(0,xs.min()-3):xs.max()+4]
    crop=cv2.copyMakeBorder(crop,8,8,8,8,cv2.BORDER_CONSTANT,value=255)
    return Image.fromarray(crop).convert('RGB').resize((crop.shape[1]*3,crop.shape[0]*3))


def punch_bands(ink):
    # Search two bands in the first ~60% of a day: the remaining rules are unused.
    profile=np.count_nonzero(ink,axis=1).astype(float)
    profile=np.convolve(profile,np.ones(3)/3,mode='same')
    h=ink.shape[0]; first=int(np.argmax(profile[3:max(5,int(h*.29))]))+3
    second=int(np.argmax(profile[int(h*.29):int(h*.60)]))+int(h*.29)
    # Cut in the whitespace between lines, not halfway between their darkest
    # strokes: a tall minute digit can extend well past that midpoint.
    lo=first+2; hi=second-1
    split=min(range(lo,hi),key=lambda y:(profile[y],abs(y-(first+second)/2))) if hi>lo else round((first+second)/2)
    if second-first<8 or not profile[first] or not profile[second]: split=round(h*.28)
    return [(0,split),(split,round(h*.64))]


def punch_crops(ink):
    return [tight_white(ink[a:b]) for a,b in punch_bands(ink)]


def photo_punch_crops(cell,ink):
    """Preserve grayscale strokes for readers trained on photographic text."""
    result=[]
    for a,b in punch_bands(ink):
        part=cell[a:b].copy()
        ys,xs=np.where(ink[a:b]>0)
        if len(xs):
            part=part[max(0,ys.min()-2):ys.max()+3,max(0,xs.min()-2):xs.max()+3]
        part=cv2.copyMakeBorder(part,5,5,5,5,cv2.BORDER_CONSTANT,value=(255,255,255))
        result.append(Image.fromarray(cv2.cvtColor(part,cv2.COLOR_BGR2RGB)).resize(
            (part.shape[1]*3,part.shape[0]*3),Image.Resampling.BICUBIC))
    return result


def png_data(image):
    import base64,io
    if not isinstance(image,Image.Image): image=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
    buf=io.BytesIO(); image.save(buf,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()


def extract(image,recognizer,layouts=None):
    cards=[]
    if layouts is None:layouts=detect_cards(image)
    if hasattr(recognizer,'prepare'):
        recognizer.prepare(layouts)
    for ci,layout in enumerate(layouts):
        name=recognizer.read(Image.fromarray(cv2.cvtColor(layout.name,cv2.COLOR_BGR2RGB)),'text')
        written=recognizer.read(Image.fromarray(cv2.cvtColor(layout.written,cv2.COLOR_BGR2RGB)),'total')
        card={'id':str(ci),'name':name.text,'name_confidence':name.confidence,'written_total':written.text,'days':[], 'image':png_data(layout.image)}
        for di,cell in enumerate(layout.cells):
            if os.getenv('EXTRACT_PROGRESS'):
                print(f'Reading card {ci+1}, day {di+1}',flush=True)
            guessed,fraction,ink=classify_ink(cell)
            original=Image.fromarray(cv2.cvtColor(cell,cv2.COLOR_BGR2RGB))
            status_read=(recognizer.read_status(original,ink) if hasattr(recognizer,'read_status')
                         else recognizer.read(original,'text') if guessed!='blank' else None)
            # Ink density cannot overrule recognized clock text, or prove OFF.
            import re
            off_text=re.sub(r'[^a-z]', '',status_read.text.lower()) if status_read else ''
            status=('worked' if status_read and status_read.has_clock else 'off' if off_text=='off'
                    else 'blank' if guessed=='blank' and not (status_read and status_read.text.strip())
                    else 'worked')
            punches=punch_crops(ink)
            values=(recognizer.read_punches(layout,di,punches) if hasattr(recognizer,'read_punches')
                    else [recognizer.read(p,'time') for p in punches]) if status=='worked' else []
            if status=='worked' and not any(value.text for value in values):
                status='unknown'
            note=recognizer.read(Image.fromarray(cv2.cvtColor(layout.notes[di],cv2.COLOR_BGR2RGB)),'text')
            import re
            adjustments=re.findall(r'\+\s*(\d+(?:\.\d+)?)',note.text)
            row={'label':f'Day {di+1}','status':status,'in':values[0].text if values else '', 'out':values[1].text if values else '',
                 'in_confidence':values[0].confidence if values else None,'out_confidence':values[1].confidence if values else None,
                 'raw_in':values[0].raw_text if values else '', 'raw_out':values[1].raw_text if values else '',
                 'ocr_alternatives':{'in':values[0].alternatives,'out':values[1].alternatives} if values else {},
                 'ocr_conflict':any(v.conflict for v in values),
                 'ocr_cross_check_skipped':any(v.cross_check_skipped for v in values),
                 'status_confidence':status_read.confidence if status_read else .5,'status_guessed':True,'ink_fraction':fraction,
                 'ink_class':guessed,'raw_status':status_read.text if status_read else '', 'source':'ocr','reviewed':False,
                 'note':note.text,'adjustment_hours':adjustments[0] if len(adjustments)==1 else '0',
                 'adjustment_confirmed':False, # Every notes area must be inspected, including failed OCR.
                 'image':png_data(cell),'note_image':png_data(layout.notes[di]),'punch_images':[png_data(p) for p in punches]}
            card['days'].append(row)
        cards.append(card)
    return cards
