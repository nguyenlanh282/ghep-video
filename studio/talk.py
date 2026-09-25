"""Video chia sẻ: turn a raw talking-to-camera video into finished videos.

  analyze <job.json>   transcribe, find cuts (silence, "ờ/ừm", stutters, retakes), AI spelling fix, titles, caption +
                       hashtags, keywords, short-clip ideas, B-roll plan  →  project.json (edited in the app)
  render  <job.json>   cut + punch-in zoom + denoise + keyword captions + title + B-roll, in every chosen aspect ratio,
                       plus the chosen short clips

Every word keeps its original timing; a cut is just a flag on words (reason: im-lang/am-u/lap/noi-lai/tay), so the
transcript editor can restore or cut anything and subtitles stay in sync.
"""
import hashlib, json, math, os, re, shutil, subprocess, sys, tempfile, time, unicodedata, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import renderer as R
from analyzer import parse_json
from platform_tools import FFMPEG, FFPROBE, NOWIN, vlm_ask, ai_provider, utf8_stdio

emit = R.emit
nfc = lambda s: unicodedata.normalize('NFC', s)
FPS = 30
PAD_BEFORE, PAD_AFTER, MAX_GAP = .08, .14, .35
# Hesitation sounds. Whisper often leaves them out altogether; those show up as gaps and are cut the same way.
FILLERS = {'ờ', 'ơ', 'ừ', 'ừm', 'ưm', 'ờm', 'ậm', 'à', 'ầ', 'hừm', 'hmm', 'um', 'uhm', 'uh', 'ah', 'eh', 'ừa'}
ASPECTS = {'9:16': (1080, 1920), '1:1': (1080, 1080), '16:9': (1920, 1080)}
CAPTION_Y = {'9:16': None, '1:1': .80, '16:9': .86}  # None: the user's captionY setting
KEYWORD_COLOR = '#ff9f43'

def norm(w): return re.sub(r'[^\w]', '', nfc(w).lower())

# ---------------- analysis ----------------

def mark_auto_cuts(words):
    for w in words:
        if norm(w['text']) in FILLERS: w['cut'] = 'am-u'
    # Stutters: the same word twice in a row, or the same two words twice ("thứ ba thứ ba"): keep the last one.
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        if norm(a['text']) and norm(a['text']) == norm(b['text']) and b['start'] - a['end'] < .8 and not a.get('cut'): a['cut'] = 'lap'
    for i in range(len(words) - 3):
        if not any(words[j].get('cut') for j in range(i, i + 2)) and [norm(words[i]['text']), norm(words[i + 1]['text'])] == [norm(words[i + 2]['text']), norm(words[i + 3]['text'])] \
           and words[i + 2]['start'] - words[i + 1]['end'] < .8:
            words[i]['cut'] = words[i + 1]['cut'] = 'lap'

def phrase_list(words):
    """Phrases (sentence pieces) over all words, with their word index range."""
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and w['start'] - words[cur[-1]]['end'] > .65: out.append(cur); cur = []
        cur.append(i)
        if w['text'].endswith(R.PUNCT): out.append(cur); cur = []
    if cur: out.append(cur)
    return [dict(id=k + 1, first=p[0], last=p[-1], start=words[p[0]]['start'], end=words[p[-1]]['end'],
                 text=' '.join(words[i]['text'] for i in p)) for k, p in enumerate(out)]

def ai_json(question, schema=None, fallback=None):
    try: return parse_json(vlm_ask(question, (), schema), None) or (fallback if fallback is not None else {})
    except Exception as exc:
        emit(None, f'AI chưa trả lời được: {str(exc)[:160]}'); return fallback if fallback is not None else {}

def ai_correct(words, progress):
    """Spelling/diacritics, one word at a time so every timing stays put. Only single-word replacements are applied."""
    fixed = 0
    for c in range(0, len(words), 120):
        part = words[c:c + 120]
        lines = '\n'.join(f'{c + k}|{w["text"]}' for k, w in enumerate(part))
        got = ai_json(f'''Đây là bản nhận dạng giọng nói tiếng Việt, mỗi dòng là "số|từ". Sửa lỗi chính tả, thiếu dấu, sai dấu, sai từ do nhận dạng nhầm (dựa vào ngữ cảnh), viết hoa đầu câu và tên riêng. Giữ nguyên dấu câu đi kèm từ. KHÔNG thêm, bớt, gộp hay tách từ.
{lines}
Chỉ trả về những từ cần sửa, dạng JSON: {{"sua": {{"số": "từ đã sửa"}}}}''', fallback={})
        for k, v in (got.get('sua') or {}).items():
            i = int(k) if str(k).isdigit() else -1
            v = nfc(str(v)).strip()
            if c <= i < c + len(part) and v and ' ' not in v and v != words[i]['text']:
                words[i]['raw'] = words[i].get('raw', words[i]['text']); words[i]['text'] = v; fixed += 1
        progress(c / max(1, len(words)))
    return fixed

def sentences(words):
    """Whole sentences (split at . ? ! or a long pause only), so a comma pause never looks like an abandoned sentence."""
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and w['start'] - words[cur[-1]]['end'] > 1.2: out.append(cur); cur = []
        cur.append(i)
        if w['text'].endswith(('.', '?', '!', '…')): out.append(cur); cur = []
    if cur: out.append(cur)
    return [dict(id=k + 1, first=s[0], last=s[-1], text=' '.join(words[i]['text'] for i in s)) for k, s in enumerate(out)]

SELF_CORRECTION = re.compile(r'à không|ờ không|nhầm|nói lại|xin lỗi|không phải|ý mình là|à mà', re.I)

def is_retake(words, sent, later):
    """Safety check on the AI's pick: the next sentence(s) must repeat most of it, or it must contain a self-correction."""
    import difflib
    if SELF_CORRECTION.search(sent['text']): return True
    mine = [norm(words[i]['text']) for i in range(sent['first'], sent['last'] + 1) if not words[i].get('cut')]
    mine = [t for t in mine if t]
    if len(mine) < 2: return False
    for nxt in later[:2]:
        theirs = [t for t in (norm(words[i]['text']) for i in range(nxt['first'], nxt['last'] + 1)) if t]
        match = difflib.SequenceMatcher(None, mine, theirs[:len(mine) + 3]).find_longest_match(0, len(mine), 0, min(len(theirs), len(mine) + 3))
        if match.size >= max(2, .6 * len(mine)): return True
    return False

def ai_retakes(words, phrases):
    sents = sentences(words)
    listing = '\n'.join(f'{s["id"]}. {s["text"]}' for s in sents)
    got = ai_json(f'''Đây là lời nói trong một video chia sẻ quay 1 lần, chưa cắt (mỗi dòng là một câu).
Tìm các câu người nói đã nói HỎNG rồi NÓI LẠI: câu bỏ dở kèm "à không", "để mình nói lại", hoặc câu được lặp lại gần như y hệt ngay ở câu sau. Chỉ chọn câu hỏng cần bỏ; giữ lần nói hoàn chỉnh sau cùng. Câu mở đầu, câu chào, câu có nội dung riêng thì KHÔNG chọn. Nếu không có câu nào thì trả về danh sách rỗng.
{listing}
Trả về JSON: {{"bo": [số câu cần bỏ]}}''', fallback={})
    cut = 0
    for sid in got.get('bo') or []:
        k = next((k for k, s in enumerate(sents) if str(s['id']) == str(sid)), None)
        if k is None or not is_retake(words, sents[k], sents[k + 1:]): continue
        for i in range(sents[k]['first'], sents[k]['last'] + 1):
            if not words[i].get('cut'): words[i]['cut'] = 'noi-lai'; cut += 1
    return cut

def ai_package(phrases):
    listing = '\n'.join(f'{p["id"]}. [{p["start"]:.0f}s] {p["text"]}' for p in phrases)
    return ai_json(f'''Đây là lời nói của một video chia sẻ (mỗi dòng: số đoạn, thời điểm, nội dung):
{listing}

Hãy trả về đúng một JSON tiếng Việt có dấu:
{{"tieu_de": [{{"dong1": "tiêu đề chính gây tò mò, tối đa 6 chữ, VIẾT HOA", "dong2": "dòng phụ tối đa 8 chữ"}} (đúng 3 lựa chọn khác nhau)],
 "caption": "nội dung đăng TikTok/Facebook 2-4 câu, có lời kêu gọi theo dõi",
 "hashtag": ["6-10 hashtag tiếng Việt không dấu và tiếng Anh, có dấu #"],
 "tu_khoa": ["5-12 từ hoặc cụm từ quan trọng nhất đúng như trong lời nói (số liệu, tên sản phẩm, ý chính) để tô màu trong phụ đề"],
 "clip": [{{"tu": số đoạn bắt đầu, "den": số đoạn kết thúc, "tieu_de": "tiêu đề clip", "ly_do": "vì sao hay"}} (các đoạn hay nhất dài 20-90 giây, tự trọn ý; tối đa 5; bỏ trống nếu video ngắn hơn 40 giây)]}}''', fallback={})

def face_track(src, duration, tmp):
    """Where the speaker's face usually is (normalised centre and height), from frames across the video."""
    frames = []
    for k in range(8):
        f = tmp / f'face-{k}.jpg'
        t = duration * (k + .5) / 8
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', str(src), '-frames:v', '1', '-vf', 'scale=720:-2', '-q:v', '4', str(f)], capture_output=True, **NOWIN)
        if f.exists(): frames.append(f)
    try:
        from platform_tools import detect_faces_many
        found = detect_faces_many(frames) if frames else {}
    except Exception: found = {}
    centres = []
    for f in frames:
        faces = (found.get(str(f)) or {}).get('faces') or []
        if faces:
            x, y, w, h = max(faces, key=lambda b: b[2] * b[3]); centres.append((x + w / 2, y + h / 2, h))
    if not centres: return None
    cx, cy, h = (float(np.median([c[i] for c in centres])) for i in range(3))
    return dict(cx=cx, cy=cy, h=h)

def build_kho_units(folder, analysis):
    """B-roll candidates from the user's library folder (its AI analysis gives the descriptions)."""
    details = []
    for p in sorted(Path(folder).iterdir()) if folder and Path(folder).is_dir() else []:
        if p.name.startswith(('.', '_')) or p.suffix.lower() not in R.VIDEO | R.PHOTO: continue
        try: d = float(R.probe(p)['format'].get('duration', 0)) if p.suffix.lower() in R.VIDEO else 0
        except Exception: continue
        details.append((p, d, p))
    return R.build_units(details, analysis)

def pick_broll(phrases, words, choices, units, density):
    """Which phrases get a B-roll cut-away: never the opening phrase (the speaker's face hooks the viewer), not two in
    a row, at most `density` of the talk time, 1.5–3.5 s each."""
    by_id = {u['id']: u for u in units}; total = sum(p['end'] - p['start'] for p in phrases) or 1
    picked, used, last, used_units = [], 0, -9, set()
    for k, p in enumerate(phrases):
        length = p['end'] - p['start']
        if k == 0 or k - last < 2 or length < 1.5 or used / total >= density: continue
        ranked = [i for i in choices.get(p['id'], []) if i in by_id]
        uid = next((i for i in ranked if i not in used_units), ranked[0] if ranked else None)
        if uid is None: continue
        u = by_id[uid]; dur = min(3.5, length - .2)
        picked.append(dict(phrase=p['id'], first=p['first'], lead=.15, dur=round(dur, 2), path=str(u['path']), d=u['d'], a=u['a'], b=u['b'],
                           text=u['text'], source=u['source'], on=True))
        used += dur; last = k; used_units.add(uid)
    return picked

def analyze(job):
    src = Path(job['video']).expanduser().resolve()
    if not src.is_file(): raise ValueError('Chưa chọn video thô.')
    work = Path(job['projectDir']); work.mkdir(parents=True, exist_ok=True); cache = Path(job['cacheFolder']); cache.mkdir(parents=True, exist_ok=True)
    duration = float(R.probe(src)['format']['duration'])
    emit(3, 'Đang nghe và ghi lại lời nói (lần đầu hơi lâu)…')
    words = R.get_words(src, cache)
    for w in words: w['cut'] = None
    emit(25, 'Đang tìm chỗ im lặng, ậm ừ, nói vấp…'); mark_auto_cuts(words)
    ai = ai_provider()
    info = dict(ai=ai, corrected=0, retakes=0)
    if ai:
        emit(30, 'AI đang soát chính tả phụ đề…')
        info['corrected'] = ai_correct(words, lambda f: emit(30 + 15 * f, f'AI đang soát chính tả phụ đề… {int(f * 100)}%'))
    R.apply_fixes(words, R.parse_fixes(job.get('fixesText', '')))
    phrases = phrase_list(words)
    if ai and job.get('cutRetakes', True):
        emit(47, 'AI đang tìm câu nói hỏng rồi nói lại…'); info['retakes'] = ai_retakes(words, phrases)
    pack = {}
    if ai:
        emit(55, 'AI đang viết tiêu đề, caption, hashtag, chọn từ khoá và clip ngắn…'); pack = ai_package(phrases)
    emit(68, 'Đang tìm khuôn mặt người nói…')
    with tempfile.TemporaryDirectory(prefix='talk-face-') as tmp: face = face_track(src, duration, Path(tmp))
    broll = []
    kho = job.get('brollFolder')
    if job.get('broll', True) and ai:
        emit(72, 'Đang chọn cảnh trám hợp với từng câu…')
        analysis = R.load_analysis(Path(kho)) if kho and Path(kho).is_dir() else {}
        units = build_kho_units(kho, analysis) if analysis else []
        kept = [p for p in phrases if not all(words[i].get('cut') for i in range(p['first'], p['last'] + 1))]
        spans = [dict(start=p['start'], end=p['end'], text=p['text']) for p in kept]
        rjob = dict(job, stockEnabled=job.get('stockEnabled', False))
        plan = R.plan_scenes(spans, units, rjob, cache) if (units or rjob['stockEnabled']) else {}
        if plan:
            stock_dir = work / 'stock'; stock_dir.mkdir(exist_ok=True)
            R.add_stock(plan, units, stock_dir, 1080, 1920, False)
            ids = {k + 1: p['id'] for k, p in enumerate(kept)}
            choices = {ids[k]: v for k, v in plan['choices'].items() if k in ids}
            broll = pick_broll(kept, words, choices, units, float(job.get('brollDensity', .3)))
    shorts = []
    for c in (pack.get('clip') or [])[:5]:
        a = next((p for p in phrases if str(p['id']) == str(c.get('tu'))), None); b = next((p for p in phrases if str(p['id']) == str(c.get('den'))), None)
        if a and b and b['end'] - a['start'] >= 15:
            shorts.append(dict(first=a['first'], last=b['last'], title=str(c.get('tieu_de', ''))[:60], reason=str(c.get('ly_do', ''))[:160], on=True))
    titles = [dict(dong1=str(t.get('dong1', ''))[:40], dong2=str(t.get('dong2', ''))[:60]) for t in (pack.get('tieu_de') or []) if isinstance(t, dict)][:3]
    project = dict(version=1, source=str(src), duration=duration, created=time.strftime('%Y-%m-%d %H:%M'), words=words, face=face,
                   titles=titles, caption=str(pack.get('caption', '')), hashtags=[str(h) for h in (pack.get('hashtag') or [])][:12],
                   keywords=[str(k) for k in (pack.get('tu_khoa') or [])][:15], shorts=shorts, broll=broll, info=info)
    (work / 'project.json').write_text(json.dumps(project, ensure_ascii=False, indent=1), encoding='utf-8')
    cut = sum(w['end'] - w['start'] for w in words if w.get('cut'))
    kept_len = sum(b - a for a, b in keep_ranges(words, duration))
    emit(100, f'Đã phân tích: giữ {kept_len:.0f}s trên {duration:.0f}s video thô' + (f', AI sửa {info["corrected"]} chữ' if ai else ' (chưa có AI: bỏ qua soát chính tả, tiêu đề, cảnh trám)'),
         done=True, project=str(work / 'project.json'))

# ---------------- cutting ----------------

def keep_ranges(words, duration, first=0, last=None):
    """Source-time ranges to keep: runs of kept words, padded, split wherever a cut word or a pause sits between them."""
    last = len(words) - 1 if last is None else last
    runs, cur = [], None
    for i in range(first, last + 1):
        w = words[i]
        if w.get('cut'):
            if cur: runs.append(cur); cur = None
            continue
        if cur and w['start'] - cur[1] > MAX_GAP: runs.append(cur); cur = None
        cur = [w['start'], w['end']] if cur is None else [cur[0], w['end']]
    if cur: runs.append(cur)
    out = []
    for k, (a, b) in enumerate(runs):
        lo = max(0, a - PAD_BEFORE, (runs[k - 1][1] + a) / 2 if k else 0)
        hi = min(duration, b + PAD_AFTER, (b + runs[k + 1][0]) / 2 if k + 1 < len(runs) else duration)
        if out and lo - out[-1][1] < .12: out[-1][1] = hi
        else: out.append([lo, hi])
    return [(round(a, 3), round(b, 3)) for a, b in out if b - a > .05]

def clean_audio(src, work, denoise):
    """Source audio as 48 kHz stereo PCM, optionally denoised (hum cut, broadband noise reduction). Cached per project."""
    dest = work / ('voice-denoised.wav' if denoise else 'voice.wav')
    if not dest.exists():
        af = 'highpass=f=70,afftdn=nf=-28:nr=18:tn=1,lowpass=f=14000' if denoise else 'anull'
        R.run([FFMPEG, '-v', 'error', '-y', '-i', str(src), '-vn', '-af', af, '-ac', '2', '-ar', '48000', '-c:a', 'pcm_s16le', str(dest)])
    return dest

def cut_audio(wav, keep, dest):
    with wave.open(str(wav)) as f: pcm = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2').reshape(-1, 2)
    parts = []
    for a, b in keep:
        part = pcm[round(a * 48000):round(b * 48000)].astype(np.float32); fade = min(384, len(part) // 2)
        if fade: part[:fade] *= np.linspace(0, 1, fade)[:, None]; part[-fade:] *= np.linspace(1, 0, fade)[:, None]
        parts.append(part.astype('<i2').tobytes())
    with wave.open(str(dest), 'wb') as f: f.setnchannels(2); f.setsampwidth(2); f.setframerate(48000); f.writeframes(b''.join(parts))
    return dest

def speaker_crop(W0, H0, face, W, H, zoom):
    """Cover-crop of the speaker for the output aspect: face centred horizontally, eyes near the upper third."""
    ratio = W / H
    cw = min(W0, H0 * ratio) / zoom; ch = cw / ratio
    cx = (face['cx'] if face else .5) * W0; cy = (face['cy'] if face else .42) * H0
    x = min(max(0, cx - cw / 2), W0 - cw); y = min(max(0, cy - ch * .38), H0 - ch)
    return round(x), round(y), round(cw), round(ch)

# ---------------- rendering ----------------

def caption_img(group, positions, font, style, active, keywords, W, top, height):
    layer = Image.new('RGBA', (W, height)); d = ImageDraw.Draw(layer); sw = max(2, round(font.size / 17)); hl = R.HIGHLIGHT.get(style)
    for j, w in enumerate(group):
        x, y = positions[j]
        color = hl if hl and j == active else KEYWORD_COLOR if w.get('kw') else 'white'
        d.text((x, y - top), w['text'], font=font, anchor='ls', fill=color, stroke_width=sw, stroke_fill='#171717')
    return layer

def mark_keywords(words, keywords):
    seqs = [[norm(t) for t in k.split() if norm(t)] for k in keywords]
    toks = [norm(w['text']) for w in words]
    for i in range(len(words)):
        for s in seqs:
            if s and toks[i:i + len(s)] == s:
                for j in range(i, i + len(s)): words[j]['kw'] = True

def render_variant(project, job, aspect, first, last, title, dest, tmp, progress):
    src = Path(project['source']); W, H = ASPECTS[aspect]; words = project['words']
    keep = keep_ranges(words, project['duration'], first, last)
    if not keep: raise ValueError('Không còn đoạn nào để xuất (tất cả đã bị cắt).')
    total = sum(b - a for a, b in keep)
    # Output-time words (for captions) and speaker pieces.
    out_words = []
    for i in range(first, last + 1):
        w = words[i]
        if w.get('cut'): continue
        a, b = R.mapped_time(w['start'], keep), R.mapped_time(w['end'], keep)
        if b > a + .001: out_words.append(dict(text=w['text'], start=a, end=b, kw=w.get('kw', False)))
    info = R.probe(src); vs = next(s for s in info['streams'] if s['codec_type'] == 'video')
    rot = abs(int(float((vs.get('side_data_list') or [{}])[0].get('rotation', 0) or 0))) % 180 == 90
    W0, H0 = (vs['height'], vs['width']) if rot else (vs['width'], vs['height'])
    zoom_on = job.get('punchIn', True); face = project.get('face')
    pieces, t = [], 0.0
    for k, (a, b) in enumerate(keep):
        pieces.append(dict(kind='speaker', out=t, len=b - a, src=a, zoom=1.12 if zoom_on and k % 2 else 1.0)); t += b - a
    # B-roll cut-aways replace the speaker picture for a moment; the voice keeps running underneath.
    for br in project.get('broll', []):
        if not br.get('on') or not (first <= br['first'] <= last) or words[br['first']].get('cut'): continue
        o = R.mapped_time(words[br['first']]['start'], keep) + br.get('lead', .15); o2 = min(total - .1, o + br['dur'])
        if o2 - o < .8 or o < 1.0: continue
        new = []
        for p in pieces:
            e = p['out'] + p['len']
            if p['kind'] != 'speaker' or e <= o or p['out'] >= o2: new.append(p); continue
            if p['out'] < o: new.append(dict(p, len=o - p['out']))
            new.append(dict(kind='broll', out=max(o, p['out']), len=min(e, o2) - max(o, p['out']), br=br, off=max(0, p['out'] - o)))
            if e > o2: new.append(dict(p, out=o2, len=e - o2, src=p['src'] + (o2 - p['out'])))
        pieces = new
    clips = []
    for n, p in enumerate(pieces):
        frames = round((p['out'] + p['len']) * FPS) - round(p['out'] * FPS)
        if frames < 1: continue
        out = tmp / f'{aspect.replace(":", "x")}-{n:04}.mp4'
        if p['kind'] == 'speaker':
            if (W0 / H0) / (W / H) < .6:
                # Upright footage in a wide frame: keep the whole speaker in the middle over a blurred copy, not a huge zoom.
                fh = round(H * p['zoom']); fw = round(fh * W0 / H0 / 2) * 2
                vf = (f'split=2[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=30[b];'
                      f'[fg]scale={fw}:{fh}[f];[b][f]overlay=(W-w)/2:(H-h)*0.4,setsar=1,fps={FPS}')
            else:
                x, y, cw, ch = speaker_crop(W0, H0, face, W, H, p['zoom'])
                vf = f'crop={cw}:{ch}:{x}:{y},scale={W}:{H},setsar=1,fps={FPS}'
            cmd = [FFMPEG, '-v', 'error', '-y', '-ss', f'{p["src"]:.3f}', '-i', str(src), '-vf', vf]
        else:
            br = p['br']; bp = Path(br['path'])
            vf = f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}'
            if br['d']: cmd = [FFMPEG, '-v', 'error', '-y', '-stream_loop', '-1', '-ss', f'{min(max(0, br["d"] - 4), br["a"] + p["off"]):.3f}', '-i', str(bp), '-vf', vf]
            else: cmd = [FFMPEG, '-v', 'error', '-y', '-loop', '1', '-i', str(bp), '-vf', vf]
        R.run(cmd + ['-frames:v', str(frames), '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p', str(out)])
        clips.append(out); progress(.1 + .45 * (n + 1) / len(pieces))
    voice = cut_audio(clean_audio(src, Path(job['projectDir']), job.get('denoise', True)), keep, tmp / f'voice-{aspect.replace(":", "x")}-{first}.wav')
    concat = tmp / f'clips-{aspect.replace(":", "x")}-{first}.txt'; concat.write_text(''.join(f"file '{c.name}'\n" for c in clips), encoding='utf-8')
    nframes = round(total * FPS)
    movie = tmp / f'movie-{aspect.replace(":", "x")}-{first}.mp4'
    music = Path(job['music']) if job.get('music') and Path(job['music']).is_file() else None
    gain = R.voice_gain_db(voice, job, Path(job['cacheFolder']))
    cmd = [FFMPEG, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', 'pipe:0', '-i', str(voice)]
    vchain = f'[1:a]asetpts=PTS-STARTPTS,volume={gain:.2f}dB[voice];'
    if music:
        vol = max(0, min(1, float(job.get('musicVolume', .15))))
        cmd += ['-stream_loop', '-1', '-i', str(music), '-filter_complex', vchain + f'[2:a]asetpts=PTS-STARTPTS,volume={vol},afade=t=out:st={max(0, total - 1.2)}:d=1.2[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.79:level=0[a]']
    else: cmd += ['-filter_complex', vchain + '[voice]alimiter=limit=0.79:level=0[a]']
    cmd += ['-map', '0:v', '-map', '[a]', '-t', f'{total:.3f}', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(movie)]
    dec = subprocess.Popen([FFMPEG, '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(concat), '-frames:v', str(nframes), '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], stdout=subprocess.PIPE, **NOWIN)
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, **NOWIN); R.CHILDREN.extend([dec, enc])
    # Captions: same steady karaoke line as the main mode, sized to the shorter side so every aspect reads alike.
    size = round(60 * min(W, H) / 1080); font = ImageFont.truetype(R.FONT, size)
    groups = R.groups_for(out_words, max_width=min(.83 * W, 1150) * 40 / size)
    cy = CAPTION_Y[aspect] or float(job.get('captionY', .73))
    positions = [R.caption_layout(g, font, W, H, cy) for g in groups]; top, bh = R.caption_band(font, H, cy)
    tw = min(W, 1080); tjob = dict(job, title=title[0], subtitle=title[1])
    title_img = R.make_title(tjob, tw, H) if job.get('titleStyle', 'pop') != 'none' and (title[0] or title[1]) else None
    ty = round(H * (.21875 if aspect == '9:16' else .12)); style = job.get('subStyle', 'sweep'); gi = 0; key = None; cap = None
    try:
        for n in range(nframes):
            data = dec.stdout.read(W * H * 3)
            if len(data) != W * H * 3: raise RuntimeError(f'Video dừng ở khung {n}/{nframes}.')
            im = Image.frombytes('RGB', (W, H), data); t = n / FPS
            if title_img and t < 3.4:
                z = .86 + .14 * min(1, t / .22); ov = title_img if z >= 1 else title_img.resize((round(tw * z), round(title_img.height * z)))
                im.paste(ov, ((W - ov.width) // 2, ty), ov)
            if style != 'none' and groups:
                while gi + 1 < len(groups) and groups[gi + 1][0]['start'] <= t: gi += 1
                g = groups[gi]
                if g[0]['start'] <= t < R.group_end(groups, gi, total):
                    active = next((j for j, w in enumerate(g) if w['start'] <= t < w['end']), -1)
                    if (gi, active) != key: key = (gi, active); cap = caption_img(g, positions[gi], font, style, active, None, W, top, bh)
                    im.paste(cap, (0, top), cap)
            enc.stdin.write(im.tobytes())
            if n % 30 == 0: progress(.55 + .43 * n / nframes)
        enc.stdin.close()
        if enc.wait() != 0: raise RuntimeError(enc.stderr.read().decode(errors='replace')[-800:])
        dec.stdout.close(); dec.wait()
    finally:
        for p in (dec, enc):
            if p.poll() is None: p.terminate()
            if p in R.CHILDREN: R.CHILDREN.remove(p)
    partial = dest.with_name('.' + dest.name + '.partial'); shutil.copyfile(movie, partial); partial.replace(dest)
    dest.with_suffix('.srt').write_text('\n\n'.join(f'{i + 1}\n{R.srt_stamp(g[0]["start"])} --> {R.srt_stamp(R.group_end(groups, i, total))}\n' + ' '.join(w['text'] for w in g)
                                                    for i, g in enumerate(groups)), encoding='utf-8')
    return dict(path=str(dest), duration=round(total, 2), cut=round(sum(words[i]['end'] - words[i]['start'] for i in range(first, last + 1) if words[i].get('cut')), 1))

def render(job):
    project = json.loads(Path(job['projectDir'], 'project.json').read_text(encoding='utf-8'))
    words = project['words']
    if job.get('highlightKeywords', True): mark_keywords(words, project.get('keywords', []))
    aspects = [a for a in job.get('aspects', ['9:16']) if a in ASPECTS] or ['9:16']
    shorts = [s for s in project.get('shorts', []) if s.get('on')] if job.get('exportShorts', True) else []
    stem = re.sub(r'[\\/:*?"<>|]+', ' ', Path(project['source']).stem).strip()[:50]
    folder = Path(job['outputFolder']) / f'{stem} - hoàn thiện {time.strftime("%Y%m%d-%H%M")}'; folder.mkdir(parents=True, exist_ok=True)
    title = (job.get('title', ''), job.get('subtitle', ''))
    tasks = [(a, 0, len(words) - 1, title, folder / f'{stem} {a.replace(":", "x")}.mp4') for a in aspects]
    tasks += [('9:16', s['first'], s['last'], (s['title'].upper()[:40], ''), folder / f'Clip {k + 1} - {re.sub(r"[^\w ]+", "", s["title"])[:40].strip() or k + 1}.mp4') for k, s in enumerate(shorts)]
    results = []
    with tempfile.TemporaryDirectory(prefix='talk-render-') as tmp:
        for n, (aspect, a, b, ttl, dest) in enumerate(tasks):
            label = f'clip ngắn {n - len(aspects) + 1}' if n >= len(aspects) else f'video {aspect}'
            base = 100 * n / len(tasks); step = 100 / len(tasks)
            emit(base, f'Đang xuất {label}…')
            results.append(dict(render_variant(project, job, aspect, a, b, ttl, dest, Path(tmp), lambda f: emit(base + step * f, f'Đang xuất {label} · {int(f * 100)}%')), kind=label))
    post = (project.get('caption', '') + '\n\n' + ' '.join(project.get('hashtags', []))).strip()
    if post: (folder / 'caption-hashtag.txt').write_text(post + '\n', encoding='utf-8')
    (folder / 'ket-qua.json').write_text(json.dumps(dict(results=results, job={k: v for k, v in job.items() if 'Key' not in k}), ensure_ascii=False, indent=1), encoding='utf-8')
    emit(100, f'Đã xuất {len(results)} video vào thư mục “{folder.name}”.', done=True, output=results[0]['path'], folder=str(folder))

if __name__ == '__main__':
    import signal
    utf8_stdio()
    def cancel(*_):
        for p in R.CHILDREN:
            try: p.terminate()
            except Exception: pass
        raise SystemExit(130)
    signal.signal(signal.SIGTERM, cancel); signal.signal(signal.SIGINT, cancel)
    try:
        cmd, path = sys.argv[1], sys.argv[2]
        job = json.loads(Path(path).read_text(encoding='utf-8'))
        {'analyze': analyze, 'render': render}[cmd](job)
    except Exception as e:
        R.emit(-1, str(e), error=True); sys.exit(1)
