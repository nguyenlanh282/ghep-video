"""Local media analysis with a vision-language model (Qwen3-VL: mlx-vlm on Mac, Ollama on Windows).
All media stays on this computer, except downloads from free stock sites when that option is on.

analyze <folder> [--no-rename]   describe every photo/video (videos per scene), rename files, write notes
undo <folder>                    restore the original file names
plan <plan.json> <out.json>      pick the best matching scenes for each spoken phrase;
                                 optionally find free stock photos/videos for phrases nothing fits
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

from platform_tools import FFMPEG, FFPROBE, NOWIN, vlm_ask, vlm_name, vlm_ready, utf8_stdio
VIDEO={'.mp4','.mov','.m4v','.mkv','.webm'}
PHOTO={'.jpg','.jpeg','.png','.webp','.heic'}
MODEL=vlm_name()
INDEX='_phan-tich.json'
NOTES='_ghi-chu-tu-lieu.md'
_model=None

def emit(progress,message,**kw):
 print(json.dumps(dict(progress=progress,message=message,**kw),ensure_ascii=False),flush=True)

def run(args):
 p=subprocess.run(args,capture_output=True,**NOWIN)
 if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace')[-1200:])
 return p

def nfc(s):return unicodedata.normalize('NFC',s)

def model():
 vlm_ready()

def ask(question,images=(),schema=None):
 return vlm_ask(question,images,schema)

def obj(props,required=None):
 """JSON schema for an object of string fields (and string lists for keys ending in _list-like 'tu_khoa')."""
 return {'type':'object','properties':{k:({'type':'array','items':{'type':'string'}} if k=='tu_khoa' else {'type':'boolean'} if k=='hop' else {'type':'string'}) for k in props},'required':required or list(props)}

def parse_json(text,fallback):
 m=re.search(r'\{.*\}',text,re.S)
 try:return json.loads(m.group(0)) if m else fallback
 except json.JSONDecodeError:return fallback
 finally:
  if not m:print('Câu trả lời AI không đọc được:',repr(text[:300]),file=sys.stderr,flush=True)

def duration(path):
 out=run([FFPROBE,'-v','error','-show_entries','format=duration','-of','csv=p=0',str(path)]).stdout.decode().strip()
 return float(out or 0)

def still(path,at,dest):
 """One frame, longest side 768 px: enough detail for the model, several times faster than full size."""
 args=[FFMPEG,'-v','error','-y']+(['-ss',f'{at:.3f}'] if at is not None else [])+['-i',str(path),'-frames:v','1','-vf','scale=768:768:force_original_aspect_ratio=decrease','-q:v','3',str(dest)]
 run(args);return dest

def scene_cuts(path):
 p=subprocess.run([FFMPEG,'-hide_banner','-i',str(path),'-vf',"scale=320:-2,select='gt(scene,0.32)',showinfo",'-an','-f','null','-'],capture_output=True,**NOWIN)
 return [float(x) for x in re.findall(rb'pts_time:([0-9.]+)',p.stderr)]

def segments(total,cuts,min_len=2.5,max_len=8):
 """Shots between hard cuts; very short ones merge into the previous, long ones split evenly."""
 bounds=[0]+[c for c in cuts if 0<c<total]+[total];merged=[]
 for a,b in zip(bounds,bounds[1:]):
  if merged and (b-a<min_len or merged[-1][1]-merged[-1][0]<min_len):merged[-1]=(merged[-1][0],b)
  else:merged.append((a,b))
 out=[]
 for a,b in merged:
  n=max(1,round((b-a)/max_len+.49))
  out+=[(a+(b-a)*k/n,a+(b-a)*(k+1)/n) for k in range(n)]
 return [(round(a,2),round(b,2)) for a,b in out if b-a>.3]

PHOTO_Q='''Bạn là trợ lý dựng video. Mô tả hình này bằng tiếng Việt có dấu, trả về đúng một JSON:
{"ten":"tên ngắn 3-7 chữ tiếng Việt có dấu, cách nhau bằng khoảng trắng (không dùng _ hay -), nói rõ ai đang làm gì","mo_ta":"1-2 câu mô tả cụ thể","nguoi":"ai xuất hiện, đang làm gì","boi_canh":"địa điểm, thời điểm","cam_xuc":"cảm xúc của cảnh","tu_khoa":["6-10 từ khoá tiếng Việt, gồm cả những từ người ta hay nói khi kể về cảnh này"]}'''
SCENE_Q='''Đây là một khung hình trong video. Mô tả cảnh bằng tiếng Việt có dấu, trả về đúng một JSON:
{"mo_ta":"1 câu mô tả cụ thể ai đang làm gì, ở đâu","cam_xuc":"cảm xúc","tu_khoa":["5-8 từ khoá tiếng Việt"]}'''

def describe_video(path,tmp):
 total=duration(path);parts=segments(total,scene_cuts(path));scenes=[]
 for i,(a,b) in enumerate(parts):
  frame=still(path,(a+b)/2,tmp/f'{path.stem[:40]}-{i}.jpg')
  d=parse_json(ask(SCENE_Q,[frame],obj(['mo_ta','cam_xuc','tu_khoa'])),{})
  scenes.append(dict(start=a,end=b,mo_ta=d.get('mo_ta',''),cam_xuc=d.get('cam_xuc',''),tu_khoa=d.get('tu_khoa',[])))
  yield i+1,len(parts),None
 listing='\n'.join(f'- {s["start"]:.0f}-{s["end"]:.0f}s: {s["mo_ta"]}' for s in scenes)
 d=parse_json(ask('Video gồm các cảnh sau:\n'+listing+'\nTrả về đúng một JSON tiếng Việt có dấu: {"ten":"tên ngắn 3-7 chữ tiếng Việt có dấu, cách nhau bằng khoảng trắng (không dùng _ hay -) nói rõ nội dung chính","mo_ta":"1-2 câu tóm tắt cả video","tu_khoa":["6-10 từ khoá"]}',(),obj(['ten','mo_ta','tu_khoa'])),{})
 yield len(parts),len(parts),dict(kind='video',duration=round(total,2),ten=d.get('ten',''),mo_ta=d.get('mo_ta',''),tu_khoa=d.get('tu_khoa',[]),scenes=scenes)

def safe_name(text,ext,taken):
 # Some models answer in file-name style (bo_chup_anh): turn separators back into spaces.
 base=re.sub(r'[\\/:*?"<>|\n\r\t_]+',' ',nfc(text)).strip(' .-')
 base=re.sub(r'\s+',' ',base)[:60].strip() or 'Tư liệu'
 base=base[:1].upper()+base[1:];name=base+ext;n=2
 while name.lower() in taken:name=f'{base} {n}{ext}';n+=1
 return name

def load_index(folder):
 p=folder/INDEX
 return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'version':1,'model':MODEL,'files':{}}

def save_index(folder,index):
 tmp=folder/(INDEX+'.tmp');tmp.write_text(json.dumps(index,ensure_ascii=False,indent=1),encoding='utf-8');tmp.replace(folder/INDEX)
 write_notes(folder,index)

def write_notes(folder,index):
 lines=['# Ghi chú tư liệu','',f'Thư mục: `{folder}`  ','Tạo tự động bởi Ghép Video (phân tích trên máy). Sửa tên/mô tả trong app hoặc trong `'+INDEX+'`.','']
 for name,e in sorted(index['files'].items()):
  lines+=[f'## {name}','',f'- Loại: {"video "+str(round(e.get("duration",0)))+" giây" if e["kind"]=="video" else "ảnh"}',f'- Tên gốc: `{e["original"]}`',f'- Mô tả: {e.get("mo_ta","")}']
  for k,label in (('nguoi','Người'),('boi_canh','Bối cảnh'),('cam_xuc','Cảm xúc')):
   if e.get(k):lines.append(f'- {label}: {e[k]}')
  if e.get('tu_khoa'):lines.append('- Từ khoá: '+', '.join(e['tu_khoa']))
  if e.get('scenes'):
   lines+=['','| Đoạn | Mô tả | Từ khoá |','|---|---|---|']
   lines+=[f'| {s["start"]:.1f}–{s["end"]:.1f}s | {s["mo_ta"]} | {", ".join(s.get("tu_khoa",[]))} |' for s in e['scenes']]
  lines.append('')
 (folder/NOTES).write_text('\n'.join(lines),encoding='utf-8')

def analyze(folder,rename=True):
 folder=Path(folder).expanduser().resolve();index=load_index(folder);files=index['files']
 media=sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith(('.','_')) and p.suffix.lower() in VIDEO|PHOTO)
 # Drop entries whose file was deleted or renamed outside the app.
 for name in [n for n in files if not (folder/n).exists()]:del files[name]
 todo=[p for p in media if not (nfc(p.name) in files and files[nfc(p.name)].get('size')==p.stat().st_size)]
 if not todo:emit(100,f'Tư liệu đã được phân tích hết ({len(media)} file).',done=True);save_index(folder,index);return
 emit(1,'Đang nạp mô hình nhận diện hình ảnh…');model()
 with tempfile.TemporaryDirectory(prefix='phan-tich-') as tmp:
  tmp=Path(tmp)
  for i,p in enumerate(todo):
   base=100*i/len(todo);step=100/len(todo)
   emit(base,f'Đang xem {p.name} ({i+1}/{len(todo)})…')
   try:
    if p.suffix.lower() in PHOTO:
     d=parse_json(ask(PHOTO_Q,[still(p,None,tmp/'photo.jpg')],obj(['ten','mo_ta','nguoi','boi_canh','cam_xuc','tu_khoa'])),{})
     entry=dict(kind='photo',ten=d.get('ten',''),mo_ta=d.get('mo_ta',''),nguoi=d.get('nguoi',''),boi_canh=d.get('boi_canh',''),cam_xuc=d.get('cam_xuc',''),tu_khoa=d.get('tu_khoa',[]))
    else:
     for k,n,entry in describe_video(p,tmp):emit(base+step*k/(n+1),f'Đang xem {p.name}: đoạn {k}/{n}')
   except Exception as exc:
    emit(base,f'Bỏ qua {p.name}: {exc}');continue
   entry.update(original=files.get(nfc(p.name),{}).get('original',nfc(p.name)),size=p.stat().st_size,analyzed=time.strftime('%Y-%m-%d %H:%M'))
   name=nfc(p.name)
   if rename and entry.get('ten'):
    taken={n.lower() for n in (nfc(x.name) for x in folder.iterdir())}-{name.lower()}
    new=safe_name(entry['ten'],p.suffix.lower(),taken)
    if new!=name:p.rename(folder/new);name=new
   files[name]=entry;save_index(folder,index)
 emit(100,f'Đã phân tích {len(todo)} file. Ghi chú: {NOTES}',done=True,notes=str(folder/NOTES))

def undo(folder):
 folder=Path(folder).expanduser().resolve();index=load_index(folder);files=index['files'];restored={}
 for name,e in files.items():
  src=folder/name;dest=folder/e['original']
  if name!=e['original'] and src.exists() and not dest.exists():src.rename(dest);name=e['original']
  restored[name]=e
 index['files']=restored;save_index(folder,index);emit(100,'Đã trả lại tên gốc cho tư liệu.',done=True)

PLAN_Q='''Bạn là biên tập viên dựng video. Có các cảnh quay (mã số: mô tả):
{units}

Chọn cảnh minh hoạ hợp nhất cho từng câu lời đọc dưới đây. Ưu tiên cảnh đúng nội dung câu nói (người, hành động, đồ vật, cảm xúc); câu chung chung thì chọn cảnh hợp cảm xúc. Mỗi câu chọn 3 mã khác nhau, cảnh hợp nhất đứng trước; nên lấy từ các file khác nhau (tên file trong ngoặc vuông) để video đa dạng, hạn chế lặp một cảnh cho các câu liền nhau.
{lines}

Trả về đúng một JSON dạng {{"số câu": [mã1, mã2], ...}}'''

def plan(job_path,out_path):
 job=json.loads(Path(job_path).read_text(encoding='utf-8'));units=job['units'];sentences=job['sentences'];ids={u['id'] for u in units}
 unit_text='\n'.join(f'{u["id"]}: {u["text"]}' for u in units);choices={};chunk=8
 emit(0,'Đang chọn cảnh khớp với lời đọc…');model()
 for c in range(0,len(sentences),chunk):
  part=sentences[c:c+chunk]
  got=parse_json(ask(PLAN_Q.format(units=unit_text,lines='\n'.join(f'{s["id"]}. {s["text"]}' for s in part))),{})
  for s in part:
   picked=pick(got,s,ids)
   # Malformed or missing answer for this phrase: ask again for it alone.
   if not picked:picked=pick(parse_json(ask(PLAN_Q.format(units=unit_text,lines=f'{s["id"]}. {s["text"]}')),{}),s,ids)
   choices[s['id']]=picked
  emit(100*min(1,(c+chunk)/len(sentences)),f'Đã chọn cảnh cho {min(len(sentences),c+chunk)}/{len(sentences)} câu')
 stock={}
 if job.get('stock'):
  # A scene is always chosen, so ask separately whether the best one truly illustrates the phrase.
  texts={u['id']:u['text'] for u in units};missing=[]
  for n,s in enumerate(sentences):
   emit(100*n/len(sentences),f'Đang kiểm tra cảnh có hợp câu {n+1}/{len(sentences)}…')
   best=choices.get(s['id'])
   verdict=parse_json(ask(FIT_Q.format(text=s['text'],scene=texts[best[0]]),(),obj(['hop'])),{}) if best else {}
   if not best or verdict.get('hop') is not True:missing.append(s)
  stock=find_stock(missing,sentences,job['stock'])
 Path(out_path).write_text(json.dumps(dict(choices=choices,stock=stock),ensure_ascii=False),encoding='utf-8')

def pick(got,s,ids):
 raw=got.get(str(s['id'])) or []
 if not isinstance(raw,list):raw=[raw]
 return list(dict.fromkeys(int(x) for x in raw if str(x).lstrip('-').isdigit() and int(x) in ids))[:3]

FIT_Q="""Câu lời đọc: "{text}"
Cảnh quay định dùng: "{scene}"
Người xem có thấy cảnh này minh hoạ đúng ý câu nói không (đúng người, việc làm, đồ vật hoặc cảm xúc chính)? Trả về đúng một JSON: {{"hop": true hoặc false}}"""

# ---- Free stock media for phrases that none of the user's scenes illustrate ----
UA={'User-Agent':'GhepVideo/1.0 (local video editor)'}

def http_json(url,headers={}):
 with urllib.request.urlopen(urllib.request.Request(url,headers={**UA,**headers}),timeout=20) as r:return json.loads(r.read())

def download(url,folder,ext):
 dest=folder/(hashlib.sha1(url.encode()).hexdigest()[:20]+ext)
 if not dest.exists():
  tmp=dest.with_suffix('.part')
  with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=60) as r,open(tmp,'wb') as f:shutil.copyfileobj(r,f)
  tmp.replace(dest)
 return dest

def pexels_candidates(query,key):
 """Portrait videos first (moving B-roll), then portrait photos. Pexels licence: free to use, no attribution required."""
 h={'Authorization':key};q=urllib.parse.quote(query);out=[]
 for v in http_json(f'https://api.pexels.com/videos/search?query={q}&orientation=portrait&size=medium&per_page=4',h).get('videos',[]):
  files=sorted((f for f in v.get('video_files',[]) if f.get('height') and f.get('width') and f['height']>f['width'] and f['height']>=1280 and f.get('file_type')=='video/mp4'),key=lambda f:f['height'])
  if files:out.append(dict(kind='video',url=files[0]['link'],ext='.mp4',credit=f"Video của {v.get('user',{}).get('name','')} trên Pexels",page=v.get('url',''),license='Pexels License'))
 for ph in http_json(f'https://api.pexels.com/v1/search?query={q}&orientation=portrait&per_page=4',h).get('photos',[]):
  out.append(dict(kind='photo',url=ph['src']['large2x'],ext='.jpg',credit=f"Ảnh của {ph.get('photographer','')} trên Pexels",page=ph.get('url',''),license='Pexels License'))
 return out

def pixabay_candidates(query,key):
 """Pixabay API: portrait videos first, then vertical photos. Pixabay Content License: free, no attribution required."""
 q=urllib.parse.quote(query);out=[]
 for v in http_json(f'https://pixabay.com/api/videos/?key={key}&q={q}&safesearch=true&per_page=10').get('hits',[]):
  files=sorted((f for f in v.get('videos',{}).values() if f.get('url') and f.get('height',0)>f.get('width',0) and f['height']>=1280),key=lambda f:f['height'])
  if files:out.append(dict(kind='video',url=files[0]['url'],ext='.mp4',credit=f"Video của {v.get('user','')} trên Pixabay",page=v.get('pageURL',''),license='Pixabay Content License'))
 for ph in http_json(f'https://pixabay.com/api/?key={key}&q={q}&image_type=photo&orientation=vertical&safesearch=true&per_page=10').get('hits',[]):
  out.append(dict(kind='photo',url=ph.get('largeImageURL') or ph['webformatURL'],ext='.jpg',credit=f"Ảnh của {ph.get('user','')} trên Pixabay",page=ph.get('pageURL',''),license='Pixabay Content License'))
 return out[:4]+[c for c in out[4:] if c['kind']=='photo'][:2]

def openverse_candidates(query):
 """Openverse, CC0 / public-domain only, so no attribution is legally required."""
 q=urllib.parse.quote(query)
 rows=http_json(f'https://api.openverse.org/v1/images/?q={q}&license=cc0,pdm&category=photograph&page_size=20&mature=false').get('results',[])
 # Wikimedia is mostly historical and celebrity photos: not usable as everyday B-roll.
 rows=[r for r in rows if r.get('source')!='wikimedia']
 rows=[r for r in rows if min(r.get('width') or 0,r.get('height') or 0)>=600]
 rows.sort(key=lambda r:(-(r['height']>=r['width']),r.get('source')!='stocksnap'))
 return [dict(kind='photo',url=r['url'],ext='.'+(r.get('filetype') or 'jpg').lower().replace('jpeg','jpg'),credit=f"{r.get('title','')} — {r.get('creator') or 'không rõ tác giả'} ({r.get('source','')})",page=r.get('foreign_landing_url',''),license=(r.get('license') or '').upper()) for r in rows[:6]]

QUERY_Q="""Video kể chuyện sau (tiếng Việt):
{story}

Với mỗi câu dưới đây, viết 2 cụm từ tìm ảnh/video stock bằng TIẾNG ANH: cụm thứ nhất cụ thể (3-5 từ: người, hành động, đồ vật nhìn thấy được), cụm thứ hai chung hơn (1-3 từ) để dự phòng:
{lines}
Trả về đúng một JSON dạng {{"số câu": ["specific query", "general query"], ...}}"""
CHECK_Q="""Câu lời đọc: "{text}"
Hình này có minh hoạ hợp cho câu trên trong một video gia đình hiện đại không?
Trả lời false nếu hình là ảnh đen trắng hoặc ảnh cũ, người nổi tiếng / nhân vật lịch sử, tranh vẽ, có chữ hoặc logo lớn, hoặc không liên quan nội dung câu.
Trả về đúng một JSON: {{"hop": true hoặc false, "mo_ta": "1 câu mô tả hình bằng tiếng Việt"}}"""

def stock_providers(source,keys):
 """Which sites to search, in order. 'auto': every site that has a key (Pexels, then Pixabay), then Openverse."""
 if source=='auto':return [p for p in ('pexels','pixabay') if keys.get(p)]+['openverse']
 return [source] if source=='openverse' or keys.get(source) else ['openverse']

def find_stock(missing,sentences,cfg):
 if not missing:return {}
 folder=Path(cfg['folder']);folder.mkdir(parents=True,exist_ok=True)
 keys={'pexels':os.environ.get('PEXELS_API_KEY','').strip(),'pixabay':os.environ.get('PIXABAY_API_KEY','').strip()}
 providers=stock_providers(cfg.get('source','auto'),keys)
 search={'pexels':lambda q:pexels_candidates(q,keys['pexels']),'pixabay':lambda q:pixabay_candidates(q,keys['pixabay']),'openverse':openverse_candidates}
 names={'pexels':'Pexels','pixabay':'Pixabay','openverse':'Openverse'};blocked=set()
 story=' '.join(s['text'] for s in sentences)[:900]
 queries=parse_json(ask(QUERY_Q.format(story=story,lines='\n'.join(f'{s["id"]}. {s["text"]}' for s in missing))),{})
 found={}
 for n,s in enumerate(missing):
  q=queries.get(str(s['id'])) or []
  tries=[str(x).strip() for x in (q if isinstance(q,list) else [q]) if str(x).strip()]
  # Try each site in turn; move to the next one only when nothing on this site fits the phrase.
  for provider in providers:
   if provider in blocked or s['id'] in found:continue
   emit(100*n/len(missing),f'Đang tìm trên {names[provider]} cho câu: {s["text"][:40]}…')
   cands=[]
   for query in tries:
    try:cands+=[dict(c,query=query) for c in search[provider](query)[:3]]
    except Exception as exc:
     if '429' in str(exc):blocked.add(provider);emit(100*n/len(missing),f'{names[provider]} đang tạm chặn vì gọi quá nhiều, chuyển nguồn khác.');break
     secret=keys.get(provider) or '\0'
     emit(100*n/len(missing),f'Không tìm được trên {names[provider]}: '+str(exc).replace(secret,'***'))
   # The model looks at each candidate and keeps the first one that really illustrates the phrase.
   for c in cands[:5]:
    try:
     path=download(c['url'],folder,c['ext'])
     frame=still(path,(duration(path)/2 if c['kind']=='video' else None),folder/(path.stem+'-check.jpg'))
     verdict=parse_json(ask(CHECK_Q.format(text=s['text']),[frame],obj(['hop','mo_ta'])),{})
    except Exception:continue
    if verdict.get('hop') is True:
     found[s['id']]=dict(c,path=str(path),mo_ta=verdict.get('mo_ta',''),provider=provider);break
 emit(100,f'Đã thêm {len(found)} ảnh/video miễn phí cho {len(missing)} câu chưa có cảnh hợp.')
 return found

if __name__=='__main__':
 import signal
 signal.signal(signal.SIGTERM,lambda *_:sys.exit(130))
 utf8_stdio()
 try:
  cmd=sys.argv[1]
  if cmd=='analyze':analyze(sys.argv[2],rename='--no-rename' not in sys.argv)
  elif cmd=='undo':undo(sys.argv[2])
  elif cmd=='plan':plan(sys.argv[2],sys.argv[3])
  else:raise SystemExit(__doc__)
 except Exception as e:emit(-1,str(e),error=True);sys.exit(1)
