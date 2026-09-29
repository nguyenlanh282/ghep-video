"""Ghép Video intro, v2 (2.8.0): 1920x1080 (ORIENT=h) or 1080x1920 for TikTok (ORIENT=v). Real app screenshots and
real exports; narration subtitles on screen; audio is mixed afterwards (mix.py)."""
import json, math, os, re, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
FF = '/opt/homebrew/bin/ffmpeg'
V = os.environ.get('ORIENT', 'h') == 'v'
W, H, FPS = (1080, 1920, 30) if V else (1920, 1080, 30)
OUT = HERE / 'root' / 'output'
EXP = next(OUT.glob('1 - mo dau*hoàn thiện*/'))
RAW = HERE / 'root' / '1 - mo dau.mp4'
TALK916, TALK169 = next(EXP.glob('*9x16.mp4')), next(EXP.glob('*16x9.mp4'))
CLIP = next(EXP.glob('Clip 1*.mp4'))
STORY = next(OUT.glob('Video-*.mp4'))
SH = {p.stem: Image.open(p).convert('RGB') for p in (HERE / 'shots').glob('*.png')}
LOOKS = [(n, Image.open(HERE / 'looks' / f'{n}.jpg').convert('RGB')) for n in json.loads((HERE / 'looks' / 'order.json').read_text())]
ORIG = Image.open(HERE / 'looks' / 'goc.jpg').convert('RGB')
LINES = [l.strip() for l in open(HERE / 'lines.txt', encoding='utf-8') if l.strip()]
VOICE = json.loads(os.environ['VOICE']); DURS = json.loads(os.environ['DURS']); LEAD = .45
ICON = Image.open(sys.argv[1]).convert('RGBA')


BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
REG = '/System/Library/Fonts/Supplemental/Arial.ttf'
_fc = {}
def font(size, bold=True):
    k = (size, bold)
    if k not in _fc: _fc[k] = ImageFont.truetype(BOLD if bold else REG, size)
    return _fc[k]

BG = (11, 15, 20); PANEL = (20, 26, 35); TEXT = (238, 241, 245); MUTED = (156, 168, 186)
ACCENT = (186, 242, 94); YELLOW = (255, 213, 74); PINK = (233, 77, 121)

def clamp(x, a=0., b=1.): return max(a, min(b, x))
def ease(p): p = clamp(p); return 1 - (1 - p) ** 3
def back(p, c=1.7): p = clamp(p); return 1 + (c + 1) * (p - 1) ** 3 + c * (p - 1) ** 2

# ---------- background: dark with two slow glowing blobs ----------
def make_bg():
    small = Image.new('RGB', (192, 108), BG); d = ImageDraw.Draw(small)
    d.ellipse((-30, -40, 80, 60), fill=(40, 70, 30)); d.ellipse((120, 50, 230, 150), fill=(30, 45, 85))
    return small.filter(ImageFilter.GaussianBlur(22)).resize((W + 200, H + 120), Image.Resampling.BICUBIC)
BGIMG = make_bg()
def background(t):
    x = round(100 + 90 * math.sin(t / 7)); y = round(60 + 50 * math.cos(t / 9))
    return BGIMG.crop((x, y, x + W, y + H)).copy()

# ---------- drawing helpers ----------
def alpha_img(img, k):
    if k >= 1: return img
    img = img.copy(); a = img.getchannel('A').point(lambda v: int(v * k)); img.putalpha(a); return img

def text_layer(txt, size, fill=TEXT, bold=True, stroke=0):
    f = font(size, bold); l, t, r, b = f.getbbox(txt, stroke_width=stroke)
    im = Image.new('RGBA', (r - l + 4, b - t + 4)); ImageDraw.Draw(im).text((2 - l, 2 - t), txt, font=f, fill=fill, stroke_width=stroke, stroke_fill=(10, 12, 16))
    return im

def put_text(frame, txt, x, y, size, t0, t, fill=TEXT, bold=True, anchor='l'):
    """Fade + slide up in from t0."""
    p = ease((t - t0) / .45)
    if p <= 0: return
    im = alpha_img(text_layer(txt, size, fill, bold), p)
    if anchor == 'c': x -= im.width // 2
    frame.paste(im, (int(x), int(y + 28 * (1 - p))), im)

def rounded(img, r):
    m = Image.new('L', img.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, img.width - 1, img.height - 1), r, fill=255)
    out = img.convert('RGBA'); out.putalpha(m); return out

def shadowed(frame, img, x, y, r=18, blur=26, k=1.0):
    sh = Image.new('RGBA', (img.width + blur * 4, img.height + blur * 4), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((blur * 2, blur * 2, blur * 2 + img.width, blur * 2 + img.height), r, fill=(0, 0, 0, int(170 * k)))
    sh = sh.filter(ImageFilter.GaussianBlur(blur)); frame.paste(sh, (int(x - blur * 2), int(y - blur * 2 + 14)), sh)
    im = alpha_img(img, k) if k < 1 else img; frame.paste(im, (int(x), int(y)), im)

def pill(frame, txt, x, y, t0, t, fg=(11, 15, 20), bg=ACCENT, size=26):
    p = ease((t - t0) / .35)
    if p <= 0: return
    f = font(size); w = f.getlength(txt) + 36; h = size + 22
    im = Image.new('RGBA', (int(w), h)); d = ImageDraw.Draw(im); d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=bg)
    d.text((w / 2, h / 2), txt, font=f, fill=fg, anchor='mm'); im = alpha_img(im, p)
    frame.paste(im, (int(x), int(y + 16 * (1 - p))), im)

def bullets(frame, items, x, y, t0, t, gap=.55, size=34, width=None):
    for i, s in enumerate(items):
        ti = t0 + i * gap; p = ease((t - ti) / .45)
        if p <= 0: continue
        yy = y + i * (size + 34) + 24 * (1 - p)
        dot = Image.new('RGBA', (size, size)); ImageDraw.Draw(dot).ellipse((6, 6, size - 6, size - 6), fill=ACCENT + (int(255 * p),))
        frame.paste(dot, (int(x), int(yy + 4)), dot)
        im = alpha_img(text_layer(s, size, TEXT, False), p); frame.paste(im, (int(x + size + 18), int(yy)), im)

def shot_card(frame, shot, box, dst, t, t0, dur, zoom_to=None, r=22, k=1.):
    """Crop `box` of a screenshot (Ken Burns toward `zoom_to` over the scene) into dst=(x, y, w, h)."""
    x0, y0, x1, y1 = box
    if zoom_to:
        p = ease((t - t0) / dur) * .9; zx0, zy0, zx1, zy1 = zoom_to
        x0, y0, x1, y1 = [a + (b - a) * p for a, b in zip((x0, y0, x1, y1), (zx0, zy0, zx1, zy1))]
    x, y, w, h = dst
    # keep aspect of the destination
    cw = x1 - x0; ch = cw * h / w; cy = (y0 + y1) / 2
    crop = shot.crop((round(x0), round(cy - ch / 2), round(x1), round(cy + ch / 2))).resize((w, h), Image.Resampling.LANCZOS)
    shadowed(frame, rounded(crop, r), x, y, r, k=k)

class Clip:
    """Sequential frames of a video, scaled to fit (w, h); holds the last frame when it ends; loops if asked."""
    def __init__(self, path, w, h, start=0., loop=False):
        self.path, self.w, self.h, self.start, self.loop = path, w, h, start, loop; self.last = None; self._open()
    def _open(self):
        self.p = subprocess.Popen([FF, '-v', 'error', '-ss', str(self.start), '-i', str(self.path), '-vf', f'fps={FPS},scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h}',
                                   '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], stdout=subprocess.PIPE)
    def frame(self):
        data = self.p.stdout.read(self.w * self.h * 3)
        if len(data) == self.w * self.h * 3: self.last = Image.frombytes('RGB', (self.w, self.h), data)
        elif self.loop: self.p.kill(); self._open(); return self.frame()
        return self.last

PHONE_BEZEL = 14
def phone(frame, clip, x, y, w, h, k=1., label=None, t=0, t0=0):
    img = clip.frame()
    if img is None: return
    body = Image.new('RGB', (w + PHONE_BEZEL * 2, h + PHONE_BEZEL * 2), (29, 37, 49)); body.paste(img, (PHONE_BEZEL, PHONE_BEZEL))
    body = rounded(body, 38)
    inner = Image.new('L', body.size, 0); ImageDraw.Draw(inner).rounded_rectangle((PHONE_BEZEL, PHONE_BEZEL, PHONE_BEZEL + w - 1, PHONE_BEZEL + h - 1), 26, fill=255)
    shadowed(frame, alpha_img(body, k), x, y, 38, k=1)
    if label: pill(frame, label, x + (w + 2 * PHONE_BEZEL) / 2 - len(label) * 8.2, y - 64, t0, t, size=24)

def screen16(frame, clip, x, y, w, h, k=1.):
    img = clip.frame()
    if img is None: return
    body = Image.new('RGB', (w + 20, h + 20), (29, 37, 49)); body.paste(img, (10, 10)); shadowed(frame, alpha_img(rounded(body, 18), k), x, y, 18)

def heading(frame, kicker, title, t0, t, x=120, y=150, size=64, lines=None):
    pill(frame, kicker, x, y, t0, t, size=24)
    for i, line in enumerate(lines or [title]):
        put_text(frame, line, x, y + 80 + i * (size + 14), size, t0 + .15 + .12 * i, t)


def make_bg():
    small = Image.new('RGB', (108, 192) if V else (192, 108), BG); d = ImageDraw.Draw(small)
    d.ellipse((-30, -40, 80, 60), fill=(40, 70, 30)); d.ellipse((60 if V else 120, 120 if V else 50, 170 if V else 230, 230 if V else 150), fill=(30, 45, 85))
    return small.filter(ImageFilter.GaussianBlur(22)).resize((W + 200, H + 120), Image.Resampling.BICUBIC)
BGIMG = make_bg()

def card(frame, img, x, y, w=None, h=None, k=1., r=20):
    """A screenshot crop, scaled to width w (or height h), rounded with a shadow."""
    s = (w / img.width) if w else (h / img.height)
    im = img.resize((round(img.width * s), round(img.height * s)), Image.Resampling.LANCZOS)
    shadowed(frame, alpha_img(rounded(im, r), k), x, y, r)
    return im.size

def chunks(text, limit):
    out, cur = [], ''
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > limit: out.append(cur); cur = w
        else: cur = (cur + ' ' + w).strip()
    return out + ([cur] if cur else [])

def subtitle(f, k, t):
    parts = chunks(LINES[k], 30 if V else 52); total = sum(len(p) for p in parts); pos = t - LEAD
    if pos < 0 or pos > VOICE[k] + .25: return
    acc = 0
    for p in parts:
        acc += len(p) / total * VOICE[k]
        if pos <= acc or p is parts[-1]: break
    fo = font(54 if V else 40); w = fo.getlength(p) + 56; h = 96 if V else 72
    im = Image.new('RGBA', (int(w), h)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 20, fill=(11, 15, 20, 215)); d.text((w / 2, h / 2 + 2), p, font=fo, fill=(255, 255, 255), anchor='mm')
    f.paste(im, (int(W / 2 - w / 2), 1300 if V else 968), im)

def head(f, kicker, lines, t):
    if V:
        pill(f, kicker, 80, 170, 0, t, size=30)
        for i, l in enumerate(lines): put_text(f, l, 80, 262 + i * 100, 84, .15 + .12 * i, t)
    else:
        pill(f, kicker, 120, 180, 0, t, size=26)
        for i, l in enumerate(lines): put_text(f, l, 120, 266 + i * 82, 68, .15 + .12 * i, t)

def notes(f, items, t):
    if not V: bullets(f, items, 124, 470, .9, t, size=34)

def wave(f, x, y, w, h, t, k):
    """Animated voice waveform."""
    n = 36; bw = w / n
    layer = Image.new('RGBA', (int(w), int(h))); d = ImageDraw.Draw(layer)
    for i in range(n):
        a = (math.sin(t * 7 + i * .55) * .5 + .5) * (math.sin(t * 3.1 + i * 1.7) * .35 + .65) * (1 - abs(i - n / 2) / (n / 2)) ** .5
        bh = max(8, a * h); cx = i * bw + bw / 2
        d.rounded_rectangle((cx - bw * .3, h / 2 - bh / 2, cx + bw * .3, h / 2 + bh / 2), bw * .3, fill=ACCENT + (int(255 * k),))
    f.paste(layer, (int(x), int(y)), layer)

# ---------- scenes (f=frame, t=time in scene, d=duration, c=clips) ----------
def s_intro(f, t, d, c):
    cy = H * (.25 if V else .27)
    p = back(t / .6); s = max(1, round((190 if V else 150) * p)); ic = ICON.resize((s, s)); f.paste(ic, (W // 2 - s // 2, int(cy - s // 2)), ic)
    put_text(f, 'GHÉP VIDEO', W / 2, cy + 110, 64 if V else 58, .35, t, ACCENT, anchor='c')
    L = ['Từ video thô', 'đến video hoàn thiện'] if V else ['Từ video thô đến video hoàn thiện']
    for i, l in enumerate(L): put_text(f, l, W / 2, cy + 230 + i * 108, 92 if V else 84, .6 + .15 * i, t, anchor='c')
    put_text(f, 'chỉ với một cú bấm', W / 2, cy + (470 if V else 340), 92 if V else 84, 1.0, t, YELLOW, anchor='c')
    tags = ['Ghép nhiều video', 'Chỉnh màu', 'Giọng MiniMax', 'Phụ đề đúng chính tả']
    for i, tag in enumerate(tags):
        if V: pill(f, tag, 130 + (i % 2) * 430, cy + 600 + (i // 2) * 90, 1.4 + i * .12, t, TEXT, (40, 50, 66), 32)
        else: pill(f, tag, 330 + i * 330, cy + 480, 1.4 + i * .12, t, TEXT, (40, 50, 66), 28)

def s_multi(f, t, d, c):
    head(f, 'MỚI · GHÉP NHIỀU VIDEO', ['Quay nhiều đoạn,', 'app tự nối lại'], t)
    notes(f, ['Thêm nhiều video một lần', 'Đánh số 1, 2, 3… đổi thứ tự dễ dàng', 'Sắp xếp theo tên file', 'Bản chữ đánh dấu từng video'], t)
    k = ease((t - .3) / .5)
    if k <= 0: return
    if V: card(f, SH['talk-videos'], 80, 560, w=920, k=k)
    else: card(f, SH['talk-videos'], 880, 230, w=900, k=k)

def s_cut(f, t, d, c):
    head(f, 'EDIT VIDEO CHIA SẺ', ['Tự cắt gọn,', 'sửa bằng chữ'], t)
    notes(f, ['Cắt im lặng, “ờ, ừm”', 'Cắt câu nói vấp, câu nói lại', 'Sửa video bằng cách sửa chữ', 'Phụ đề đúng chính tả'], t)
    k = ease((t - .3) / .5)
    if k <= 0: return
    img = SH['talk-editor']; z = 1 + .08 * ease(t / d)
    if V: card(f, img, 80, 620, w=int(920 * z), k=k)
    else: card(f, img, 860, 260, w=int(940 * z), k=k)

def s_before_after(f, t, d, c):
    head(f, 'TRƯỚC  →  SAU', ['23 giây thô', 'còn 15 giây gọn'], t)
    if not V:
        put_text(f, 'Bỏ khoảng lặng và tiếng ậm ừ,', 120, 470, 34, .8, t, MUTED, False)
        put_text(f, 'thêm tiêu đề và phụ đề karaoke.', 120, 520, 34, 1.0, t, MUTED, False)
    k = ease((t - .2) / .5)
    if k <= 0: return
    if V:
        screen16(f, c['raw'], 50, 800, 500, 281, k); pill(f, 'Video thô', 60, 730, .4, t, TEXT, (50, 60, 78), 28)
        phone(f, c['after'], 620, 590, 370, 658, k); pill(f, 'Sau khi edit', 650, 520, .8, t, size=28)
    else:
        screen16(f, c['raw'], 760, 330, 560, 315, k); pill(f, 'Video thô', 760, 262, .4, t, TEXT, (50, 60, 78), 24)
        put_text(f, '→', 1345, 440, 80, .6, t, ACCENT)
        phone(f, c['after'], 1450, 110, 380, 676, k); pill(f, 'Sau khi edit', 1500, 42, .8, t, size=24)

def s_color(f, t, d, c):
    head(f, 'MỚI · CHỈNH MÀU', ['Màu đẹp', 'như dân chuyên'], t)
    notes(f, ['9 mẫu: Điện ảnh, Ấm áp, Phim cổ điển…', '13 thanh chỉnh ánh sáng, màu, hiệu ứng', 'Xem trước ngay trên hình của bạn', 'Lưu mẫu màu riêng để dùng lại'], t)
    k = ease((t - .3) / .5)
    if k <= 0: return
    step = max(1.1, (d - 1) / len(LOOKS)); i = min(len(LOOKS) - 1, int(max(0, t - .5) / step)); name, img = LOOKS[i]
    bw, bh = (920, 518) if V else (900, 506); x, y = (80, 560) if V else (880, 250)
    a = ORIG.resize((bw, bh)); b = img.resize((bw, bh)); split = int(bw * (.5 + .32 * math.sin(t * 1.6)))
    comp = a.copy(); comp.paste(b.crop((split, 0, bw, bh)), (split, 0)); ImageDraw.Draw(comp).line([(split, 0), (split, bh)], fill=(255, 255, 255), width=3)
    shadowed(f, alpha_img(rounded(comp, 20), k), x, y, 20)
    pill(f, 'Gốc', x + 16, y + 16, .5, t, TEXT, (0, 0, 0), 24); pill(f, name, x + bw - 40 - len(name) * 15, y + 16, .5, t, size=24)

def s_voice(f, t, d, c):
    head(f, 'MỚI · GIỌNG MINIMAX', ['Không cần thu âm:', 'dán kịch bản là xong'], t)
    notes(f, ['Đọc bằng giọng bạn đã clone', 'Kịch bản dài tự chia đoạn', 'Không tốn phí lần 2 cho cùng nội dung'], t)
    k = ease((t - .3) / .5)
    if k <= 0: return
    if V:
        card(f, SH['idx-minimax'], 90, 530, h=720, k=k); wave(f, 520, 800, 480, 200, t, k)
        put_text(f, 'Giọng của chính bạn', 760, 1030, 36, 1.0, t, ACCENT, anchor='c')
    else:
        card(f, SH['idx-minimax'], 880, 130, h=800, k=k); wave(f, 1330, 420, 460, 220, t, k)
        put_text(f, 'Giọng của chính bạn', 1560, 690, 38, 1.0, t, ACCENT, anchor='c')

SYM = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf', 40)  # ✓ ✗

def spell_box(f, x, y, w, t, k):
    """Before → after of the AI spelling check."""
    h = 236; box = Image.new('RGBA', (w, h)); d = ImageDraw.Draw(box)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 22, fill=PANEL + (255,), outline=(60, 72, 90), width=2)
    d.text((24, 22), 'Nhận dạng', font=font(24, False), fill=MUTED)
    d.text((24, 56), 'Bà con nên tỉ cành, bóng phân', font=font(32), fill=(255, 140, 140))
    p = ease((t - 1.3) / .6)
    if p > 0:
        d.text((24, 118), 'AI sửa thành', font=font(24, False), fill=ACCENT + (int(255 * p),))
        d.text((24, 152), 'Bà con nên tỉa cành, bón phân', font=font(32), fill=TEXT + (int(255 * p),))
    shadowed(f, alpha_img(box, k), x, y, 22)

def s_title(f, t, d, c):
    head(f, 'MỚI · PHỤ ĐỀ ĐÚNG CHÍNH TẢ', ['AI soát chính tả', 'trước khi tạo phụ đề'], t)
    notes(f, ['Sửa dấu, từ nghe nhầm', 'Đối chiếu kịch bản khi dùng MiniMax', 'Karaoke: chữ đứng yên, đổi màu', '4 kiểu tiêu đề · 6 hiệu ứng'], t)
    k = ease((t - .3) / .5)
    if k <= 0: return
    if V: card(f, SH['idx-sub'], 60, 520, w=560, k=k); spell_box(f, 60, 980, 560, t, k); phone(f, c['after'], 650, 540, 360, 640, k)
    else: card(f, SH['idx-sub'], 860, 130, w=480, k=k); spell_box(f, 860, 530, 520, t, k); phone(f, c['after'], 1420, 150, 380, 676, k)

def s_story(f, t, d, c):
    head(f, 'GHÉP ẢNH + LỜI ĐỌC', ['Thả ảnh và giọng,', 'AI hiểu từng cảnh'], t)
    notes(f, ['Khi xuất, AI tự xem ảnh chưa phân tích', 'Chọn cảnh khớp từng câu nói', 'Ảnh đã phân tích thì dùng luôn', 'Giọng to rõ chuẩn −14 LUFS'], t)
    k = ease((t - .3) / .5)
    if k <= 0: return
    if V: card(f, SH['idx-match'], 60, 560, w=520, k=k); phone(f, c['story'], 620, 540, 380, 676, k)
    else: card(f, SH['idx-match'], 860, 200, w=480, k=k); phone(f, c['story'], 1400, 150, 400, 711, k)

def s_context(f, t, d, c):
    head(f, 'MỚI · ẢNH TRÁM ĐÚNG BỐI CẢNH', ['Ảnh trên mạng', 'đúng bối cảnh'], t)
    notes(f, ['AI xác định bối cảnh của video', 'Từ khoá tìm giữ đúng chủ thể', 'Ảnh lạc đề bị loại', 'Thiếu key Pexels thì app nhắc'], t)
    k = ease((t - .3) / .5)
    if k <= 0: return
    x, y, w = (80, 520, 920) if V else (860, 170, 900)
    # 1. the setting the AI works out
    bw = w; box = Image.new('RGBA', (bw, 110)); dd = ImageDraw.Draw(box)
    dd.rounded_rectangle((0, 0, bw - 1, 109), 22, fill=(30, 44, 26, 255), outline=ACCENT + (255,), width=2)
    dd.text((26, 18), 'Bối cảnh AI nhận ra', font=font(24, False), fill=MUTED); dd.text((26, 52), 'Vườn sầu riêng ở Việt Nam', font=font(38), fill=ACCENT)
    shadowed(f, alpha_img(box, k), x, y, 22)
    # 2. search words
    qx = x
    for i, q in enumerate(['durian farmer pruning', 'durian orchard', 'durian tree']):
        pill(f, q, qx, y + 140, .9 + i * .2, t, TEXT, (40, 50, 66), 26); qx += font(26).getlength(q) + 60
    # 3. what is kept and what is dropped
    rows = [('✓', 'Vườn sầu riêng', 'đúng bối cảnh → dùng', ACCENT), ('✗', 'Quả mít', 'sai bối cảnh → loại', (255, 120, 120)), ('✗', 'Ảnh cũ đen trắng', 'không hợp → loại', (255, 120, 120))]
    for i, (m, a, b, col) in enumerate(rows):
        p = ease((t - 1.8 - i * .35) / .4)
        if p <= 0: continue
        r = Image.new('RGBA', (w, 84)); dd = ImageDraw.Draw(r)
        dd.rounded_rectangle((0, 0, w - 1, 83), 18, fill=PANEL + (255,), outline=(60, 72, 90), width=2)
        dd.text((28, 42), m, font=SYM, fill=col, anchor='lm'); dd.text((84, 42), a, font=font(32), fill=TEXT, anchor='lm')
        dd.text((w - 28, 42), b, font=font(26, False), fill=col, anchor='rm')
        shadowed(f, alpha_img(r, p), x, y + 230 + i * 100 + 20 * (1 - p), 18)


def s_export(f, t, d, c):
    head(f, 'XUẤT MỌI NỀN TẢNG', ['Một lần xuất,', 'đủ cho mọi kênh'], t)
    notes(f, ['9:16 TikTok · 1:1 Facebook · 16:9 YouTube', 'Clip ngắn AI gợi ý', 'Caption + hashtag sẵn để đăng', 'Cảnh trám từ kho hoặc Pexels/Pixabay'], t)
    k = ease((t - .3) / .5)
    if k <= 0: return
    if V:
        phone(f, c['after'], 50, 560, 330, 587, k); pill(f, '9:16 TikTok', 70, 490, .6, t, size=26)
        screen16(f, c['wide'], 420, 560, 580, 326, k); pill(f, '16:9 YouTube', 430, 490, .7, t, size=26)
        phone(f, c['short'], 560, 930, 170, 302, k); pill(f, 'Clip ngắn', 760, 1000, .8, t, size=26)
    else:
        phone(f, c['after'], 880, 260, 260, 462, k); pill(f, '9:16 TikTok', 900, 190, .6, t, size=22)
        screen16(f, c['wide'], 1190, 380, 400, 225, k); pill(f, '16:9 YouTube', 1190, 312, .7, t, size=22)
        phone(f, c['short'], 1640, 260, 200, 356, k); pill(f, 'Clip ngắn', 1650, 190, .8, t, size=22)

def s_trust(f, t, d, c):
    L = ['Chạy ngay', 'trên máy của bạn'] if V else ['Chạy ngay trên máy của bạn']
    for i, l in enumerate(L): put_text(f, l, W / 2, (220 if V else 190) + i * 100, 84 if V else 72, .1 * i, t, anchor='c')
    cards = [('1', 'Mac & Windows', 'Cài 1 file, bấm là chạy'), ('2', 'Dùng gói AI sẵn có', 'Claude hoặc ChatGPT của bạn'), ('3', 'Cập nhật 1 nút bấm', 'Có tính năng mới là lên ngay')]
    for i, (n, a, b) in enumerate(cards):
        p = back((t - .5 - i * .25) / .6)
        if p <= 0: continue
        cw, ch = (900, 200) if V else (480, 300)
        x, y = (90, 500 + i * 240) if V else (180 + i * 540, 400)
        y += 40 * (1 - clamp(p))
        cd = Image.new('RGBA', (cw, ch)); dd = ImageDraw.Draw(cd)
        dd.rounded_rectangle((0, 0, cw - 1, ch - 1), 30, fill=PANEL + (255,), outline=(60, 72, 90), width=2)
        if V:
            dd.rounded_rectangle((36, 50, 136, 150), 24, fill=(38, 52, 30)); dd.text((86, 100), n, font=font(52), fill=ACCENT, anchor='mm')
            dd.text((170, 52), a, font=font(46), fill=TEXT); dd.text((170, 120), b, font=font(32, False), fill=MUTED)
        else:
            dd.rounded_rectangle((36, 36, 116, 116), 20, fill=(38, 52, 30)); dd.text((76, 78), n, font=font(44), fill=ACCENT, anchor='mm')
            dd.text((36, 160), a, font=font(36), fill=TEXT); dd.text((36, 220), b, font=font(26, False), fill=MUTED)
        shadowed(f, alpha_img(cd, clamp(p)), x, y, 30)

def s_cta(f, t, d, c):
    cy = H * (.22 if V else .2)
    p = back(t / .6); s = max(1, round((160 if V else 120) * p)); ic = ICON.resize((s, s)); f.paste(ic, (W // 2 - s // 2, int(cy - s // 2)), ic)
    L = ['Nhận Ghép Video', 'miễn phí'] if V else ['Nhận Ghép Video miễn phí']
    for i, l in enumerate(L): put_text(f, l, W / 2, cy + 120 + i * 112, 100 if V else 92, .3 + .12 * i, t, anchor='c')
    Y = ['Vào nhóm Zalo để nhận phần mềm', 'và buổi Zoom hướng dẫn'] if V else ['Vào nhóm Zalo để nhận phần mềm và buổi Zoom hướng dẫn']
    for i, l in enumerate(Y): put_text(f, l, W / 2, cy + (380 if V else 250) + i * 66, 48 if V else 44, .7 + .1 * i, t, YELLOW, anchor='c')
    pe = ease((t - 1.1) / .5)
    if pe > 0:
        fo = font(40 if V else 44); txt = 'ghep-video.it-nguyenlanh.workers.dev'; w = fo.getlength(txt) + 80; h = 96 if V else 100
        b = Image.new('RGBA', (int(w), h)); dd = ImageDraw.Draw(b); dd.rounded_rectangle((0, 0, w - 1, h - 1), 26, fill=ACCENT); dd.text((w / 2, h / 2), txt, font=fo, fill=BG, anchor='mm')
        shadowed(f, alpha_img(b, pe), W / 2 - w / 2, cy + (560 if V else 400), 26)

SCENES = [(s_intro, None), (s_multi, None), (s_cut, None), (s_before_after, 'ba'), (s_color, None), (s_voice, None), (s_title, 'title'), (s_story, 'story'), (s_context, None), (s_export, 'export'), (s_trust, None), (s_cta, None)]

def main():
    out = sys.argv[2]
    enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', 'pipe:0',
                            '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
    tg = 0; FADE = .35
    for k, ((fn, kind), d) in enumerate(zip(SCENES, DURS)):
        C = Clip; c = {}
        if kind == 'ba': c = dict(raw=C(RAW, 500, 281, 0, True) if V else C(RAW, 540, 304, 0, True), after=C(TALK916, 370, 658, 0, True) if V else C(TALK916, 380, 676, 0, True))
        if kind == 'title': c = dict(after=C(TALK916, 380, 676, 0, True) if V else C(TALK916, 420, 747, 0, True))
        if kind == 'story': c = dict(story=C(STORY, 380, 676, 0, True) if V else C(STORY, 400, 711, 0, True))
        if kind == 'export': c = dict(after=C(TALK916, 330, 587, 4, True) if V else C(TALK916, 260, 462, 4, True), wide=C(TALK169, 580, 326, 2, True) if V else C(TALK169, 400, 225, 2, True),
                                      short=C(CLIP, 170, 302, 0, True) if V else C(CLIP, 200, 356, 0, True))
        for i in range(round(d * FPS)):
            t = i / FPS; frame = background(tg + t); fn(frame, t, d, c); subtitle(frame, k, t)
            a = min(1, t / FADE, (d - t) / FADE)
            if a < 1: frame = Image.blend(Image.new('RGB', (W, H), BG), frame, clamp(a))
            enc.stdin.write(frame.tobytes())
        for x in c.values(): x.p.kill()
        tg += d; print(fn.__name__, flush=True)
    enc.stdin.close(); enc.wait()

if __name__ == '__main__': main()
