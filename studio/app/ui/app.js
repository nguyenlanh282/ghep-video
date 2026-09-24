'use strict';
const TOKEN = new URLSearchParams(location.search).get('t') || '';
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
let S = null;            // last state from the backend
let sampleWords = [];    // karaoke timings for the bundled sample clip
let groups = [];
let showingResult = false;
let SAMPLE = 'assets/';

async function api(name, body = {}) {
  const r = await fetch('/api/' + name, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': TOKEN}, body: JSON.stringify(body)});
  const out = await r.json();
  if (out && out.settings) render(out);
  return out;
}
const set = (values) => api('set', {values});
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const base = (p) => p ? p.split(/[\\/]/).pop() : '';

/* ---------- controls wired once; render() only updates values ---------- */
function formatValue(fmt, v) {
  if (fmt === 'percent') return Math.round(v * 100) + '%';
  if (fmt === 'seconds') return v.toFixed(1).replace('.', ',') + ' giây';
  return String(v);
}

function buildValueControls() {
  for (const el of $$('.value')) {
    const key = el.dataset.valueKey, min = +el.dataset.min, max = +el.dataset.max, step = +el.dataset.step, fmt = el.dataset.format;
    const label = el.textContent.trim();
    el.innerHTML = `<span class="label">${label}</span><span class="out"></span>
      <div class="ctl"><button class="step" data-d="-1" aria-label="Giảm ${label.toLowerCase()}">−</button>
      <input type="range" min="${min}" max="${max}" step="${step}" aria-label="${label}">
      <button class="step" data-d="1" aria-label="Tăng ${label.toLowerCase()}">+</button></div>`;
    const range = $('input', el), out = $('.out', el);
    const commit = debounce((v) => set({[key]: v}), 250);
    const apply = (v) => {
      v = Math.min(max, Math.max(min, Math.round(v / step) * step));
      v = +v.toFixed(3); range.value = v; out.textContent = formatValue(fmt, v);
      $$('.step', el).forEach(b => b.disabled = (+b.dataset.d < 0 ? v <= min : v >= max));
      return v;
    };
    range.addEventListener('input', () => commit(apply(+range.value)));
    $$('.step', el).forEach(b => b.addEventListener('click', () => commit(apply(+range.value + (+b.dataset.d) * step))));
    el._apply = apply;
  }
}

function wire() {
  buildValueControls();
  $$('input[type=checkbox][data-key]').forEach(cb => cb.addEventListener('change', () => set({[cb.dataset.key]: cb.checked})));
  $$('input[type=text][data-key], textarea[data-key]').forEach(inp => {
    const save = debounce(() => set({[inp.dataset.key]: inp.value}), 400);
    inp.addEventListener('input', () => { save(); if (inp.dataset.key === 'title' || inp.dataset.key === 'subtitle') paintTitle(); });
  });
  $$('[data-seg]').forEach(seg => seg.addEventListener('click', e => {
    const b = e.target.closest('button[data-value]'); if (!b) return;
    set({[seg.dataset.seg]: b.dataset.value}).then(replaySample);
  }));
  $$('[data-choice]').forEach(box => box.addEventListener('click', e => {
    const b = e.target.closest('button[data-value]'); if (!b) return;
    set({[box.dataset.choice]: b.dataset.value}).then(replaySample);
  }));
  $('#showTitle').addEventListener('change', e => set({titleStyle: e.target.checked ? 'pop' : 'none'}).then(replaySample));
  $$('[data-choose]').forEach(b => b.addEventListener('click', () => choose(b.dataset.choose)));

  $('#analyzeBtn').addEventListener('click', () => api('start', {task: 'analyze'}).then(poll));
  $('#undoBtn').addEventListener('click', () => { if (confirm('Trả lại tên gốc cho tất cả tư liệu đã đổi tên?')) api('start', {task: 'undo'}).then(poll); });
  $('#notesBtn').addEventListener('click', () => api('openNotes'));
  $('#previewBtn').addEventListener('click', () => startRender(true));
  $('#exportBtn').addEventListener('click', () => startRender(false));
  $('#cancelBtn').addEventListener('click', () => api('cancel'));
  $('#errorClose').addEventListener('click', () => api('clearError'));
  $('#revealBtn').addEventListener('click', () => api('reveal'));
  $('#backToSample').addEventListener('click', () => { showingResult = false; loadSample(); });
  $('#clearMusic').addEventListener('click', () => { stopListening(); set({music: ''}); });
  $$('[data-listen]').forEach(b => b.addEventListener('click', () => listen(b.dataset.listen, b)));
  $('#listenAudio').addEventListener('ended', stopListening);

  $$('.keyrow').forEach(wireKeyRow);
  wireUpdates();

  const player = $('#player');
  $('#playBtn').addEventListener('click', () => { stopListening(); player.paused ? player.play() : player.pause(); });
  $('#restartBtn').addEventListener('click', replaySample);
  player.addEventListener('play', () => { $('#playBtn').textContent = '❚❚'; $('#playBtn').setAttribute('aria-label', 'Tạm dừng'); });
  player.addEventListener('pause', () => { $('#playBtn').textContent = '▶'; $('#playBtn').setAttribute('aria-label', 'Phát xem thử'); });
}

/* ---------- API keys: one row per platform, saved only when its own "Lưu" is pressed ---------- */
const KEY_NAMES = {pixabay: 'Pixabay', pexels: 'Pexels'};
function keyState(row, text, cls) { const el = $('.keystate', row); el.textContent = text; el.className = 'keystate ' + (cls || ''); }
function wireKeyRow(row) {
  const src = row.dataset.source, input = $('input', row), save = $('.save', row);
  const sync = () => { save.disabled = !input.value.trim(); };
  input.addEventListener('input', () => { sync(); keyState(row, 'Chưa lưu', ''); });
  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !save.disabled) save.click(); });
  $('.eye', row).addEventListener('click', e => {
    const show = input.type === 'password'; input.type = show ? 'text' : 'password';
    e.currentTarget.setAttribute('aria-label', show ? 'Ẩn key' : 'Hiện key');
  });
  save.addEventListener('click', async () => {
    save.disabled = true; keyState(row, 'Đang kiểm tra key…', '');
    const out = await api('saveKey', {source: src, value: input.value});
    if (out.check === 'invalid') { keyState(row, `Key ${KEY_NAMES[src]} không đúng · chưa lưu, key cũ giữ nguyên`, 'bad'); sync(); return; }
    if (out.check === 'busy') { keyState(row, `${KEY_NAMES[src]} đang tạm chặn vì gọi quá nhiều · chưa lưu, thử lại sau ít phút`, 'bad'); sync(); return; }
    if (out.check === 'offline') { keyState(row, `Không kết nối được ${KEY_NAMES[src]} · chưa lưu, thử lại sau`, 'bad'); sync(); return; }
    input.value = ''; sync();
    keyState(row, `Đã lưu ✓ ${out.settings[src + 'KeyHint']}`, 'ok');
  });
  $('.clear', row).addEventListener('click', async () => {
    if (!S.settings[src + 'KeySet'] || !confirm(`Xoá key ${KEY_NAMES[src]} đã lưu?`)) return;
    await api('saveKey', {source: src, value: ''}); keyState(row, 'Đã xoá key', '');
  });
  $('.getkey', row).addEventListener('click', () => api('openLink', {url: $('.getkey', row).dataset.url}));
  sync();
}

/* ---------- updates ---------- */
function wireUpdates() {
  const dlg = $('#updateDialog');
  $('#updateBtn').addEventListener('click', () => { paintUpdate(); dlg.showModal(); if (S.updateConfigured && !S.update) api('checkUpdate').then(paintUpdate); });
  $('#updCheck').addEventListener('click', () => { $('#updBody').innerHTML = '<p>Đang kiểm tra…</p>'; api('checkUpdate').then(paintUpdate); });
  $('#updUrlSave').addEventListener('click', () => set({updateManifest: $('#updUrl').value.trim()}).then(() => api('checkUpdate')).then(paintUpdate));
  $('#rollbackBtn').addEventListener('click', () => {
    if (confirm(`Quay lại ${S.backups[0]}? Bản hiện tại sẽ được thay bằng bản sao lưu.`)) { dlg.close(); api('rollback').then(poll); }
  });
  $('#updBody').addEventListener('click', e => {
    if (e.target.id === 'updGo') { dlg.close(); api('applyUpdate').then(poll); }
    if (e.target.id === 'updRestart') api('restart');
  });
}
function paintUpdate() {
  if (!S) return;
  const u = S.update, b = $('#updBody'), job = S.job;
  $('#updCurrent').textContent = S.version;
  if (document.activeElement !== $('#updUrl')) $('#updUrl').value = S.settings.updateManifest || '';
  $('#rollbackBtn').hidden = !S.backups.length;
  if (job.task === 'update' && job.restartNeeded && !job.running) {
    b.innerHTML = `<p class="ok">${esc(job.status)}</p><button class="btn primary" id="updRestart" type="button">Khởi động lại app</button>`; return;
  }
  if (!S.updateConfigured) { b.innerHTML = '<p class="hint">Chưa có địa chỉ cập nhật. Mở mục “Địa chỉ cập nhật” bên dưới và dán link được cung cấp.</p>'; $('#updAdvanced').open = true; return; }
  if (!u) { b.innerHTML = '<p class="hint">Bấm “Kiểm tra” để xem có bản mới không.</p>'; return; }
  if (u.error) { b.innerHTML = `<p class="bad">${esc(u.error)}</p>`; return; }
  if (!u.available) { b.innerHTML = `<p class="ok">✓ Đang dùng bản mới nhất (${esc(u.latest)}).</p>`; return; }
  b.innerHTML = `<p>Có bản mới <b>${esc(u.latest)}</b>${u.size ? ` · ${Math.max(1, Math.round(u.size / 1048576))} MB` : ''}.</p>
    ${u.notes ? `<div class="notes">${esc(u.notes)}</div>` : ''}
    <p class="hint">Chỉ thay file của app; tư liệu, video đã xuất, cài đặt và key giữ nguyên. Bản hiện tại được sao lưu để quay lại khi cần.</p>
    <button class="btn primary" id="updGo" type="button">Cập nhật lên ${esc(u.latest)}</button>`;
}

async function choose(kind) {
  const out = await api('choose', {kind});
  if (out && out.error) {
    // Browser mode has no native dialog: let the user paste a path instead.
    const key = {media: 'mediaFolder', output: 'outputFolder', audio: 'audio', music: 'music'}[kind];
    const path = prompt('Dán đường dẫn đầy đủ:', S.settings[key] || '');
    if (path) set({[key]: path.trim()});
  }
}

async function startRender(preview) {
  stopListening(); $('#player').pause();
  const out = await api('start', {task: 'render', preview});
  if (out && out.job && out.job.running) poll();
}

/* ---------- state → DOM ---------- */
function render(state) {
  const prevJob = S && S.job; S = state; const s = state.settings, job = state.job;
  $$('input[type=checkbox][data-key]').forEach(cb => cb.checked = !!s[cb.dataset.key]);
  $$('input[type=text][data-key], textarea[data-key]').forEach(inp => { if (document.activeElement !== inp) inp.value = s[inp.dataset.key] ?? ''; });
  $$('.value').forEach(el => { if (!el.contains(document.activeElement) || el._apply) el._apply(+s[el.dataset.valueKey]); });
  $$('[data-seg]').forEach(seg => $$('button', seg).forEach(b => b.classList.toggle('on', s[seg.dataset.seg] === b.dataset.value)));
  $$('[data-choice]').forEach(box => $$('button', box).forEach(b => { b.classList.toggle('on', s[box.dataset.choice] === b.dataset.value); b.setAttribute('aria-pressed', s[box.dataset.choice] === b.dataset.value); }));
  $('#showTitle').checked = s.titleStyle !== 'none';
  $$('[data-path]').forEach(el => { const p = s[el.dataset.path]; if (p) { el.textContent = base(p); el.parentElement.parentElement.title = p; } });
  $('#musicLabel').textContent = s.music ? 'Đổi nhạc nền' : 'Thêm nhạc nền';
  $('#mediaCount').textContent = state.mediaCount;
  $('#versionLabel').textContent = state.version + (state.update && state.update.available ? ' · có bản mới' : '');
  $('#updateBtn').classList.toggle('primary', !!(state.update && state.update.available));
  if (job.task === 'update' && job.restartNeeded && !job.running && prevJob && prevJob.running) { paintUpdate(); $('#updateDialog').showModal(); }
  if ($('#updateDialog').open) paintUpdate();
  $('#platformLabel').textContent = 'Xử lý trên máy · ' + (state.platform === 'windows' ? 'Windows' : state.platform === 'mac' ? 'macOS' : 'Linux');

  // analysis
  const analysed = state.analyzedCount > 0;
  $('#analyzeBtn').textContent = analysed ? '✨ Phân tích file mới' : '✨ Phân tích & đặt tên';
  $('#notesBtn').hidden = !analysed; $('#noteList').hidden = !analysed;
  $('#analysisInfo').textContent = analysed ? `${state.analyzedCount}/${state.mediaCount} file đã phân tích · ${state.sceneCount} đoạn cảnh` : 'AI trên máy xem từng ảnh/video, đặt tên theo nội dung và ghi chú từng đoạn cảnh.';
  const match = $('input[data-key=matchScenes]'), stock = $('input[data-key=stockEnabled]');
  match.disabled = !analysed; match.closest('.switch').classList.toggle('disabled', !analysed);
  stock.disabled = !analysed || !s.matchScenes; stock.closest('.switch').classList.toggle('disabled', stock.disabled);
  $('#stockBox').hidden = !(s.stockEnabled && s.matchScenes && analysed);
  const src = s.stockSource, needsKey = src === 'pexels' || src === 'pixabay', hasKey = needsKey && s[src + 'KeySet'];
  // Only the chosen site's key is shown; "Tự động" uses every saved key, so both rows are shown.
  if (render.lastSource && render.lastSource !== src) $$('.keyrow').forEach(r => { $('input', r).value = ''; $('.save', r).disabled = true; $('.keystate', r).className = 'keystate'; });
  render.lastSource = src;
  for (const row of $$('.keyrow')) {
    const k = row.dataset.source, saved = s[k + 'KeySet'], input = $('input', row);
    row.hidden = !(src === k || src === 'auto');
    input.placeholder = saved ? `Đã lưu ${s[k + 'KeyHint']} · dán key mới để thay` : `Dán API key ${KEY_NAMES[k]}`;
    $('.clear', row).disabled = !saved;
    const st = $('.keystate', row);
    if (!input.value && !st.classList.contains('bad')) keyState(row, saved ? `Đã lưu ✓ ${s[k + 'KeyHint']}` : 'Chưa có key', saved ? 'ok' : '');
  }
  const order = ['pexels', 'pixabay'].filter(k => s[k + 'KeySet']).map(k => KEY_NAMES[k]).concat('Openverse');
  $('#stockHint').textContent = src === 'auto' ? `Tự thử lần lượt: ${order.join(' → ')}. Câu nào nguồn trước không có hình hợp thì tìm tiếp ở nguồn sau.`
    : src === 'openverse' ? 'Openverse: ảnh CC0, không cần key, nhưng kho ảnh đời thường ít.'
    : !hasKey ? `Chưa lưu key ${KEY_NAMES[src]}: sẽ dùng Openverse thay thế.`
    : 'AI tự viết từ khoá, tải về và chỉ giữ hình thật sự hợp câu. Nguồn ghi trong file .nguon-anh.txt cạnh video.';
  $('#notes').innerHTML = state.notes.map(n => `<div class="note"><b>${n.kind === 'video' ? '🎬' : '🖼'} ${esc(n.name)}</b><small>${esc(n.text)}${n.kind === 'video' ? ' · ' + n.scenes + ' đoạn' : ''}</small></div>`).join('');

  // music
  const hasMusic = !!s.music;
  $('[data-listen=music]').disabled = !hasMusic; $('[data-listen=mix]').disabled = !hasMusic || !s.audio; $('[data-listen=voice]').disabled = !s.audio;
  $('#musicHint').hidden = hasMusic; $('#clearMusic').hidden = !hasMusic;

  // job
  $('#main').classList.toggle('busy', job.running);
  $('#progress').hidden = !job.running; $('#progress').value = job.progress;
  $('#status').textContent = job.status;
  $('#substatus').textContent = job.running ? `${Math.round(job.progress * 100)}% · Bạn có thể dừng bất cứ lúc nào` : `Video dọc 9:16 · ${s.resolution}p · Giữ nguyên file gốc`;
  $('#actions').hidden = job.running; $('#cancelBtn').hidden = !job.running;
  $('#cancelBtn').textContent = job.task === 'render' ? 'Dừng xuất' : 'Dừng phân tích';
  if (job.task === 'update') $('#cancelBtn').hidden = true;  // an update must finish (or fail and leave the old version)
  $('#error').hidden = !job.error; $('#errorText').textContent = job.error || '';
  if (state.resultUrl && (!prevJob || prevJob.result !== job.result || !showingResult) && prevJob && prevJob.running && !job.running) showResult(state.resultUrl);
  $('#resultRow').hidden = !job.result;
  paintTitle();
}
const esc = (t) => String(t).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

let polling = false;
async function poll() {
  if (polling) return; polling = true;
  try { while ((await api('state')).job.running) await new Promise(r => setTimeout(r, 400)); }
  finally { polling = false; }
}

/* ---------- audio preview ---------- */
// Previews are mixed by the backend exactly like the export (voice gain to -14 LUFS, music level, limiter),
// so what you hear here is what the video will sound like. 30 seconds each.
const LISTEN_LABEL = {voice: '▶ Nghe giọng đọc', music: '▶ Nghe nhạc', mix: '▶ Nghe cùng lời đọc'};
let listening = null;
function stopListening() {
  $('#listenAudio').pause(); listening = null;
  $$('[data-listen]').forEach(b => b.textContent = LISTEN_LABEL[b.dataset.listen]);
}
async function listen(mode, btn) {
  const was = listening; stopListening(); if (was === mode) return;
  $('#player').pause(); listening = mode; btn.textContent = '… Đang chuẩn bị';
  const out = await api('listen', {mode});
  if (listening !== mode) return;
  if (!out.url) { stopListening(); alert(out.error || 'Không nghe thử được.'); return; }
  const a = $('#listenAudio'); a.src = out.url; a.play(); btn.textContent = '■ Dừng nghe';
}

/* ---------- sample preview: title + karaoke drawn over the bundled clip ---------- */
const measure = document.createElement('canvas').getContext('2d');
function captionGroups(words) {
  // Same rules as renderer.groups_for: a phrase ends at punctuation or a pause, long phrases split evenly.
  measure.font = 'bold 16px Arial';
  const fits = g => g.length <= 7 && measure.measureText(g.map(w => w.text).join(' ')).width <= 258;
  const phrases = []; let cur = [];
  for (const w of words) {
    if (cur.length && w.start - cur[cur.length - 1].end > 0.65) { phrases.push(cur); cur = []; }
    cur.push(w);
    if (/[,.?!:;…]$/.test(w.text)) { phrases.push(cur); cur = []; }
  }
  if (cur.length) phrases.push(cur);
  const out = [];
  for (const ph of phrases) {
    for (let parts = 1; parts <= ph.length; parts++) {
      const size = Math.floor(ph.length / parts), extra = ph.length % parts, lines = []; let i = 0;
      for (let k = 0; k < parts; k++) { const n = size + (k < extra ? 1 : 0); lines.push(ph.slice(i, i + n)); i += n; }
      if (lines.every(fits) || parts === ph.length) { out.push(...lines); break; }
    }
  }
  return out;
}
const HL = {active: '#9cfa68', sweep: '#ffd54a', pill: '#f37aa5'};

function paintTitle() {
  if (!S) return;
  const st = S.settings.titleStyle, ov = $('#titleOv');
  $('#t1').textContent = S.settings.title; $('#t2').textContent = S.settings.subtitle;
  ov.className = 'title-ov ' + st;
}

let capKey = '';
function tick() {
  const p = $('#player'), t = p.currentTime || 0;
  $('#time').textContent = String(Math.floor(t / 60)).padStart(2, '0') + ':' + String(Math.floor(t % 60)).padStart(2, '0');
  if (S && !showingResult) {
    const st = S.settings.titleStyle, ov = $('#titleOv');
    ov.hidden = st === 'none' || t >= 3.4;
    if (!ov.hidden) {
      if (st === 'pop') ov.style.transform = `scale(${0.86 + 0.14 * Math.min(1, t / 0.22)})`;
      else if (st === 'card') ov.style.transform = `translateX(${-100 * Math.pow(1 - Math.min(1, t / 0.26), 3)}%)`;
      else ov.style.transform = '';
    }
    // The line holds until the next one starts (max 1.5 s after its last word): no blinking between phrases.
    let g = null;
    for (const x of groups) if (x[0].start <= t) g = x; else break;
    if (g && t >= g[g.length - 1].end + 1.5) g = null;
    const style = S.settings.subStyle, active = g ? g.findIndex(w => w.start <= t && t < w.end) : -1;
    const key = style === 'none' || !g ? '' : groups.indexOf(g) + ':' + active + ':' + style;
    if (key !== capKey) {
      capKey = key;
      $('#cap').innerHTML = key ? g.map((w, j) => `<span style="${j === active && HL[style] ? 'color:' + HL[style] : ''}">${esc(w.text)}</span>`).join('') : '';
    }
  } else { $('#titleOv').hidden = true; if (capKey) { capKey = ''; $('#cap').innerHTML = ''; } }
  requestAnimationFrame(tick);
}

function loadSample() {
  const p = $('#player'); showingResult = false; p.controls = false;
  p.src = SAMPLE + 'demo.mp4'; $('#pv').textContent = 'XEM MẪU KIỂU CHỮ';
  $('#previewHint').hidden = false; $('#backToSample').hidden = true;
}
function replaySample() { if (showingResult) loadSample(); const p = $('#player'); p.currentTime = 0; p.play().catch(() => {}); }
function showResult(url) {
  const p = $('#player'); showingResult = true; p.src = url; p.controls = true;
  $('#pv').textContent = 'VIDEO ĐÃ XUẤT'; $('#previewHint').hidden = true; $('#backToSample').hidden = false;
  p.play().catch(() => {});
}

async function init() {
  wire();
  // A machine may keep its own sample in assets/local/ (never published, never replaced by updates).
  try { if ((await fetch('assets/local/words.json', {method: 'HEAD'})).ok) SAMPLE = 'assets/local/'; } catch (e) {}
  loadSample();
  try { sampleWords = await (await fetch(SAMPLE + 'words.json')).json(); groups = captionGroups(sampleWords); } catch (e) { groups = []; }
  const st = await api('state');
  if (st.job && st.job.running) poll();
  // Quietly look for a new version once per launch; the header button lights up when one exists.
  if (st.updateConfigured) api('checkUpdate');
  requestAnimationFrame(tick);
}
init();
