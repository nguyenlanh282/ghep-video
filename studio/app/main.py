"""Ghép Video — cross-platform desktop app (macOS + Windows).

The UI is plain HTML/JS in ui/, shown in a native window by pywebview (WebKit on macOS, Edge WebView2 on Windows).
It talks to this process over a local HTTP API on 127.0.0.1 protected by a random token; rendering and analysis
run as separate processes (renderer.py / analyzer.py) that report progress as JSON lines.

  python main.py            open the app window
  python main.py --browser  serve the UI and open it in the default browser (no pywebview needed)
"""
import json, mimetypes, os, re, secrets, subprocess, sys, threading, time, unicodedata, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

APP=Path(__file__).resolve().parent;ENGINE=APP.parent;UI=APP/'ui'
sys.path.insert(0,str(ENGINE))
from platform_tools import DATA, WINDOWS, MAC, NOWIN, utf8_stdio
import platform_tools
import updater, thumbnail

ROOT=Path(os.environ.get('GHEPVIDEO_ROOT',ENGINE.parent))  # project folder: media, recordings, output
MEDIA_EXT={'.mp4','.mov','.m4v','.mkv','.webm','.jpg','.jpeg','.png','.webp','.heic'}
AUDIO_EXT={'.m4a','.mp3','.wav','.aac','.flac','.ogg'}
TOKEN=secrets.token_urlsafe(18)
nfc=lambda s:unicodedata.normalize('NFC',s)

def find_child(parent,name):
 """Match a file name regardless of Unicode normalisation (macOS stores decomposed Vietnamese)."""
 p=Path(parent)
 try:return next((c for c in p.iterdir() if nfc(c.name)==nfc(name)),p/name)
 except OSError:return p/name

def first_audio():
 try:return next((str(p) for p in sorted(ROOT.iterdir()) if p.suffix.lower() in AUDIO_EXT),'')
 except OSError:return ''

DEFAULTS=dict(mediaFolder=str(find_child(ROOT,'Video - ảnh')),audio=first_audio(),music='',outputFolder=str(ROOT/'output'),
 title='VỢ CHỒNG',subtitle='Ai làm việc nhà?',titleStyle='pop',subStyle='sweep',musicVolume=.15,voiceVolume=1.0,normalizeVoice=True,
 shotSeconds=2.5,removeSilence=True,faceAwareFill=True,resolution='1080',fixesText='xòng => sòng\nđận => đần',
 matchScenes=True,stockEnabled=False,stockSource='auto',pexelsKey='',pixabayKey='',updateManifest='',captionY=.73,aiProvider='auto')
SECRET_KEYS={'pexelsKey','pixabayKey'}

def check_key(source,key):
 """One tiny search on the platform: 'ok', 'invalid', 'busy' (rate-limited / anti-bot page) or 'offline'."""
 import urllib.request, urllib.error
 if source=='pixabay':req=urllib.request.Request(f'https://pixabay.com/api/?key={key}&q=family&per_page=3')
 else:req=urllib.request.Request('https://api.pexels.com/v1/search?query=family&per_page=1',headers={'Authorization':key})
 req.add_header('User-Agent','GhepVideo/1.0')
 try:
  with urllib.request.urlopen(req,timeout=12) as r:return 'ok' if r.status==200 else 'invalid'
 except urllib.error.HTTPError as e:return 'invalid' if e.code in (400,401,403) else 'busy' if e.code==429 else 'offline'
 except Exception:return 'offline'

class Studio:
 def __init__(self):
  self.settings_file=DATA/'settings.json';self.settings=dict(DEFAULTS)
  try:self.settings.update({k:v for k,v in json.loads(self.settings_file.read_text(encoding='utf-8')).items() if k in DEFAULTS})
  except Exception:pass
  # Paths saved on another machine / folder may be gone: fall back to this project's defaults.
  for k in ('mediaFolder','outputFolder'):
   if not Path(self.settings[k]).is_dir():self.settings[k]=DEFAULTS[k]
  if self.settings['audio'] and not Path(self.settings['audio']).is_file():self.settings['audio']=DEFAULTS['audio']
  # A fresh copy on a new computer: create the project's media and output folders.
  for k in ('mediaFolder','outputFolder'):
   if self.settings[k]==DEFAULTS[k]:Path(self.settings[k]).mkdir(parents=True,exist_ok=True)
  self.update_info=None;self.thumbs=[];self.thumb_saved=None
  self.window=None;self.proc=None;self.lock=threading.Lock();self.media={}
  self.job=dict(running=False,task='',progress=0,status='Sẵn sàng dựng video',error=None,result=None,cancelled=False)

 # ---- settings ----
 def save(self):
  DATA.mkdir(parents=True,exist_ok=True);tmp=self.settings_file.with_suffix('.tmp')
  tmp.write_text(json.dumps(self.settings,ensure_ascii=False,indent=1),encoding='utf-8');tmp.replace(self.settings_file)

 def set(self,values):
  for k,v in values.items():
   if k not in DEFAULTS:continue
   want=type(DEFAULTS[k])
   if want is float:v=float(v)
   elif want is bool:v=bool(v)
   else:v=str(v)
   self.settings[k]=v
  self.save();return self.state()

 # ---- state for the UI ----
 def media_names(self):
  try:return [p.name for p in Path(self.settings['mediaFolder']).iterdir() if p.is_file() and not p.name.startswith(('.','_')) and p.suffix.lower() in MEDIA_EXT]
  except OSError:return []

 def analysis(self):
  names={nfc(n) for n in self.media_names()}
  try:files=json.loads((Path(self.settings['mediaFolder'])/'_phan-tich.json').read_text(encoding='utf-8'))['files']
  except Exception:files={}
  notes=[dict(name=k,kind=v.get('kind',''),text=v.get('mo_ta',''),scenes=len(v.get('scenes') or [1]),original=v.get('original','')) for k,v in sorted(files.items()) if nfc(k) in names]
  return notes

 def state(self):
  s={k:v for k,v in self.settings.items() if k not in SECRET_KEYS}
  s.update({k+'Set':bool(self.settings[k]) for k in SECRET_KEYS})
  # Only the last 4 characters ever reach the UI, so the saved key can be recognised without exposing it.
  s.update({k+'Hint':('••••'+self.settings[k][-4:]) if self.settings[k] else '' for k in SECRET_KEYS})
  notes=self.analysis()
  return dict(settings=s,mediaCount=len(self.media_names()),notes=notes,analyzedCount=len(notes),sceneCount=sum(n['scenes'] for n in notes),
   job=dict(self.job),platform='windows' if WINDOWS else 'mac' if MAC else 'linux',version=updater.current_version(),ai=self.ai_state(),
   update=self.update_info,thumbs=[dict(id=c['id'],preview=self.url(c['preview']),fits=c.get('fits',True),tilt=c.get('tilt',0),
    source=c['source'],time=c.get('time'),upload=c.get('upload',False)) for c in self.thumbs],thumbSaved=self.thumb_saved,backups=[p.stem for p in updater.backups(DATA)][:3],updateConfigured=bool(updater.manifest_url(self.settings)),
   audioUrl=self.url(self.settings['audio']),musicUrl=self.url(self.settings['music']),resultUrl=self.url(self.job['result']))

 def url(self,path):
  """Register a local file for the UI's <video>/<audio> elements; returns a tokenised URL."""
  if not path or not Path(path).is_file():return None
  key=uuid.uuid5(uuid.NAMESPACE_URL,str(path)).hex[:16];self.media[key]=str(path)
  return f'/m/{TOKEN}/{key}/{Path(path).name}'

 # ---- dialogs and OS helpers ----
 def choose(self,kind):
  if not self.window:return dict(error='Hộp thoại chọn file chỉ có trong cửa sổ app. Hãy dán đường dẫn vào ô.')
  import webview
  folder=kind in ('media','output')
  current=self.settings.get({'media':'mediaFolder','output':'outputFolder','audio':'audio','music':'music'}[kind]) or str(ROOT)
  start=current if Path(current).is_dir() else str(Path(current).parent) if Path(current).parent.is_dir() else str(ROOT)
  dialog=getattr(webview,'FileDialog',None)
  kind_folder=dialog.FOLDER if dialog else webview.FOLDER_DIALOG;kind_open=dialog.OPEN if dialog else webview.OPEN_DIALOG
  types=() if folder else ('Âm thanh (*.m4a;*.mp3;*.wav;*.aac;*.flac;*.ogg)','Tất cả (*.*)')
  picked=self.window.create_file_dialog(kind_folder if folder else kind_open,directory=start,file_types=types)
  if not picked:return self.state()
  path=picked[0] if isinstance(picked,(list,tuple)) else picked
  return self.set({{'media':'mediaFolder','output':'outputFolder','audio':'audio','music':'music'}[kind]:path})

 def reveal(self,path=None):
  path=path or self.job['result'] or self.settings['outputFolder']
  if WINDOWS:subprocess.Popen(['explorer','/select,',str(Path(path))] if Path(path).is_file() else ['explorer',str(Path(path))])
  elif MAC:subprocess.Popen(['open','-R',path] if Path(path).is_file() else ['open',path])
  else:subprocess.Popen(['xdg-open',str(Path(path).parent if Path(path).is_file() else path)])
  return {}

 def open_path(self,path):
  if WINDOWS:os.startfile(path)
  elif MAC:subprocess.Popen(['open',path])
  else:subprocess.Popen(['xdg-open',path])
  return {}

 def open_notes(self):return self.open_path(str(Path(self.settings['mediaFolder'])/'_ghi-chu-tu-lieu.md'))

 # ---- picture AI: on this computer, or the customer's own Claude / ChatGPT subscription ----
 def ai_state(self):
  now=time.time()
  if not getattr(self,'_ai',None) or now-self._ai[0]>10:self._ai=(now,platform_tools.ai_status())  # cheap, but state is polled
  status=self._ai[1];choice=self.settings['aiProvider'] if self.settings['aiProvider'] in ('claude','codex') else 'auto'
  used=choice if choice!='auto' else next((p for p in ('claude','codex') if status[p]),None)
  return dict(status=status,used=used,ready=bool(used and status.get(used)))

 def open_link(self,url):
  if url in ('https://pixabay.com/api/docs/','https://www.pexels.com/api/','https://code.claude.com/docs/en/setup','https://developers.openai.com/codex/cli'):webbrowser.open(url)
  return {}

 # ---- background tasks ----
 def cache(self):
  c=Path(self.settings['outputFolder'])/'.studio-cache' if Path(self.settings['outputFolder']).is_dir() else DATA/'cache'
  c.mkdir(parents=True,exist_ok=True);return c

 def start(self,task,preview=False):
  if self.job['running']:return dict(error='Đang có tác vụ chạy.')
  s=self.settings;names=self.media_names()
  if not names:return self.fail('Hãy chọn thư mục có ảnh hoặc video.')
  if task=='render':
   if not Path(s['audio']).is_file():return self.fail('Hãy chọn file ghi âm.')
   if not Path(s['outputFolder']).is_dir():return self.fail('Hãy chọn thư mục lưu video.')
   analysed=len(self.analysis())>0
   job={k:s[k] for k in ('mediaFolder','audio','music','outputFolder','title','subtitle','titleStyle','subStyle','musicVolume','shotSeconds','resolution','removeSilence','faceAwareFill','fixesText','voiceVolume','normalizeVoice','stockSource','captionY')}
   job.update(preview=bool(preview),cacheFolder=str(self.cache()),matchScenes=s['matchScenes'] and analysed,stockEnabled=s['stockEnabled'] and s['matchScenes'] and analysed,aiPython=sys.executable)
   job_file=self.cache()/f'job-{uuid.uuid4().hex}.json';job_file.write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
   args=[str(ENGINE/'renderer.py'),str(job_file)];log='render.log';cleanup=lambda:job_file.unlink(missing_ok=True)
  elif task in ('analyze','undo'):
   args=[str(ENGINE/'analyzer.py'),task,s['mediaFolder']];log='analyze.log';cleanup=lambda:None
  else:return dict(error='Tác vụ không hợp lệ.')
  env=dict(os.environ,PYTHONUNBUFFERED='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',GHEPVIDEO_AI=s['aiProvider'] if s['aiProvider'] in ('claude','codex') else 'auto')
  if MAC:env['HF_HUB_OFFLINE']='1';env['PATH']='/opt/homebrew/bin:/usr/local/bin:'+env.get('PATH','')
  # API keys travel only through the environment, never into job or result files.
  if s['pexelsKey']:env['PEXELS_API_KEY']=s['pexelsKey']
  if s['pixabayKey']:env['PIXABAY_API_KEY']=s['pixabayKey']
  logf=open(self.cache()/log,'wb')
  self.proc=subprocess.Popen([sys.executable,'-u',*args],stdout=subprocess.PIPE,stderr=logf,env=env,cwd=str(ENGINE),**NOWIN)
  self.job=dict(running=True,task=task,progress=0,status='Đang chuẩn bị…',error=None,result=None if task=='render' else self.job.get('result'),cancelled=False,log=log)
  threading.Thread(target=self.watch,args=(self.proc,logf,cleanup),daemon=True).start()
  return self.state()

 def fail(self,message):
  self.job.update(error=message);return self.state()

 def watch(self,proc,logf,cleanup):
  for raw in proc.stdout:
   try:msg=json.loads(raw.decode('utf-8'))
   except Exception:continue
   with self.lock:
    if isinstance(msg.get('progress'),(int,float)):self.job['progress']=max(0,msg['progress'])/100
    if msg.get('message'):self.job['status']=msg['message']
    if msg.get('error'):self.job['error']=msg['message']
    if msg.get('output'):self.job['result']=msg['output']
  code=proc.wait();logf.close();cleanup()
  with self.lock:
   self.job['running']=False
   if self.job['cancelled']:self.job['status']='Đã dừng xuất video' if self.job['task']=='render' else 'Đã dừng phân tích'
   elif code!=0 and not self.job['error']:self.job['error']=f"Chưa thành công. Xem chi tiết tại {self.cache()/self.job['log']}";self.job['status']='Cần kiểm tra lại'

 def cancel(self):
  p=self.proc
  if p and p.poll() is None:
   self.job['cancelled']=True
   # Windows has no SIGTERM for child trees: kill the renderer and its ffmpeg processes together.
   if WINDOWS:subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,**NOWIN)
   else:p.terminate()
  return self.state()

 def save_key(self,source,value):
  """Save (or clear, when empty) the API key of one platform, after checking it really works."""
  if source not in ('pixabay','pexels'):return dict(error='Nguồn không hợp lệ.')
  value=value.strip()
  if not value:self.settings[source+'Key']='';self.save();return dict(self.state(),check='cleared')
  # Save only a key the platform has accepted: a wrong key, or no connection, never replaces the saved one.
  check=check_key(source,value)
  if check!='ok':return dict(self.state(),check=check)
  self.settings[source+'Key']=value;self.save()
  return dict(self.state(),check='ok')

 def listen(self,mode):
  """30-second preview mixed exactly like the export: measured voice gain, music level, limiter."""
  import renderer
  from platform_tools import FFMPEG
  s=self.settings;voice=s['audio'] if Path(s['audio']).is_file() else '';music=s['music'] if Path(s['music']).is_file() else ''
  if mode in ('voice','mix') and not voice:return dict(error='Hãy chọn file ghi âm.')
  if mode in ('music','mix') and not music:return dict(error='Hãy chọn nhạc nền.')
  cache=self.cache();secs=30
  job=dict(voiceVolume=s['voiceVolume'],normalizeVoice=s['normalizeVoice'])
  vol=max(0,min(1,float(s['musicVolume'])));fade=f'afade=t=out:st={secs-1.2}:d=1.2'
  args=[FFMPEG,'-v','error','-y']
  # Load only what this preview plays, so input [0] is always the right file.
  if mode!='music':args+=['-t',str(secs),'-i',voice]
  if mode!='voice':args+=['-stream_loop','-1','-i',music]
  if mode=='voice':graph=f'[0:a]volume={renderer.voice_gain_db(Path(voice),job,cache):.2f}dB,alimiter=limit=0.79:level=0[a]'
  elif mode=='music':graph=f'[0:a]volume={vol},{fade}[a]'
  else:graph=(f'[0:a]asetpts=PTS-STARTPTS,volume={renderer.voice_gain_db(Path(voice),job,cache):.2f}dB[voice];[1:a]asetpts=PTS-STARTPTS,volume={vol},{fade}[music];'
              '[voice][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.79:level=0[a]')
  out=cache/f'nghe-thu-{mode}.m4a'
  p=subprocess.run(args+['-filter_complex',graph,'-map','[a]','-t',str(secs),'-c:a','aac','-b:a','160k',str(out)],capture_output=True,**NOWIN)
  if p.returncode:return dict(error='Không tạo được bản nghe thử: '+p.stderr.decode(errors='replace')[-300:])
  return dict(url=self.url(str(out))+f'?v={time.time():.0f}')

 # ---- thumbnails ----
 def thumb_job(self):
  """The render whose footage to search: the last exported video, else the newest one in the output folder."""
  out=Path(self.job['result']).with_suffix('.json') if self.job.get('result') else None
  if not (out and out.exists()):
   found=sorted(Path(self.settings['outputFolder']).glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
   out=found[0] if found else None
  try:return json.loads(out.read_text(encoding='utf-8')),out
  except Exception:return {},None

 def thumb_find(self):
  if self.job['running']:return dict(error='Đang có tác vụ chạy.')
  self.job=dict(running=True,task='thumbs',progress=0,status='Đang tìm hình rõ mặt…',error=None,result=self.job.get('result'),cancelled=False,log='')
  def work():
   try:
    job,_=self.thumb_job()
    uploads=[c for c in self.thumbs if c.get('upload')]
    found=thumbnail.find_candidates(job,job.get('mediaFolder') or self.settings['mediaFolder'],self.cache()/'thumbs',
                                    progress=lambda p,m:self.job.update(progress=p/100,status=m))
    self.thumbs=uploads+found
    if not found:self.job['status']='Không tìm thấy khung hình có mặt người rõ. Hãy tải ảnh lên.'
   except Exception as exc:self.job.update(error=f'Chưa tìm được hình: {exc}')
   finally:self.job['running']=False
  threading.Thread(target=work,daemon=True).start()
  return self.state()

 def thumb_upload(self,name,data):
  if len(data)>60*1024*1024:return dict(error='Ảnh quá lớn (tối đa 60 MB).')
  folder=self.cache()/'thumbs'/'uploads';folder.mkdir(parents=True,exist_ok=True)
  src=folder/(uuid.uuid4().hex+Path(name).suffix.lower()[:6]);src.write_bytes(data)
  c=thumbnail.add_upload(src,self.cache()/'thumbs');src.unlink(missing_ok=True)
  c['id']='u'+uuid.uuid4().hex[:6];self.thumbs=[c]+self.thumbs
  return dict(self.state(),added=c['id'])

 def thumb_pick(self,ids):
  chosen=[next((c for c in self.thumbs if c['id']==i),None) for i in ids]
  if not chosen or None in chosen or not 1<=len(chosen)<=3:raise ValueError('Hãy chọn từ 1 đến 3 hình.')
  return chosen

 def thumb_compose(self,ids,text):
  s=self.settings;chosen=self.thumb_pick(ids)
  full=thumbnail.compose(chosen,self.cache()/'thumbs'/'bia-xem-truoc.jpg',s['title'],s['subtitle'],s['titleStyle'],text)
  from PIL import Image
  small=self.cache()/'thumbs'/'bia-xem-truoc-nho.jpg';Image.open(full).resize((540,960)).save(small,quality=88)
  return dict(url=self.url(str(small))+f'?v={time.time():.3f}')

 def thumb_save(self,ids,text):
  s=self.settings;chosen=self.thumb_pick(ids);_,src=self.thumb_job()
  folder=Path(s['outputFolder']);name=(src.stem if src else 'Video-'+time.strftime('%Y%m%d-%H%M%S'))+'-anh-bia'
  dest=folder/(name+'.jpg');n=2
  while dest.exists():dest=folder/f'{name}-{n}.jpg';n+=1
  thumbnail.compose(chosen,dest,s['title'],s['subtitle'],s['titleStyle'],text)
  self.thumb_saved=str(dest);return dict(self.state(),saved=str(dest))

 # ---- updates ----
 def check_update(self):
  try:
   info=updater.check(self.settings)
   if info.get('manifest'):info['notes']=info['manifest'].get('notes','');info['size']=info['manifest'].get('size',0);info.pop('manifest')
   self.update_info=info
  except Exception as exc:self.update_info=dict(error=f'Không kiểm tra được cập nhật: {exc}')
  return self.state()

 def run_update(self,kind):
  """Install the newer version (or roll back) in the background, reporting progress like a render."""
  if self.job['running']:return dict(error='Đang có tác vụ chạy.')
  self.job=dict(running=True,task='update',progress=0,status='Đang chuẩn bị cập nhật…',error=None,result=self.job.get('result'),cancelled=False,log='')
  def progress(p,m):self.job.update(progress=p/100,status=m)
  def work():
   try:
    out=updater.update(self.settings,DATA,sys.executable,progress) if kind=='update' else updater.rollback(DATA,sys.executable,progress)
    self.job['restartNeeded']=bool(out.get('installed',True))
    if kind=='update' and not out.get('installed'):self.job['status']='Đang dùng bản mới nhất.'
   except Exception as exc:self.job.update(error=str(exc),status='Cập nhật chưa thành công · app vẫn là bản cũ')
   finally:self.job['running']=False;self.update_info=None
  threading.Thread(target=work,daemon=True).start()
  return self.state()

 def restart(self):
  """Start a fresh copy of the app, then close this one."""
  if self.job['running']:return dict(error='Đang có tác vụ chạy.')
  if MAC and (ROOT/'Ghép Video.app').exists():subprocess.Popen(['/bin/sh','-c',f'sleep 1; open -n "{ROOT/"Ghép Video.app"}"'],start_new_session=True)
  else:
   exe=Path(sys.executable);exe=exe.with_name('pythonw.exe') if WINDOWS and exe.with_name('pythonw.exe').exists() else exe
   subprocess.Popen([str(exe),str(APP/'main.py')],cwd=str(ENGINE),**({'creationflags':0x00000008|0x00000200} if WINDOWS else {'start_new_session':True}))
  threading.Timer(.5,lambda:os._exit(0)).start()
  return {}

 def clear_error(self):
  self.job['error']=None;return self.state()

studio=Studio()
API={'state':lambda b:studio.state(),'set':lambda b:studio.set(b.get('values',{})),'choose':lambda b:studio.choose(b['kind']),
 'start':lambda b:studio.start(b['task'],b.get('preview',False)),'cancel':lambda b:studio.cancel(),'reveal':lambda b:studio.reveal(),
 'openNotes':lambda b:studio.open_notes(),'openLink':lambda b:studio.open_link(b.get('url','')),'clearError':lambda b:studio.clear_error(),
 'saveKey':lambda b:studio.save_key(b.get('source',''),b.get('value','')),'listen':lambda b:studio.listen(b.get('mode','mix')),
 'checkUpdate':lambda b:studio.check_update(),'applyUpdate':lambda b:studio.run_update('update'),'rollback':lambda b:studio.run_update('rollback'),
 'restart':lambda b:studio.restart(),
 'thumbFind':lambda b:studio.thumb_find(),'thumbCompose':lambda b:studio.thumb_compose(b.get('ids',[]),b.get('text',True)),
 'thumbSave':lambda b:studio.thumb_save(b.get('ids',[]),b.get('text',True)),'thumbReveal':lambda b:studio.reveal(studio.thumb_saved)}

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass

 def send(self,code,body,ctype='application/json; charset=utf-8',extra=()):
  self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
  for k,v in extra:self.send_header(k,v)
  self.end_headers()
  if self.command!='HEAD':self.wfile.write(body)

 def do_POST(self):
  path=urlparse(self.path).path
  if self.headers.get('X-Token')!=TOKEN:return self.send(403,b'{}')
  if path=='/upload':
   # Raw image bytes from the page's file picker (works in the app window and in a browser).
   from urllib.parse import unquote as uq
   try:out=studio.thumb_upload(uq(self.headers.get('X-Filename','anh.jpg')),self.rfile.read(int(self.headers.get('Content-Length') or 0)))
   except Exception as exc:out=dict(error=str(exc))
   return self.send(200,json.dumps(out,ensure_ascii=False).encode())
  if not path.startswith('/api/'):return self.send(403,b'{}')
  body=json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
  fn=API.get(path[5:])
  if not fn:return self.send(404,b'{}')
  try:out=fn(body)
  except Exception as exc:out=dict(error=str(exc))
  self.send(200,json.dumps(out,ensure_ascii=False).encode())

 def do_HEAD(self):self.do_GET()

 def do_GET(self):
  url=urlparse(self.path);parts=url.path.split('/')
  if url.path.startswith('/m/'):
   if len(parts)<4 or parts[2]!=TOKEN or parts[3] not in studio.media:return self.send(403,b'')
   return self.file(Path(studio.media[parts[3]]))
  if url.path in ('/','/index.html'):
   if parse_qs(url.query).get('t',[''])[0]!=TOKEN:return self.send(403,'Mở app bằng cửa sổ Ghép Video.'.encode(),'text/plain; charset=utf-8')
   return self.file(UI/'index.html')
  target=(UI/unquote(url.path).lstrip('/')).resolve()
  if UI.resolve() not in target.parents or not target.is_file():return self.send(404,b'')
  return self.file(target)

 def file(self,path):
  """Static file with HTTP Range support (WebKit will not play <video> without it)."""
  size=path.stat().st_size;ctype=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
  if path.suffix.lower()=='.m4a':ctype='audio/mp4'
  rng=re.match(r'bytes=(\d*)-(\d*)',self.headers.get('Range',''))
  start,end=0,size-1
  if rng and (rng.group(1) or rng.group(2)):
   if rng.group(1):start=int(rng.group(1));end=int(rng.group(2)) if rng.group(2) else size-1
   else:start=max(0,size-int(rng.group(2)))
   end=min(end,size-1)
  length=max(0,end-start+1)
  self.send_response(206 if rng else 200);self.send_header('Content-Type',ctype);self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(length))
  if rng:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.end_headers()
  if self.command=='HEAD':return
  with open(path,'rb') as f:
   f.seek(start);left=length
   try:
    while left>0:
     chunk=f.read(min(1<<20,left))
     if not chunk:break
     self.wfile.write(chunk);left-=len(chunk)
   except (BrokenPipeError,ConnectionResetError):pass

def serve():
 server=ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('GHEPVIDEO_PORT','0'))),Handler)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 return f'http://127.0.0.1:{server.server_address[1]}/?t={TOKEN}',server

def main():
 utf8_stdio();url,server=serve()
 if '--browser' in sys.argv or '--serve' in sys.argv:
  print(url,flush=True)
  if '--browser' in sys.argv:webbrowser.open(url)
  try:
   while True:time.sleep(3600)
  except KeyboardInterrupt:return
 import webview
 studio.window=webview.create_window('Ghép Video',url,width=1240,height=900,min_size=(980,700),background_color='#0b0f14')
 webview.start()
 studio.cancel()

if __name__=='__main__':main()
