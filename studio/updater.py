"""Self-update: build release zips, check a manifest, install a new version safely, roll back.

A release is a zip of the app files only (never media, output, caches or settings). The manifest is a small JSON:
  {"version": "2.2.0", "url": "https://…/GhepVideo-2.2.0.zip", "sha256": "…", "notes": "…", "size": 123}

Installing: download → check SHA-256 → check every path in the zip is an app path → back up the current app files
→ replace files (removing files the new version no longer ships) → reinstall Python packages if requirements changed.
"""
import hashlib, json, os, re, shutil, tempfile, time, unicodedata, urllib.request, zipfile
from pathlib import Path

ENGINE=Path(__file__).resolve().parent;ROOT=ENGINE.parent
VERSION_FILE=ENGINE/'VERSION'
# Only these paths belong to the app; user folders (media, output, recordings) are never read or written.
APP_PATHS=('studio/','Ghép Video.app/','Ghep Video (Windows).bat','Cai dat (Windows).bat')
SKIP_PARTS={'__pycache__','.DS_Store','.pytest_cache'}
SKIP_FILES={'studio/VideoStudio.swift','studio/build.command'}  # legacy Swift app sources, not shipped
# This machine's own files inside the app folder: never published, never replaced or removed by an update.
LOCAL_DIRS=('studio/app/ui/assets/local/',)
nfc=lambda s:unicodedata.normalize('NFC',s)

def current_version():
 try:return VERSION_FILE.read_text(encoding='utf-8').strip()
 except OSError:return '0.0.0'

def newer(a,b):
 """True when version a is newer than b ('2.10.0' > '2.9.1')."""
 parse=lambda v:[int(x) for x in re.findall(r'\d+',v)[:3]]+[0]*(3-len(re.findall(r'\d+',v)[:3]))
 return parse(a)>parse(b)

def is_app_path(rel):
 rel=nfc(rel).replace('\\','/')
 if rel.startswith('/') or '..' in rel.split('/') or re.match(r'^[A-Za-z]:',rel):return False
 if any(p in SKIP_PARTS for p in rel.split('/')) or rel in SKIP_FILES or rel.endswith('.pyc') or rel.startswith(LOCAL_DIRS):return False
 return any(rel==p or (p.endswith('/') and rel.startswith(p)) for p in APP_PATHS)

def app_files(root=ROOT):
 """Relative NFC paths of the app files that exist under root."""
 out=[]
 for base,dirs,files in os.walk(root):
  dirs[:]=[d for d in dirs if d not in SKIP_PARTS]
  for f in files:
   rel=nfc(os.path.relpath(os.path.join(base,f),root)).replace('\\','/')
   if is_app_path(rel):out.append(rel)
 return sorted(out)

def locate(root,rel):
 """Real path for an NFC relative path (macOS may store Vietnamese names decomposed)."""
 p=Path(root)
 for part in rel.split('/'):
  try:p=next((c for c in p.iterdir() if nfc(c.name)==part),p/part)
  except OSError:p=p/part
 return p

def write_zip(files,root,dest,version):
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for rel in files:
   src=locate(root,rel);info=zipfile.ZipInfo(rel,time.localtime(src.stat().st_mtime)[:6])
   info.external_attr=(src.stat().st_mode&0o777|0o100000)<<16;info.compress_type=zipfile.ZIP_DEFLATED
   z.writestr(info,src.read_bytes())
  z.writestr('studio/FILES.txt','\n'.join(files+['studio/FILES.txt'])+'\n')

def sha256(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

# ---------------- building a release (run by the developer) ----------------

def build_release(version,notes,base_url,out_dir):
 out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
 VERSION_FILE.write_text(version+'\n',encoding='utf-8')
 zip_path=out/f'GhepVideo-{version}.zip'
 write_zip([f for f in app_files() if f!='studio/FILES.txt'],ROOT,zip_path,version)
 manifest=dict(version=version,url=base_url.rstrip('/')+'/'+zip_path.name if base_url else zip_path.name,
               sha256=sha256(zip_path),size=zip_path.stat().st_size,notes=notes,date=time.strftime('%Y-%m-%d'))
 (out/'latest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=1),encoding='utf-8')
 return zip_path,manifest

# ---------------- checking and installing (run by the app) ----------------

def manifest_url(settings):
 url=(settings or {}).get('updateManifest','').strip()
 if not url:
  try:url=json.loads((ENGINE/'update.json').read_text(encoding='utf-8')).get('manifest','').strip()
  except Exception:url=''
 return url

def fetch(url,dest=None,timeout=30):
 if not re.match(r'^(https://|http://127\.0\.0\.1[:/]|http://localhost[:/]|file:)',url):raise ValueError('Địa chỉ cập nhật phải dùng https.')
 req=urllib.request.Request(url,headers={'User-Agent':'GhepVideo-Updater/'+current_version()})
 with urllib.request.urlopen(req,timeout=timeout) as r:
  if dest is None:return r.read()
  with open(dest,'wb') as f:shutil.copyfileobj(r,f)

def check(settings):
 url=manifest_url(settings)
 if not url:return dict(configured=False,current=current_version())
 m=json.loads(fetch(url,timeout=15))
 for k in ('version','url','sha256'):
  if not m.get(k):raise ValueError('File cập nhật thiếu thông tin: '+k)
 if not re.match(r'^https?://|^file:',m['url']):m['url']=url.rsplit('/',1)[0]+'/'+m['url']  # relative zip name
 return dict(configured=True,current=current_version(),latest=m['version'],available=newer(m['version'],current_version()),manifest=m)

def safe_members(z):
 names=[nfc(n) for n in z.namelist() if not n.endswith('/')]
 bad=[n for n in names if not is_app_path(n) and n!='studio/FILES.txt']
 if bad:raise ValueError('Gói cập nhật chứa file ngoài phạm vi app: '+', '.join(bad[:3]))
 if 'studio/VERSION' not in names or 'studio/app/main.py' not in names:raise ValueError('Gói cập nhật không đúng cấu trúc.')
 return names

def backup(data_dir,keep=3):
 """Zip the current app files so the previous version can be restored."""
 folder=Path(data_dir)/'backups';folder.mkdir(parents=True,exist_ok=True)
 dest=folder/f'GhepVideo-{current_version()}-{time.strftime("%Y%m%d-%H%M%S")}.zip'
 write_zip([f for f in app_files() if f!='studio/FILES.txt'],ROOT,dest,current_version())
 for old in sorted(folder.glob('GhepVideo-*.zip'),key=lambda p:p.stat().st_mtime)[:-keep]:old.unlink()
 return dest

def backups(data_dir):
 folder=Path(data_dir)/'backups'
 return sorted(folder.glob('GhepVideo-*.zip'),key=lambda p:p.stat().st_mtime,reverse=True) if folder.exists() else []

def install_zip(zip_path,progress=lambda p,m:None):
 """Replace the app files with the zip's. Returns (old_version, new_version, requirements_changed)."""
 old=current_version();req_before={p.name:sha256(p) for p in ENGINE.glob('requirements-*.txt')}
 before=set(app_files())
 with zipfile.ZipFile(zip_path) as z:
  names=safe_members(z);infos={nfc(i.filename):i for i in z.infolist()}
  with tempfile.TemporaryDirectory(prefix='ghepvideo-update-',dir=str(ROOT)) as tmp:
   # Extract everything first; only when that fully succeeds are files moved into place.
   for n in names:
    dest=Path(tmp)/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(infos[n]))
    mode=(infos[n].external_attr>>16)&0o777
    if mode:os.chmod(dest,mode|0o600)
   progress(70,'Đang thay file app…')
   for n in names:
    target=locate(ROOT,n);target.parent.mkdir(parents=True,exist_ok=True)
    os.replace(Path(tmp)/n,target)
 # Files the new version no longer ships are removed (only app paths, never user files).
 for rel in sorted(before-set(names)-{'studio/FILES.txt'}):
  p=locate(ROOT,rel)
  if p.is_file() and is_app_path(rel):p.unlink()
 req_after={p.name:sha256(p) for p in ENGINE.glob('requirements-*.txt')}
 return old,current_version(),req_after!=req_before

def update(settings,data_dir,python,progress=lambda p,m:None):
 info=check(settings)
 if not info.get('available'):return dict(info,installed=False)
 m=info['manifest'];folder=Path(data_dir)/'updates';folder.mkdir(parents=True,exist_ok=True)
 zip_path=folder/f"GhepVideo-{m['version']}.zip"
 progress(10,f"Đang tải bản {m['version']}…");fetch(m['url'],zip_path,timeout=300)
 progress(45,'Đang kiểm tra gói tải về…')
 if sha256(zip_path)!=m['sha256'].lower():zip_path.unlink();raise ValueError('Gói tải về bị lỗi (sai mã SHA-256). Chưa thay đổi gì.')
 with zipfile.ZipFile(zip_path) as z:safe_members(z)
 progress(55,'Đang sao lưu bản hiện tại…');saved=backup(data_dir)
 old,new,req=install_zip(zip_path,progress)
 if req:pip_install(python,progress)
 progress(100,f'Đã cập nhật {old} → {new}. Khởi động lại app để dùng bản mới.')
 return dict(info,installed=True,old=old,new=new,backup=str(saved))

def rollback(data_dir,python,progress=lambda p,m:None):
 saved=backups(data_dir)
 if not saved:raise ValueError('Chưa có bản sao lưu nào để quay lại.')
 target=saved[0];progress(30,f'Đang quay lại {target.stem}…')
 old,new,req=install_zip(target,progress);target.unlink()
 if req:pip_install(python,progress)
 progress(100,f'Đã quay lại bản {new}. Khởi động lại app.')
 return dict(old=old,new=new)

def pip_install(python,progress):
 import subprocess
 from platform_tools import WINDOWS, NOWIN
 req=ENGINE/('requirements-windows.txt' if WINDOWS else 'requirements-mac.txt')
 progress(85,'Đang cài thêm thư viện cho bản mới…')
 p=subprocess.run([python,'-m','pip','install','-q','-r',str(req)],capture_output=True,**NOWIN)
 if p.returncode:raise RuntimeError('Cài thư viện chưa được: '+p.stderr.decode(errors='replace')[-400:])

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser(description='Tạo gói phát hành Ghép Video')
 ap.add_argument('version');ap.add_argument('--notes',default='');ap.add_argument('--base-url',default='');ap.add_argument('--out',default=str(ROOT/'dist'))
 a=ap.parse_args()
 z,m=build_release(a.version,a.notes,a.base_url,a.out)
 print(f"Đã tạo {z} ({m['size']//1024} KB)\nsha256 {m['sha256']}\nlatest.json → {Path(a.out)/'latest.json'}")
