"""Everything that differs between macOS and Windows, in one place.

macOS (Apple Silicon): mlx-whisper, Apple Vision face detector (face-detect helper), mlx-vlm.
Windows / other:       faster-whisper, OpenCV YuNet face detector.
Picture descriptions come from the customer's own Claude / ChatGPT subscription (see vlm_ask).
"""
import json, os, platform, re, shutil, subprocess, sys
from pathlib import Path

WINDOWS=os.name=='nt'
MAC=sys.platform=='darwin'
APPLE_SILICON=MAC and platform.machine()=='arm64'
HERE=Path(__file__).resolve().parent

if WINDOWS:DATA=Path(os.environ.get('APPDATA',Path.home()/'AppData'/'Roaming'))/'GhepVideo'
elif MAC:DATA=Path.home()/'Library'/'Application Support'/'GhepVideo'
else:DATA=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local'/'share'))/'GhepVideo'

# Child processes must not flash a console window when the app runs without one (pythonw on Windows).
NOWIN={'creationflags':0x08000000} if WINDOWS else {}

def tool(name):
 exe=name+('.exe' if WINDOWS else '')
 for candidate in (shutil.which(name),DATA/'bin'/exe,Path('/opt/homebrew/bin')/name,Path('/usr/local/bin')/name):
  if candidate and Path(candidate).exists():return str(candidate)
 return name

FFMPEG=tool('ffmpeg');FFPROBE=tool('ffprobe')

def font_path():
 for p in ('/System/Library/Fonts/Supplemental/Arial Bold.ttf',
           os.path.join(os.environ.get('WINDIR','C:\\Windows'),'Fonts','arialbd.ttf'),
           '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',str(HERE/'fonts'/'Arial Bold.ttf')):
  if Path(p).exists():return p
 raise RuntimeError('Không tìm thấy font Arial Bold trên máy.')

def utf8_stdio():
 """Progress lines carry Vietnamese text; Windows pipes default to a legacy code page."""
 for s in (sys.stdout,sys.stderr):
  try:s.reconfigure(encoding='utf-8')
  except Exception:pass

# ---------- Speech recognition ----------

def transcribe(audio):
 """Word-level Vietnamese transcript as {'segments':[{'words':[{'word','start','end'}]}]}."""
 if APPLE_SILICON:
  try:
   import mlx_whisper
   return mlx_whisper.transcribe(str(audio),path_or_hf_repo='mlx-community/whisper-medium-mlx',language='vi',word_timestamps=True,verbose=None)
  except ImportError:pass
 from faster_whisper import WhisperModel
 # NVIDIA GPU when its CUDA libraries are present; otherwise CPU (slower, always works).
 for device,compute in (('cuda','float16'),('cpu','int8')):
  try:
   model=WhisperModel('medium',device=device,compute_type=compute)
   segments,_=model.transcribe(str(audio),language='vi',word_timestamps=True)
   return {'segments':[{'words':[{'word':w.word,'start':w.start,'end':w.end} for w in (s.words or [])]} for s in segments]}
  except Exception:
   if device=='cpu':raise

# ---------- Face detection ----------

YUNET=DATA/'models'/'face_detection_yunet_2023mar.onnx'

def detect_faces(image):
 """{'width','height','faces':[[x,y,w,h] normalised, top-left origin]} for one image file."""
 helper=next((p for p in (HERE/'face-detect',HERE.parent/'Ghép Video.app'/'Contents'/'Resources'/'face-detect') if p.exists()),None)
 if MAC and helper:
  out=subprocess.run([str(helper),str(image)],capture_output=True,**NOWIN)
  if out.returncode:raise RuntimeError(out.stderr.decode(errors='replace')[-800:])
  found=json.loads(out.stdout)[str(image)]
  if 'error' in found:raise RuntimeError('Không kiểm tra được khuôn mặt: '+found['error'])
  return found
 import cv2, numpy as np
 if not YUNET.exists():raise RuntimeError(f'Thiếu mô hình nhận diện khuôn mặt {YUNET}; hãy chạy lại bước cài đặt.')
 # imdecode instead of imread: imread cannot open non-ASCII (Vietnamese) paths on Windows.
 img=cv2.imdecode(np.fromfile(str(image),dtype=np.uint8),cv2.IMREAD_COLOR)
 if img is None:raise RuntimeError('Không đọc được ảnh '+Path(image).name)
 H,W=img.shape[:2];scale=min(1,1280/max(W,H));small=cv2.resize(img,(round(W*scale),round(H*scale))) if scale<1 else img
 det=cv2.FaceDetectorYN.create(str(YUNET),'',(small.shape[1],small.shape[0]),0.75)
 _,faces=det.detect(small)
 import math
 rows=[f for f in (faces if faces is not None else [])]
 # Tiny faces (a photo on the wall, a poster) must not decide the crop: keep those at least 20% of the largest.
 if rows:biggest=max(float(f[2]) for f in rows);rows=[f for f in rows if float(f[2])>=biggest*.2]
 boxes=[[float(f[0])/small.shape[1],float(f[1])/small.shape[0],float(f[2])/small.shape[1],float(f[3])/small.shape[0]] for f in rows]
 # Head tilt from the two eye landmarks (YuNet: right eye x,y = f[4],f[5]; left eye = f[6],f[7]).
 rolls=[math.degrees(math.atan2(float(f[7])-float(f[5]),float(f[6])-float(f[4]))) for f in rows]
 return {'width':W,'height':H,'faces':boxes,'rolls':rolls}

def detect_faces_many(images):
 """{path: result} for many images; one helper process on macOS instead of one per image."""
 helper=next((p for p in (HERE/'face-detect',) if p.exists()),None)
 if MAC and helper and images:
  out=subprocess.run([str(helper),*map(str,images)],capture_output=True,**NOWIN)
  if out.returncode:raise RuntimeError(out.stderr.decode(errors='replace')[-800:])
  return json.loads(out.stdout)
 return {str(i):detect_faces(i) for i in images}

# ---------- Vision-language model ----------
# Pictures are described by the customer's own subscription, chosen by GHEPVIDEO_AI (set by the app from its settings):
#   claude  Claude Pro/Max, through the official Claude Code CLI they installed and signed in to
#   codex   ChatGPT, through the official Codex CLI
#   auto    Claude if installed, else Codex
#   local   (developers only, not installed for customers) MLX on Apple Silicon / Ollama on Windows
# With claude/codex, the small (768 px) stills are sent to Anthropic / OpenAI; the app says so next to the choice.

MLX_MODEL='mlx-community/Qwen3-VL-4B-Instruct-4bit'
# The Instruct build answers directly; the default qwen3-vl:4b tag is the Thinking build, whose long <think> text
# ran out of tokens before any JSON appeared.
OLLAMA_MODEL=os.environ.get('GHEPVIDEO_OLLAMA_MODEL','qwen3-vl:4b-instruct')
OLLAMA_URL=os.environ.get('OLLAMA_HOST','http://127.0.0.1:11434').rstrip('/')
CLAUDE_MODEL=os.environ.get('GHEPVIDEO_CLAUDE_MODEL','sonnet')  # good Vietnamese at a moderate share of the plan's limits
AI_CHOICES=('auto','local','claude','codex')
AI_NAMES={'local':'AI trên máy','claude':'Claude','codex':'ChatGPT (Codex)'}
_mlx=None

def cli_path(name):
 """The official CLI if installed: on PATH, or in the places its installers use."""
 home=Path.home()
 extra=[home/'.local'/'bin'/(name+'.exe'),Path(os.environ.get('APPDATA',''))/'npm'/(name+'.cmd'),home/'.local'/'bin'/name] if WINDOWS \
       else [home/'.local'/'bin'/name,home/'.claude'/'local'/name,Path('/opt/homebrew/bin')/name,Path('/usr/local/bin')/name,home/'.npm-global'/'bin'/name]
 for c in [shutil.which(name),*extra]:
  if c and Path(c).is_file():return str(c)
 return None

def ollama_exe():
 exe=shutil.which('ollama') or (str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs'/'Ollama'/'ollama.exe') if WINDOWS else None)
 return exe if exe and Path(exe).exists() else None

def local_ai_available():
 if APPLE_SILICON:
  import importlib.util
  return importlib.util.find_spec('mlx_vlm') is not None
 return ollama_exe() is not None

def ai_status():
 return {'local':local_ai_available(),'claude':cli_path('claude') is not None,'codex':cli_path('codex') is not None}

def ai_provider():
 choice=os.environ.get('GHEPVIDEO_AI','auto')
 if choice in ('local','claude','codex'):return choice
 return next((p for p in ('claude','codex') if cli_path(p)),None)

def vlm_name():
 p=ai_provider()
 return {'local':MLX_MODEL if APPLE_SILICON else 'ollama:'+OLLAMA_MODEL,'claude':'claude:'+CLAUDE_MODEL,'codex':'codex'}.get(p,'none')

def vlm_ready():
 p=ai_provider()
 if p is None:raise RuntimeError('Chưa có AI xem ảnh. Cài Claude Code hoặc Codex rồi đăng nhập 1 lần bằng gói Claude / ChatGPT của bạn.')
 if p in ('claude','codex'):
  if not cli_path(p):raise RuntimeError(f'Chưa cài {AI_NAMES[p]} trên máy này.')
  return
 if APPLE_SILICON:
  global _mlx
  if _mlx is None:
   from mlx_vlm import load
   _mlx=load(MLX_MODEL)
  return
 import urllib.request, time
 def up():
  try:urllib.request.urlopen(OLLAMA_URL+'/api/tags',timeout=3).read();return True
  except Exception:return False
 if not up() and ollama_exe():
  subprocess.Popen([ollama_exe(),'serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**NOWIN)
  for _ in range(30):
   if up():break
   time.sleep(1)
 if not up():raise RuntimeError('Chưa có AI trên máy (Ollama). Chọn Claude hoặc ChatGPT.')

JSON_ONLY='\n\nChỉ in đúng một đối tượng JSON, không giải thích, không bọc trong ```.'

def run_cli(args,prompt,timeout=300,cwd=None):
 # The prompt goes through stdin: quotes, newlines and Vietnamese survive intact (Windows .cmd shims included).
 p=subprocess.run(args,input=prompt,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,cwd=cwd,**NOWIN)
 if p.returncode:
  hint=(p.stderr or p.stdout).strip()[-400:]
  if re.search(r'log ?in|auth|credential|unauthori[sz]ed|not signed',hint,re.I):hint='chưa đăng nhập. Mở Terminal/Command Prompt, gõ lệnh đăng nhập rồi thử lại. '+hint[-160:]
  raise RuntimeError(hint or f'lỗi {p.returncode}')
 return p.stdout

def ask_claude(question,images):
 files=[str(Path(i).resolve()) for i in images]
 lead=('Đọc các ảnh sau bằng công cụ Read: '+', '.join(files)+'\n\n') if files else ''
 args=[cli_path('claude'),'-p','--model',CLAUDE_MODEL,'--output-format','json','--allowedTools','Read']
 for d in sorted({str(Path(f).parent) for f in files}):args+=['--add-dir',d]
 try:out=run_cli(args,lead+question+JSON_ONLY,cwd=str(Path(files[0]).parent) if files else None)
 except RuntimeError as e:raise RuntimeError('Claude: '+str(e))
 data=json.loads(out)
 if data.get('is_error'):raise RuntimeError('Claude: '+str(data.get('result',''))[:300])
 return str(data.get('result',''))

def ask_codex(question,images):
 import tempfile
 with tempfile.TemporaryDirectory(prefix='ghepvideo-codex-') as tmp:
  out=Path(tmp)/'answer.txt'
  args=[cli_path('codex'),'exec','--skip-git-repo-check','--ephemeral','--sandbox','read-only','-o',str(out),'-']
  if images:args+=['--image',*[str(Path(i).resolve()) for i in images]]
  try:run_cli(args,question+JSON_ONLY,cwd=tmp)
  except RuntimeError as e:raise RuntimeError('ChatGPT (Codex): '+str(e))
  return out.read_text(encoding='utf-8',errors='replace') if out.exists() else ''

def vlm_ask(question,images=(),schema=None):
 vlm_ready()
 p=ai_provider()
 if p=='claude':return ask_claude(question,images)
 if p=='codex':return ask_codex(question,images)
 if APPLE_SILICON:
  from mlx_vlm import generate
  from mlx_vlm.prompt_utils import apply_chat_template
  m,proc=_mlx
  prompt=apply_chat_template(proc,m.config,question,num_images=len(images))
  r=generate(m,proc,prompt,[str(i) for i in images] or None,max_tokens=400,temperature=0,verbose=False)
  return getattr(r,'text',r)
 import base64, urllib.request, urllib.error
 # A JSON schema (when the caller knows the fields) constrains Ollama far better than plain format='json',
 # which can loop on whitespace for long prompts. An empty/unreadable answer is retried once without any format.
 message=dict(role='user',content=question,images=[base64.b64encode(Path(i).read_bytes()).decode() for i in images])
 def call(fmt,think=True):
  body=dict(model=OLLAMA_MODEL,messages=[message],stream=False,options=dict(temperature=0,num_predict=2048))
  if fmt is not None:body['format']=fmt
  if not think:body['think']=False
  req=urllib.request.Request(OLLAMA_URL+'/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=900) as r:msg=json.loads(r.read()).get('message',{})
  except urllib.error.HTTPError as e:
   if e.code==400 and not think:return call(fmt,True)  # a model without the thinking switch rejects think=False
   raise
  text=(msg.get('content') or '').strip() or (msg.get('thinking') or '').strip()
  return re.sub(r'<think>.*?(</think>|$)','',text,flags=re.S).strip()
 text=call(schema or 'json',think=False)
 if '{' not in text:text=call(None,think=False)
 return text
