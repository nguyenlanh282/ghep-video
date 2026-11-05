"""Video chia sẻ → HyperFrames project, to keep editing after the automatic edit.

  hyperframes_export.py <job.json>     job = the talk-render job + aspect, plus hfFolder (where to write)

The automatic edit is rendered once more without captions and title (the cuts, punch-ins, B-roll and colour stay in
the picture). Captions and the opening title become HTML clips, so text, timing and style can be changed in the
HyperFrames editor, which re-renders the final video. Progress is JSON lines like renderer.py.
"""
import html, json, re, shutil, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import renderer as R
import talk
from platform_tools import utf8_stdio

def emit(progress, message, **extra): R.emit(progress, message, **extra)

def caption_groups(words, max_words=4):
    """Short groups of words for one-at-a-time captions: break at a sentence end, a pause, or the word limit."""
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w['start'] - cur[-1]['end'] > .35 or cur[-1]['text'].endswith(('.', '?', '!', ','))):
            groups.append(cur); cur = []
        cur.append(w)
    if cur: groups.append(cur)
    return groups

def esc(t): return html.escape(str(t), quote=True)

def index_html(W, H, total, title, subtitle, title_secs, accent):
    tdur = min(total, max(1.0, title_secs))
    vars_ = [dict(id='accent', type='color', label='Màu nhấn (từ khoá, dòng 2 tiêu đề)', default=accent),
             dict(id='captionColor', type='color', label='Màu chữ phụ đề', default='#ffffff')]
    return f'''<!doctype html>
<html lang="vi" data-composition-variables='{esc(json.dumps(vars_, ensure_ascii=False))}'>
<head>
<meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
  html, body {{ margin: 0; background: #000; }}
  #main {{ position: relative; overflow: hidden; background: #000; }}
  #speaker {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; object-fit: cover; z-index: 1; }}
</style>
</head>
<body>
  <div id="main" data-composition-id="main" data-start="0" data-duration="{total:.3f}" data-width="{W}" data-height="{H}" data-fps="30">
    <video id="speaker" class="clip" src="assets/video.mp4" data-start="0" data-duration="{total:.3f}" data-track-index="0" data-has-audio="true" playsinline></video>
    <div id="title" data-composition-id="title" data-composition-src="compositions/title.html" data-start="0" data-duration="{tdur:.3f}"
         data-track-index="1" data-track-kind="graphics" data-width="{W}" data-height="{H}" style="z-index: 3"></div>
    <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0" data-duration="{total:.3f}"
         data-track-index="2" data-track-kind="captions" data-width="{W}" data-height="{H}" style="z-index: 2"></div>
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    window.__timelines["main"] = gsap.timeline({{ paused: true }});
  </script>
</body>
</html>
'''

def title_html(W, H, title, subtitle, dur):
    portrait = H > W; size = round(min(W, H) * (.085 if portrait else .075)); top = round(H * (.2 if portrait else .1))
    line2 = f'<div id="title-l2" data-layout-allow-overlap>{esc(subtitle)}</div>' if subtitle else ''
    return f'''<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    #title-box {{ position: absolute; left: 0; right: 0; top: {top}px; text-align: center; font-family: Montserrat, sans-serif; }}
    #title-l1 {{ font-size: {size}px; font-weight: 900; color: #fff; line-height: 1.1; padding: 0 6%;
      text-shadow: 0 0 10px rgba(0,0,0,.85), 0 4px 0 #151a22; }}
    #title-l2 {{ display: inline-block; margin-top: {round(size * .25)}px; font-size: {round(size * .62)}px; font-weight: 800; color: var(--accent, #ffd54a);
      text-shadow: 0 0 8px rgba(0,0,0,.85); }}
  </style>
  <div id="root" data-composition-id="title" data-width="{W}" data-height="{H}">
    <div id="title-box" class="clip" data-start="0" data-duration="{dur:.3f}">
      <div id="title-l1">{esc(title)}</div>
      {line2}
    </div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#title-l1", {{ opacity: 0, scale: 0.7 }}, {{ opacity: 1, scale: 1, duration: 0.45, ease: "back.out(2)" }}, 0.15);
    {"tl.fromTo('#title-l2', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power3.out' }, 0.35);" if subtitle else ''}
    tl.to("#title-box", {{ opacity: 0, duration: 0.25, ease: "power2.in" }}, {max(0.5, dur - 0.3):.3f});
    window.__timelines["title"] = tl;
  </script>
</template>
'''

def captions_html(W, H, groups, cap_y):
    portrait = H > W; size = round(min(W, H) * (.062 if portrait else .055)); bottom = round(H * (1 - cap_y))
    rows, tweens = [], []
    for g, words in enumerate(groups):
        a = max(.1, words[0]['start'] - .05); b = words[-1]['end'] + .12
        if g + 1 < len(groups): b = min(b, groups[g + 1][0]['start'] - .02)
        if b - a < .15: b = a + .15
        spans = ''.join(f'<span id="w{g}-{i}" class="w{" kw" if w.get("kw") else ""}">{esc(w["text"])}</span> ' for i, w in enumerate(words))
        rows.append(f'    <div id="cap-{g}" class="clip cap" data-start="{a:.3f}" data-duration="{b - a:.3f}"><div class="line">{spans.strip()}</div></div>')
        tweens.append(f'tl.fromTo("#cap-{g} .line", {{ opacity: 0, y: 14 }}, {{ opacity: 1, y: 0, duration: 0.12, ease: "power2.out" }}, {a:.3f});')
        for i, w in enumerate(words):   # the word being said lights up (karaoke)
            tweens.append(f'tl.fromTo("#w{g}-{i}", {{ opacity: 0.6 }}, {{ opacity: 1, duration: 0.08 }}, {max(a, w["start"]):.3f});')
    return f'''<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    .cap {{ position: absolute; left: 0; right: 0; bottom: {bottom}px; text-align: center; overflow: visible; }}
    .cap .line {{ display: inline-block; max-width: 84%; font-family: Montserrat, sans-serif; font-weight: 800; font-size: {size}px; line-height: 1.2;
      color: var(--captionColor, #fff); text-shadow: 0 0 6px rgba(0,0,0,.9), 0 3px 0 #171717; }}
    .cap .kw {{ color: var(--accent, #ffd54a); }}
  </style>
  <div id="root" data-composition-id="captions" data-width="{W}" data-height="{H}">
{chr(10).join(rows)}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    {(chr(10) + '    ').join(tweens)}
    window.__timelines["captions"] = tl;
  </script>
</template>
'''

def export(job):
    project = json.loads(Path(job['projectDir'], 'project.json').read_text(encoding='utf-8'))
    words = project['words']
    if job.get('highlightKeywords', True): talk.mark_keywords(words, project.get('keywords', []))
    aspect = job.get('aspect') if job.get('aspect') in talk.ASPECTS else '9:16'; W, H = talk.ASPECTS[aspect]
    stem = re.sub(r'[\\/:*?"<>|]+', ' ', project.get('name') or Path(project['source']).stem).strip()[:50]
    dest = Path(job['hfFolder']) / f'{stem} - HyperFrames {aspect.replace(":", "x")} {time.strftime("%Y%m%d-%H%M")}'
    (dest / 'assets').mkdir(parents=True, exist_ok=True); (dest / 'compositions').mkdir(exist_ok=True)
    emit(2, 'Đang dựng video sạch (chưa in chữ) cho HyperFrames…')
    clean = dict(job, subStyle='none', titleStyle='none')
    with tempfile.TemporaryDirectory(prefix='talk-hf-') as tmp:
        out = talk.render_variant(project, clean, aspect, 0, len(words) - 1, ('', ''), dest / 'assets' / 'video.mp4', Path(tmp),
                                  lambda f: emit(2 + 88 * f, f'Đang dựng video sạch · {int(f * 100)}%'))
    keep = talk.keep_ranges(words, project['duration'])
    out_words = []
    for w in words:
        if w.get('cut'): continue
        a, b = R.mapped_time(w['start'], keep), R.mapped_time(w['end'], keep)
        if b > a + .001: out_words.append(dict(text=w['text'], start=a, end=b, kw=w.get('kw', False)))
    total = float(out['duration'])
    groups = caption_groups(out_words)
    cap_y = talk.CAPTION_Y.get(aspect) or float(job.get('captionY', .73))
    title, subtitle = (job.get('title') or '').strip(), (job.get('subtitle') or '').strip()
    emit(93, 'Đang viết dự án HyperFrames…')
    (dest / 'index.html').write_text(index_html(W, H, total, title, subtitle, float(job.get('titleSeconds', 3)), '#ffd54a'), encoding='utf-8')
    if title or subtitle: (dest / 'compositions' / 'title.html').write_text(title_html(W, H, title or subtitle, subtitle if title else '', min(total, float(job.get('titleSeconds', 3)))), encoding='utf-8')
    else:  # no title: an empty scene keeps the structure valid
        (dest / 'compositions' / 'title.html').write_text(title_html(W, H, '', '', 1.0), encoding='utf-8')
    (dest / 'compositions' / 'captions.html').write_text(captions_html(W, H, groups, cap_y), encoding='utf-8')
    (dest / 'README.txt').write_text('Dự án HyperFrames tạo từ Ghép Video.\n\n'
        '- assets/video.mp4: video đã edit tự động (cắt, zoom, cảnh trám, màu), chưa in chữ.\n'
        '- compositions/captions.html: phụ đề, mỗi nhóm chữ là một khối sửa được chữ và thời gian.\n'
        '- compositions/title.html: tiêu đề mở đầu.\n\n'
        'Sửa trong trình chỉnh sửa HyperFrames rồi bấm Render, hoặc chạy: npx hyperframes render .\n', encoding='utf-8')
    emit(100, f'Đã tạo dự án HyperFrames “{dest.name}”.', done=True, hfProject=str(dest))
    return dest

if __name__ == '__main__':
    utf8_stdio()
    try: export(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
    except Exception as e: emit(-1, str(e), error=True); sys.exit(1)
