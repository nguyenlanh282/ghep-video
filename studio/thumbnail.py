"""Thumbnails (cover images): find clear-face frames in the footage a video used, then compose 1–3 of them.

Candidates come from the ORIGINAL media at the moments the video showed them (clean frames, no burned-in captions).
Each frame is scored on: a detected face, face size, face sharpness (no motion blur), face exposure, and whether a
9:16 crop can keep every face. The best distinct frames are offered; the user picks 1–3 or uploads their own.
"""
import hashlib, json, math, subprocess, time, unicodedata
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from platform_tools import FFMPEG, FFPROBE, NOWIN, detect_faces_many, font_path

VIDEO={'.mp4','.mov','.m4v','.mkv','.webm'}
PHOTO={'.jpg','.jpeg','.png','.webp','.heic'}
SIZE=(1080,1920)
nfc=lambda s:unicodedata.normalize('NFC',s)

def crop_for(width,height,faces,ratio,margin=(.10,.45,.25),zone=(.18,1)):
 """Largest crop of the given aspect ratio (w/h) that contains all faces with forehead/chin room; None if impossible.
 zone=(top,bottom) is where the faces should sit inside the crop (fractions of its height), e.g. away from the title."""
 cw=min(width,height*ratio);ch=cw/ratio
 if not faces:x=(width-cw)/2;y=(height-ch)/2
 else:
  side,top_room,chin=margin
  left=min(max(0,(x-side*w)*width) for x,y,w,h in faces);right=max(min(width,(x+(1+side)*w)*width) for x,y,w,h in faces)
  top=min(max(0,(y-top_room*h)*height) for x,y,w,h in faces);bottom=max(min(height,(y+(1+chin)*h)*height) for x,y,w,h in faces)
  if right-left>cw or bottom-top>ch:return None
  x=min(min(left,width-cw),max(max(0,right-cw),(left+right-cw)/2))
  lo=max(0,bottom-ch);hi=min(top,height-ch)  # any y in [lo,hi] keeps every face inside
  # Prefer faces inside the zone; when it cannot hold them, just keep them inside the crop.
  zlo=max(lo,bottom-ch*zone[1]);zhi=min(hi,top-ch*zone[0])
  y=min(max(top-ch*zone[0],zlo),zhi) if zlo<=zhi else min(max(top-ch*zone[0],lo),hi)
 return (round(x),round(y),round(x+cw),round(y+ch))

def fitted(img,faces,box_w,box_h,zone=(.18,1)):
 """Cover-crop img to box size keeping faces: all faces, else the largest face, else centre."""
 ratio=box_w/box_h
 crop=crop_for(img.width,img.height,faces,ratio,zone=zone)
 if crop is None and faces:crop=crop_for(img.width,img.height,[max(faces,key=lambda f:f[2]*f[3])],ratio,(.02,.2,.1),zone)
 if crop is None:crop=crop_for(img.width,img.height,[],ratio)
 return img.crop(crop).resize((box_w,box_h),Image.Resampling.LANCZOS)

def sharpness(gray):
 """Variance of the Laplacian: high for crisp detail, low for blur."""
 g=gray.astype(np.float32)
 lap=4*g[1:-1,1:-1]-g[:-2,1:-1]-g[2:,1:-1]-g[1:-1,:-2]-g[1:-1,2:]
 return float(lap.var())

def score(path,found):
 faces=found.get('faces') or []
 if not faces:return None
 img=Image.open(path).convert('L');W,H=img.size
 x,y,w,h=max(faces,key=lambda f:f[2]*f[3])
 face=img.crop((round(x*W),round(y*H),round((x+w)*W),round((y+h)*H)))
 if face.width<24 or face.height<24:return None
 face=face.resize((128,round(128*face.height/face.width)))
 arr=np.asarray(face);sharp=min(1,sharpness(arr)/250);light=arr.mean()
 exposure=1 if 70<=light<=200 else .55
 size=math.sqrt(w*h)  # fraction of the frame's side the face occupies
 # A face touching the picture's edge is already cut in the source: it cannot be shown whole.
 edge=any(fx<.012 or fy<.012 or fx+fw>.988 or fy+fh>.988 for fx,fy,fw,fh in faces)
 fits=not edge and crop_for(W,H,faces,9/16) is not None
 rolls=found.get('rolls') or [0]*len(faces)
 tilt=abs(rolls[faces.index(max(faces,key=lambda f:f[2]*f[3]))]) if rolls else 0
 upright=1 if tilt<=15 else .6 if tilt<=25 else .15  # sideways selfies make poor covers
 value=size*(.35+.65*sharp)*exposure*upright*(1 if fits else .4)*(1+.08*min(2,len(faces)-1))
 return dict(score=round(value,4),faces=faces,sharp=round(sharp,2),fits=fits,tilt=round(tilt),width=W,height=H)

def moments(job,media_folder,per_shot=3):
 """(file, time) pairs: the moments the video actually showed, or evenly spread samples of all media."""
 folder=Path(media_folder);files={nfc(p.name):p for p in folder.iterdir() if p.suffix.lower() in VIDEO|PHOTO} if folder.is_dir() else {}
 out=[]
 for shot in (job or {}).get('scenePlan',[]):
  p=files.get(nfc(shot.get('file','')))
  if not p:continue
  if p.suffix.lower() in PHOTO:out.append((p,None));continue
  a,b=map(float,shot['time'].split('-'));length=b-a
  out+=[(p,shot['sourceStart']+length*k/(per_shot+1)) for k in range(1,per_shot+1)]
 if not out:
  for p in files.values():
   if p.suffix.lower() in PHOTO:out.append((p,None));continue
   d=duration(p);n=max(1,min(12,int(d//3)))
   out+=[(p,d*(k+.5)/n) for k in range(n)]
 seen=set();unique=[]
 for p,t in out:
  key=(str(p),None if t is None else round(t,1))
  if key not in seen:seen.add(key);unique.append((p,t))
 return unique

def duration(p):
 r=subprocess.run([FFPROBE,'-v','error','-show_entries','format=duration','-of','csv=p=0',str(p)],capture_output=True,**NOWIN)
 try:return float(r.stdout.decode().strip())
 except ValueError:return 0

def grab(path,t,dest):
 """Full-resolution frame (display orientation) as JPEG."""
 args=[FFMPEG,'-v','error','-y']+(['-ss',f'{t:.3f}'] if t is not None else [])+['-i',str(path),'-frames:v','1','-q:v','2',str(dest)]
 subprocess.run(args,capture_output=True,**NOWIN)
 return dest if dest.exists() else None

def find_candidates(job,media_folder,work,limit=12,progress=lambda p,m:None):
 work=Path(work);work.mkdir(parents=True,exist_ok=True);frames=[]
 todo=moments(job,media_folder)
 for i,(p,t) in enumerate(todo):
  name=hashlib.sha1(f'{p}|{t}'.encode()).hexdigest()[:14]+'.jpg'
  f=work/name
  if f.exists() or grab(p,t,f):frames.append((f,p,t))
  if i%4==0:progress(5+55*i/max(1,len(todo)),f'Đang lấy khung hình {i+1}/{len(todo)}…')
 progress(62,'Đang tìm khuôn mặt rõ nét…')
 found=detect_faces_many([f for f,_,_ in frames]) if frames else {}
 scored=[]
 for f,p,t in frames:
  s=score(f,found.get(str(f),{}))
  if s:scored.append(dict(s,path=str(f),source=p.name,time=None if t is None else round(t,2)))
 scored.sort(key=lambda c:-c['score']);picked=[]
 for c in scored:
  # Distinct moments only: not the same file within 2.5 s of an already picked frame.
  if any(c['source']==o['source'] and (c['time'] is None or o['time'] is None or abs(c['time']-o['time'])<2.5) for o in picked):continue
  picked.append(c)
  if len(picked)>=limit:break
 for i,c in enumerate(picked):
  c['id']=f'c{i+1}';c['preview']=str(preview(Path(c['path']),c['faces'],work))
 progress(100,f'Đã tìm được {len(picked)} hình rõ mặt.')
 return picked

def preview(path,faces,work):
 dest=work/(path.stem+'-p.jpg')
 if not dest.exists():fitted(Image.open(path).convert('RGB'),faces,270,480).save(dest,quality=85)
 return dest

def add_upload(src,work):
 """A user's own image becomes a candidate (converted to JPEG, faces detected)."""
 work=Path(work);work.mkdir(parents=True,exist_ok=True)
 dest=work/('up-'+hashlib.sha1(Path(src).read_bytes()).hexdigest()[:14]+'.jpg')
 if not grab(src,None,dest):raise ValueError('Không đọc được ảnh này.')
 found=detect_faces_many([dest]).get(str(dest),{})
 s=score(dest,found) or dict(score=0,faces=found.get('faces',[]),sharp=0,fits=True)
 img=Image.open(dest)
 return dict(s,path=str(dest),source='Ảnh tải lên',time=None,width=img.width,height=img.height,upload=True,preview=str(preview(dest,s['faces'],work)))

# ---------------- composition ----------------

def layout(n,W,H,gap=10):
 """Cells (x0,y0,x1,y1,face_zone). The title sits at 20% (one picture) or across the middle seam (2–3 pictures),
 so each cell keeps its faces out of the title's way."""
 if n==1:return [(0,0,W,H,(.34,.97))]
 half=(H-gap)//2
 if n==2:return [(0,0,W,half,(.06,.78)),(0,half+gap,W,H,(.24,1))]
 col=(W-gap)//2
 return [(0,0,W,half,(.06,.78)),(0,half+gap,col,H,(.2,1)),(col+gap,half+gap,W,H,(.2,1))]

def fit_font(text,size,max_w):
 f=ImageFont.truetype(font_path(),size)
 while f.getlength(text)>max_w and f.size>30:f=ImageFont.truetype(font_path(),f.size-2)
 return f

def draw_title(canvas,title,subtitle,style,center_y):
 W,H=canvas.size;title=title.strip();subtitle=subtitle.strip()
 if style=='none' or not (title or subtitle):return
 big=fit_font(title,128,W*.88) if title else None;small=fit_font(subtitle,86,W*.84) if subtitle else None
 h1=big.size*1.15 if big else 0;h2=small.size*1.25 if small else 0;gap=24 if big and small else 0
 top=center_y-(h1+gap+h2)/2
 layer=Image.new('RGBA',canvas.size);d=ImageDraw.Draw(layer)
 if style=='card':
  d.rounded_rectangle((W*.05,top-34,W*.95,top+h1+gap+h2+34),radius=44,fill=(15,18,26,225));colors=('white','#ffd54a');stroke=0
 else:
  # Soft dark band behind the words so they read on any picture.
  band=Image.new('L',(1,256));band.putdata([int(150*math.sin(math.pi*i/255)) for i in range(256)])
  shade=Image.new('RGBA',(W,int(h1+gap+h2+220)),(0,0,0,255));shade.putalpha(band.resize(shade.size))
  layer.alpha_composite(shade,(0,int(top-110)));colors=('white','#9cfa68');stroke=9
 if style=='ribbon' and small:
  d.rounded_rectangle((W*.04,top+h1+gap-12,W*.96,top+h1+gap+h2+8),radius=26,fill='#e94d79');colors=('white','white')
 if big:d.text((W/2,top+h1/2),title,font=big,anchor='mm',fill=colors[0],stroke_width=stroke,stroke_fill='#11151c')
 if small:d.text((W/2,top+h1+gap+h2/2),subtitle,font=small,anchor='mm',fill=colors[1],stroke_width=0 if style=='ribbon' else round(stroke*.8),stroke_fill='#11151c')
 canvas.alpha_composite(layer)

def compose(chosen,dest,title='',subtitle='',style='pop',text=True,size=SIZE):
 """chosen: 1–3 candidate dicts (path, faces). Writes a JPEG of `size` and returns its path."""
 if not 1<=len(chosen)<=3:raise ValueError('Hãy chọn từ 1 đến 3 hình.')
 W,H=size;canvas=Image.new('RGBA',size,'#0b0f14')
 for c,(x0,y0,x1,y1,zone) in zip(chosen,layout(len(chosen),W,H)):
  img=Image.open(c['path']).convert('RGB')
  canvas.paste(fitted(img,c.get('faces') or [],x1-x0,y1-y0,zone),(x0,y0))
 if text:draw_title(canvas,title,subtitle,style if style!='none' else 'pop',H*(.2 if len(chosen)==1 else .5))
 dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
 canvas.convert('RGB').save(dest,quality=92)
 return dest
