"""Ghép Video — cross-platform desktop app (macOS + Windows).

The UI is plain HTML/JS in ui/, shown in a native window by pywebview (WebKit on macOS, Edge WebView2 on Windows).
It talks to this process over a local HTTP API on 127.0.0.1 protected by a random token; rendering and analysis
run as separate processes (renderer.py / analyzer.py) that report progress as JSON lines.

  python main.py            open the app window
  python main.py --browser  serve the UI and open it in the default browser (no pywebview needed)
"""
import hashlib, json, mimetypes, os, re, secrets, subprocess, sys, threading, time, unicodedata, uuid, webbrowser

def _crash(kind, err, tb):
 """The Windows shortcut starts the app with pythonw (no console): without this a start-up error just closes
 silently. Write it to a log and show it in a message box, so the customer can send a screenshot."""
 import traceback
 text=''.join(traceback.format_exception(kind,err,tb))
 home=Path(os.environ.get('APPDATA') or Path.home()/'Library'/'Application Support')/'GhepVideo'
 try:home.mkdir(parents=True,exist_ok=True);(home/'loi-khoi-dong.txt').write_text(time.strftime('%Y-%m-%d %H:%M:%S\n')+text,encoding='utf-8')
 except Exception:pass
 if sys.platform=='win32':
  try:
   import ctypes
   if os.environ.get('GHEPVIDEO_NO_DIALOG'):ctypes.windll.user32.MessageBoxW=lambda *a:0  # automated checks
   setup=Path(__file__).resolve().parent.parent/'setup-windows.ps1'
   if issubclass(kind,ImportError) and setup.is_file():
    # A library is missing (install cut short, antivirus…): run the installer's library step again, it reopens the app.
    subprocess.Popen(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(setup)],creationflags=0x10)  # new console
    ctypes.windll.user32.MessageBoxW(None,f'Ghép Video thiếu thư viện ({getattr(err,"name",None) or err}).\n\nApp đang tự cài lại trong cửa sổ xanh vừa mở. Đừng đóng cửa sổ đó; cài xong app sẽ tự mở (vài phút).','Ghép Video · đang tự sửa',0x40)
   else:ctypes.windll.user32.MessageBoxW(None,'Ghép Video không mở được. Chụp màn hình này gửi người hỗ trợ.\n\n'+text[-1500:]+f'\n\nĐã lưu: {home/"loi-khoi-dong.txt"}','Ghép Video · lỗi khởi động',0x10)
  except Exception:pass
 sys.__excepthook__(kind,err,tb)
sys.excepthook=_crash
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
 shotSeconds=2.5,removeSilence=True,faceAwareFill=True,resolution='1080',aspect='9:16',fixesText='xòng => sòng\nđận => đần',
 matchScenes=True,stockEnabled=False,stockSource='auto',pexelsKey='',pixabayKey='',updateManifest='',captionY=.73,aiProvider='auto',titleSeconds=3.0,
 titleScale=1.0,titleEffect='bounce',subScale=1.0,subFont='arial',aiSpelling=True,
 # colour grade of both modes (JSON: slider values + chosen look) and the user's saved grades (JSON list)
 grade='{}',gradePresets='[]',
 # voice-over: a recording ('file') or MiniMax Speech from text ('minimax', the user's own key and cloned voice)
 voiceSource='file',ttsText='',minimaxVoice='',minimaxModel='speech-2.8-hd',minimaxSpeed=1.0,minimaxRegion='intl',minimaxKey='',
 # Video chia sẻ (talking-video editor)
 talkVideo='',talkVideos='[]',talkBrollFolder=str(find_child(ROOT,'Video - ảnh')),talkBroll=True,talkDensity='vua',talkAspects='9:16',
 talkPunchIn=True,talkDenoise=True,talkRetakes=True,talkKeywords=True,talkShorts=True,
 talkFill=True)  # upright video in a 16:9 / 1:1 frame: fill it (crop top and bottom) or keep the whole picture on a blurred copy
TALK_DENSITY={'it':.18,'vua':.3,'nhieu':.45}
SECRET_KEYS={'pexelsKey','pixabayKey','minimaxKey'}

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
  vids=self.talk_videos()  # drops raw videos that are gone
  self.settings['talkVideos']=json.dumps(vids,ensure_ascii=False);self.settings['talkVideo']=vids[0] if vids else ''
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
  if 'talkVideos' in values:vids=self.talk_videos();self.settings['talkVideos']=json.dumps(vids,ensure_ascii=False);self.settings['talkVideo']=vids[0] if vids else ''
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
  import renderer
  looks=[dict(id=k,name=n,grade=g) for k,(n,g) in renderer.LOOKS.items()]
  return dict(grade=dict(looks=looks,presets=self.grade_presets()),settings=s,mediaCount=len(self.media_names()),notes=notes,analyzedCount=len(notes),sceneCount=sum(n['scenes'] for n in notes),
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
  keys={'media':'mediaFolder','output':'outputFolder','audio':'audio','music':'music','talkVideo':'talkVideo','talkBroll':'talkBrollFolder'}
  folder=kind in ('media','output','talkBroll')
  current=self.settings.get(keys[kind]) or str(ROOT)
  start=current if Path(current).is_dir() else str(Path(current).parent) if Path(current).parent.is_dir() else str(ROOT)
  dialog=getattr(webview,'FileDialog',None)
  kind_folder=dialog.FOLDER if dialog else webview.FOLDER_DIALOG;kind_open=dialog.OPEN if dialog else webview.OPEN_DIALOG
  types=() if folder else ('Video (*.mp4;*.mov;*.m4v;*.mkv;*.webm)','Tất cả (*.*)') if kind=='talkVideo' else ('Âm thanh (*.m4a;*.mp3;*.wav;*.aac;*.flac;*.ogg)','Tất cả (*.*)')
  picked=self.window.create_file_dialog(kind_folder if folder else kind_open,directory=start,file_types=types,allow_multiple=kind=='talkVideo')
  if not picked:return self.state()
  if kind=='talkVideo':  # several raw videos, added after the ones already chosen, numbered in that order
   paths=list(picked) if isinstance(picked,(list,tuple)) else [picked]
   return self.set_talk_videos(self.talk_videos()+[p for p in paths if p not in self.talk_videos()])
  path=picked[0] if isinstance(picked,(list,tuple)) else picked
  return self.set({keys[kind]:path})

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
  if url in ('https://pixabay.com/api/docs/','https://www.pexels.com/api/','https://code.claude.com/docs/en/setup','https://developers.openai.com/codex/cli','https://zalo.me/g/gimz1uxcifvaydqar800'):webbrowser.open(url)
  return {}

 # ---- background tasks ----
 def cache(self):
  c=Path(self.settings['outputFolder'])/'.studio-cache' if Path(self.settings['outputFolder']).is_dir() else DATA/'cache'
  c.mkdir(parents=True,exist_ok=True);return c

 def start(self,task,preview=False):
  if self.job['running']:return dict(error='Đang có tác vụ chạy.')
  s=self.settings;names=self.media_names()
  if not names and task in ('render','analyze','undo'):return self.fail('Hãy chọn thư mục có ảnh hoặc video.')
  if task in ('talk-analyze','talk-render'):
   if not self.talk_videos():return self.fail('Hãy chọn video thô.')
   if task=='talk-render' and not self.talk_project():return self.fail('Hãy bấm “Phân tích video” trước.')
   job=dict(video=self.talk_videos()[0],videos=self.talk_videos(),grade=self.grade(),projectDir=str(self.talk_dir()),cacheFolder=str(self.cache()),brollFolder=s['talkBrollFolder'],broll=s['talkBroll'],
            brollDensity=TALK_DENSITY.get(s['talkDensity'],.3),stockEnabled=s['stockEnabled'],stockSource=s['stockSource'],cutRetakes=s['talkRetakes'],
            fixesText=s['fixesText'],outputFolder=s['outputFolder'],titleStyle=s['titleStyle'],titleSeconds=s['titleSeconds'],titleScale=s['titleScale'],titleEffect=s['titleEffect'],subScale=s['subScale'],subFont=s['subFont'],aiSpelling=s['aiSpelling'],subStyle=s['subStyle'],captionY=s['captionY'],
            aspects=[a for a in s['talkAspects'].split(',') if a],exportShorts=s['talkShorts'],talkFill=s['talkFill'],punchIn=s['talkPunchIn'],denoise=s['talkDenoise'],
            highlightKeywords=s['talkKeywords'],voiceVolume=s['voiceVolume'],normalizeVoice=s['normalizeVoice'],music=s['music'],musicVolume=s['musicVolume'],aiPython=sys.executable)
   if task=='talk-render':
    proj=self.talk_project() or {};pick=proj.get('title_choice') or (proj.get('titles') or [{}])[0]  # ⚡ exports before the editor saves a choice
    job.update(title=pick.get('dong1',''),subtitle=pick.get('dong2',''))
   job_file=self.cache()/f'job-{uuid.uuid4().hex}.json';job_file.write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
   args=[str(ENGINE/'talk.py'),task[5:],str(job_file)];log='talk.log';cleanup=lambda:job_file.unlink(missing_ok=True)
  elif task in ('render','plan'):
   if not Path(s['audio']).is_file():return self.fail('Hãy chọn file ghi âm.')
   if not Path(s['outputFolder']).is_dir():return self.fail('Hãy chọn thư mục lưu video.')
   analysed=len(self.analysis())>0
   job={k:s[k] for k in ('mediaFolder','audio','music','outputFolder','title','subtitle','titleStyle','subStyle','musicVolume','shotSeconds','resolution','aspect','removeSilence','faceAwareFill','fixesText','voiceVolume','normalizeVoice','stockSource','captionY','titleSeconds','titleScale','titleEffect','subScale','subFont','aiSpelling')}
   pf=self.story_file()
   if pf:self.story_save();job['projectFile']=str(pf)   # settings + timeline of this narration + media folder
   if task=='plan':job['planOnly']=True
   # The MiniMax voice-over's own script is the reference text for the AI spelling check.
   if s['voiceSource']=='minimax' and s['ttsText'].strip() and 'Giọng đọc - ' in Path(s['audio']).name:job['script']=s['ttsText']
   # Matching scenes needs every photo/video analysed: the renderer analyses the new ones first (the AI must be ready).
   ai_ready=self.ai_state()['ready'];match=s['matchScenes'] and (analysed or ai_ready)
   job.update(preview=bool(preview),grade=self.grade(),cacheFolder=str(self.cache()),matchScenes=match,autoAnalyze=match and ai_ready,
              stockEnabled=s['stockEnabled'] and match,context=s['title']+(' · '+s['subtitle'] if s['subtitle'] else ''),aiPython=sys.executable)
   job_file=self.cache()/f'job-{uuid.uuid4().hex}.json';job_file.write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
   args=[str(ENGINE/'renderer.py'),str(job_file)];log='render.log';cleanup=lambda:job_file.unlink(missing_ok=True)
  elif task=='tts':
   if not s['minimaxKey']:return self.fail('Hãy dán API key MiniMax rồi bấm Lưu.')
   if not s['ttsText'].strip():return self.fail('Hãy nhập nội dung cần đọc.')
   if not s['minimaxVoice'].strip():return self.fail('Hãy nhập Voice ID (giọng đã clone trên MiniMax).')
   job=dict(text=s['ttsText'],voice=s['minimaxVoice'],model=s['minimaxModel'],speed=s['minimaxSpeed'],region=s['minimaxRegion'],
            outDir=str(Path(s['outputFolder'])/'Giọng đọc MiniMax' if Path(s['outputFolder']).is_dir() else DATA/'giong-doc'))
   job_file=self.cache()/f'job-{uuid.uuid4().hex}.json';job_file.write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
   args=[str(ENGINE/'tts.py'),str(job_file)];log='tts.log';cleanup=lambda:job_file.unlink(missing_ok=True)
  elif task in ('analyze','undo'):
   args=[str(ENGINE/'analyzer.py'),task,s['mediaFolder']];log='analyze.log';cleanup=lambda:None
  else:return dict(error='Tác vụ không hợp lệ.')
  env=dict(os.environ,PYTHONUNBUFFERED='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',GHEPVIDEO_AI=s['aiProvider'] if s['aiProvider'] in ('claude','codex') else 'auto')
  if MAC:env['HF_HUB_OFFLINE']='1';env['PATH']='/opt/homebrew/bin:/usr/local/bin:'+env.get('PATH','')
  # API keys travel only through the environment, never into job or result files.
  if s['pexelsKey']:env['PEXELS_API_KEY']=s['pexelsKey']
  if s['pixabayKey']:env['PIXABAY_API_KEY']=s['pixabayKey']
  if task=='tts':env['MINIMAX_API_KEY']=s['minimaxKey']
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
    if msg.get('audio') and Path(msg['audio']).is_file():self.settings['audio']=msg['audio'];self.save()  # the new voice-over becomes the recording
  code=proc.wait();logf.close();cleanup()
  with self.lock:
   self.job['running']=False
   if self.job['cancelled']:self.job['status']={'render':'Đã dừng xuất video','tts':'Đã dừng tạo giọng đọc'}.get(self.job['task'],'Đã dừng phân tích')
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
  if source not in ('pixabay','pexels','minimax'):return dict(error='Nguồn không hợp lệ.')
  value=value.strip()
  if not value:self.settings[source+'Key']='';self.save();return dict(self.state(),check='cleared')
  # MiniMax has no free test call (every request is billed): the key is checked on the first voice-over.
  if source=='minimax':self.settings['minimaxKey']=value;self.save();return dict(self.state(),check='saved')
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

 # ---- Video chia sẻ ----
 def talk_dir(self):
  vids=[Path(v) for v in self.talk_videos()]
  sig='|'.join(f'{v.resolve()}|{v.stat().st_size if v.exists() else 0}' for v in vids)  # one video: same key as before
  return self.cache()/'talk'/hashlib.sha1(sig.encode()).hexdigest()[:16]

 def talk_videos(self):
  try:vids=[str(v) for v in json.loads(self.settings['talkVideos'] or '[]')]
  except Exception:vids=[]
  if not vids and self.settings['talkVideo']:vids=[self.settings['talkVideo']]
  return [v for v in vids if Path(v).is_file()]

 def set_talk_videos(self,vids):
  vids=[str(v) for v in vids][:50]
  self.settings['talkVideos']=json.dumps(vids,ensure_ascii=False);self.settings['talkVideo']=vids[0] if vids else ''
  self.save();return self.state()

 def talk_videos_op(self,b):
  vids=self.talk_videos();op=b.get('op');i=int(b.get('index',-1))
  if op=='remove' and 0<=i<len(vids):vids.pop(i)
  elif op=='move' and 0<=i<len(vids):
   j=i+(1 if b.get('dir',1)>0 else -1)
   if 0<=j<len(vids):vids[i],vids[j]=vids[j],vids[i]
  elif op=='sort':
   natural=lambda p:[int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)',Path(p).name)]
   vids.sort(key=natural)
  elif op=='clear':vids=[]
  return self.set_talk_videos(vids)

 # ---- projects: everything worked on is kept, so it can be opened and edited again ----
 STORY_KEYS=('mediaFolder','audio','music','title','subtitle','titleStyle','titleEffect','titleScale','titleSeconds','subStyle','subScale','subFont','captionY',
             'musicVolume','voiceVolume','normalizeVoice','shotSeconds','removeSilence','faceAwareFill','resolution','aspect','fixesText','matchScenes','grade',
             'voiceSource','ttsText','minimaxVoice','minimaxModel','minimaxSpeed','aiSpelling')

 def story_file(self):
  """Project of the Ghép ảnh mode: one per narration + media folder."""
  a=Path(self.settings['audio'])
  if not a.is_file():return None
  key=hashlib.sha1(f"{a.resolve()}|{a.stat().st_size}|{Path(self.settings['mediaFolder']).resolve()}".encode()).hexdigest()[:14]
  return self.cache()/'projects'/f'{key}.json'

 def story_read(self,f=None):
  f=f or self.story_file()
  try:return json.loads(f.read_text(encoding='utf-8')) if f and f.is_file() else {}
  except Exception:return {}

 def story_write(self,data,f=None):
  f=f or self.story_file()
  if not f:return
  f.parent.mkdir(parents=True,exist_ok=True);data['updated']=time.strftime('%Y-%m-%d %H:%M')
  tmp=f.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=1),encoding='utf-8');tmp.replace(f)

 def story_save(self):
  """Keep this project's settings with its timeline."""
  f=self.story_file()
  if not f:return
  d=self.story_read(f);s=self.settings
  d.update(kind='story',settings={k:s[k] for k in self.STORY_KEYS})
  d.setdefault('name',(s['title'].strip() or Path(s['audio']).stem)[:60]);d.setdefault('created',time.strftime('%Y-%m-%d %H:%M'))
  self.story_write(d,f)

 def thumb_url(self,path,at=0):
  from urllib.parse import quote
  return f'/t/{TOKEN}/?p={quote(str(path))}&at={float(at):.2f}'

 def thumb_file(self,src,at):
  """Small still of a photo, or of a video at a time, cached on disk (whole picture, never cropped)."""
  import renderer
  folder=self.cache()/'thumbs-tl';folder.mkdir(parents=True,exist_ok=True)
  out=folder/(hashlib.sha1(f'{src}|{src.stat().st_size}|{at:.1f}'.encode()).hexdigest()[:20]+'.jpg')
  if not out.is_file():
   seek=['-ss',f'{max(0,at):.2f}'] if src.suffix.lower() in renderer.VIDEO else []
   subprocess.run([renderer.FFMPEG,'-v','error','-y',*seek,'-i',str(src),'-frames:v','1','-vf','scale=480:480:force_original_aspect_ratio=decrease','-q:v','4',str(out)],capture_output=True,**NOWIN)
  return out if out.is_file() else None

 def media_list(self,folder):
  """Photos and videos of a folder for the timeline's picker (durations are read once and remembered)."""
  import renderer
  out=[];memo=self.__dict__.setdefault('_durations',{})
  try:files=sorted(p for p in Path(folder).iterdir() if p.is_file() and not p.name.startswith(('.','_')) and p.suffix.lower() in MEDIA_EXT)
  except OSError:files=[]
  notes={}
  try:notes=renderer.load_analysis(Path(folder))
  except Exception:pass
  for p in files[:400]:
   video=p.suffix.lower() in renderer.VIDEO;k=(str(p),p.stat().st_size);d=0
   if video:
    if k not in memo:
     try:memo[k]=float(renderer.probe(p)['format']['duration'])
     except Exception:memo[k]=0
    d=memo[k]
    if d<.2:continue
   out.append(dict(path=str(p),name=p.name,kind='video' if video else 'photo',d=round(d,2),thumb=self.thumb_url(p,min(1,d/2) if d else 0),
                   note=(notes.get(nfc(p.name)) or {}).get('mo_ta','')))
  return out

 def timeline_state(self):
  d=self.story_read();tl=d.get('timeline') or {}
  stale=tl.get('aspect','9:16')!=self.settings['aspect']   # automatic crops were found for another output shape
  shots=[dict({k:v for k,v in sh.items() if not (stale and k=='auto')},name=Path(sh['file']).name,missing=not Path(sh['file']).is_file(),thumb=self.thumb_url(sh['file'],float(sh.get('srcStart') or 0)+.2 if sh.get('d') else 0)) for sh in tl.get('shots') or []]
  last=d.get('lastExport') or {}
  return dict(shots=shots,duration=tl.get('duration',0),name=d.get('name',''),files=self.media_list(self.settings['mediaFolder']) if shots else [],
              exportUrl=self.url(last.get('path')) if last.get('path') else None,hasAudio=bool(self.story_file()))

 def timeline_edit(self,b):
  """Save the shot list edited on the timeline: shots stay back to back from 0 to the end of the narration."""
  f=self.story_file();d=self.story_read(f);tl=d.get('timeline')
  if not tl:return dict(error='Chưa có timeline.')
  dur=float(tl['duration']);shots=[]
  for sh in sorted(b.get('shots') or [],key=lambda x:float(x.get('start',0))):
   if not Path(str(sh.get('file',''))).is_file():continue
   fr=sh.get('frame');fr=dict(zoom=max(1,min(4,float(fr.get('zoom',1)))),cx=max(0,min(1,float(fr.get('cx',.5)))),cy=max(0,min(1,float(fr.get('cy',.5))))) if isinstance(fr,dict) else None
   shots.append(dict(start=float(sh['start']),end=float(sh['end']),file=str(sh['file']),d=float(sh.get('d') or 0),srcStart=max(0,float(sh.get('srcStart') or 0)),
                     text=str(sh.get('text',''))[:300],scene=str(sh.get('scene',''))[:300],matched=bool(sh.get('matched')),frame=fr,edited=bool(sh.get('edited')),
                     **({'auto':sh['auto']} if isinstance(sh.get('auto'),list) and len(sh['auto'])==4 and not sh.get('edited') else {})))
  if not shots:return dict(error='Timeline phải có ít nhất 1 cảnh.')
  shots[0]['start']=0
  for a,c in zip(shots,shots[1:]):a['end']=c['start']
  shots[-1]['end']=dur
  shots=[x for x in shots if x['end']-x['start']>=.2]
  for a,c in zip(shots,shots[1:]):a['end']=c['start']
  shots[0]['start']=0;shots[-1]['end']=dur
  for x in shots:x['start']=round(x['start'],3);x['end']=round(x['end'],3)
  tl['shots']=shots;d['timeline']=tl;self.story_write(d,f)
  return self.timeline_state()

 def timeline_reset(self):
  f=self.story_file();d=self.story_read(f)
  if d.pop('timeline',None) is not None:self.story_write(d,f)
  return self.timeline_state()

 def projects(self):
  """Every project kept in this output folder, newest first."""
  out=[]
  for f in (self.cache()/'projects').glob('*.json'):
   d=self.story_read(f)
   if d.get('kind')!='story':continue
   st=d.get('settings') or {};last=d.get('lastExport') or {}
   out.append(dict(kind='story',id=f.stem,name=d.get('name') or f.stem,updated=d.get('updated',''),shots=len((d.get('timeline') or {}).get('shots') or []),
                   detail=Path(st.get('audio','')).name,missing=not Path(st.get('audio','')).is_file(),exported=bool(last.get('path') and Path(last['path']).is_file()),
                   active=f==self.story_file()))
  cur=self.talk_dir() if self.talk_videos() else None
  for f in (self.cache()/'talk').glob('*/project.json'):
   try:d=json.loads(f.read_text(encoding='utf-8'))
   except Exception:continue
   vids=d.get('videos') or ([d['source']] if d.get('source') else [])
   out.append(dict(kind='talk',id=f.parent.name,name=d.get('label') or d.get('name') or Path(d.get('source','')).stem,updated=d.get('updated') or (d.get('last_export') or {}).get('at') or d.get('created',''),
                   shots=len(vids),detail=', '.join(Path(v).name for v in vids)[:80],missing=not all(Path(v).is_file() for v in vids),
                   exported=bool((d.get('last_export') or {}).get('results')),active=cur is not None and f.parent==cur))
  return dict(projects=sorted(out,key=lambda x:x['updated'],reverse=True))

 @staticmethod
 def project_id(pid):
  """Project ids are hex digests made by the app; anything else ('..', a path) must never reach the disk."""
  return pid if isinstance(pid,str) and re.fullmatch(r'[0-9a-f]{8,40}',pid) else None

 def project_open(self,kind,pid):
  pid=self.project_id(pid)
  if not pid:return dict(error='Không mở được dự án này.')
  if kind=='story':
   d=self.story_read(self.cache()/'projects'/f'{Path(pid).name}.json');st=d.get('settings') or {}
   if not Path(st.get('audio','')).is_file():return dict(error='Không còn file ghi âm của dự án này.')
   return self.set({k:v for k,v in st.items() if k in self.STORY_KEYS})
  try:d=json.loads((self.cache()/'talk'/Path(pid).name/'project.json').read_text(encoding='utf-8'))
  except Exception:return dict(error='Không mở được dự án này.')
  vids=d.get('videos') or ([d['source']] if d.get('source') else [])
  if not vids or not all(Path(v).is_file() for v in vids):return dict(error='Không còn đủ video gốc của dự án này.')
  return self.set_talk_videos(vids)

 def project_rename(self,kind,pid,name):
  name=str(name).strip()[:60]
  if not name:return dict(error='Hãy nhập tên.')
  pid=self.project_id(pid)
  if not pid:return dict(error='Không tìm thấy dự án.')
  f=self.cache()/'projects'/f'{Path(pid).name}.json' if kind=='story' else self.cache()/'talk'/Path(pid).name/'project.json'
  try:d=json.loads(f.read_text(encoding='utf-8'))
  except Exception:return dict(error='Không tìm thấy dự án.')
  d['name' if kind=='story' else 'label']=name
  tmp=f.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=1),encoding='utf-8');tmp.replace(f)
  return self.projects()

 def project_delete(self,kind,pid):
  """Removes the saved edit only (transcript, timeline, choices). Source files and exported videos are not touched."""
  import shutil
  pid=self.project_id(pid)
  if not pid:return dict(error='Không tìm thấy dự án.')
  if kind=='story':(self.cache()/'projects'/f'{pid}.json').unlink(missing_ok=True)
  else:
   folder=self.cache()/'talk'/pid
   if (folder/'project.json').is_file():shutil.rmtree(folder,ignore_errors=True)
  return self.projects()

 # ---- colour grading ----
 def grade(self):
  try:g=json.loads(self.settings['grade'] or '{}')
  except Exception:g={}
  return g if isinstance(g,dict) else {}

 def grade_presets(self):
  try:p=json.loads(self.settings['gradePresets'] or '[]')
  except Exception:p=[]
  return [x for x in p if isinstance(x,dict) and x.get('name')]

 def grade_save(self,name):
  name=str(name).strip()[:40]
  if not name:return dict(error='Hãy đặt tên cho mẫu màu.')
  g={k:v for k,v in self.grade().items() if k!='look'}
  presets=[x for x in self.grade_presets() if x['name']!=name]+[dict(name=name,grade=g)]
  return self.set({'gradePresets':json.dumps(presets[-30:],ensure_ascii=False),'grade':json.dumps(dict(g,look='mau:'+name),ensure_ascii=False)})

 def grade_delete(self,name):
  return self.set({'gradePresets':json.dumps([x for x in self.grade_presets() if x['name']!=name],ensure_ascii=False)})

 def grade_preview(self,mode):
  """Before/after stills of the current grade on a frame of the user's own footage."""
  import renderer
  src=None
  if mode=='talk':src=next(iter(self.talk_videos()),None)
  else:
   try:
    files=sorted(p for p in Path(self.settings['mediaFolder']).iterdir() if p.is_file() and not p.name.startswith(('.','_')) and p.suffix.lower() in MEDIA_EXT)
    src=str(next((p for p in files if p.suffix.lower() in renderer.PHOTO),files[0])) if files else None
   except OSError:src=None
  demo=ENGINE/'app'/'ui'/'assets'/'demo.mp4'
  if not src and demo.is_file():src=str(demo)
  if not src:return dict(error='Chưa có ảnh hoặc video để xem thử màu.')
  folder=self.cache()/'grade';folder.mkdir(parents=True,exist_ok=True)
  before=folder/f'truoc-{hashlib.sha1(src.encode()).hexdigest()[:10]}.jpg'
  if not before.is_file():
   seek=[] if Path(src).suffix.lower() in renderer.PHOTO else ['-ss',str(min(3,max(0,float(renderer.probe(src)['format']['duration'])*.3)))]
   p=subprocess.run([renderer.FFMPEG,'-v','error','-y',*seek,'-i',src,'-frames:v','1','-vf','scale=720:720:force_original_aspect_ratio=decrease','-q:v','3',str(before)],capture_output=True,**NOWIN)
   if p.returncode or not before.is_file():return dict(error='Không lấy được khung hình để xem thử màu.')
  after=folder/'sau.jpg';vf=renderer.grade_filter(self.grade()) or 'null'
  p=subprocess.run([renderer.FFMPEG,'-v','error','-y','-i',str(before),'-vf',vf,'-q:v','3',str(after)],capture_output=True,**NOWIN)
  if p.returncode:return dict(error='Chỉnh màu chưa được: '+p.stderr.decode(errors='replace')[-200:])
  v=f'?v={time.time():.3f}'
  return dict(before=self.url(str(before))+v,after=self.url(str(after))+v,source=Path(src).name)

 def talk_project(self):
  try:return json.loads((self.talk_dir()/'project.json').read_text(encoding='utf-8')) if self.settings['talkVideo'] else None
  except Exception:return None

 def talk_state(self):
  p=self.talk_project()
  # Finished videos of the last export, so the preview can play the edited result (title, captions, B-roll).
  exports=[]
  for r in ((p or {}).get('last_export') or {}).get('results',[]):
   if Path(r['path']).is_file():exports.append(dict(kind=r['kind'],name=Path(r['path']).name,duration=r.get('duration'),url=self.url(r['path'])))
  vids=self.talk_videos();src=(p or {}).get('source')
  video=src if src and Path(src).is_file() else (vids[0] if vids else None)
  return dict(project=p,videoUrl=self.url(video) if video else None,exports=exports,
              videos=[dict(name=Path(v).name,path=v,url=self.url(v)) for v in vids],
              exportFolder=((p or {}).get('last_export') or {}).get('folder'))

 def talk_edit(self,b):
  """Edits from the transcript editor: cut flags per word, chosen title, keywords, caption, shorts, B-roll on/off."""
  p=self.talk_project()
  if not p:return dict(error='Chưa có dự án.')
  for i,reason in (b.get('cuts') or {}).items():
   i=int(i)
   if 0<=i<len(p['words']):p['words'][i]['cut']=reason or None
  for k in ('title_choice','caption'):
   if k in b:p[k]=b[k]
  if 'hashtags' in b:p['hashtags']=[str(h) for h in b['hashtags']][:20]
  if 'keywords' in b:p['keywords']=[str(k) for k in b['keywords'] if str(k).strip()][:30]
  for key in ('shorts','broll'):
   for i,on in (b.get(key) or {}).items():
    if 0<=int(i)<len(p.get(key,[])):p[key][int(i)]['on']=bool(on)
  frame=lambda fr:dict(zoom=max(1,min(4,float(fr.get('zoom',1)))),cx=max(0,min(1,float(fr.get('cx',.5)))),cy=max(0,min(1,float(fr.get('cy',.5))))) if isinstance(fr,dict) else None
  if isinstance(b.get('brollList'),list):
   # The B-roll track edited on the timeline: where each cut-away starts (a word), how long, which file, which part, framing.
   items=[]
   for x in b['brollList'][:200]:
    if not Path(str(x.get('path',''))).is_file() or not 0<=int(x.get('first',-1))<len(p['words']):continue
    d=float(x.get('d') or 0)
    items.append(dict(first=int(x['first']),lead=max(0,min(2,float(x.get('lead',.15)))),dur=round(max(.8,min(15,float(x.get('dur',2.5)))),2),path=str(x['path']),d=d,
                      a=max(0,min(float(x.get('a') or 0),max(0,d-.5))),b=float(x.get('b') or d),text=str(x.get('text',''))[:300],source=str(x.get('source') or Path(str(x['path'])).name)[:200],
                      on=bool(x.get('on',True)),frame=frame(x.get('frame'))))
   p['broll']=sorted(items,key=lambda x:x['first'])
  if isinstance(b.get('frames'),dict):
   frames=p.get('frames') or {}
   for k,v in b['frames'].items():
    if frame(v):frames[str(k)]=frame(v)
    else:frames.pop(str(k),None)
   p['frames']=frames
  p['updated']=time.strftime('%Y-%m-%d %H:%M')
  f=self.talk_dir()/'project.json';tmp=f.with_suffix('.tmp');tmp.write_text(json.dumps(p,ensure_ascii=False,indent=1),encoding='utf-8');tmp.replace(f)
  return dict(ok=True)

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
 'restart':lambda b:studio.restart(),'talkVideos':lambda b:studio.talk_videos_op(b),
 'gradePreview':lambda b:studio.grade_preview(b.get('mode','story')),'gradeSave':lambda b:studio.grade_save(b.get('name','')),
 'gradeDelete':lambda b:studio.grade_delete(b.get('name','')),'talkState':lambda b:studio.talk_state(),'talkEdit':lambda b:studio.talk_edit(b),
 'thumbFind':lambda b:studio.thumb_find(),'thumbCompose':lambda b:studio.thumb_compose(b.get('ids',[]),b.get('text',True)),
 'thumbSave':lambda b:studio.thumb_save(b.get('ids',[]),b.get('text',True)),'thumbReveal':lambda b:studio.reveal(studio.thumb_saved),
 'timelineState':lambda b:studio.timeline_state(),'timelineEdit':lambda b:studio.timeline_edit(b),'timelineReset':lambda b:studio.timeline_reset(),
 'mediaList':lambda b:dict(files=studio.media_list(studio.settings['talkBrollFolder' if b.get('which')=='broll' else 'mediaFolder'])),
 'projects':lambda b:studio.projects(),'projectOpen':lambda b:studio.project_open(b.get('kind'),b.get('id','')),
 'projectRename':lambda b:studio.project_rename(b.get('kind'),b.get('id',''),b.get('name','')),'projectDelete':lambda b:studio.project_delete(b.get('kind'),b.get('id',''))}

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
  if url.path.startswith('/t/'):
   q=parse_qs(url.query);src=Path(q.get('p',[''])[0])
   if len(parts)<3 or parts[2]!=TOKEN or not src.is_file() or src.suffix.lower() not in MEDIA_EXT:return self.send(403,b'')
   thumb=studio.thumb_file(src,float(q.get('at',['0'])[0] or 0))
   return self.file(thumb) if thumb else self.send(404,b'')
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
