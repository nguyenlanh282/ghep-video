"""Smoke test for a fresh install (used by GitHub Actions on real Windows/macOS machines).

Makes synthetic media (two test videos, one photo, a spoken sentence when the OS can synthesise speech), then:
  1. renders a 1080p video end to end (speech recognition, silence cut, karaoke, face-aware crop, voice gain);
  2. optionally (--vlm) analyses the photo with the local vision model and finds thumbnail candidates.
Exits non-zero with a readable message on the first failure.
"""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from platform_tools import FFMPEG, FFPROBE, WINDOWS, MAC, NOWIN

def run(args,**kw):
 p=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',**NOWIN,**kw)
 if p.returncode:raise SystemExit(f'FAILED: {args[0]} …\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}')
 return p.stdout

def speech(text,dest):
 """A spoken sentence from the OS voice (English voices are fine: this checks the pipeline, not accuracy)."""
 if WINDOWS:
  ps=(f"Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
      f"$s.SetOutputToWaveFile('{dest}');$s.Speak('{text}');$s.Dispose()")
  subprocess.run(['powershell','-NoProfile','-Command',ps],capture_output=True,**NOWIN)
 elif MAC:subprocess.run(['say','-o',str(dest),'--data-format=LEI16@22050',text],capture_output=True)
 return Path(dest).exists() and Path(dest).stat().st_size>10000

def main():
 vlm='--vlm' in sys.argv
 work=Path(tempfile.mkdtemp(prefix='ghepvideo-smoke-'));media=work/'Video - ảnh';out=work/'output';media.mkdir();out.mkdir()
 print('Tạo tư liệu thử trong',work,flush=True)
 run([FFMPEG,'-v','error','-f','lavfi','-i','testsrc2=s=720x1280:d=6:r=30','-pix_fmt','yuv420p',str(media/'canh 1.mp4')])
 run([FFMPEG,'-v','error','-f','lavfi','-i','mandelbrot=s=1280x720:r=30','-t','6','-pix_fmt','yuv420p',str(media/'cảnh ngang 2.mp4')])
 from PIL import Image,ImageDraw
 img=Image.new('RGB',(1080,1920),(40,90,140));d=ImageDraw.Draw(img);d.ellipse((340,500,740,1000),fill=(230,190,160));img.save(media/'ảnh 3.jpg')
 voice=work/'loi doc.wav'
 spoken=speech('Hello. This is a short test of the video app. Every family needs a little praise. Thank you for watching.',voice)
 if not spoken:run([FFMPEG,'-v','error','-f','lavfi','-i','sine=f=220:d=8','-ar','48000',str(voice)])
 job=dict(mediaFolder=str(media),audio=str(voice),music='',outputFolder=str(out),cacheFolder=str(out/'.studio-cache'),
          title='THỬ CÀI ĐẶT',subtitle='Ghép Video',titleStyle='pop',subStyle='sweep' if spoken else 'none',
          shotSeconds=2.5,resolution='1080',preview=True,removeSilence=True,faceAwareFill=False,matchScenes=False,
          voiceVolume=1.0,normalizeVoice=True,fixesText='',captionY=.73)
 (work/'job.json').write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
 t=time.time();print('Dựng video 1080p (nhận dạng lời đọc: %s)…'%('có' if spoken else 'không'),flush=True)
 log=run([sys.executable,'-u',str(HERE/'renderer.py'),str(work/'job.json')],env=dict(os.environ,PYTHONUTF8='1'))
 result=[json.loads(l) for l in log.splitlines() if l.startswith('{')][-1]
 if not result.get('output'):raise SystemExit('FAILED: renderer produced no video\n'+log[-2000:])
 info=json.loads(run([FFPROBE,'-v','error','-show_entries','stream=width,height:format=duration','-of','json',result['output']]))
 w,h=info['streams'][0]['width'],info['streams'][0]['height'];dur=float(info['format']['duration'])
 assert (w,h)==(1080,1920),f'unexpected size {w}x{h}'
 assert dur>2,f'video too short: {dur}'
 srt=Path(result['output']).with_suffix('.srt').read_text(encoding='utf-8')
 if spoken:assert srt.strip(),'no subtitles recognised'
 print(f'✓ Video {w}x{h}, {dur:.1f}s, {time.time()-t:.0f}s; phụ đề: {srt.splitlines()[2] if srt.strip() else "(không)"}',flush=True)
 if vlm:
  t=time.time();print('AI xem ảnh + ảnh bìa…',flush=True)
  run([sys.executable,'-u',str(HERE/'analyzer.py'),'analyze',str(media),'--no-rename'],env=dict(os.environ,PYTHONUTF8='1'))
  index=json.loads((media/'_phan-tich.json').read_text(encoding='utf-8'))['files']
  assert len(index)==3,f'analysed {len(index)} of 3 files'
  empty=[n for n,e in index.items() if not (e.get('mo_ta') or '').strip()]
  if empty:
   # Show exactly what the model answered, to see why no description came out.
   from platform_tools import vlm_ask
   raw=vlm_ask('Mô tả hình này bằng tiếng Việt, trả về đúng một JSON: {"mo_ta":"1 câu"}',[media/'ảnh 3.jpg'])
   raise SystemExit(f'FAILED: empty description for {empty}\nraw model answer: {raw[:600]!r}')
  for n,e in index.items():print(f'✓ {n}: {e["mo_ta"][:90]}',flush=True)
  print(f'  ({time.time()-t:.0f}s)',flush=True)
  import thumbnail
  thumbnail.find_candidates(json.loads(Path(result['output']).with_suffix('.json').read_text(encoding='utf-8')),str(media),out/'thumbs')
  print('✓ Tìm ảnh bìa chạy được',flush=True)
 print('SMOKE TEST OK')

if __name__=='__main__':main()
