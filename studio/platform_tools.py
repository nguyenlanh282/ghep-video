"""Everything that differs between macOS and Windows, in one place.

macOS (Apple Silicon): mlx-whisper, Apple Vision face detector (face-detect helper), mlx-vlm.
Windows / other:       faster-whisper, OpenCV YuNet face detector, Ollama (qwen3-vl).
"""
import json, os, platform, shutil, subprocess, sys
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

MLX_MODEL='mlx-community/Qwen3-VL-4B-Instruct-4bit'
OLLAMA_MODEL=os.environ.get('GHEPVIDEO_OLLAMA_MODEL','qwen3-vl:4b')
OLLAMA_URL=os.environ.get('OLLAMA_HOST','http://127.0.0.1:11434').rstrip('/')
_mlx=None

def vlm_name():
 return MLX_MODEL if APPLE_SILICON else 'ollama:'+OLLAMA_MODEL

def vlm_ready():
 if APPLE_SILICON:
  global _mlx
  if _mlx is None:
   from mlx_vlm import load
   _mlx=load(MLX_MODEL)
  return
 import urllib.request
 try:urllib.request.urlopen(OLLAMA_URL+'/api/tags',timeout=5).read()
 except Exception:raise RuntimeError('Chưa mở Ollama. Hãy cài và chạy Ollama (ollama.com), rồi chạy lại bước cài đặt.')

def vlm_ask(question,images=()):
 vlm_ready()
 if APPLE_SILICON:
  from mlx_vlm import generate
  from mlx_vlm.prompt_utils import apply_chat_template
  m,proc=_mlx
  prompt=apply_chat_template(proc,m.config,question,num_images=len(images))
  r=generate(m,proc,prompt,[str(i) for i in images] or None,max_tokens=400,temperature=0,verbose=False)
  return getattr(r,'text',r)
 import base64, urllib.request
 body=dict(model=OLLAMA_MODEL,prompt=question,stream=False,think=False,options=dict(temperature=0,num_predict=400),
           images=[base64.b64encode(Path(i).read_bytes()).decode() for i in images])
 req=urllib.request.Request(OLLAMA_URL+'/api/generate',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=600) as r:return json.loads(r.read())['response']
