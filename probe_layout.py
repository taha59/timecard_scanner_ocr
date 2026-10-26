import cv2
from backend.extractor import detect_cards,classify_ink
im=cv2.imread('fixtures/timecards.jpg');cards=detect_cards(im)
canvas=[]
for ci,c in enumerate(cards):
 print(ci,c.anchor)
 column=[]
 for di,cell in enumerate(c.cells):
  status,f,ink=classify_ink(cell);print(di+1,status,round(f,4))
  crop=cv2.resize(cell,(216,172)); cv2.putText(crop,f'{di+1} {status} {f:.3f}',(4,162),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,200),1)
  column.append(crop)
 canvas.append(cv2.vconcat(column))
cv2.imwrite('layout_contact.jpg',cv2.hconcat(canvas))
