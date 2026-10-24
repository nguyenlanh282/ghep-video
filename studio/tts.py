"""Voice-over from text with MiniMax Speech (the user's own API key and voice, e.g. a clone of their own voice).

  tts.py <job.json>    job: text, voice, model, speed, region, outDir.  API key: env MINIMAX_API_KEY only.

Long text is split at sentence ends into pieces the API accepts, synthesised one by one and joined into one MP3.
The same text + voice + settings reuses the file made before, so a second export costs nothing.
Progress is JSON lines on stdout, like renderer.py; the finished file is reported as {"done": true, "audio": path}.
"""
import hashlib, importlib, json, os, re, subprocess, sys, tempfile, time, unicodedata, urllib.error, urllib.request
from pathlib import Path
from platform_tools import DATA, FFMPEG, NOWIN, WINDOWS, utf8_stdio

HOSTS = {'intl': 'https://api.minimax.io', 'cn': 'https://api.minimaxi.com'}
MODELS = ('speech-2.8-hd', 'speech-2.8-turbo', 'speech-2.6-hd', 'speech-2.6-turbo', 'speech-02-hd', 'speech-02-turbo')
PIECE = 2500  # characters per request (the API allows 10,000; smaller pieces fail less and show progress)
ERRORS = {1002: 'MiniMax đang giới hạn tốc độ. Chờ 1 phút rồi thử lại.', 1004: 'API key MiniMax không đúng hoặc đã hết hạn.',
          1008: 'Tài khoản MiniMax không đủ số dư.', 1039: 'MiniMax đang giới hạn tốc độ. Chờ 1 phút rồi thử lại.',
          1042: 'Nội dung có quá nhiều ký tự lạ.', 2013: 'Thông tin gửi lên chưa đúng (kiểm tra Voice ID và mẫu giọng).',
          2049: 'API key MiniMax không đúng (kiểm tra đã dán đủ key, đúng khu vực Quốc tế / Trung Quốc).',
          2056: 'Gói MiniMax của key này đã hết lượt tạo giọng, hoặc gói (Token / Coding Plan) không có phần giọng nói. Kiểm tra gói trên trang MiniMax, hoặc dùng API key trả theo lượt.'}

def emit(progress, message, **extra):
    print(json.dumps(dict(progress=progress, message=message, **extra), ensure_ascii=False), flush=True)

def pieces(text, limit=PIECE):
    """Split at sentence ends (then commas, then spaces) so no piece is longer than limit."""
    text = unicodedata.normalize('NFC', text).strip()
    sentences = re.split(r'(?<=[.!?…。\n])\s+', text)
    out, cur = [], ''
    for s in sentences:
        if len(s) > limit and cur: out.append(cur); cur = ''
        while len(s) > limit:  # one very long sentence: cut at the last comma or space before the limit
            cut = max(s.rfind(',', 0, limit), s.rfind(' ', 0, limit))
            if cut <= 0: cut = limit - 1
            out.append(s[:cut + 1].strip()); s = s[cut + 1:].strip()
        if cur and len(cur) + 1 + len(s) > limit: out.append(cur); cur = s
        else: cur = (cur + ' ' + s).strip()
    return [p for p in out + [cur] if p.strip()]

def synthesize(text, job, key):
    body = dict(model=job['model'], text=text, stream=False, language_boost='Vietnamese', output_format='hex',
                voice_setting=dict(voice_id=job['voice'], speed=job['speed'], vol=1.0, pitch=int(job.get('pitch') or 0), **({'emotion': job['emotion']} if job.get('emotion') else {})),
                audio_setting=dict(sample_rate=44100, bitrate=256000, format='mp3', channel=1))  # bitrate: 32000/64000/128000/256000 only
    host = os.environ.get('MINIMAX_API_BASE') or HOSTS.get(job.get('region'), HOSTS['intl'])  # override only for tests
    req = urllib.request.Request(host + '/v1/t2a_v2', data=json.dumps(body).encode(),
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r: out = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < 3: time.sleep(3 * (attempt + 1)); continue
            raise RuntimeError(ERRORS[1004] if e.code in (401, 403) else f'MiniMax trả lỗi HTTP {e.code}.') from None
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            # MiniMax now and then drops a connection (more so with several requests in a row): wait and try again.
            if attempt < 3: time.sleep(3 * (attempt + 1)); continue
            raise RuntimeError(f'Không kết nối được MiniMax sau 4 lần thử ({getattr(e, "reason", e)}). Kiểm tra mạng (hoặc thử đổi khu vực Quốc tế / Trung Quốc).') from None
    base = out.get('base_resp') or {}
    code = base.get('status_code', -1)
    if code != 0:
        detail = str(base.get('status_msg', '')).strip()
        msg = (ERRORS.get(code) or f'MiniMax báo lỗi {code}') + (f' (MiniMax: {detail})' if detail and detail.lower() != 'success' else '')
        if 'voice' in str(base.get('status_msg', '')).lower(): msg = 'Không tìm thấy Voice ID này. Kiểm tra lại Voice ID giọng đã clone (và khu vực tài khoản).'
        raise RuntimeError(msg)
    audio = (out.get('data') or {}).get('audio')
    if not audio: raise RuntimeError('MiniMax không trả về âm thanh.')
    return bytes.fromhex(audio)

# ---------- Edge (Microsoft's free online voices): the fallback when MiniMax fails, or chosen on purpose ----------
EDGE_VOICES = {'vi-VN-NamMinhNeural': 'Nam Minh (nam)', 'vi-VN-HoaiMyNeural': 'Hoài My (nữ)'}

def edge_module():
    """The edge-tts library, installed into the app's own Python the first time it is needed."""
    try: return importlib.import_module('edge_tts')
    except ImportError: pass
    uv = DATA / 'bin' / ('uv.exe' if WINDOWS else 'uv')
    cmd = [str(uv), 'pip', 'install', '--python', sys.executable, '-q', 'edge-tts'] if uv.is_file() else [sys.executable, '-m', 'pip', 'install', '-q', 'edge-tts']
    r = subprocess.run(cmd, capture_output=True, **NOWIN)
    importlib.invalidate_caches()
    try: return importlib.import_module('edge_tts')
    except ImportError: raise RuntimeError('Chưa cài được giọng Edge (cần mạng lần đầu). ' + r.stderr.decode(errors='replace')[-200:]) from None

def edge_synthesize(text, voice='vi-VN-NamMinhNeural', speed=1.0, pitch=0):
    """MP3 bytes from Edge. speed 1.06 → +6 %; pitch in semitones (about 5 Hz each). Edge sometimes returns
    nothing: tried up to 4 times."""
    import asyncio
    edge = edge_module(); voice = voice if voice in EDGE_VOICES else 'vi-VN-NamMinhNeural'
    rate = f'{round((float(speed) - 1) * 100):+d}%'; ph = f'{int(pitch) * 5:+d}Hz'
    async def go():
        out = bytearray()
        async for chunk in edge.Communicate(text, voice, rate=rate, pitch=ph).stream():
            if chunk.get('type') == 'audio': out += chunk['data']
        return bytes(out)
    last = None
    for attempt in range(4):
        try:
            data = asyncio.run(go())
            if len(data) > 1000: return data
        except Exception as e: last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError('Giọng Edge chưa tạo được, kiểm tra mạng rồi thử lại.' + (f' ({last})' if last else ''))

def joined(files, dest):
    """Join MP3 pieces into dest (one piece is copied as is)."""
    part = dest.with_suffix('.part.mp3')
    if len(files) == 1: part.write_bytes(files[0].read_bytes())
    else:
        lst = files[0].parent / 'list.txt'; lst.write_text(''.join(f"file '{f.name}'\n" for f in files), encoding='utf-8')
        p = subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst), '-c:a', 'libmp3lame', '-b:a', '192k', str(part)], capture_output=True, **NOWIN)
        if p.returncode: raise RuntimeError('Ghép các đoạn giọng đọc chưa được: ' + p.stderr.decode(errors='replace')[-300:])
    part.replace(dest)

def run_edge(job, text, reason=''):
    out_dir = Path(job['outDir']); out_dir.mkdir(parents=True, exist_ok=True)
    voice = job.get('edgeVoice') if job.get('edgeVoice') in EDGE_VOICES else 'vi-VN-NamMinhNeural'; speed = max(.5, min(2, float(job.get('speed', 1) or 1)))
    sig = hashlib.sha1(json.dumps(['edge', text, voice, speed], ensure_ascii=False).encode()).hexdigest()[:8]
    words = re.sub(r'[\\/:*?"<>|\n\r]+', ' ', ' '.join(text.split()[:6])).strip()[:40]
    dest = out_dir / f'Giọng đọc Edge - {words} - {sig}.mp3'
    note = f'{reason} Đã dùng giọng Edge (miễn phí) thay thế.' if reason else ''
    if dest.is_file() and dest.stat().st_size > 1000:
        emit(100, (note + ' ' if note else '') + 'Đã có sẵn giọng đọc cho nội dung này.', done=True, audio=str(dest)); return
    parts = pieces(text, 1500)
    with tempfile.TemporaryDirectory(prefix='tts-edge-') as tmp:
        files = []
        for i, p in enumerate(parts):
            emit(5 + 85 * i / len(parts), (note + ' ' if note else '') + f'Giọng Edge đang đọc đoạn {i + 1}/{len(parts)}…')
            f = Path(tmp) / f'{i:03}.mp3'; f.write_bytes(edge_synthesize(p, voice, speed)); files.append(f)
        emit(92, 'Đang ghép và lưu giọng đọc…'); joined(files, dest)
    emit(100, (note + ' ' if note else '') + f'Đã tạo giọng đọc Edge ({len(text)} ký tự).', done=True, audio=str(dest))

def run(job):
    key = os.environ.get('MINIMAX_API_KEY', '').strip()
    text = (job.get('text') or '').strip()
    if not text: raise ValueError('Hãy nhập nội dung cần đọc.')
    if job.get('engine') == 'edge': return run_edge(job, text)
    if not key:
        if job.get('fallback', True): return run_edge(job, text, 'Chưa có API key MiniMax.')
        raise ValueError('Chưa có API key MiniMax.')
    if not (job.get('voice') or '').strip(): raise ValueError('Hãy nhập Voice ID (giọng đã clone trên MiniMax).')
    job = dict(job, voice=job['voice'].strip(), model=job.get('model') if job.get('model') in MODELS else MODELS[0],
               speed=max(.5, min(2, float(job.get('speed', 1) or 1))))
    out_dir = Path(job['outDir']); out_dir.mkdir(parents=True, exist_ok=True)
    sig = hashlib.sha1(json.dumps([text, job['voice'], job['model'], job['speed']], ensure_ascii=False).encode()).hexdigest()[:8]
    words = re.sub(r'[\\/:*?"<>|\n\r]+', ' ', ' '.join(text.split()[:6])).strip()[:40]
    dest = out_dir / f'Giọng đọc - {words} - {sig}.mp3'
    if dest.is_file() and dest.stat().st_size > 1000:
        emit(100, 'Đã có sẵn giọng đọc cho nội dung này (không tốn thêm phí).', done=True, audio=str(dest)); return
    parts = pieces(text)
    with tempfile.TemporaryDirectory(prefix='tts-') as tmp:
        files = []
        for i, p in enumerate(parts):
            emit(5 + 85 * i / len(parts), f'MiniMax đang đọc đoạn {i + 1}/{len(parts)}…' if len(parts) > 1 else 'MiniMax đang tạo giọng đọc…')
            for attempt in range(3):
                try: data = synthesize(p, job, key); break
                except RuntimeError as e:
                    if 'giới hạn tốc độ' in str(e) and attempt < 2: time.sleep(20); continue
                    if job.get('fallback', True): return run_edge(job, text, f'MiniMax lỗi: {e}')
                    raise
            f = Path(tmp) / f'{i:03}.mp3'; f.write_bytes(data); files.append(f)
        emit(92, 'Đang ghép và lưu giọng đọc…')
        part = dest.with_suffix('.part.mp3')
        if len(files) == 1: part.write_bytes(files[0].read_bytes())
        else:
            lst = Path(tmp) / 'list.txt'; lst.write_text(''.join(f"file '{f.name}'\n" for f in files), encoding='utf-8')
            p = subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst), '-c:a', 'libmp3lame', '-b:a', '192k', str(part)], capture_output=True, **NOWIN)
            if p.returncode: raise RuntimeError('Ghép các đoạn giọng đọc chưa được: ' + p.stderr.decode(errors='replace')[-300:])
        part.replace(dest)
    emit(100, f'Đã tạo giọng đọc ({len(text)} ký tự).', done=True, audio=str(dest))

if __name__ == '__main__':
    utf8_stdio()
    try: run(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
    except Exception as e: emit(-1, str(e), error=True); sys.exit(1)
