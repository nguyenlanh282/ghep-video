'use strict';
// Video chia sẻ: transcript editor for a raw talking video. The project (words with cut flags, titles, caption,
// keywords, shorts, B-roll) lives in the backend; edits are sent back with talkEdit.
const TOKEN = new URLSearchParams(location.search).get('t') || '';
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const base = p => p ? p.split(/[\\/]/).pop() : '';
const fmt = s => { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const REASON = {'im-lang': 'Im lặng', 'am-u': 'Ậm ừ', 'lap': 'Nói vấp', 'noi-lai': 'Nói lại', 'tay': 'Bạn cắt'};
let S = null, P = null, videoUrl = null, keep = [];
let autoExport = false;
let exportsList = [], view = 'raw', currentExport = 0, preferRaw = false;  // preview: the edited result, or the raw video with cuts skipped  // “Edit & xuất ngay”: export as soon as the analysis finishes

async function api(name, body = {}) {
  const r = await fetch('/api/' + name, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': TOKEN}, body: JSON.stringify(body)});
  const out = await r.json();
  if (out && out.settings) renderState(out);
  return out;
}
const set = values => api('set', {values});

/* ---------- same cutting rule as talk.py keep_ranges ---------- */
const PAD_BEFORE = .08, PAD_AFTER = .14, MAX_GAP = .35;
function keepRanges(words, duration) {
  const runs = []; let cur = null;
  for (const w of words) {
    if (w.cut) { if (cur) { runs.push(cur); cur = null; } continue; }
    if (cur && w.start - cur[1] > MAX_GAP) { runs.push(cur); cur = null; }
    cur = cur ? [cur[0], w.end] : [w.start, w.end];
  }
  if (cur) runs.push(cur);
  const out = [];
  runs.forEach(([a, b], k) => {
    const lo = Math.max(0, a - PAD_BEFORE, k ? (runs[k - 1][1] + a) / 2 : 0);
    const hi = Math.min(duration, b + PAD_AFTER, k + 1 < runs.length ? (b + runs[k + 1][0]) / 2 : duration);
    if (out.length && lo - out[out.length - 1][1] < .12) out[out.length - 1][1] = hi; else out.push([lo, hi]);
  });
  return out.filter(([a, b]) => b - a > .05);
}

/* ---------- settings panel ---------- */
// − / slider / + rows (same control as the Ghép ảnh page): <div class="value" data-value-key data-min data-max data-step data-format>Label</div>
function buildValueControls() {
  const fmt = (f, v) => f === 'percent' ? Math.round(v * 100) + '%' : f === 'seconds' ? v.toFixed(1).replace('.', ',') + ' giây' : String(v);
  for (const el of $$('.value[data-value-key]')) {
    const key = el.dataset.valueKey, min = +el.dataset.min, max = +el.dataset.max, step = +el.dataset.step, label = el.textContent.trim();
    el.innerHTML = `<span class="label">${label}</span><span class="out"></span><div class="ctl"><button class="step" data-d="-1" aria-label="Giảm ${label.toLowerCase()}">−</button><input type="range" min="${min}" max="${max}" step="${step}" aria-label="${label}"><button class="step" data-d="1" aria-label="Tăng ${label.toLowerCase()}">+</button></div>`;
    const range = $('input', el), commit = debounce(v => set({[key]: v}), 250);
    const apply = v => {
      v = +Math.min(max, Math.max(min, Math.round(v / step) * step)).toFixed(3); range.value = v; $('.out', el).textContent = fmt(el.dataset.format, v);
      $$('.step', el).forEach(b => b.disabled = +b.dataset.d < 0 ? v <= min : v >= max); return v;
    };
    range.addEventListener('input', () => commit(apply(+range.value)));
    $$('.step', el).forEach(b => b.addEventListener('click', () => commit(apply(+range.value + (+b.dataset.d) * step))));
    el._apply = apply;
  }
}

function renderState(st) {
  const prev = S && S.job; S = st; const s = st.settings, job = st.job;
  $$('input[type=checkbox][data-key]').forEach(cb => cb.checked = !!s[cb.dataset.key]);
  $$('[data-seg]').forEach(seg => $$('button', seg).forEach(b => b.classList.toggle('on', s[seg.dataset.seg] === b.dataset.value)));
  $$('[data-choice]').forEach(box => $$('button', box).forEach(b => b.classList.toggle('on', s[box.dataset.choice] === b.dataset.value)));
  $$('[data-path]').forEach(el => { const p = s[el.dataset.path]; if (p) { el.textContent = base(p); el.closest('button').title = p; } });
  $$('.value[data-value-key]').forEach(el => { if (el._apply && !el.contains(document.activeElement)) el._apply(+s[el.dataset.valueKey]); });
  const aspects = (s.talkAspects || '9:16').split(',');
  $$('#aspects input').forEach(i => i.checked = aspects.includes(i.value));
  const ai = st.ai;
  $('#aiLine').textContent = ai.ready ? `AI soát chính tả, tiêu đề, cảnh trám: ${ai.used === 'claude' ? 'Claude' : 'ChatGPT (Codex)'}.`
    : 'Chưa có Claude Code / Codex: vẫn cắt và làm phụ đề, nhưng không có soát chính tả, tiêu đề gợi ý, cảnh trám.';
  $('#main').classList.toggle('busy', job.running);
  $('#progress').hidden = !job.running; $('#progress').value = job.progress;
  $('#status').textContent = job.status;
  $('#substatus').textContent = job.running ? `${Math.round(job.progress * 100)}% · Bạn có thể dừng bất cứ lúc nào` : 'Video thô → video hoàn thiện có phụ đề, tiêu đề, cảnh trám';
  $('#actions').hidden = job.running; $('#cancelBtn').hidden = !job.running || !['talk-analyze', 'talk-render'].includes(job.task);
  $('#error').hidden = !job.error; $('#errorText').textContent = job.error || '';
  $('#exportBtn').disabled = !P;
  if (prev && prev.running && !job.running) {
    if (job.task === 'talk-analyze' && !job.error) loadProject().then(() => { if (autoExport) { autoExport = false; startExport(); } });
    if (job.task === 'talk-analyze' && job.error) autoExport = false;
    if (job.task === 'talk-render' && job.result && !job.error) {
      $('#resultRow').hidden = false; $('#status').textContent = '✓ ' + job.status;
      preferRaw = false; loadProject().then(() => { if (exportsList.length) { currentExport = 0; setView('edited', true); } });
    }
  }
}

async function poll() {
  for (;;) { const st = await api('state'); if (!st.job.running) break; await new Promise(r => setTimeout(r, 500)); }
}

/* ---------- transcript editor ---------- */
const pending = {}; let pendingOther = {};
const saveEdits = debounce(async () => {
  const body = {cuts: {...pending}, ...pendingOther};
  for (const k in pending) delete pending[k]; pendingOther = {};
  await api('talkEdit', body);
}, 500);
function setCut(indices, reason) {
  for (const i of indices) { P.words[i].cut = reason; pending[i] = reason; }
  paintWords(); saveEdits();
}
function editOther(obj) { Object.assign(pendingOther, obj); saveEdits(); }

const norm = w => w.normalize('NFC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
function keywordIndices() {
  const toks = P.words.map(w => norm(w.text)), out = new Set();
  for (const k of P.keywords || []) {
    const seq = k.split(/\s+/).map(norm).filter(Boolean); if (!seq.length) continue;
    for (let i = 0; i + seq.length <= toks.length; i++) if (seq.every((t, j) => toks[i + j] === t)) seq.forEach((_, j) => out.add(i + j));
  }
  return out;
}

function buildTranscript() {
  const brAt = new Map((P.broll || []).map((b, k) => [b.first, k]));
  $('#transcript').innerHTML = P.words.map((w, i) => {
    const br = brAt.has(i) ? `<button class="brmark" data-br="${brAt.get(i)}" title="${esc(P.broll[brAt.get(i)].source + ': ' + P.broll[brAt.get(i)].text)}">🎬</button>` : '';
    return `${br}<span class="w" data-i="${i}">${esc(w.text)}</span> `;
  }).join('');
  paintWords();
}

function paintWords() {
  if (!P) return;
  const kws = keywordIndices();
  $$('#transcript .w').forEach(el => {
    const w = P.words[+el.dataset.i];
    el.className = 'w' + (w.cut ? ' cut c-' + w.cut : '') + (kws.has(+el.dataset.i) ? ' kw' : '');
    el.title = w.cut ? `${REASON[w.cut] || 'Cắt'} · bấm để khôi phục` : (w.raw ? `Đã sửa từ “${w.raw}”` : '');
  });
  $$('#transcript .brmark').forEach(b => b.classList.toggle('off', !P.broll[+b.dataset.br].on));
  keep = keepRanges(P.words, P.duration);
  const kept = keep.reduce((s, [a, b]) => s + b - a, 0), by = {};
  for (const w of P.words) if (w.cut) by[w.cut] = (by[w.cut] || 0) + (w.end - w.start);
  const wordsCut = Object.values(by).reduce((a, b) => a + b, 0);
  by['im-lang'] = Math.max(0, P.duration - kept - wordsCut);
  $('#stats').textContent = `Thô ${fmt(P.duration)} → còn ${fmt(kept)} · cắt ` +
    Object.entries(by).filter(([, v]) => v >= .5).map(([k, v]) => `${REASON[k]} ${Math.round(v)}s`).join(', ');
}

function selectedWordIndices() {
  const sel = getSelection(); if (!sel.rangeCount || sel.isCollapsed) return [];
  const range = sel.getRangeAt(0);
  return $$('#transcript .w').filter(el => range.intersectsNode(el)).map(el => +el.dataset.i);
}

function paintExtras() {
  const titles = P.titles || [];
  const chosen = P.title_choice || titles[0] || {dong1: '', dong2: ''};
  if (!P.title_choice && titles[0]) editOther({title_choice: titles[0]}), P.title_choice = titles[0];
  $('#titles').innerHTML = titles.map((t, k) => `<label class="tchoice"><input type="radio" name="title" value="${k}" ${t.dong1 === chosen.dong1 && t.dong2 === chosen.dong2 ? 'checked' : ''}><span><b>${esc(t.dong1)}</b><small>${esc(t.dong2)}</small></span></label>`).join('')
    || '<p class="hint">Chưa có gợi ý (cần Claude Code hoặc Codex). Tự nhập bên dưới.</p>';
  $('#t1in').value = chosen.dong1 || ''; $('#t2in').value = chosen.dong2 || '';
  $('#caption').value = P.caption || ''; $('#hashtags').value = (P.hashtags || []).join(' ');
  $('#keywords').value = (P.keywords || []).join(', ');
  $('#shorts').innerHTML = (P.shorts || []).map((c, k) => {
    const a = P.words[c.first].start, b = P.words[c.last].end;
    return `<label class="short"><input type="checkbox" data-short="${k}" ${c.on ? 'checked' : ''}><span><b>${esc(c.title)}</b><small>${fmt(a)}–${fmt(b)} (bản thô) · ${esc(c.reason)}</small></span><button class="btn small" data-play="${a}">▶</button></label>`;
  }).join('') || '<p class="hint">Video ngắn hoặc chưa có AI: không có gợi ý clip.</p>';
}

async function loadProject() {
  const out = await api('talkState');
  P = out.project; videoUrl = out.videoUrl; exportsList = out.exports || [];
  $('#emptyEditor').hidden = !!P; $('#editorBody').hidden = !P; $('#exportBtn').disabled = !P;
  $('#resultRow').hidden = !exportsList.length;
  if (P) { buildTranscript(); paintExtras(); }
  setView(exportsList.length && !preferRaw ? 'edited' : 'raw');
}

/* Preview source: the finished video (what viewers will see: title, captions, B-roll) or the raw take with cuts skipped. */
function setView(v, play) {
  view = v === 'edited' && exportsList.length ? 'edited' : 'raw';
  $$('#viewSeg button').forEach(b => { b.classList.toggle('on', b.dataset.view === view); b.disabled = b.dataset.view === 'edited' && !exportsList.length; });
  $('#editedPick').innerHTML = view === 'edited' ? exportsList.map((e, k) =>
    `<button data-export="${k}" class="${k === currentExport ? 'on' : ''}"><span>${esc(e.kind === 'clip ngắn' ? e.name : e.name)}</span><small>${e.duration ? fmt(e.duration) : ''}</small></button>`).join('') : '';
  $('#skipRow').hidden = view !== 'raw';
  $('#viewHint').textContent = view === 'edited' ? 'Video đã edit, đúng như người xem sẽ thấy. Sửa bản chữ rồi bấm “Xuất video” để xem lại bản mới.'
    : exportsList.length ? 'Bản thô: bấm chữ trong bản chữ để nghe đúng đoạn đó.' : 'Chưa xuất video: đang phát bản thô. Bấm “Xuất video” hoặc “⚡ Edit & xuất ngay” để xem video đã edit.';
  const src = view === 'edited' ? exportsList[currentExport].url : videoUrl, p = $('#player');
  if (src && p.dataset.src !== src) { p.src = src; p.dataset.src = src; }
  if (play) p.play().catch(() => {});
}

/* ---------- preview: play the raw video but jump over every cut ---------- */
function followPlayer() {
  const p = $('#player');
  if (P && !p.paused && view === 'raw') {
    const t = p.currentTime;
    if ($('#skipCuts').checked && keep.length) {
      const inside = keep.some(([a, b]) => t >= a && t < b);
      if (!inside) { const next = keep.find(([a]) => a > t); if (next) p.currentTime = next[0]; else p.pause(); }
    }
    const i = P.words.findIndex(w => t >= w.start && t < w.end);
    $$('#transcript .w.now').forEach(e => e.classList.remove('now'));
    if (i >= 0) { const el = $(`#transcript .w[data-i="${i}"]`); el.classList.add('now'); }
  }
  requestAnimationFrame(followPlayer);
}

async function startExport() {
  $('#player').pause(); $('#resultRow').hidden = true;
  const out = await api('start', {task: 'talk-render'}); if (out.job && out.job.running) poll();
}

/* ---------- wiring ---------- */
function wire() {
  $$('[data-mode-link]').forEach(a => a.href = `${a.dataset.modeLink}?t=${TOKEN}`);
  $$('input[type=checkbox][data-key]').forEach(cb => cb.addEventListener('change', () => set({[cb.dataset.key]: cb.checked})));
  $$('[data-seg]').forEach(seg => seg.addEventListener('click', e => { const b = e.target.closest('button[data-value]'); if (b) set({[seg.dataset.seg]: b.dataset.value}); }));
  $$('[data-choice]').forEach(box => box.addEventListener('click', e => { const b = e.target.closest('button[data-value]'); if (b) set({[box.dataset.choice]: b.dataset.value}); }));
  $$('#aspects input').forEach(i => i.addEventListener('change', () => {
    const v = $$('#aspects input').filter(x => x.checked).map(x => x.value);
    if (!v.length) { i.checked = true; return; }
    set({talkAspects: v.join(',')});
  }));
  $$('[data-choose]').forEach(b => b.addEventListener('click', async () => {
    const out = await api('choose', {kind: b.dataset.choose});
    if (out.error) {
      const key = b.dataset.choose === 'talkVideo' ? 'talkVideo' : 'talkBrollFolder';
      const path = prompt('Dán đường dẫn đầy đủ:', S.settings[key] || ''); if (path) await set({[key]: path.trim()});
    }
    if (b.dataset.choose === 'talkVideo') loadProject();
  }));
  $('#analyzeBtn').addEventListener('click', async () => {
    if (P && !confirm('Phân tích lại sẽ thay bản chữ hiện tại (các chỗ bạn đã sửa sẽ mất). Tiếp tục?')) return;
    const out = await api('start', {task: 'talk-analyze'}); if (out.job && out.job.running) poll();
  });
  $('#exportBtn').addEventListener('click', startExport);
  $('#autoBtn').addEventListener('click', async () => {
    if (!S.settings.talkVideo) { alert('Hãy chọn video thô trước.'); return; }
    if (P && !confirm('Edit lại từ đầu sẽ thay bản chữ hiện tại (các chỗ bạn đã sửa sẽ mất). Tiếp tục?')) return;
    autoExport = true; $('#resultRow').hidden = true;
    const out = await api('start', {task: 'talk-analyze'}); if (out.job && out.job.running) poll(); else autoExport = false;
  });
  $('#cancelBtn').addEventListener('click', () => api('cancel'));
  $('#viewSeg').addEventListener('click', e => { const b = e.target.closest('[data-view]'); if (b && !b.disabled) { preferRaw = b.dataset.view === 'raw'; setView(b.dataset.view, true); } });
  $('#editedPick').addEventListener('click', e => { const b = e.target.closest('[data-export]'); if (b) { currentExport = +b.dataset.export; setView('edited', true); } });
  buildValueControls();
  $('#errorClose').addEventListener('click', () => api('clearError'));
  $('#openFolder').addEventListener('click', () => api('reveal'));

  const tr = $('#transcript');
  tr.addEventListener('click', e => {
    const br = e.target.closest('.brmark');
    if (br) { const k = +br.dataset.br; P.broll[k].on = !P.broll[k].on; editOther({broll: {[k]: P.broll[k].on}}); paintWords(); return; }
    const el = e.target.closest('.w'); if (!el || !getSelection().isCollapsed) return;
    const i = +el.dataset.i, w = P.words[i];
    if (w.cut) setCut([i], null);
    else { if (view === 'edited') setView('raw'); const p = $('#player'); p.currentTime = Math.max(0, w.start - .05); p.play().catch(() => {}); }
  });
  const cutSelection = () => { const idx = selectedWordIndices().filter(i => !P.words[i].cut); if (idx.length) { setCut(idx, 'tay'); getSelection().removeAllRanges(); } };
  tr.addEventListener('keydown', e => { if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); cutSelection(); } });
  document.addEventListener('keydown', e => { if ((e.key === 'Delete' || e.key === 'Backspace') && selectedWordIndices().length && !/input|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); cutSelection(); } });
  $('#cutSel').addEventListener('click', cutSelection);
  $('#restoreSel').addEventListener('click', () => { const idx = selectedWordIndices().filter(i => P.words[i].cut); if (idx.length) setCut(idx, null); });
  $('#restoreAuto').addEventListener('click', () => {
    const idx = P.words.map((w, i) => w.cut && w.cut !== 'tay' ? i : -1).filter(i => i >= 0);
    if (idx.length && confirm(`Khôi phục ${idx.length} chữ app đã tự cắt (ậm ừ, nói vấp, nói lại)? Khoảng im lặng vẫn được cắt.`)) setCut(idx, null);
  });

  $('#titles').addEventListener('change', e => { const t = P.titles[+e.target.value]; P.title_choice = t; $('#t1in').value = t.dong1; $('#t2in').value = t.dong2; editOther({title_choice: t}); });
  const saveTitle = debounce(() => { P.title_choice = {dong1: $('#t1in').value.trim(), dong2: $('#t2in').value.trim()}; editOther({title_choice: P.title_choice}); }, 400);
  $('#t1in').addEventListener('input', saveTitle); $('#t2in').addEventListener('input', saveTitle);
  $('#caption').addEventListener('input', debounce(() => editOther({caption: $('#caption').value}), 500));
  $('#hashtags').addEventListener('input', debounce(() => editOther({hashtags: $('#hashtags').value.split(/\s+/).filter(Boolean)}), 500));
  $('#keywords').addEventListener('input', debounce(() => { P.keywords = $('#keywords').value.split(',').map(s => s.trim()).filter(Boolean); editOther({keywords: P.keywords}); paintWords(); }, 500));
  $('#copyPost').addEventListener('click', async () => {
    const text = ($('#caption').value + '\n\n' + $('#hashtags').value).trim();
    try { await navigator.clipboard.writeText(text); $('#copyPost').textContent = '✓ Đã sao chép'; }
    catch (e) { $('#caption').select(); document.execCommand('copy'); $('#copyPost').textContent = '✓ Đã sao chép'; }
    setTimeout(() => $('#copyPost').textContent = '📋 Sao chép caption + hashtag', 1800);
  });
  $('#shorts').addEventListener('change', e => { const k = e.target.dataset.short; if (k != null) { P.shorts[+k].on = e.target.checked; editOther({shorts: {[k]: e.target.checked}}); } });
  $('#shorts').addEventListener('click', e => { const b = e.target.closest('[data-play]'); if (b) { e.preventDefault(); if (view === 'edited') setView('raw'); const p = $('#player'); p.currentTime = +b.dataset.play; p.play().catch(() => {}); } });
}

async function init() {
  wire();
  const st = await api('state');
  await loadProject();
  if (st.job && st.job.running) poll();
  requestAnimationFrame(followPlayer);
}
init();
