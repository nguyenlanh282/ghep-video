"""End-to-end test of the self-updater on throwaway copies of the app (the real app folder is never touched)."""
import functools, http.server, json, shutil, subprocess, sys, tempfile, threading, unittest, zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import updater

def copy_app(dest):
 for rel in updater.app_files():
  src=updater.locate(updater.ROOT,rel);target=Path(dest)/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)

def run(root,code):
 """Run code with root's own updater.py, as that installed copy would."""
 out=subprocess.run([sys.executable,'-c','import sys,json;sys.path.insert(0,sys.argv[1]);import updater;'+code,str(Path(root)/'studio')],capture_output=True,text=True)
 if out.returncode:raise AssertionError(out.stderr[-1500:])
 return out.stdout.strip()

class UpdaterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=Path(tempfile.mkdtemp(prefix='ghepvideo-test-'))
  cls.installed=cls.tmp/'may-dang-dung';cls.newer=cls.tmp/'ban-moi';cls.site=cls.tmp/'site';cls.data=cls.tmp/'data'
  copy_app(cls.installed);copy_app(cls.newer)
  (cls.installed/'studio'/'VERSION').write_text('2.1.0\n')
  # The user's own files next to the app, which an update must never touch.
  (cls.installed/'Video - ảnh').mkdir();(cls.installed/'Video - ảnh'/'clip.mp4').write_bytes(b'user video')
  (cls.installed/'output').mkdir();(cls.installed/'output'/'Video-1.mp4').write_bytes(b'rendered')
  local=cls.installed/'studio'/'app'/'ui'/'assets'/'local';local.mkdir(parents=True,exist_ok=True);(local/'demo.mp4').write_bytes(b'family sample')
  # Version 2.2.0: one changed file, one new file, one file removed.
  (cls.newer/'studio'/'app'/'ui'/'index.html').write_text((cls.newer/'studio'/'app'/'ui'/'index.html').read_text()+'<!-- 2.2.0 -->')
  (cls.newer/'studio'/'tinh-nang-moi.py').write_text('NEW=1\n')
  (cls.newer/'studio'/'test_updater.py').unlink()
  run(cls.newer,"updater.build_release('2.2.0','Thêm tính năng mới','',sys.argv[1]+'/../../site')")
  handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(cls.site))
  handler.log_message=lambda *a:None
  cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
  threading.Thread(target=cls.server.serve_forever,daemon=True).start()
  cls.url=f'http://127.0.0.1:{cls.server.server_address[1]}/latest.json'

 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();shutil.rmtree(cls.tmp,ignore_errors=True)

 def settings(self):return json.dumps({'updateManifest':self.url})

 def test_1_check_sees_newer_version(self):
  out=json.loads(run(self.installed,f"print(json.dumps(updater.check({self.settings()})))"))
  self.assertTrue(out['available']);self.assertEqual((out['current'],out['latest']),('2.1.0','2.2.0'))

 def test_2_update_then_rollback(self):
  i=self.installed
  run(i,f"print(json.dumps(updater.update({self.settings()},{str(self.data)!r},sys.executable)))")
  self.assertEqual((i/'studio'/'VERSION').read_text().strip(),'2.2.0')
  self.assertIn('<!-- 2.2.0 -->',(i/'studio'/'app'/'ui'/'index.html').read_text())
  self.assertTrue((i/'studio'/'tinh-nang-moi.py').exists())
  self.assertFalse((i/'studio'/'test_updater.py').exists(),'files dropped by the new version are removed')
  self.assertEqual((i/'Video - ảnh'/'clip.mp4').read_bytes(),b'user video')
  self.assertEqual((i/'output'/'Video-1.mp4').read_bytes(),b'rendered')
  self.assertEqual((i/'studio'/'app'/'ui'/'assets'/'local'/'demo.mp4').read_bytes(),b'family sample','machine-only sample survives updates')
  self.assertTrue(list((self.data/'backups').glob('GhepVideo-2.1.0-*.zip')))
  self.assertFalse([p for p in i.iterdir() if p.name.startswith('ghepvideo-update-')],'temporary folder cleaned up')
  run(i,f"updater.rollback({str(self.data)!r},sys.executable)")
  self.assertEqual((i/'studio'/'VERSION').read_text().strip(),'2.1.0')
  self.assertNotIn('<!-- 2.2.0 -->',(i/'studio'/'app'/'ui'/'index.html').read_text())
  self.assertFalse((i/'studio'/'tinh-nang-moi.py').exists())
  self.assertTrue((i/'studio'/'test_updater.py').exists())
  self.assertEqual((i/'Video - ảnh'/'clip.mp4').read_bytes(),b'user video')

 def test_3_corrupted_download_changes_nothing(self):
  m=json.loads((self.site/'latest.json').read_text());good=m['sha256']
  m['sha256']='0'*64;(self.site/'latest.json').write_text(json.dumps(m))
  try:
   with self.assertRaises(AssertionError) as err:run(self.installed,f"updater.update({self.settings()},{str(self.data)!r},sys.executable)")
   self.assertIn('SHA-256',str(err.exception))
   self.assertEqual((self.installed/'studio'/'VERSION').read_text().strip(),'2.1.0')
  finally:
   m['sha256']=good;(self.site/'latest.json').write_text(json.dumps(m))

 def test_4_zip_writing_outside_the_app_is_refused(self):
  bad=self.tmp/'bad.zip'
  with zipfile.ZipFile(bad,'w') as z:
   z.writestr('studio/VERSION','9.9.9');z.writestr('studio/app/main.py','');z.writestr('../ngoai-app.txt','x');z.writestr('Video - ảnh/clip.mp4','x')
  with zipfile.ZipFile(bad) as z,self.assertRaises(ValueError):updater.safe_members(z)

 def test_5_version_order(self):
  self.assertTrue(updater.newer('2.10.0','2.9.9'));self.assertFalse(updater.newer('2.1.0','2.1.0'));self.assertTrue(updater.newer('3','2.9'))

if __name__=='__main__':unittest.main()
