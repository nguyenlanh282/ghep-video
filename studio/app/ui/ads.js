'use strict';
// Video quảng cáo: product brief → script (hooks, parts, call to action) → one video per chosen hook.
// The script lives in the backend (settings.adScript); the editor sends it back with adSave.
const TOKEN = new URLSearchParams(location.search).get('t') || '';
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const base = p => p ? p.split(/[\\/]/).pop() : '';
const count = t => (String(t || '').trim().match(/\S+/g) || []).length;
const clock = s => { s = Math.round(s); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
let S = null, A = null, script = null, shown = '';

async function api(name, body = {}) {
  const r = await fetch('/api/' + name, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': TOKEN}, body: JSON.stringify(body)});
  const out = await r.json();
  if (out && out.settings) renderState(out);
  if (out && out.meta) renderAds(out);
  return out;
}
const set = values => api('set', {values});
const picked = () => (S.settings.adHooks || '').split(',').filter(x => /^\d+$/.test(x)).map(Number);

/* ---------- app state: settings, job ---------- */
function renderState(st) {
  const prev = S && S.job; S = st; const s = st.settings, job = st.job;
  $$('[data-text]').forEach(el => { if (document.activeElement !== el && !el.dataset.dirty) el.value = s[el.dataset.text] ?? ''; });
  $$('[data-seg]').forEach(seg => $$('button', seg).forEach(b => b.classList.toggle('on', s[seg.dataset.seg] === b.dataset.value)));
  $$('[data-path]').forEach(el => { const p = s[el.dataset.path]; el.textContent = p ? base(p) : el.dataset.empty; el.closest('button').title = p || ''; });
  $$('#adTypes button').forEach(b => { b.classList.toggle('on', b.dataset.type === s.adType); b.setAttribute('aria-checked', b.dataset.type === s.adType); });
  const tts = s.adVoiceSource === 'minimax'; $('#voiceTts').hidden = !tts; $('#voiceFile').hidden = tts;
  $('#keyNote').textContent = s.minimaxKeySet ? `Đã có API key MiniMax (${s.minimaxKeyHint}). Mỗi phần chỉ tạo giọng một lần, các bản khác hook dùng chung phần thân.`
    : 'Chưa có API key MiniMax: dán key ở trang “Ghép ảnh + lời đọc” → “Tạo giọng MiniMax”.';
  $('#aiNote').textContent = st.ai.ready ? `AI viết: ${st.ai.used === 'codex' ? 'ChatGPT' : 'Claude'}` : 'Chưa có AI (Claude / ChatGPT): dùng “Tự viết theo khung”.';
  $('#aiWrite').disabled = !st.ai.ready;
  $('#ratio').textContent = s.adAspect;
  $('#progress').hidden = !job.running; $('#progress').value = job.progress;
  $('#status').textContent = job.error ? 'Cần kiểm tra lại' : job.status || 'Sẵn sàng';
  $('#substatus').textContent = job.running ? `${Math.round(job.progress * 100)}% · Bạn có thể dừng bất cứ lúc nào` : 'Thông tin sản phẩm → kịch bản → video quảng cáo theo từng hook';
  $('#actions').hidden = job.running; $('#cancelBtn').hidden = !job.running || !['ad-script', 'ad-render'].includes(job.task);
  $('#error').hidden = !job.error; $('#errorText').textContent = job.error || '';
  // A finished task: fetch the new script / the new videos.
  if (prev && prev.running && !job.running && ['ad-script', 'ad-render'].includes(job.task)) { shown = ''; api('adState'); }
  if (A) paintNotes();
}

/* ---------- ad state: kinds, script, results ---------- */
function renderAds(a) {
  A = a;
  if (!$('#adTypes').children.length) {
    $('#adTypes').innerHTML = a.meta.types.map(t => `<button role="radio" data-type="${t.id}" title="${esc(t.parts.join(' → '))}"><b>${esc(t.name)}</b><small>${esc(t.when)}</small></button>`).join('');
    if (S) renderState(S);
  }
  const key = JSON.stringify(a.script);
  if (key !== shown && !document.activeElement.closest('#scriptBox')) { shown = key; script = a.script ? JSON.parse(key) : null; paintScript(); }
  paintNotes(); paintResults();
}

function paintNotes() {
  $('#mediaNote').textContent = A.mediaCount ? `${A.mediaCount} ảnh/video${A.analysed ? ' · đã phân tích nội dung' : ' · chưa phân tích: app tự phân tích khi xuất để chọn cảnh đúng lời đọc'}` : 'Thư mục chưa có ảnh/video.';
  if (!script) return;
  const sel = picked().filter(i => script.hooks[i]), first = script.hooks[sel[0] ?? 0] || {loi: ''};
  const words = count(first.loi) + script.phan.reduce((n, p) => n + count(p.loi), 0) + count(script.cta.loi), secs = Math.round(words / rate());
  $('#lenNote').textContent = `${words} chữ ≈ ${secs} giây đọc (mục tiêu ${script.giay} giây)`;
  $('#lenNote').classList.toggle('warn', secs > script.giay * 1.2);
  $('#exportBtn').textContent = `Xuất ${Math.max(1, Math.min(3, sel.length))} video quảng cáo ↗`;
}

function paintScript() {
  $('#scriptBox').hidden = !script; $('#noScript').hidden = !!script;
  if (!script) return;
  const sel = picked();
  $('#hooks').innerHTML = script.hooks.map((h, i) => `<div class="hook ${sel.includes(i) ? 'on' : ''}" data-i="${i}">
      <label class="hpick"><input type="checkbox" ${sel.includes(i) ? 'checked' : ''} aria-label="Xuất video với hook ${i + 1}"><b>${'ABCDEF'[i]}</b></label>
      <div class="hbody">${h.kieu ? `<span class="htag">${esc(h.kieu)}</span>` : ''}
        <input type="text" data-f="loi" value="${esc(h.loi)}" placeholder="Câu nói mở đầu (dưới 14 chữ)" aria-label="Câu nói của hook ${i + 1}">
        <input type="text" data-f="chu" value="${esc(h.chu)}" placeholder="Chữ trên màn hình" aria-label="Chữ trên màn hình của hook ${i + 1}">
        ${h.hinh ? `<small class="hint">🎬 ${esc(h.hinh)}</small>` : ''}</div>
      <button class="x" data-del aria-label="Xoá hook ${i + 1}">✕</button></div>`).join('');
  const row = (p, i) => `<div class="part" data-i="${i}">
      <div class="row between"><input type="text" class="vai" data-f="vai" value="${esc(p.vai)}" aria-label="Tên phần ${i + 1}"><span class="row gap"><small class="hint pcount"></small><button class="x" data-del aria-label="Xoá phần ${i + 1}">✕</button></span></div>
      ${p.hinh ? `<small class="hint">🎬 ${esc(p.hinh)}</small>` : ''}
      <textarea data-f="loi" rows="2" placeholder="Lời đọc" aria-label="Lời đọc phần ${i + 1}">${esc(p.loi)}</textarea>
      <input type="text" data-f="chu" value="${esc(p.chu)}" placeholder="Chữ trên màn hình (dưới 8 chữ)" aria-label="Chữ trên màn hình phần ${i + 1}"></div>`;
  $('#parts').innerHTML = script.phan.map(row).join('');
  $('#cta').innerHTML = `${script.cta.hinh ? `<small class="hint">🎬 ${esc(script.cta.hinh)}</small>` : ''}
    <textarea data-f="loi" rows="2" placeholder="Lời kêu gọi cuối video" aria-label="Lời kêu gọi">${esc(script.cta.loi)}</textarea>
    <input type="text" data-f="chu" value="${esc(script.cta.chu)}" placeholder="Chữ trên nút (vd: Nhắn Zalo 08xx)" aria-label="Chữ trên nút kêu gọi">`;
  $('#warns').hidden = !script.luu_y.length;
  $('#warns').innerHTML = `<b>Cần bạn kiểm tra</b><ul>${script.luu_y.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
  $('#caption').value = script.caption; $('#hashtags').value = script.hashtags.join(' ');
  $('#srcNote').textContent = (script.nguon || []).length ? 'AI đã đọc: ' + script.nguon.join(' · ') : '';
  counts();
}
const counts = () => $$('#parts .part').forEach(el => { $('.pcount', el).textContent = count($('[data-f=loi]', el).value) + ' chữ'; });

const save = debounce(async () => { shown = JSON.stringify(script); const out = await api('adSave', {script}); shown = JSON.stringify(out.script); }, 500);
function edited(e) {
  const f = e.target.dataset.f; if (!f) return;
  const hook = e.target.closest('.hook'), part = e.target.closest('#parts .part'), cta = e.target.closest('#cta');
  if (hook) script.hooks[+hook.dataset.i][f] = e.target.value;
  else if (part) script.phan[+part.dataset.i][f] = e.target.value;
  else if (cta) script.cta[f] = e.target.value;
  counts(); paintNotes(); save();
}

// Words per second at the chosen energy (a livelier voice reads faster).
const rate = () => A.wordsPerSecond * ((A.meta.energy.find(e => e.id === S.settings.adEnergy) || {speed: 1}).speed);

/* ---------- the whole script of each version, to read before exporting ---------- */
let fullTab = 0;
function fullRows(h) {
  const rows = [{vai: 'Hook', ...script.hooks[h]}, ...script.phan.filter(p => p.loi.trim()), ...(script.cta.loi.trim() ? [{vai: 'Kêu gọi', ...script.cta}] : [])];
  let t = 0;
  return rows.map(r => { const d = count(r.loi) / rate(), row = {...r, from: t, to: t + d}; t += d; return row; });
}
function fullPicks() { const sel = picked().filter(i => script.hooks[i]).slice(0, 3); return sel.length ? sel : [0]; }
function paintFull() {
  const sel = fullPicks(); fullTab = Math.min(fullTab, sel.length - 1);
  $('#fullTabs').innerHTML = sel.length > 1 ? sel.map((h, k) => `<button data-k="${k}" class="${k === fullTab ? 'on' : ''}">Bản ${'ABC'[k]}</button>`).join('') : '';
  const rows = fullRows(sel[fullTab]), total = rows.length ? rows[rows.length - 1].to : 0, type = A.meta.types.find(t => t.id === script.kieu), energy = A.meta.energy.find(e => e.id === S.settings.adEnergy);
  $('#fullInfo').textContent = `${S.settings.adProduct} · ${type ? type.name : ''} · giọng ${energy ? energy.name.toLowerCase() : ''} · khoảng ${Math.round(total)} giây (mục tiêu ${script.giay} giây) · khung ${S.settings.adAspect}. Thời gian là ước tính theo số chữ.`;
  $('#fullBody').innerHTML = `<table class="fulltable"><thead><tr><th>Giây</th><th>Phần</th><th>Hình</th><th>Lời đọc</th><th>Chữ trên màn hình</th></tr></thead><tbody>${rows.map(r =>
      `<tr><td>${clock(r.from)}–${clock(r.to)}</td><td><b>${esc(r.vai)}</b></td><td>${esc(r.hinh || '')}</td><td>${esc(r.loi)}</td><td><span class="chu">${esc(r.chu || '')}</span></td></tr>`).join('')}</tbody></table>
    <p class="fullread"><b>Lời đọc liền mạch:</b> ${esc(rows.map(r => r.loi).join(' '))}</p>
    ${script.luu_y.length ? `<div class="warns"><b>Cần bạn kiểm tra</b><ul>${script.luu_y.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
    ${script.caption ? `<p class="fullread"><b>Lời mô tả khi đăng:</b> ${esc(script.caption)} ${esc(script.hashtags.join(' '))}</p>` : ''}`;
}
const fullText = () => fullPicks().map((h, k) => `BẢN ${'ABC'[k]}\n` + fullRows(h).map(r => `[${clock(r.from)}–${clock(r.to)}] ${r.vai}\n  Hình: ${r.hinh || ''}\n  Lời: ${r.loi}\n  Chữ: ${r.chu || ''}`).join('\n')).join('\n\n')
  + (script.caption ? `\n\nLỜI MÔ TẢ\n${script.caption}\n${script.hashtags.join(' ')}` : '');

function paintResults() {
  const r = A.results || [];
  $('#resultRow').hidden = !r.length;
  $('#results').innerHTML = r.map((x, i) => `<button class="adres" data-i="${i}"><b>${esc(x.label)}</b><small>${esc(x.hook)}</small></button>`).join('');
  if (r.length && !$('#player').dataset.src) play(0);
}
function play(i) {
  const r = A.results[i]; if (!r) return; const p = $('#player');
  p.src = r.url; p.dataset.src = r.path; $$('#results .adres').forEach((b, k) => b.classList.toggle('on', k === i)); p.play().catch(() => {});
}

async function poll() {
  for (;;) { const st = await api('state'); if (!st.job.running) break; await new Promise(r => setTimeout(r, 600)); }
}
async function start(task, preview = false) {
  await flush(); $('#player').dataset.src = '';
  const out = await api('start', {task, preview}); if (out.job && out.job.running) poll();
}
// Text typed in the brief and the script reaches the backend before a task starts.
async function flush() {
  const dirty = $$('[data-text]').filter(el => el.dataset.dirty);
  if (dirty.length) { await set(Object.fromEntries(dirty.map(el => [el.dataset.text, el.value]))); dirty.forEach(el => delete el.dataset.dirty); }
  if (script) { const out = await api('adSave', {script}); shown = JSON.stringify(out.script); }
}

async function boot() {
  $$('[data-mode-link]').forEach(a => a.href = `${a.dataset.modeLink}?t=${TOKEN}`);
  $$('[data-path]').forEach(el => el.dataset.empty = el.textContent);
  $$('[data-text]').forEach(el => {
    const send = debounce(async () => { await set({[el.dataset.text]: el.value}); delete el.dataset.dirty; }, 500);
    el.addEventListener('input', () => { el.dataset.dirty = '1'; send(); });
  });
  $$('[data-seg]').forEach(seg => seg.addEventListener('click', e => { const b = e.target.closest('button[data-value]'); if (b) set({[seg.dataset.seg]: b.dataset.value}); }));
  $$('[data-choose]').forEach(b => b.addEventListener('click', async () => {
    const out = await api('choose', {kind: b.dataset.choose});
    if (out.error) { const key = $('[data-path]', b).dataset.path, path = prompt('Dán đường dẫn đầy đủ:', S.settings[key] || ''); if (path) await set({[key]: path.trim()}); }
    api('adState');
  }));
  $('#kbClear').addEventListener('click', e => { e.preventDefault(); set({adKnowledgeFolder: ''}); });
  $('#adTypes').addEventListener('click', e => { const b = e.target.closest('button[data-type]'); if (b) set({adType: b.dataset.type}); });
  $('#aiWrite').addEventListener('click', () => { if (!script || confirm('AI viết lại sẽ thay kịch bản hiện tại. Tiếp tục?')) start('ad-script'); });
  $('#handWrite').addEventListener('click', async () => { if (script && !confirm('Tạo khung mới sẽ thay kịch bản hiện tại. Tiếp tục?')) return; await flush(); shown = ''; await api('adSkeleton'); });
  $('#scriptBox').addEventListener('input', edited);
  $('#scriptBox').addEventListener('change', e => {
    const hook = e.target.closest('.hook');
    if (hook && e.target.type === 'checkbox') {
      let sel = picked().filter(i => i !== +hook.dataset.i); if (e.target.checked) sel.push(+hook.dataset.i);
      if (sel.length > 3) { e.target.checked = false; alert('Mỗi lần xuất tối đa 3 hook.'); return; }
      hook.classList.toggle('on', e.target.checked); set({adHooks: sel.sort((a, b) => a - b).join(',')});
    }
  });
  $('#scriptBox').addEventListener('click', e => {
    if (!e.target.closest('[data-del]')) return;
    const hook = e.target.closest('.hook'), part = e.target.closest('#parts .part');
    if (hook) { const i = +hook.dataset.i; script.hooks.splice(i, 1); set({adHooks: picked().filter(x => x !== i).map(x => x > i ? x - 1 : x).join(',')}); }
    else if (part) script.phan.splice(+part.dataset.i, 1);
    paintScript(); paintNotes(); save();
  });
  $('#addHook').addEventListener('click', () => { if (script.hooks.length >= 6) return alert('Tối đa 6 hook.'); script.hooks.push({loi: '', chu: '', hinh: '', kieu: ''}); paintScript(); save(); });
  $('#addPart').addEventListener('click', () => { if (script.phan.length >= 8) return alert('Tối đa 8 phần.'); script.phan.push({vai: 'Phần mới', hinh: '', loi: '', chu: ''}); paintScript(); save(); });
  $('#caption').addEventListener('input', () => { script.caption = $('#caption').value; save(); });
  $('#hashtags').addEventListener('input', () => { script.hashtags = $('#hashtags').value.split(/\s+/).filter(Boolean); save(); });
  $$('[data-full]').forEach(b => b.addEventListener('click', async () => { if (!script) return alert('Chưa có kịch bản.'); await flush(); fullTab = 0; paintFull(); $('#fullDlg').showModal(); }));
  $('#fullTabs').addEventListener('click', e => { const b = e.target.closest('button[data-k]'); if (b) { fullTab = +b.dataset.k; paintFull(); } });
  $('#fullClose').addEventListener('click', () => $('#fullDlg').close());
  $('#fullCopy').addEventListener('click', async () => { try { await navigator.clipboard.writeText(fullText()); $('#fullCopy').textContent = 'Đã chép ✓'; } catch (e) { $('#fullCopy').textContent = 'Không chép được'; } setTimeout(() => $('#fullCopy').textContent = 'Sao chép', 1500); });
  $('#fullExport').addEventListener('click', () => { $('#fullDlg').close(); start('ad-render'); });
  $('#results').addEventListener('click', e => { const b = e.target.closest('.adres'); if (b) play(+b.dataset.i); });
  $('#previewBtn').addEventListener('click', () => start('ad-render', true));
  $('#exportBtn').addEventListener('click', () => start('ad-render'));
  $('#cancelBtn').addEventListener('click', () => api('cancel'));
  $('#revealBtn').addEventListener('click', () => api('reveal'));
  $('#errorClose').addEventListener('click', () => api('clearError'));
  const st = await api('state'); await api('adState');
  if (st.job.running) poll();
}
boot();
