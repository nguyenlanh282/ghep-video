'use strict';
// Timeline for both modes: every shot is a block (width = its time) with a thumbnail; click a block to change its
// picture, its length, the part of the source video it plays and its framing (drag the crop box, zoom).
//   TL.story(root, {api, player, isResult})  – Ghép ảnh + lời đọc: shots back to back along the narration
//   TL.talk(root, ctx)                       – Video chia sẻ: the speaker's videos + a B-roll track over them
window.TL = (() => {
  const TOKEN = new URLSearchParams(location.search).get('t') || '';
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const sec = t => (Math.round(t * 10) / 10).toFixed(1).replace('.', ',') + 's';
  const thumb = (path, at = 0) => `/t/${TOKEN}/?p=${encodeURIComponent(path)}&at=${(+at).toFixed(2)}`;
  const isVideo = p => /\.(mp4|mov|m4v|mkv|webm)$/i.test(p);

  /* ---------- crop box editor: frame = {zoom, cx, cy} on the whole picture; null = automatic ---------- */
  function frameEditor(host, {src, aspect, frame, auto, onChange}) {
    host.innerHTML = `<div class="fe-stage"><img alt="Ảnh nguồn của cảnh" draggable="false"><div class="fe-rect" title="Kéo để chọn vùng hiện trong video"></div></div>
      <div class="fe-row"><label>Phóng to</label><input type="range" min="1" max="4" step="0.05" aria-label="Phóng to"><output></output></div>
      <div class="fe-row"><button class="btn small" data-fe="auto">↺ Khung tự động</button><span class="hint fe-state"></span></div>`;
    const img = host.querySelector('img'), rect = host.querySelector('.fe-rect'), zoom = host.querySelector('input'), out = host.querySelector('output'), state = host.querySelector('.fe-state');
    let f = frame ? {...frame} : null, nw = 0, nh = 0;
    const size = z => { const w = Math.min(1, nh * aspect / nw) / z; return [w, w * nw / aspect / nh]; };  // fractions of the picture
    const fromAuto = () => {
      if (auto && auto.length === 4) { const w = auto[2] - auto[0]; return {zoom: clamp(size(1)[0] / w, 1, 4), cx: (auto[0] + auto[2]) / 2, cy: (auto[1] + auto[3]) / 2}; }
      return {zoom: 1, cx: .5, cy: .5};
    };
    function paint() {
      if (!nw) return;
      const cur = f || fromAuto(), [w, h] = size(cur.zoom);
      const cx = clamp(cur.cx, w / 2, 1 - w / 2), cy = clamp(cur.cy, h / 2, 1 - h / 2);
      Object.assign(rect.style, {left: (cx - w / 2) * 100 + '%', top: (cy - h / 2) * 100 + '%', width: w * 100 + '%', height: h * 100 + '%'});
      zoom.value = cur.zoom; out.textContent = Math.round(cur.zoom * 100) + '%';
      state.textContent = f ? 'Khung do bạn chọn' : 'Đang dùng khung tự động (giữ mặt người)';
      rect.classList.toggle('manual', !!f);
    }
    const commit = () => { paint(); onChange(f ? {zoom: +(+f.zoom).toFixed(3), cx: +f.cx.toFixed(4), cy: +f.cy.toFixed(4)} : null); };
    img.addEventListener('load', () => { nw = img.naturalWidth; nh = img.naturalHeight; paint(); });
    img.src = src;
    zoom.addEventListener('input', () => { f = {...(f || fromAuto()), zoom: +zoom.value}; commit(); });
    host.querySelector('[data-fe=auto]').addEventListener('click', () => { f = null; commit(); });
    rect.addEventListener('pointerdown', e => {
      e.preventDefault(); rect.setPointerCapture(e.pointerId);
      const box = img.getBoundingClientRect(), start = f || fromAuto(), x0 = e.clientX, y0 = e.clientY;
      const move = ev => {
        const [w, h] = size(start.zoom);
        f = {zoom: start.zoom, cx: clamp(start.cx + (ev.clientX - x0) / box.width, w / 2, 1 - w / 2), cy: clamp(start.cy + (ev.clientY - y0) / box.height, h / 2, 1 - h / 2)}; paint();
      };
      const up = () => { rect.removeEventListener('pointermove', move); rect.removeEventListener('pointerup', up); commit(); };
      rect.addEventListener('pointermove', move); rect.addEventListener('pointerup', up);
    });
    return {setSrc(s) { img.src = s; }, setAspect(a) { aspect = a; paint(); }};
  }

  /* ---------- pick another photo / video ---------- */
  function picker(host, files, onPick) {
    host.hidden = false;
    host.innerHTML = `<div class="row between"><b>Chọn ảnh hoặc video cho cảnh này</b><button class="btn small" data-close>Đóng</button></div>
      <div class="tl-files">${files.map((f, i) => `<button class="tl-file" data-i="${i}" title="${esc(f.note || f.name)}"><img loading="lazy" src="${f.thumb}" alt=""><span>${f.kind === 'video' ? '▶ ' + sec(f.d) + ' · ' : ''}${esc(f.name)}</span></button>`).join('') || '<p class="hint">Thư mục chưa có ảnh/video.</p>'}</div>`;
    host.onclick = e => {
      if (e.target.closest('[data-close]')) { host.hidden = true; return; }
      const b = e.target.closest('.tl-file'); if (b) { host.hidden = true; onPick(files[+b.dataset.i]); }
    };
  }

  /* ---------- shared strip: ruler, zoom, playhead ---------- */
  function strip(root, {title, tools, tracks}) {
    root.innerHTML = `<div class="row between tl-head"><h2><span class="num">🎞</span>${title}</h2><div class="row gap tl-tools">${tools}
        <span class="tl-zoom"><button class="btn small" data-z="-1" aria-label="Thu nhỏ timeline">−</button><button class="btn small" data-z="1" aria-label="Phóng to timeline">+</button></span></div></div>
      <p class="hint tl-hint"></p>
      <div class="tl-scroll" hidden><div class="tl-inner"><div class="tl-ruler"></div>${tracks.map(t => `<div class="tl-track ${t}"></div>`).join('')}<div class="tl-playhead"></div></div></div>
      <div class="tl-inspector" hidden></div><div class="tl-picker" hidden></div>`;
    const st = {pps: 70, dur: 0, scroll: root.querySelector('.tl-scroll'), inner: root.querySelector('.tl-inner'), ruler: root.querySelector('.tl-ruler'),
      head: root.querySelector('.tl-playhead'), hint: root.querySelector('.tl-hint'), insp: root.querySelector('.tl-inspector'), pick: root.querySelector('.tl-picker')};
    st.layout = dur => {
      st.dur = dur; st.inner.style.width = Math.max(st.scroll.clientWidth - 4, dur * st.pps) + 'px';
      const step = st.pps >= 90 ? 1 : st.pps >= 40 ? 2 : 5; let marks = '';
      for (let t = 0; t <= dur; t += step) marks += `<span style="left:${t * st.pps}px">${t}s</span>`;
      st.ruler.innerHTML = marks;
    };
    st.fit = dur => { if (!st.scroll.clientWidth) return; st.pps = clamp((st.scroll.clientWidth - 8) / Math.max(1, dur), 25, 160); };
    new ResizeObserver(() => { if (st.scroll.clientWidth && st.onResize) st.onResize(); }).observe(st.scroll);  // first shown, window resized
    st.setHead = t => { st.head.style.left = clamp(t, 0, st.dur) * st.pps + 'px'; };
    return st;
  }
  const stripShot = sh => { const {thumb: _t, name: _n, missing: _m, ...rest} = sh; return rest; };

  /* ================= Ghép ảnh + lời đọc ================= */
  function story(root, {api, player, isResult, poll, aspect = () => 9 / 16}) {
    const plan = async () => { const out = await api('start', {task: 'plan'}); if (out.job && out.job.running && poll) poll(); };
    const st = strip(root, {title: 'Timeline', tracks: ['main'], tools: `<button class="btn small primary" data-act="plan">✨ Lên timeline</button><button class="btn small" data-act="reset" hidden>↺ Tạo lại tự động</button>`});
    const track = root.querySelector('.tl-track.main');
    let shots = [], files = [], dur = 0, sel = -1, fe = null;
    const save = debounce(async () => { const out = await api('timelineEdit', {shots: shots.map(stripShot)}); if (out.shots) { shots = out.shots; draw(false); } }, 450);

    function draw(rebuildInspector = true) {
      const has = shots.length > 0;
      st.scroll.hidden = !has; root.querySelector('[data-act=reset]').hidden = !has;
      root.querySelector('[data-act=plan]').textContent = has ? '✨ Lên lại timeline' : '✨ Lên timeline';
      root.querySelector('[data-act=plan]').hidden = has;
      st.hint.textContent = has ? `${shots.length} cảnh · ${sec(dur)}. Bấm một cảnh để đổi ảnh/video, độ dài, đoạn nguồn và khung hình; kéo mép phải của cảnh để kéo dài hay rút ngắn. Sửa xong bấm “Dựng thử” hoặc “Xuất”.`
        : 'Chưa có timeline. Bấm “✨ Lên timeline” để app chọn cảnh cho từng câu, rồi bạn chỉnh từng cảnh theo ý trước khi xuất.';
      if (!has) { st.insp.hidden = true; return; }
      if (!st.zoomed) st.fit(dur);
      st.layout(dur);
      track.innerHTML = shots.map((sh, i) => `<div class="tl-block ${i === sel ? 'on' : ''} ${sh.missing ? 'missing' : ''} ${sh.edited ? 'edited' : ''}" data-i="${i}" style="left:${sh.start * st.pps}px;width:${(sh.end - sh.start) * st.pps}px" title="${esc((sh.text || '') + ' · ' + sh.name)}">
          <img src="${sh.thumb}" alt="" draggable="false"><b>${i + 1}</b><span>${sh.d ? '▶ ' : ''}${esc(sh.name)}</span>${i < shots.length - 1 ? '<i class="tl-handle" title="Kéo để kéo dài / rút ngắn"></i>' : ''}</div>`).join('');
      if (rebuildInspector) inspect();
    }

    function patch(i, changes, redraw = true) { Object.assign(shots[i], changes, {edited: true}); delete shots[i].auto; if (changes.auto !== undefined) shots[i].auto = changes.auto; save(); if (redraw) draw(false); }

    function inspect() {
      const sh = shots[sel];
      if (!sh) { st.insp.hidden = true; return; }
      st.insp.hidden = false; const len = sh.end - sh.start;
      st.insp.innerHTML = `<div class="tl-col"><div class="fe"></div></div>
        <div class="tl-col"><h3>Cảnh ${sel + 1} <small>${sec(sh.start)} → ${sec(sh.end)} · dài ${sec(len)}</small></h3>
          ${sh.text ? `<p class="tl-phrase">“${esc(sh.text)}”</p>` : ''}<p class="hint">${esc(sh.name)}${sh.scene ? ' · ' + esc(sh.scene) : ''}${sh.missing ? ' · <b>không tìm thấy file, hãy đổi ảnh/video</b>' : ''}</p>
          <div class="row gap wrap"><button class="btn small primary" data-do="pick">🖼 Đổi ảnh / video</button>
            <button class="btn small" data-do="shorter" ${len <= .9 || sel === shots.length - 1 ? 'disabled' : ''}>− 0,5s</button><button class="btn small" data-do="longer" ${sel === shots.length - 1 || shots[sel + 1].end - shots[sel + 1].start <= .9 ? 'disabled' : ''}>+ 0,5s</button></div>
          ${sh.d ? `<div class="fe-row"><label>Bắt đầu từ giây</label><input type="range" data-src min="0" max="${Math.max(0, sh.d - len - .12).toFixed(2)}" step="0.1" value="${sh.srcStart}" aria-label="Đoạn nguồn bắt đầu từ giây"><output>${sec(sh.srcStart)}</output></div><p class="hint">Video dài ${sec(sh.d)}. Cảnh phát ${sec(len)} kể từ giây đã chọn.</p>` : ''}
          <div class="row gap wrap"><button class="btn small" data-do="split" ${len < 1.6 ? 'disabled' : ''}>✂ Tách đôi cảnh</button><button class="btn small" data-do="merge" ${sel === 0 ? 'disabled' : ''}>⟵ Gộp vào cảnh trước</button>
            <button class="btn small" data-do="left" ${sel === 0 ? 'disabled' : ''}>◀ Đổi chỗ</button><button class="btn small" data-do="right" ${sel === shots.length - 1 ? 'disabled' : ''}>Đổi chỗ ▶</button></div></div>`;
      fe = frameEditor(st.insp.querySelector('.fe'), {src: thumb(sh.file, sh.d ? sh.srcStart + .2 : 0), aspect: aspect(), frame: sh.frame, auto: sh.auto,
        onChange: f => patch(sel, {frame: f, auto: f ? undefined : sh.auto}, true)});
      const src = st.insp.querySelector('[data-src]');
      if (src) {
        const refresh = debounce(() => fe.setSrc(thumb(sh.file, +src.value + .2)), 250);
        src.addEventListener('input', () => { src.nextElementSibling.textContent = sec(+src.value); shots[sel].srcStart = +src.value; shots[sel].edited = true; refresh(); save(); });
        src.addEventListener('change', () => draw(false));
      }
    }

    const swapMedia = (a, b) => { for (const k of ['file', 'd', 'srcStart', 'frame', 'auto', 'scene', 'name', 'thumb', 'missing']) { const t = shots[a][k]; shots[a][k] = shots[b][k]; shots[b][k] = t; } shots[a].edited = shots[b].edited = true; };
    st.insp.addEventListener('click', e => {
      const b = e.target.closest('[data-do]'); if (!b || b.disabled) return; const sh = shots[sel], act = b.dataset.do;
      if (act === 'pick') return picker(st.pick, files, f => { patch(sel, {file: f.path, name: f.name, d: f.d, srcStart: 0, frame: null, auto: undefined, scene: f.note || '', thumb: f.thumb, missing: false, matched: false}); inspect(); });
      if (act === 'shorter' || act === 'longer') { const t = clamp(sh.end + (act === 'longer' ? .5 : -.5), sh.start + .4, shots[sel + 1].end - .4); sh.end = shots[sel + 1].start = t; sh.edited = true; }
      if (act === 'split') { const mid = (sh.start + sh.end) / 2; shots.splice(sel + 1, 0, {...sh, start: mid, srcStart: sh.d ? Math.min(sh.srcStart + (mid - sh.start), Math.max(0, sh.d - (sh.end - mid) - .12)) : 0, edited: true}); sh.end = mid; sh.edited = true; }
      if (act === 'merge') { shots[sel - 1].end = sh.end; shots[sel - 1].edited = true; shots.splice(sel, 1); sel -= 1; }
      if (act === 'left') { swapMedia(sel, sel - 1); sel -= 1; }
      if (act === 'right') { swapMedia(sel, sel + 1); sel += 1; }
      save(); draw();
    });

    track.addEventListener('pointerdown', e => {
      const h = e.target.closest('.tl-handle'), blk = e.target.closest('.tl-block'); if (!blk) return;
      const i = +blk.dataset.i;
      if (!h) { sel = i; draw(); if (isResult()) player.currentTime = shots[i].start + .05; return; }
      e.preventDefault(); h.setPointerCapture(e.pointerId);
      const x0 = e.clientX, end0 = shots[i].end, next = track.querySelector(`.tl-block[data-i="${i + 1}"]`);
      const move = ev => {
        const t = clamp(end0 + (ev.clientX - x0) / st.pps, shots[i].start + .4, shots[i + 1].end - .4);
        shots[i].end = shots[i + 1].start = t; blk.style.width = (t - shots[i].start) * st.pps + 'px';
        next.style.left = t * st.pps + 'px'; next.style.width = (shots[i + 1].end - t) * st.pps + 'px';
      };
      const up = () => { h.removeEventListener('pointermove', move); h.removeEventListener('pointerup', up); shots[i].edited = shots[i + 1].edited = true; save(); draw(); };
      h.addEventListener('pointermove', move); h.addEventListener('pointerup', up);
    });
    root.querySelector('.tl-tools').addEventListener('click', async e => {
      const z = e.target.closest('[data-z]'), a = e.target.closest('[data-act]');
      if (z) { st.zoomed = true; st.pps = clamp(st.pps * (z.dataset.z > 0 ? 1.4 : 1 / 1.4), 20, 260); draw(false); }
      if (a && a.dataset.act === 'reset') { if (!confirm('Tạo lại timeline tự động? Các chỉnh sửa cảnh của dự án này sẽ mất.')) return; await api('timelineReset'); sel = -1; plan(); }
      if (a && a.dataset.act === 'plan') plan();
    });
    st.onResize = () => { if (!shots.length) return; if (!st.zoomed) st.fit(dur); draw(false); };
    setInterval(() => { if (shots.length && isResult()) st.setHead(player.currentTime || 0); }, 200);

    return {
      async refresh() {
        const out = await api('timelineState');
        shots = out.shots || []; files = out.files || []; dur = out.duration || 0;
        if (sel >= shots.length) sel = -1;
        root.hidden = !out.hasAudio;
        draw();
      },
    };
  }

  /* ================= Video chia sẻ ================= */
  // ctx: {api, player, project(), keep(), settings(), view(), save(patch), brollFiles()}
  function talk(root, ctx) {
    const st = strip(root, {title: 'Timeline', tracks: ['broll', 'main'], tools: `<span class="seg tl-aspect"></span><button class="btn small primary" data-act="add">＋ Cảnh trám tại vạch phát</button>`});
    const main = root.querySelector('.tl-track.main'), bt = root.querySelector('.tl-track.broll');
    let sel = null, files = null, aspect = '9:16', cursor = 0;
    const RATIO = {'9:16': 9 / 16, '1:1': 1, '16:9': 16 / 9};
    const P = () => ctx.project();
    const outOf = t => ctx.keep().reduce((s, [a, b]) => s + clamp(t, a, b) - a, 0);
    const srcOf = o => { for (const [a, b] of ctx.keep()) { if (o <= b - a) return a + o; o -= b - a; } const k = ctx.keep(); return k.length ? k[k.length - 1][1] : 0; };
    const total = () => ctx.keep().reduce((s, [a, b]) => s + b - a, 0);
    const brStart = br => clamp(outOf(P().words[br.first].start) + (br.lead ?? .15), 0, Math.max(0, total() - .3));
    const clips = () => (P().clips && P().clips.length ? P().clips.map((c, i) => ({...c, path: (P().videos || [])[i] || P().source})) : [{name: (P().source || '').split(/[\\/]/).pop(), start: 0, end: P().duration, path: (P().videos || [])[0] || P().source}]);
    const saveBroll = debounce(() => ctx.save({brollList: P().broll}), 400);
    const nearestWord = o => { let best = -1, bd = 1e9; P().words.forEach((w, i) => { if (w.cut) return; const d = Math.abs(outOf(w.start) - o); if (d < bd) { bd = d; best = i; } }); return best; };

    function draw(rebuild = true) {
      const p = P(); root.hidden = !p; if (!p) return;
      const dur = total(); st.scroll.hidden = false;
      if (!st.zoomed) st.fit(dur);
      st.layout(dur);
      const aspects = (ctx.settings().talkAspects || '9:16').split(',').filter(a => RATIO[a]); if (!aspects.includes(aspect)) aspect = aspects[0] || '9:16';
      root.querySelector('.tl-aspect').innerHTML = aspects.length > 1 ? aspects.map(a => `<button data-aspect="${a}" class="${a === aspect ? 'on' : ''}">${a}</button>`).join('') : '';
      st.hint.textContent = `Video sau khi cắt dài ${sec(dur)}. Hàng trên: cảnh trám (kéo để dời, kéo mép phải để đổi độ dài). Hàng dưới: video người nói. Bấm một ô để chỉnh khung hình, đoạn nguồn, đổi ảnh/video.`;
      main.innerHTML = clips().map((c, i) => { const a = outOf(c.start), b = outOf(c.end); if (b - a < .05) return '';
        return `<div class="tl-block ${sel && sel.kind === 'clip' && sel.i === i ? 'on' : ''} ${(p.frames || {})[i] ? 'edited' : ''}" data-clip="${i}" style="left:${a * st.pps}px;width:${(b - a) * st.pps}px" title="${esc(c.name)}">
          <img src="${thumb(c.path, c.start + Math.min(2, (c.end - c.start) / 2) - (p.clips && p.clips.length ? c.start : 0))}" alt="" draggable="false"><b>${i + 1}</b><span>${esc(c.name)}</span></div>`; }).join('');
      bt.innerHTML = (p.broll || []).map((br, i) => { const a = brStart(br);
        return `<div class="tl-block br ${sel && sel.kind === 'br' && sel.i === i ? 'on' : ''} ${br.on === false ? 'off' : ''}" data-br="${i}" style="left:${a * st.pps}px;width:${br.dur * st.pps}px" title="${esc(br.source + (br.text ? ': ' + br.text : ''))}">
          <img src="${thumb(br.path, br.d ? br.a + .2 : 0)}" alt="" draggable="false"><span>${br.d ? '▶ ' : ''}${esc((br.source || '').split(/[\\/]/).pop())}</span><i class="tl-handle" title="Kéo để đổi độ dài"></i></div>`; }).join('')
        || '<p class="hint tl-empty">Chưa có cảnh trám. Bấm “＋ Cảnh trám tại vạch phát” để thêm.</p>';
      if (rebuild) inspect();
    }

    function inspect() {
      const p = P();
      if (!sel || (sel.kind === 'br' && !(p.broll || [])[sel.i])) { st.insp.hidden = true; return; }
      st.insp.hidden = false;
      if (sel.kind === 'clip') {
        const c = clips()[sel.i], frames = p.frames || {};
        st.insp.innerHTML = `<div class="tl-col"><div class="fe"></div></div><div class="tl-col"><h3>Video ${sel.i + 1} <small>${esc(c.name)}</small></h3>
          <p class="hint">Khung hình người nói cho video này, dùng cho mọi tỉ lệ xuất. Kéo khung để chọn vùng hiện, kéo thanh để phóng to. “Khung tự động” đặt mặt người nói vào giữa.</p>
          <p class="hint">Ô vuông đang xem theo tỉ lệ <b>${aspect}</b>${root.querySelector('.tl-aspect').children.length ? ' (đổi ở góc trên bên phải timeline)' : ''}.</p></div>`;
        frameEditor(st.insp.querySelector('.fe'), {src: thumb(c.path, (p.clips && p.clips.length ? 0 : c.start) + Math.min(2, (c.end - c.start) / 2)), aspect: RATIO[aspect], frame: frames[sel.i] || null, auto: null,
          onChange: f => { p.frames = {...(p.frames || {}), [sel.i]: f}; if (!f) delete p.frames[sel.i]; ctx.save({frames: {[sel.i]: f}}); draw(false); }});
        return;
      }
      const br = p.broll[sel.i];
      st.insp.innerHTML = `<div class="tl-col"><div class="fe"></div></div><div class="tl-col"><h3>Cảnh trám ${sel.i + 1} <small>${sec(brStart(br))} · dài ${sec(br.dur)}</small></h3>
        <p class="hint">${esc(br.source || '')}${br.text ? ' · ' + esc(br.text) : ''}</p>
        <div class="row gap wrap"><button class="btn small primary" data-do="pick">🖼 Đổi ảnh / video</button><button class="btn small" data-do="shorter" ${br.dur <= 1 ? 'disabled' : ''}>− 0,5s</button><button class="btn small" data-do="longer">+ 0,5s</button></div>
        ${br.d ? `<div class="fe-row"><label>Bắt đầu từ giây</label><input type="range" data-src min="0" max="${Math.max(0, br.d - br.dur - .1).toFixed(2)}" step="0.1" value="${br.a || 0}" aria-label="Đoạn nguồn bắt đầu từ giây"><output>${sec(br.a || 0)}</output></div>` : ''}
        <div class="row gap wrap"><button class="btn small" data-do="toggle">${br.on === false ? 'Bật cảnh trám này' : 'Tạm tắt'}</button><button class="btn small" data-do="del">🗑 Xoá cảnh trám</button></div></div>`;
      const fe = frameEditor(st.insp.querySelector('.fe'), {src: thumb(br.path, br.d ? (br.a || 0) + .2 : 0), aspect: RATIO[aspect], frame: br.frame || null, auto: null, onChange: f => { br.frame = f; saveBroll(); }});
      const src = st.insp.querySelector('[data-src]');
      if (src) { const refresh = debounce(() => fe.setSrc(thumb(br.path, +src.value + .2)), 250); src.addEventListener('input', () => { src.nextElementSibling.textContent = sec(+src.value); br.a = +src.value; refresh(); saveBroll(); }); }
    }

    async function pickFile(done) { if (!files) files = (await ctx.api('mediaList', {which: 'broll'})).files || []; picker(st.pick, files, done); }
    st.insp.addEventListener('click', e => {
      const b = e.target.closest('[data-do]'); if (!b || b.disabled || !sel || sel.kind !== 'br') return; const br = P().broll[sel.i], act = b.dataset.do;
      if (act === 'pick') return pickFile(f => { Object.assign(br, {path: f.path, d: f.d, a: 0, b: f.d, source: f.name, text: f.note || '', frame: null}); saveBroll(); draw(); });
      if (act === 'shorter') br.dur = Math.max(.8, +(br.dur - .5).toFixed(2));
      if (act === 'longer') br.dur = Math.min(15, +(br.dur + .5).toFixed(2));
      if (act === 'toggle') br.on = br.on === false;
      if (act === 'del') { P().broll.splice(sel.i, 1); sel = null; }
      saveBroll(); draw();
    });
    root.querySelector('.tl-tools').addEventListener('click', e => {
      const z = e.target.closest('[data-z]'), a = e.target.closest('[data-aspect]');
      if (z) { st.zoomed = true; st.pps = clamp(st.pps * (z.dataset.z > 0 ? 1.4 : 1 / 1.4), 20, 260); draw(false); }
      if (a) { aspect = a.dataset.aspect; draw(); }
      if (e.target.closest('[data-act=add]')) pickFile(f => {
        const first = nearestWord(cursor); if (first < 0) return;
        P().broll = [...(P().broll || []), {first, lead: 0, dur: 2.5, path: f.path, d: f.d, a: 0, b: f.d, text: f.note || '', source: f.name, on: true, frame: null}].sort((x, y) => x.first - y.first);
        sel = {kind: 'br', i: P().broll.findIndex(x => x.first === first && x.path === f.path)}; saveBroll(); draw();
      });
    });
    main.addEventListener('click', e => { const b = e.target.closest('[data-clip]'); if (b) { sel = {kind: 'clip', i: +b.dataset.clip}; draw(); } });
    bt.addEventListener('pointerdown', e => {
      const blk = e.target.closest('[data-br]'); if (!blk) return; const i = +blk.dataset.br, br = P().broll[i], h = e.target.closest('.tl-handle');
      e.preventDefault(); blk.setPointerCapture(e.pointerId); const x0 = e.clientX, a0 = brStart(br), d0 = br.dur; let moved = false, a = a0;
      const move = ev => { const dx = (ev.clientX - x0) / st.pps; if (Math.abs(ev.clientX - x0) > 3) moved = true;
        if (h) { br.dur = +clamp(d0 + dx, .8, 15).toFixed(2); blk.style.width = br.dur * st.pps + 'px'; } else { a = clamp(a0 + dx, 0, total() - .5); blk.style.left = a * st.pps + 'px'; } };
      const up = () => { blk.removeEventListener('pointermove', move); blk.removeEventListener('pointerup', up);
        if (moved && !h) { const w = nearestWord(a); if (w >= 0) { br.first = w; br.lead = 0; P().broll.sort((x, y) => x.first - y.first); } }
        sel = {kind: 'br', i: P().broll.indexOf(br)}; if (moved) saveBroll(); draw(); };
      blk.addEventListener('pointermove', move); blk.addEventListener('pointerup', up);
    });
    st.onResize = () => { if (P()) draw(false); };
    st.ruler.addEventListener('click', e => { cursor = clamp((e.clientX - st.inner.getBoundingClientRect().left) / st.pps, 0, total()); st.setHead(cursor); const pl = ctx.player; pl.currentTime = ctx.view() === 'edited' ? cursor : srcOf(cursor); });
    setInterval(() => { const pl = ctx.player; if (!P() || pl.paused) return; cursor = ctx.view() === 'edited' ? pl.currentTime : outOf(pl.currentTime); st.setHead(cursor); }, 200);
    return {refresh: () => { files = null; if (sel && sel.kind === 'br' && !(P() && (P().broll || [])[sel.i])) sel = null; draw(); }, redraw: () => draw(false)};
  }

  return {story, talk};
})();
