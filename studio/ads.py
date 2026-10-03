"""Video quảng cáo: product brief → script (AI or an empty frame to fill in) → one video per chosen hook.

  ads.py script <job.json>   AI writes hooks + parts + call to action as JSON into job['scriptFile']
  ads.py render <job.json>   voice-over per part (MiniMax) or one recording, then renderer.py once per hook

A script is {kieu, giay, hooks:[{loi, chu}], phan:[{vai, hinh, loi, chu}], cta:{loi, chu, hinh}, caption, hashtags, luu_y}:
loi = what the voice says, chu = the short line shown on screen, hinh = what the picture should show.
Progress is JSON lines on stdout, like renderer.py. API keys: env MINIMAX_API_KEY only.
"""
import hashlib, json, os, re, shutil, subprocess, sys, time, unicodedata
from pathlib import Path

# kind → (name, when to use it, parts as (label, what the voice does, what the picture shows))
AD_TYPES = {
    'van-de': ('Vấn đề → Giải pháp', 'Dễ ra đơn nhất, hợp hầu hết sản phẩm', [
        ('Vấn đề', 'tả đúng tình trạng người xem đang gặp, bằng chữ của họ', 'cảnh thật đang gặp vấn đề'),
        ('Vì sao', 'nguyên nhân thật sự, ngắn gọn', 'cận cảnh chỗ gây ra vấn đề'),
        ('Giải pháp', 'giới thiệu sản phẩm là cách xử lý', 'sản phẩm, người đang dùng sản phẩm'),
        ('Lợi ích', '2–3 lợi ích cụ thể, có căn cứ', 'kết quả sau khi dùng')]),
    'truoc-sau': ('Trước / Sau', 'Sản phẩm cho kết quả nhìn thấy được', [
        ('Trước', 'tình trạng ban đầu', 'cảnh lúc chưa dùng'),
        ('Cách dùng', 'dùng sản phẩm thế nào, bao lâu', 'thao tác dùng sản phẩm'),
        ('Sau', 'kết quả thật nhìn thấy được', 'cảnh sau khi dùng, cùng góc quay'),
        ('Lưu ý', 'điều kiện để có kết quả đó', 'sản phẩm và nhãn')]),
    'tinh-nang': ('Chỉ ra tính năng', 'Giới thiệu sản phẩm mới, cận cảnh', [
        ('Giới thiệu', 'đây là gì, dành cho ai', 'cầm sản phẩm trên tay'),
        ('Điểm 1', 'điểm mạnh thứ nhất và lợi ích của nó', 'cận cảnh điểm đó'),
        ('Điểm 2', 'điểm mạnh thứ hai', 'cận cảnh điểm đó'),
        ('Điểm 3', 'điểm mạnh thứ ba', 'cận cảnh điểm đó')]),
    'liet-ke': ('Liệt kê “3 lý do”', 'Nhiều ý, dễ quay, hợp mọi ngành', [
        ('Lý do 1', 'lý do thứ nhất, một câu', 'cảnh minh họa lý do 1, chữ đánh số'),
        ('Lý do 2', 'lý do thứ hai', 'cảnh minh họa lý do 2'),
        ('Lý do 3', 'lý do mạnh nhất để cuối', 'cảnh minh họa lý do 3'),
        ('Chốt', 'nối các lý do về sản phẩm', 'sản phẩm')]),
    'huong-dan': ('Hướng dẫn từng bước', 'Trông ít giống quảng cáo, tăng lòng tin', [
        ('Kết quả', 'làm xong sẽ được gì', 'thành quả cuối cùng'),
        ('Bước 1', 'việc đầu tiên cần làm', 'thao tác bước 1'),
        ('Bước 2', 'việc tiếp theo, sản phẩm dùng ở đây', 'thao tác bước 2 với sản phẩm'),
        ('Bước 3', 'việc cuối và điều cần tránh', 'thao tác bước 3')]),
    'cam-nhan': ('Người dùng kể lại', 'Có khách thật, vườn thật, kết quả thật', [
        ('Trước khi dùng', 'người dùng kể tình trạng của mình', 'người thật tại nơi của họ'),
        ('Trải nghiệm', 'dùng thế nào, thấy gì đầu tiên', 'cảnh họ đang dùng'),
        ('Kết quả', 'kết quả thật, không nói quá', 'kết quả tại chỗ'),
        ('Lời khuyên', 'họ khuyên ai nên dùng', 'người dùng và sản phẩm')]),
    'nhieu-nguoi': ('Ghép nhiều người dùng', 'Nhiều khách cùng nói, bằng chứng mạnh', [
        ('Người 1', 'một câu cảm nhận ngắn', 'người dùng thứ nhất'),
        ('Người 2', 'một câu cảm nhận khác góc', 'người dùng thứ hai'),
        ('Người 3', 'một câu về kết quả', 'người dùng thứ ba'),
        ('Điểm chung', 'điều cả ba cùng nhận thấy và sản phẩm', 'sản phẩm')]),
    'sang-lap': ('Chuyện người làm ra', 'Xây lòng tin cho thương hiệu', [
        ('Vì sao làm', 'lý do bắt đầu làm sản phẩm này', 'người chủ tại xưởng hoặc vườn'),
        ('Cách làm', 'điều làm khác người khác', 'cảnh sản xuất, kiểm tra'),
        ('Cam kết', 'điều doanh nghiệp giữ đúng với khách', 'đội ngũ, sản phẩm'),
        ('Lời mời', 'mời thử một cách nhẹ nhàng', 'sản phẩm và người chủ')]),
}
# formula → (name, the mechanism in one line)
HOOKS = {
    'tuyen-bo': ('Tuyên bố mạnh', 'một câu khẳng định ngược với điều người xem vẫn tin, chứng minh được ở phần sau'),
    'to-mo': ('Khoảng trống tò mò', 'hé một điều cụ thể mà chưa nói hết, phần sau phải trả lời thật'),
    'hoi-thang': ('Hỏi thẳng nỗi đau', 'hỏi đúng tình trạng người xem đang gặp'),
    'ket-qua': ('Kết quả trước', 'đưa thành quả lên đầu, khiến người xem muốn biết cách làm'),
    'tra-loi': ('Trả lời câu hỏi của khách', 'mở bằng một câu khách hay hỏi trước khi mua'),
    'soi-guong': ('Soi gương hiện trạng', 'tả tình cảnh của người xem chính xác đến mức họ nhận ra mình'),
    'sai-lam': ('Sai lầm đang mắc', 'chỉ ra một sai lầm có thật mà nhiều người mắc'),
    'nguoi-trong-nghe': ('Người trong nghề khuyên', 'lời khuyên từ người làm nghề lâu năm'),
}
LENGTHS = (15, 30, 45, 60)
# How lively the ad sounds: (name, how the script is worded, MiniMax emotion, speed ×, pitch in semitones)
ENERGY = {
    'thuong': ('Tự nhiên', 'giọng kể tự nhiên, điềm đạm, như đang nói chuyện', None, 1.0, 0),
    'soi-noi': ('Sôi nổi', 'giọng sôi nổi, hào hứng, câu ngắn, nhịp nhanh, có câu cảm thán nhưng không la hét', 'happy', 1.06, 1),
    'rat-soi-noi': ('Rất sôi nổi', 'giọng rất hào hứng như người bán hàng đang livestream, câu rất ngắn, dồn dập, nhiều câu cảm thán, nhấn mạnh ưu đãi', 'happy', 1.12, 2),
}
WORDS_PER_SECOND = 3.6   # Vietnamese voice-over at a natural pace
BRIEF = ('adProduct', 'adAudience', 'adProblem', 'adBenefits', 'adProof', 'adOffer', 'adCta', 'adNotes')

def emit(progress, message, **extra):
    print(json.dumps(dict(progress=progress, message=message, **extra), ensure_ascii=False), flush=True)

def nfc(s): return unicodedata.normalize('NFC', str(s or ''))
def plain(s): return ''.join(c for c in unicodedata.normalize('NFD', nfc(s).lower().replace('đ', 'd')) if unicodedata.category(c) != 'Mn')
def meta(): return dict(types=[dict(id=k, name=v[0], when=v[1], parts=[p[0] for p in v[2]]) for k, v in AD_TYPES.items()],
                        hooks=[dict(id=k, name=v[0], how=v[1]) for k, v in HOOKS.items()], lengths=list(LENGTHS),
                        energy=[dict(id=k, name=v[0], speed=v[3]) for k, v in ENERGY.items()])

# ---------- script ----------
def clean(script, kind='van-de', seconds=30):
    """Whatever came back (AI, the editor, an old file) as a well-formed script."""
    s = script if isinstance(script, dict) else {}
    text = lambda v, n=600: ' '.join(nfc(v).split())[:n]
    part = lambda p, vai='': dict(vai=text(p.get('vai') or vai, 40), hinh=text(p.get('hinh'), 200), loi=text(p.get('loi')), chu=text(p.get('chu'), 70)) if isinstance(p, dict) else None
    hooks = [dict(loi=text(h.get('loi'), 200), chu=text(h.get('chu'), 60), hinh=text(h.get('hinh'), 200), kieu=text(h.get('kieu'), 30)) for h in s.get('hooks') or [] if isinstance(h, dict)][:6]
    cta = s.get('cta') if isinstance(s.get('cta'), dict) else {}
    return dict(kieu=s.get('kieu') if s.get('kieu') in AD_TYPES else kind, giay=int(s.get('giay') or seconds),
                hooks=hooks, phan=[p for p in (part(x) for x in (s.get('phan') or [])[:8]) if p],
                cta=dict(loi=text(cta.get('loi'), 300), chu=text(cta.get('chu'), 60), hinh=text(cta.get('hinh'), 200)),
                caption=nfc(s.get('caption'))[:1500].strip(), hashtags=[text(h, 40) for h in (s.get('hashtags') or []) if str(h).strip()][:15],
                luu_y=[text(x, 300) for x in (s.get('luu_y') or []) if str(x).strip()][:8])

def skeleton(kind, seconds, brief):
    """The frame to write by hand: the parts of this kind of ad, with what each should say and show."""
    name, _, parts = AD_TYPES.get(kind, AD_TYPES['van-de'])
    return clean(dict(kieu=kind, giay=seconds,
                      hooks=[dict(loi='', chu='', hinh='cảnh mạnh nhất, hiện ngay giây đầu', kieu=HOOKS[k][0]) for k in ('hoi-thang', 'soi-guong', 'ket-qua')],
                      phan=[dict(vai=label, hinh=show, loi='', chu='') for label, say, show in parts],
                      cta=dict(loi=brief.get('adCta', ''), chu=brief.get('adCta', '')[:60], hinh='sản phẩm, cách liên hệ'),
                      luu_y=[f'{label}: {say}.' for label, say, show in parts]), kind, seconds)

def knowledge(folder, brief, budget=12000, top=6):
    """Notes about this product from the user's own knowledge folder (Markdown), best matches first."""
    root = Path(folder) if folder else None
    if not root or not root.is_dir(): return []
    product = plain(brief.get('adProduct', '')).strip()
    terms = {t for t in re.findall(r'[a-z0-9]{3,}', plain(' '.join(brief.get(k, '') for k in ('adProduct', 'adProblem', 'adBenefits'))))}
    if not terms: return []
    scored = []
    for n, f in enumerate(root.rglob('*.md')):
        if n > 8000: break
        rel = f.relative_to(root)
        if any(p.startswith('.') or p in ('node_modules', '__pycache__') for p in rel.parts): continue
        try:
            if f.stat().st_size > 300_000: continue
            body = f.read_text(encoding='utf-8', errors='ignore')
        except OSError: continue
        low = plain(body); name = plain(str(rel)).replace('-', ' ').replace('_', ' ')
        score = sum(6 for t in terms if t in name) + sum(min(low.count(t), 6) for t in terms)
        if product and product in low: score += 25 + 4 * min(low.count(product), 10)
        if product and product.replace(' ', '') in name.replace(' ', ''): score += 40
        if product and product not in low: score //= 3   # notes that never name the product are background at best
        if score >= 12: scored.append((score, str(rel), body))
    scored.sort(key=lambda x: -x[0]); out = []; left = budget
    for score, rel, body in scored[:top]:
        # The paragraphs that talk about the product (or the terms), in their original order.
        paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
        keep = [p for p in paras if (product and product in plain(p)) or sum(t in plain(p) for t in terms) >= 2] or paras[:4]
        piece = "\n\n".join(keep)[:min(left, 3000)]
        if len(piece) < 30: continue
        out.append(dict(file=rel, text=piece)); left -= len(piece)
        if left < 400: break
    return out

def question(brief, kind, seconds, notes, energy='soi-noi'):
    name, when, parts = AD_TYPES[kind]; tone = ENERGY.get(energy, ENERGY['soi-noi']); words = round(seconds * WORDS_PER_SECOND * tone[3])
    info = '\n'.join(f'- {label}: {nfc(brief.get(k, "")).strip()}' for k, label in (
        ('adProduct', 'Sản phẩm'), ('adAudience', 'Khách hàng'), ('adProblem', 'Vấn đề của khách'), ('adBenefits', 'Lợi ích / điểm mạnh'),
        ('adProof', 'Bằng chứng có thật'), ('adOffer', 'Ưu đãi'), ('adCta', 'Lời kêu gọi / cách liên hệ'), ('adNotes', 'Lưu ý riêng')) if nfc(brief.get(k, '')).strip())
    kb = '\n\n'.join(f'[Tài liệu: {n["file"]}]\n{n["text"]}' for n in notes)
    return f'''Bạn là người viết kịch bản video quảng cáo ngắn (TikTok, Reels, Shorts) bằng tiếng Việt, giọng nói đời thường, câu ngắn, dễ đọc thành tiếng.

THÔNG TIN SẢN PHẨM
{info}
{("TÀI LIỆU CỦA DOANH NGHIỆP (chỉ lấy sự thật từ đây, làm theo các quy định về lời nói nếu tài liệu có ghi):" + chr(10) + kb) if kb else "(Không có tài liệu kèm theo.)"}

YÊU CẦU
Giọng điệu của lời đọc: {tone[1]}.
Kiểu quảng cáo: {name} ({when}). Video dài khoảng {seconds} giây: toàn bộ lời đọc (1 hook + các phần + kêu gọi) khoảng {words} chữ, không quá {round(words * 1.12)} chữ.
Các phần theo thứ tự, mỗi phần chỉ làm một việc:
{chr(10).join(f"- {label}: lời nói {say}; hình: {show}." for label, say, show in parts)}
Viết 5 hook khác nhau cho 3 giây đầu, mỗi hook dưới 14 chữ, mỗi hook một cơ chế trong số: {"; ".join(f"{v[0]} ({v[1]})" for v in HOOKS.values())}.
Hook nào cũng phải nối liền mạch với phần đầu tiên.

QUY TẮC
1. Chỉ dùng thông tin có trong phần trên. Không bịa số liệu, lời khách hàng, giải thưởng, hạn chót hay giá.
2. Không hứa kết quả tuyệt đối (“100%”, “chắc chắn”, “trị dứt”, “tăng gấp đôi”). Nói về vấn đề, không phán xét người xem.
3. Với phân bón, thuốc, thực phẩm, sức khoẻ: không nói thay lời khuyên chuyên môn; nhắc dùng theo hướng dẫn trên nhãn khi nói liều dùng.
4. “chu” là dòng chữ hiện trên màn hình: dưới 8 chữ, là ý chính của phần đó, người tắt tiếng vẫn hiểu. Ưu đãi phải có trong “chu”.
5. “hinh” mô tả cảnh nên quay hoặc chọn cho phần đó, cụ thể, quay được bằng điện thoại.
6. Thiếu thông tin quan trọng (giá, hạn ưu đãi, bằng chứng) thì ghi câu hỏi vào “luu_y”, không tự điền.
7. Số viết sao cho đọc thành tiếng được (“ba chai”, “một trăm tám mươi lăm nghìn”) trong “loi”; trong “chu” viết số bình thường.

Trả về DUY NHẤT một JSON:
{{"hooks":[{{"kieu":"tên cơ chế","loi":"câu nói","chu":"chữ trên màn hình","hinh":"cảnh mở đầu"}}],
"phan":[{{"vai":"tên phần","hinh":"...","loi":"...","chu":"..."}}],
"cta":{{"loi":"lời kêu gọi cuối","chu":"chữ trên nút","hinh":"..."}},
"caption":"lời mô tả khi đăng, 2–4 câu","hashtags":["#..."],"luu_y":["điều cần người làm kiểm tra hoặc bổ sung"]}}'''

def write_script(job):
    from platform_tools import vlm_ask, ai_provider
    kind = job.get('adType') if job.get('adType') in AD_TYPES else 'van-de'; seconds = int(job.get('adLength') or 30)
    brief = {k: job.get(k, '') for k in BRIEF}
    if not nfc(brief['adProduct']).strip(): raise ValueError('Hãy nhập tên sản phẩm.')
    if not ai_provider(): raise RuntimeError('Chưa có AI để viết kịch bản. Cài Claude Code hoặc Codex rồi đăng nhập, hoặc bấm “Tự viết theo khung”.')
    emit(8, 'Đang đọc tài liệu về sản phẩm…')
    notes = knowledge(job.get('adKnowledgeFolder'), brief)
    emit(25, f'AI đang viết kịch bản{f" (dựa trên {len(notes)} tài liệu)" if notes else ""}, thường mất 1–4 phút…')
    text = vlm_ask(question(brief, kind, seconds, notes, job.get('adEnergy')), ())
    m = re.search(r'\{.*\}', text or '', re.S)
    try: got = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError: got = None
    if not got or not got.get('phan'): raise RuntimeError('AI chưa trả về kịch bản đọc được. Bấm viết lại.')
    script = clean(dict(got, kieu=kind, giay=seconds), kind, seconds); script['nguon'] = [n['file'] for n in notes]
    Path(job['scriptFile']).write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding='utf-8')
    emit(100, f'Đã viết kịch bản: {len(script["hooks"])} hook, {len(script["phan"])} phần.', done=True, adScript=job['scriptFile'])

# ---------- export ----------
def spoken(script, hook):
    """The parts of one version in order, each {role, loi, chu}."""
    h = script['hooks'][hook]
    return ([dict(role='hook', loi=h['loi'], chu=h['chu'])] + [dict(role='part', loi=p['loi'], chu=p['chu']) for p in script['phan'] if p['loi'].strip()]
            + ([dict(role='cta', loi=script['cta']['loi'], chu=script['cta']['chu'])] if script['cta']['loi'].strip() else []))

def title_lines(text):
    """The hook's on-screen line as the two title lines (big line first)."""
    words = nfc(text).split()
    if len(words) <= 4: return ' '.join(words).upper(), ''
    cut = (len(words) + 1) // 2
    return ' '.join(words[:cut]).upper(), ' '.join(words[cut:])

def media_duration(path):
    from platform_tools import FFPROBE, NOWIN
    p = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)], capture_output=True, **NOWIN)
    return float(p.stdout.decode().strip() or 0)

def voice_for(parts, job, cache):
    """One MP3 per part (kept per text + voice, so the shared body is made once for all hooks), joined into one file."""
    import tts
    from platform_tools import FFMPEG, NOWIN
    key = os.environ.get('MINIMAX_API_KEY', '').strip()
    if not key: raise ValueError('Chưa có API key MiniMax.')
    tjob = dict(voice=job['minimaxVoice'].strip(), model=job.get('minimaxModel') if job.get('minimaxModel') in tts.MODELS else tts.MODELS[0],
                speed=max(.5, min(2, float(job.get('minimaxSpeed', 1) or 1))), region=job.get('minimaxRegion'))
    name, _, emotion, faster, pitch = ENERGY.get(job.get('adEnergy'), ENERGY['thuong'])
    tjob.update(speed=round(min(2, tjob['speed'] * faster), 2), pitch=pitch, emotion=emotion)
    folder = cache / 'ad-voice'; folder.mkdir(parents=True, exist_ok=True); files = []
    for n, p in enumerate(parts):
        f = folder / (hashlib.sha1(json.dumps([p['loi'], tjob['voice'], tjob['model'], tjob['speed'], tjob['pitch'], tjob['emotion']], ensure_ascii=False).encode()).hexdigest()[:20] + '.mp3')
        if not (f.is_file() and f.stat().st_size > 800):
            for attempt in range(3):
                try: data = tts.synthesize(p['loi'], tjob, key); break
                except RuntimeError as e:
                    if 'giới hạn tốc độ' not in str(e) or attempt == 2: raise
                    time.sleep(20)
            f.write_bytes(data); time.sleep(.6)   # a short breath between requests: fewer dropped connections
        p['dur'] = round(media_duration(f), 3); files.append(f)
    out = folder / ('ghep-' + hashlib.sha1('|'.join(f.name for f in files).encode()).hexdigest()[:16] + '.m4a')
    args = [FFMPEG, '-v', 'error', '-y']
    for f in files: args += ['-i', str(f)]
    args += ['-filter_complex', ''.join(f'[{i}:a]' for i in range(len(files))) + f'concat=n={len(files)}:v=0:a=1[a]', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k', str(out)]
    r = subprocess.run(args, capture_output=True, **NOWIN)
    if r.returncode: raise RuntimeError('Ghép giọng đọc chưa được: ' + r.stderr.decode(errors='replace')[-300:])
    # Each part lasts exactly as long as its own file (the joined file is re-timed to these sums).
    return out

def safe(name): return re.sub(r'[\\/:*?"<>|\n\r]+', ' ', nfc(name)).strip()[:60] or 'Quang cao'

def export(job):
    import renderer as R
    script = clean(job.get('script')); cache = Path(job['cacheFolder']); cache.mkdir(parents=True, exist_ok=True)
    if not script['hooks'] or not any(h['loi'].strip() or h['chu'].strip() for h in script['hooks']): raise ValueError('Kịch bản chưa có hook.')
    if not any(p['loi'].strip() for p in script['phan']): raise ValueError('Kịch bản chưa có lời đọc cho các phần.')
    picks = [i for i in job.get('hooks') or [0] if 0 <= i < len(script['hooks']) and (script['hooks'][i]['loi'].strip() or script['hooks'][i]['chu'].strip())][:3] or [0]
    tts_voice = job.get('adVoiceSource') == 'minimax'
    if not tts_voice and not Path(job.get('adAudio') or '').is_file(): raise ValueError('Hãy chọn file ghi âm lời đọc, hoặc đổi sang giọng MiniMax.')
    if job.get('preview'): picks = picks[:1]
    output = Path(job['outputFolder'])
    if not output.is_dir(): raise ValueError('Hãy chọn thư mục lưu video.')
    stamp = time.strftime('%Y%m%d-%H%M'); folder = output if job.get('preview') else output / f'{safe(job.get("adProduct"))} - quảng cáo {stamp}'
    results = []; real_emit = R.emit
    try:
        for n, hook in enumerate(picks):
            base = 100 * n / len(picks); span = 100 / len(picks); label = f'Bản {"ABC"[n]}' if len(picks) > 1 else 'Video quảng cáo'
            parts = spoken(script, hook)
            if tts_voice:
                emit(base + span * .02, f'{label}: MiniMax đang đọc {len(parts)} đoạn…')
                audio = voice_for(parts, job, cache)
            else: audio = Path(job['adAudio'])
            t1, t2 = title_lines(script['hooks'][hook]['chu'] or script['hooks'][hook]['loi'])
            rjob = dict(job['render'], audio=str(audio), title=t1, subtitle=t2, preview=bool(job.get('preview')), outputFolder=str(output),
                        script=' '.join(p['loi'] for p in parts), ad=dict(segments=parts),
                        # A recording keeps its pauses cut as usual; synthesised parts keep their exact lengths.
                        removeSilence=not tts_voice and job['render'].get('removeSilence', True),
                        titleSeconds=max(2, min(5, parts[0].get('dur') or 3)) if parts[0]['role'] == 'hook' else 3)
            R.emit = lambda p, m, _b=base, _s=span, _l=label, **k: real_emit(_b + _s * (.08 + .92 * max(0, p) / 100), f'{_l} · {m}') if p >= 0 else real_emit(p, m, **k)
            dest = R.render(rjob); R.emit = real_emit
            if not job.get('preview'):
                folder.mkdir(parents=True, exist_ok=True)
                name = f'{safe(job.get("adProduct"))} - {"Hook " + "ABC"[n] if len(picks) > 1 else "quảng cáo"}'
                final = folder / (name + '.mp4'); shutil.move(str(dest), final)
                if dest.with_suffix('.srt').exists(): shutil.move(str(dest.with_suffix('.srt')), folder / (name + '.srt'))
                for extra in ('.json', '.nguon-anh.txt'):
                    if dest.with_suffix(extra).exists(): shutil.move(str(dest.with_suffix(extra)), folder / (name + extra))
                dest = final
            results.append(dict(path=str(dest), hook=script['hooks'][hook]['chu'] or script['hooks'][hook]['loi'], label=label))
    finally: R.emit = real_emit
    if not job.get('preview'):
        lines = [f'{safe(job.get("adProduct"))} · {AD_TYPES[script["kieu"]][0]} · khoảng {script["giay"]} giây', '']
        for r in results: lines.append(f'{r["label"]}: {r["hook"]}')
        lines += ['', 'KỊCH BẢN'] + [f'- {p["vai"]}: {p["loi"]}  [chữ: {p["chu"]}]' for p in script['phan']] + [f'- Kêu gọi: {script["cta"]["loi"]}  [chữ: {script["cta"]["chu"]}]', '',
                  'LỜI MÔ TẢ KHI ĐĂNG', script['caption'], ' '.join(script['hashtags'])]
        (folder / 'kich-ban-va-caption.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    emit(100, 'Đã xuất bản xem thử.' if job.get('preview') else f'Đã xuất {len(results)} video quảng cáo vào thư mục “{folder.name}”.',
         done=True, output=results[0]['path'], adResults=results)

if __name__ == '__main__':
    import signal
    from platform_tools import utf8_stdio
    utf8_stdio()
    def cancel(*_):
        try:
            import renderer as R
            for p in R.CHILDREN:
                try: p.terminate()
                except Exception: pass
        finally: raise SystemExit(130)
    signal.signal(signal.SIGTERM, cancel); signal.signal(signal.SIGINT, cancel)
    try:
        job = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
        write_script(job) if sys.argv[1] == 'script' else export(job)
    except Exception as e: emit(-1, str(e), error=True); sys.exit(1)
