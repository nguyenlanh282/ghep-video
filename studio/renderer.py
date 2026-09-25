"""Local video renderer (macOS and Windows). All media stays on this computer."""
import wave
import numpy as np
import hashlib, json, math, os, re, shutil, subprocess, sys, tempfile, time, unicodedata
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from platform_tools import FFMPEG, FFPROBE, NOWIN, font_path, transcribe, utf8_stdio
import platform_tools
VIDEO={'.mp4','.mov','.m4v','.mkv','.webm'}
PHOTO={'.jpg','.jpeg','.png','.webp','.heic'}
FONT=font_path()
CHILDREN=[]

def emit(progress,message,**kw):
 print(json.dumps(dict(progress=progress,message=message,**kw),ensure_ascii=False),flush=True)

def run(args):
 p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**NOWIN);CHILDREN.append(p)
 out,err=p.communicate();CHILDREN.remove(p)
 if p.returncode:raise RuntimeError(err.decode(errors='replace')[-1600:])
 return out

def probe(path):
 return json.loads(run([FFPROBE,'-v','quiet','-show_format','-show_streams','-of','json',str(path)]))

def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def get_words(audio,cache):
 cache.mkdir(parents=True,exist_ok=True);key=cache/(digest(audio)+'.json')
 if key.exists():r=json.loads(key.read_text(encoding='utf-8'))
 else:
  emit(3,'Đang nhận dạng lời đọc trên máy…')
  r=transcribe(audio)
  temp=key.with_suffix('.tmp');temp.write_text(json.dumps(r,ensure_ascii=False),encoding='utf-8');temp.replace(key)
 words=[]
 for seg in r.get('segments',[]):
  for w in seg.get('words',[]):
   text=w['word'].strip()
   if text and w['end']>w['start']:words.append(dict(text=text,start=float(w['start']),end=float(w['end'])))
 if not words:raise ValueError('Không nhận dạng được lời đọc. Hãy kiểm tra file ghi âm.')
 return words

def silence_ranges(samples,rate,min_silence=.35,threshold_db=-35):
 """Remove only sustained quiet stretches; retain 80/120 ms of speech padding."""
 hop=max(1,round(rate*.01));quiet=[]
 threshold=32768*10**(threshold_db/20)
 for start in range(0,len(samples),hop):
  quiet.append(np.max(np.abs(samples[start:start+hop].astype(np.int32))) < threshold)
 remove=[];begin=None
 for i,is_quiet in enumerate(quiet+[False]):
  if is_quiet and begin is None:begin=i*hop/rate
  elif not is_quiet and begin is not None:
   end=min(i*hop/rate,len(samples)/rate)
   if end-begin>=min_silence:
    a=begin+(.08 if begin>0 else 0);b=end-(.12 if end<len(samples)/rate else 0)
    if b>a:remove.append((a,b))
   begin=None
 return remove

def kept_ranges(duration,removed):
 keep=[];cursor=0
 for a,b in removed:
  if a>cursor:keep.append((cursor,a))
  cursor=b
 if cursor<duration:keep.append((cursor,duration))
 return keep

def mapped_time(t,keep):
 return sum(max(0,min(t,b)-a) for a,b in keep if t>a)

def cut_silence(audio,cache,words):
 emit(5,'Đang cắt các khoảng im lặng và căn lại phụ đề…')
 key=digest(audio)+'-silence-v1';wav=cache/(key+'.wav');meta=cache/(key+'.json')
 if wav.exists() and meta.exists():keep=json.loads(meta.read_text(encoding='utf-8'))['keep']
 else:
  raw=run([FFMPEG,'-v','error','-i',str(audio),'-vn','-ac','2','-ar','48000','-f','s16le','pipe:1'])
  pcm=np.frombuffer(raw,dtype='<i2').reshape(-1,2);keep=kept_ranges(len(pcm)/48000,silence_ranges(pcm,48000))
  if sum(b-a for a,b in keep)<.2:raise ValueError('File ghi âm gần như hoàn toàn im lặng; không thể dựng video.')
  parts=[]
  for a,b in keep:
   part=pcm[round(a*48000):round(b*48000)].copy();fade=min(192,len(part)//2)
   if fade:
    part[:fade]=(part[:fade]*np.linspace(0,1,fade)[:,None]).astype('<i2')
    part[-fade:]=(part[-fade:]*np.linspace(1,0,fade)[:,None]).astype('<i2')
   parts.append(part.tobytes())
  temporary=wav.with_suffix('.tmp')
  with wave.open(str(temporary),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000);f.writeframes(b''.join(parts))
  temporary.replace(wav);meta.write_text(json.dumps({'keep':keep}),encoding='utf-8')
 new_words=[]
 for w in words:
  a=mapped_time(w['start'],keep);b=mapped_time(w['end'],keep)
  if b>a+.001:new_words.append(dict(w,start=a,end=b))
 return wav,new_words,keep

def face_crop(width,height,faces):
 """A 9:16 cover crop that contains all detected faces plus forehead/chin room."""
 cw=min(width,height*9/16);ch=cw*16/9
 if faces:
  left=min(max(0,(x-.015*w)*width) for x,y,w,h in faces)
  right=max(min(width,(x+1.015*w)*width) for x,y,w,h in faces)
  top=min(max(0,(y-.48*h)*height) for x,y,w,h in faces)
  bottom=max(min(height,(y+1.2*h)*height) for x,y,w,h in faces)
  if right-left>cw-2 or bottom-top>ch-2:return None
  xmin=max(0,right-cw);xmax=min(left,width-cw)
  ymin=max(0,bottom-ch);ymax=min(top,height-ch)
  x=min(xmax,max(xmin,(left+right-cw)/2));y=min(ymax,max(ymin,(top+bottom-ch)/2))
 else:x=(width-cw)/2;y=(height-ch)/2
 return (math.floor(x),math.floor(y),math.ceil(x+cw),math.ceil(y+ch))

def detect_faces(image):
 return platform_tools.detect_faces(image)

def video_filter(p,at,tmp,W,H,fps,face_aware):
 """Cover-crop a video around the faces seen mid-clip; fall back to a blurred fit if they cannot all stay in frame."""
 blur=f'[0:v]split=2[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=28[blur];[fg]scale={W}:{H}:force_original_aspect_ratio=decrease[fit];[blur][fit]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={fps}[v]'
 if not face_aware:return blur,None
 frame=tmp/f'probe-{digest_text(str(p))}-{at:.2f}.jpg'
 try:
  run([FFMPEG,'-v','error','-y','-ss',f'{at:.3f}','-i',str(p),'-frames:v','1','-q:v','3',str(frame)])
  found=detect_faces(frame)
 except Exception:
  return f'[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps}[v]',None
 crop=face_crop(found['width'],found['height'],found['faces'])
 if crop is None:return blur,dict(found,crop=None)
 x,y,r,b=crop
 return f'[0:v]crop={r-x}:{b-y}:{x}:{y},scale={W}:{H},setsar=1,fps={fps}[v]',dict(found,crop=crop)

def digest_text(s):
 return hashlib.sha1(s.encode()).hexdigest()[:10]

def prepare_photo(path,tmp,W,H):
 normalized=tmp/(digest(path)[:16]+'.jpg')
 run([FFMPEG,'-v','error','-y','-i',str(path),'-frames:v','1','-q:v','2',str(normalized)])
 found=detect_faces(normalized)
 im=Image.open(normalized).convert('RGB');crop=face_crop(im.width,im.height,found['faces'])
 if crop is None:return None,found
 framed=tmp/(normalized.stem+'-portrait.jpg');im.crop(crop).resize((W,H),Image.Resampling.LANCZOS).save(framed,quality=96)
 return framed,dict(found,crop=crop)

PUNCT=(',','.','?','!',':',';','…')
HOLD=1.5  # keep a finished line on screen (all white) until the next line starts, instead of blinking off

def split_even(phrase,parts):
 size,extra=divmod(len(phrase),parts);out=[];i=0
 for k in range(parts):n=size+(k<extra);out.append(phrase[i:i+n]);i+=n
 return out

def phrases_for(words):
 """Spoken phrases: end at punctuation or at a pause longer than 0.65 s."""
 phrases=[];current=[]
 for w in words:
  if current and w['start']-current[-1]['end']>.65:phrases.append(current);current=[]
  current.append(w)
  if w['text'].endswith(PUNCT):phrases.append(current);current=[]
 if current:phrases.append(current)
 return phrases

def groups_for(words,max_width=600,max_words=7):
 """One steady line per phrase. A phrase ends at punctuation or a pause; a long phrase is split
 into lines of near-equal length so no line is left with a lone trailing word."""
 font=ImageFont.truetype(FONT,40);fits=lambda g:len(g)<=max_words and font.getlength(' '.join(w['text'] for w in g))<=max_width
 groups=[]
 for phrase in phrases_for(words):
  for parts in range(1,len(phrase)+1):
   lines=split_even(phrase,parts)
   if all(fits(g) for g in lines):break
  groups+=lines
 return groups

def group_end(groups,i,duration):
 """When line i leaves the screen: at the next line, or HOLD seconds after its last word."""
 end=groups[i][-1]['end']+HOLD
 if i+1<len(groups):end=min(end,groups[i+1][0]['start'])
 return min(end,duration)

def parse_fixes(text):
 """Lines like `sai => đúng` (also ->, →, =). Returns {wrong_lower: right}."""
 fixes={}
 for line in (text or '').splitlines():
  for sep in ('=>','->','→','='):
   if sep in line:
    a,b=(unicodedata.normalize('NFC',x.strip()) for x in line.split(sep,1))
    if a and b:fixes[a.lower()]=b
    break
 return fixes

def apply_fixes(words,fixes):
 """Replace whole recognised words, keeping surrounding punctuation and a leading capital."""
 for w in words:
  m=re.fullmatch(r'(\W*)(.*?)(\W*)',unicodedata.normalize('NFC',w['text']))
  right=fixes.get(m.group(2).lower())
  if right:
   if m.group(2)[:1].isupper():right=right[:1].upper()+right[1:]
   w['text']=m.group(1)+right+m.group(3)
 return words

def srt_stamp(t):
 n=round(max(0,t)*1000);return f'{n//3600000:02}:{n//60000%60:02}:{n//1000%60:02},{n%1000:03}'

def scene_spans(phrases,duration,min_len=1.2):
 """Cut the timeline at phrase starts so each scene change lands on a new phrase.
 Phrases shorter than min_len are merged into their neighbour to avoid flashing cuts."""
 spans=[]
 for k,ph in enumerate(phrases):
  a=0 if k==0 else ph[0]['start']
  if a>=duration:break
  spans.append(dict(start=a,text=' '.join(w['text'] for w in ph)))
 if not spans:return [dict(start=0,end=duration,text='')]
 for k,sp in enumerate(spans):sp['end']=spans[k+1]['start'] if k+1<len(spans) else duration
 merged=[]
 for sp in spans:
  if merged and (sp['end']-sp['start']<min_len or merged[-1]['end']-merged[-1]['start']<min_len):
   merged[-1]=dict(start=merged[-1]['start'],end=sp['end'],text=merged[-1]['text']+' '+sp['text'])
  else:merged.append(sp)
 return merged

def split_span(a,b,shot):
 n=max(1,round((b-a)/shot));return [(a+(b-a)*k/n,a+(b-a)*(k+1)/n) for k in range(n)]

def rotation_shots(duration,shot):
 """No analysis: evenly cut the timeline; the last cut absorbs a short remainder instead of flashing."""
 return split_span(0,duration,shot)

def load_analysis(folder):
 p=folder/'_phan-tich.json'
 if not p.exists():return {}
 try:return {unicodedata.normalize('NFC',k):v for k,v in json.loads(p.read_text(encoding='utf-8'))['files'].items()}
 except Exception:return {}

def build_units(details,analysis):
 """Scene candidates: one per photo, one per analysed video segment (or the whole video)."""
 units=[]
 for path,d,source in details:
  e=analysis.get(unicodedata.normalize('NFC',source.name),{})
  if d and e.get('scenes'):
   for sc in e['scenes']:
    if sc['end']-sc['start']>.3:units.append(dict(path=path,d=d,a=sc['start'],b=min(d,sc['end']),text=f"{sc['mo_ta']} ({', '.join(sc.get('tu_khoa',[]))})",source=source.name))
  else:
   text=(e.get('mo_ta','')+(' ('+', '.join(e.get('tu_khoa',[]))+')' if e.get('tu_khoa') else '')) if e else ''
   units.append(dict(path=path,d=d,a=0,b=d,text=text,source=source.name))
 for i,u in enumerate(units):u['id']=i+1
 return units

PLAN_VERSION=4

def plan_scenes(spans,units,job,cache):
 """Ask the local vision-language model which scenes illustrate each phrase. Cached per content."""
 described=[dict(id=u['id'],text=f"[{Path(u['source']).stem}] {u['text']}") for u in units if u['text']]
 sentences=[dict(id=k+1,text=sp['text']) for k,sp in enumerate(spans) if sp['text']]
 ai=job.get('aiPython') or sys.executable;script=Path(__file__).with_name('analyzer.py')
 if not described or not sentences or not Path(ai).exists() or not script.exists():return {}
 # Bump PLAN_VERSION whenever analyzer.plan changes, so cached plans are recomputed.
 request=dict(units=described,sentences=sentences,version=PLAN_VERSION)
 if job.get('stockEnabled'):
  source=job.get('stockSource') or 'auto'
  if source in ('pexels','pixabay') and not os.environ.get(source.upper()+'_API_KEY'):source='openverse'
  # Which keys exist is part of the plan: adding a key later must trigger a fresh search.
  request['stockKeys']=sorted(k for k in ('pexels','pixabay') if os.environ.get(k.upper()+'_API_KEY'))
  request['stock']=dict(source=source,folder=str(cache/'stock'))
 key=hashlib.sha256(json.dumps(request,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:24]
 out=cache/f'plan-{key}.json'
 if not out.exists():
  emit(9,f'Đang chọn cảnh khớp với {len(sentences)} câu lời đọc…')
  req=cache/f'plan-{key}-request.json';req.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
  try:run([ai,str(script),'plan',str(req),str(out)])
  except RuntimeError as exc:emit(9,'Chưa chọn được cảnh theo lời đọc, dùng thứ tự luân phiên. '+str(exc)[-200:]);return {}
  finally:req.unlink(missing_ok=True)
 data=json.loads(out.read_text(encoding='utf-8'))
 if 'choices' not in data:data=dict(choices=data,stock={})
 return dict(choices={int(k):v for k,v in data['choices'].items()},stock={int(k):v for k,v in data.get('stock',{}).items()})

def add_stock(plan,units,tmp,W,H,face_aware):
 """Turn downloaded free photos/videos into scene units and make them the choice for their phrase."""
 credits=[]
 for k,item in plan['stock'].items():
  path=Path(item['path'])
  if not path.exists():continue
  if item['kind']=='video':
   try:d=float(probe(path)['format']['duration'])
   except Exception:continue
  else:
   d=0
   if face_aware:
    framed,_=prepare_photo(path,tmp,W,H)
    if framed is None:continue
    path=framed
  uid=max([u['id'] for u in units],default=0)+1
  units.append(dict(id=uid,path=path,d=d,a=0,b=d,text=item.get('mo_ta',''),source='Miễn phí: '+item.get('provider','')))
  plan['choices'][k]=[uid];credits.append(dict(phrase=k,credit=item['credit'],page=item['page'],license=item['license'],query=item['query']))
 return credits

def assign_shots(spans,choices,units,shot,duration,max_run=2):
 """Each phrase shows its best-matching scenes. Variety rules: the same scene never plays twice in a row,
 and one file never fills more than max_run shots in a row while another good match exists."""
 by_id={u['id']:u for u in units};uses={u['id']:0 for u in units};shots=[];recent=[]
 for k,sp in enumerate(spans):
  ranked=[i for i in choices.get(k+1,[]) if i in by_id]
  for j,(a,b) in enumerate(split_span(sp['start'],sp['end'],shot)):
   last=shots[-1]['unit'] if shots else None
   run_src=recent[-1] if len(recent)>=max_run and len(set(recent[-max_run:]))==1 else None
   ok=lambda i:i!=last and by_id[i]['source']!=run_src
   rotated=ranked[j%len(ranked):]+ranked[:j%len(ranked)] if ranked else []
   # Among the matches, prefer the least used so a long phrase moves through different scenes.
   rotated=sorted(rotated,key=lambda i:(uses[i]>0,rotated.index(i)))
   uid=next((i for i in rotated if ok(i)),None);matched=uid is not None
   if uid is None:uid=next((i for i in sorted(by_id,key=lambda i:(uses[i],i)) if ok(i)),rotated[0] if rotated else min(by_id,key=lambda i:uses[i]))
   shots.append(dict(start=a,end=b,unit=uid,text=sp['text'],matched=matched));uses[uid]+=1;recent.append(by_id[uid]['source'])
 return shots

def source_start(u,length,use):
 """Where to start reading a video: inside its scene, moving forward on each reuse."""
 if not u['d']:return 0
 room=max(0,(u['b']-u['a'])-length)
 start=u['a']+((use*length)%(room+.001) if room else 0)
 return max(0,min(start,u['d']-length-.12))

TARGET_LUFS=-14

def loudness(path,cache):
 """Integrated loudness (LUFS) of a whole file, cached per file content."""
 key=cache/(digest(path)+'-lufs.json')
 if key.exists():return json.loads(key.read_text(encoding='utf-8'))['lufs']
 p=subprocess.run([FFMPEG,'-hide_banner','-nostats','-i',str(path),'-af','ebur128','-f','null','-'],capture_output=True,**NOWIN)
 found=re.findall(rb'I:\s+(-?[0-9.]+|-inf) LUFS',p.stderr)
 value=float(found[-1]) if found and found[-1]!=b'-inf' else None
 key.write_text(json.dumps({'lufs':value}),encoding='utf-8');return value

def voice_gain_db(audio,job,cache):
 """Fixed gain that brings the whole recording to -14 LUFS (social-media level), times the user's slider.
 A static gain (not loudnorm's single pass) gives the same result for a 20 s preview and the full video."""
 user=20*math.log10(max(.25,min(4,float(job.get('voiceVolume',1)))))
 if not job.get('normalizeVoice',True):return user
 measured=loudness(audio,cache)
 return user+(max(-20,min(36,TARGET_LUFS-measured)) if measured is not None else 0)

CAPTION_Y=.73  # caption baseline, as a fraction of the frame height (above TikTok/Reels bottom text)

def caption_layout(group,font,W,H,y=CAPTION_Y):
 # A fixed baseline avoids Vietnamese diacritics moving individual words up/down.
 space=font.getlength(' ');positions={}
 width=sum(font.getlength(w['text']) for w in group)+space*max(0,len(group)-1)
 x=(W-width)/2
 for j,w in enumerate(group):
  positions[j]=(x,H*y);x+=font.getlength(w['text'])+space
 return positions

def make_title(job,W,H):
 scale=W/720;layer=Image.new('RGBA',(W,round(270*scale)));d=ImageDraw.Draw(layer)
 title=job.get('title','VỢ CHỒNG').strip();subtitle=job.get('subtitle','Ai làm việc nhà?').strip();style=job.get('titleStyle','pop')
 if style=='none' or not (title or subtitle):return layer
 def fit(text,size):
  f=ImageFont.truetype(FONT,round(size*scale))
  while f.getlength(text)>W*.84 and f.size>14*scale:f=ImageFont.truetype(FONT,f.size-1)
  return f
 big=fit(title,62);small=fit(subtitle,45)
 if style=='card':
  d.rounded_rectangle((W*.07,12*scale,W*.93,213*scale),radius=24*scale,fill=(15,18,26,225));colors=['white','#ffd54a'];stroke=0
 elif style=='ribbon':
  d.rounded_rectangle((W*.04,113*scale,W*.96,193*scale),radius=15*scale,fill='#e94d79');colors=['white','white'];stroke=round(4*scale)
 else:colors=['white','#9cfa68'];stroke=round(4*scale)
 d.text((W/2,68*scale),title,font=big,anchor='mm',fill=colors[0],stroke_width=stroke,stroke_fill='#151a22')
 d.text((W/2,152*scale),subtitle,font=small,anchor='mm',fill=colors[1],stroke_width=0 if style=='ribbon' else stroke,stroke_fill='#151a22')
 return layer

def title_overlay(title,style,t,secs,frame_w):
 """(image, x) of the opening title at time t, or None once its time is up. Pop zooms in, card slides in; all fade out
 over the last 0.3 s instead of vanishing."""
 if t>=secs:return None
 if style=='pop':
  z=.86+.14*min(1,t/.22);ov=title if z>=1 else title.resize((round(title.width*z),round(title.height*z)),Image.Resampling.LANCZOS)
  x=(frame_w-ov.width)//2
 elif style=='card':ov=title;x=round((frame_w-title.width)/2-frame_w*(1-min(1,t/.26))**3)
 else:ov=title;x=(frame_w-title.width)//2
 fade=min(1,(secs-t)/.3)
 if fade<1:
  ov=ov.copy();ov.putalpha(ov.getchannel('A').point(lambda v:int(v*fade)))
 return ov,x

HIGHLIGHT={'active':'#9cfa68','sweep':'#ffd54a','pill':'#f37aa5'}

def caption_band(font,H,y=CAPTION_Y):
 """Fixed strip around the caption baseline; tall enough for stacked Vietnamese diacritics."""
 top=round(H*y-font.size*1.5);return top,round(font.size*2.1)

def caption_image(group,positions,font,style,active,W,top,height):
 """Words never move: same position and size every frame, only the spoken word changes colour."""
 layer=Image.new('RGBA',(W,height));d=ImageDraw.Draw(layer);sw=max(2,round(W/240));highlight=HIGHLIGHT.get(style)
 for j,w in enumerate(group):
  x,y=positions[j]
  d.text((x,y-top),w['text'],font=font,anchor='ls',fill=highlight if highlight and j==active else 'white',stroke_width=sw,stroke_fill='#171717')
 return layer

def render(job):
 folder=Path(job['mediaFolder']).expanduser().resolve();audio=Path(job['audio']).expanduser().resolve();output=Path(job['outputFolder']).expanduser().resolve()
 if not folder.is_dir():raise ValueError('Thư mục ảnh/video không tồn tại.')
 if not audio.is_file():raise ValueError('Chưa chọn file ghi âm hợp lệ.')
 if not output.is_dir():raise ValueError('Thư mục lưu không tồn tại.')
 media=sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO|PHOTO)
 if not media:raise ValueError('Thư mục chưa có ảnh hoặc video được hỗ trợ.')
 music=Path(job['music']).expanduser().resolve() if job.get('music') else None
 if music and not music.is_file():raise ValueError('Không tìm thấy file nhạc nền.')
 shot=max(1.5,min(5,float(job.get('shotSeconds',2.5))));W=1080 if job.get('resolution')=='1080' else 720;H=W*16//9;fps=30
 face_aware=job.get('faceAwareFill',True)
 info=probe(audio);original_duration=float(info['format']['duration'])
 cache=Path(job['cacheFolder']);cache.mkdir(parents=True,exist_ok=True);words=get_words(audio,cache) if job.get('subStyle')!='none' or job.get('matchScenes',True) else []
 keep=[[0,original_duration]]
 if job.get('removeSilence',True):audio,words,keep=cut_silence(audio,cache,words)
 audio_duration=float(probe(audio)['format']['duration']);duration=min(audio_duration,20) if job.get('preview') else audio_duration
 # Spelling fixes come from the app (Sửa chữ nhận dạng sai); applied before grouping so line widths are measured on the final text.
 fixes=parse_fixes(job.get('fixesText',''));apply_fixes(words,fixes)
 groups=[g for g in groups_for(words) if g[0]['start']<duration]
 job=dict(job,removeSilence=job.get('removeSilence',True),faceAwareFill=face_aware,originalDuration=original_duration,editedDuration=audio_duration,keptAudioRanges=keep,spellingFixes=fixes)
 emit(8,'Đang chuẩn bị cảnh quay…')
 details=[]
 for p in media:
  try:
   inf=probe(p);next(s for s in inf['streams'] if s['codec_type']=='video');d=float(inf['format'].get('duration',0)) if p.suffix.lower() in VIDEO else 0
   if p.suffix.lower() in VIDEO and d<.2:continue
   details.append((p,d))
  except Exception:emit(8,'Bỏ qua file không đọc được: '+p.name)
 if not details:raise ValueError('Không có ảnh/video đọc được trong thư mục.')
 stamp=time.strftime('%Y%m%d-%H%M%S');name=('Xem-thu' if job.get('preview') else 'Video')+'-'+stamp+'-'+os.urandom(2).hex();dest=output/(name+'.mp4')
 with tempfile.TemporaryDirectory(prefix='ghep-video-') as tmp:
  tmp=Path(tmp);clips=[];video_info=[];details=[(p,d,p) for p,d in details]
  if face_aware:
   usable=[];photo_info=[]
   for p,d,src in details:
    if d:usable.append((p,d,src));continue
    framed,found=prepare_photo(p,tmp,W,H)
    photo_info.append(dict(source=str(p),used=framed is not None,**found))
    if framed:usable.append((framed,0,src))
    else:emit(8,'Bỏ qua ảnh không thể giữ đủ khuôn mặt trong khung dọc: '+p.name)
   details=usable;job['photoFraming']=photo_info
   if not details:raise ValueError('Không có ảnh phù hợp để phủ đầy khung dọc mà giữ trọn khuôn mặt. Hãy thêm ảnh dọc hoặc video.')
  analysis=load_analysis(folder) if job.get('matchScenes',True) else {}
  if analysis and words:
   # Scene changes follow the narration: every phrase gets scenes whose description matches what is said.
   units=build_units(details,analysis);spans=scene_spans(phrases_for(words),duration)
   plan=plan_scenes(spans,units,job,cache)
   job['stockCredits']=add_stock(plan,units,tmp,W,H,face_aware) if plan else []
   shots=assign_shots(spans,plan['choices'] if plan else {},units,shot,duration)
  else:
   # Alternate videos and photos; step through different source positions on each pass.
   videos=[x for x in details if x[1]>0];photos=[x for x in details if x[1]==0];ordered=[]
   while videos or photos:
    if videos:ordered.append(videos.pop(0))
    if videos:ordered.append(videos.pop(0))
    if photos:ordered.append(photos.pop(0))
   units=[dict(id=i+1,path=p,d=d,a=0,b=d,text='',source=src.name) for i,(p,d,src) in enumerate(ordered)]
   shots=[dict(start=a,end=b,unit=units[i%len(units)]['id'],text='',matched=False) for i,(a,b) in enumerate(rotation_shots(duration,shot))]
  by_id={u['id']:u for u in units};uses={};count=len(shots);plan_log=[]
  for i,sh in enumerate(shots):
   u=by_id[sh['unit']];p,d=u['path'],u['d'];length=sh['end']-sh['start'];out=tmp/f'{i:04}.mp4';cmd=[FFMPEG,'-v','error','-y']
   # Frame counts come from rounded cut times, so scene changes never drift away from the narration.
   frames=round(sh['end']*fps)-round(sh['start']*fps)
   if frames<1:continue
   if d:
    start=source_start(u,length,uses.get(u['id'],0)) if analysis else ((i//len(units))*7.1+min(2,max(0,d-length-.12)))%(max(0,d-length-.12)+.001)
    cmd+=['-stream_loop','-1','-ss',f'{start:.3f}','-i',str(p)]
    # Videos get the same face check as photos: faces must stay inside the 9:16 crop, otherwise use a blurred fit.
    vf,found=video_filter(p,min(start+length/2,max(0,d-.05)),tmp,W,H,fps,face_aware)
    if found is not None:video_info.append(dict(source=str(p),start=round(start,2),faces=found['faces'],crop=found['crop']))
   else:
    start=0;cmd+=['-loop','1','-i',str(p)]
    # Face-safe photos are already 9:16.
    vf=f'[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps}[v]' if face_aware else video_filter(p,0,tmp,W,H,fps,False)[0]
   uses[u['id']]=uses.get(u['id'],0)+1
   plan_log.append(dict(time=f"{sh['start']:.2f}-{sh['end']:.2f}",file=u['source'],sourceStart=round(start,2),scene=u['text'],phrase=sh['text'],matched=sh['matched']))
   cmd+=['-filter_complex',vf,'-map','[v]','-frames:v',str(frames),'-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(out)]
   run(cmd);clips.append(out);emit(10+25*(i+1)/count,f'Chuẩn bị cảnh {i+1}/{count}')
  job['scenePlan']=plan_log
  if face_aware:job['videoFraming']=video_info
  concat=tmp/'clips.txt';concat.write_text(''.join(f"file '{p.name}'\n" for p in clips),encoding='utf-8')
  dec_log=open(tmp/'decode.log','wb');enc_log=open(tmp/'encode.log','wb');dec=enc=None
  try:
   dec=subprocess.Popen([FFMPEG,'-v','error','-f','concat','-safe','0','-i',str(concat),'-frames:v',str(round(duration*fps)),'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=dec_log,**NOWIN);CHILDREN.append(dec)
   movie=tmp/'movie.mp4';cmd=[FFMPEG,'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(fps),'-i','pipe:0','-i',str(audio)]
   voice='[1:a]asetpts=PTS-STARTPTS'+f',volume={voice_gain_db(audio,job,cache):.2f}dB[voice];'
   if music:
    cmd+=['-stream_loop','-1','-i',str(music)];volume=max(0,min(1,float(job.get('musicVolume',.15))))
    cmd+=['-filter_complex',f'{voice}[2:a]asetpts=PTS-STARTPTS,volume={volume},afade=t=out:st={max(0,duration-1.2)}:d=1.2[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.79:level=0[a]','-map','0:v','-map','[a]']
   else:cmd+=['-filter_complex',f'{voice}[voice]alimiter=limit=0.79:level=0[a]','-map','0:v','-map','[a]']
   cmd+=['-t',str(duration),'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(movie)]
   enc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=enc_log,**NOWIN);CHILDREN.append(enc)
   style=job.get('subStyle','active');title_style=job.get('titleStyle','pop')
   font=ImageFont.truetype(FONT,round(40*W/720));cap_y=max(.5,min(.9,float(job.get('captionY',CAPTION_Y))));positions=[caption_layout(g,font,W,H,cap_y) for g in groups];band_top,band_h=caption_band(font,H,cap_y)
   title=make_title(job,W,H);title_y=round(H*.21875);title_secs=max(.5,min(6,float(job.get('titleSeconds',3))));gi=0;nframes=round(duration*fps);cached_key=None;cached=None
   for n in range(nframes):
    data=dec.stdout.read(W*H*3)
    if len(data)!=W*H*3:raise RuntimeError(f'Video nguồn kết thúc ở khung {n}/{nframes} ({len(data)} byte).')
    im=Image.frombytes('RGB',(W,H),data);t=n/fps
    shown=title_overlay(title,title_style,t,title_secs,W) if title_style!='none' else None
    if shown:im.paste(shown[0],(shown[1],title_y),shown[0])
    if style!='none' and groups:
     while gi+1<len(groups) and groups[gi+1][0]['start']<=t:gi+=1
     g=groups[gi]
     if g[0]['start']<=t<group_end(groups,gi,duration):
      active=next((j for j,w in enumerate(g) if w['start']<=t<w['end']),-1)
      # Redraw only when the line or the highlighted word changes.
      if (gi,active)!=cached_key:cached_key=(gi,active);cached=caption_image(g,positions[gi],font,style,active,W,band_top,band_h)
      im.paste(cached,(0,band_top),cached)
    enc.stdin.write(im.tobytes())
    if n%30==0:emit(35+60*n/nframes,f'Đang xuất video · {int(t)} / {math.ceil(duration)} giây')
   enc.stdin.close()
   if enc.wait()!=0:raise RuntimeError((tmp/'encode.log').read_text(encoding='utf-8')[-1600:])
   dec.stdout.close();dec.wait()
  finally:
   for p in (dec,enc):
    if p is None:continue
    if p.poll() is None:p.terminate()
    if p in CHILDREN:CHILDREN.remove(p)
   dec_log.close();enc_log.close()
  emit(97,'Đang kiểm tra và lưu video…');check=probe(movie)
  if abs(float(check['format']['duration'])-duration)>.2:raise RuntimeError('Thời lượng xuất không khớp. Video chưa được lưu.')
  # Copy to a hidden partial file in the destination, then rename only when complete.
  partial=output/('.'+name+'.partial');shutil.copyfile(movie,partial);partial.replace(dest)
 srt=dest.with_suffix('.srt');srt.write_text('\n\n'.join(f'{i+1}\n{srt_stamp(g[0]["start"])} --> {srt_stamp(group_end(groups,i,duration))}\n'+' '.join(w['text'] for w in g) for i,g in enumerate(groups)),encoding='utf-8')
 if job.get('stockCredits'):
  dest.with_suffix('.nguon-anh.txt').write_text('Ảnh/video miễn phí dùng trong video này:\n\n'+'\n'.join(f"- {c['credit']} · {c['license']} · {c['page']}" for c in job['stockCredits'])+'\n',encoding='utf-8')
 dest.with_suffix('.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
 emit(100,'Đã xuất xong video',output=str(dest),srt=str(srt))

if __name__=='__main__':
 import signal
 utf8_stdio()
 def cancel(*_):
  for p in CHILDREN:
   try:p.terminate()
   except:pass
  raise SystemExit(130)
 signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
 try:render(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
 except Exception as e:emit(-1,str(e),error=True);sys.exit(1)
