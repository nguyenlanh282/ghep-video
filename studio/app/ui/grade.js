'use strict';
// Colour grading panel, shared by both pages: looks (built-in + saved), sliders, before/after preview on a frame of
// the user's own footage. The grade is one setting (JSON) used by both modes when exporting.
window.Grade = (() => {
  const SLIDERS = [
    ['Ánh sáng', [['exposure', 'Độ sáng'], ['contrast', 'Tương phản'], ['highlights', 'Vùng sáng'], ['shadows', 'Vùng tối']]],
    ['Màu', [['temperature', 'Nhiệt độ màu', 'Lạnh', 'Ấm'], ['tint', 'Sắc độ', 'Xanh lá', 'Hồng'], ['saturation', 'Độ bão hoà'], ['vibrance', 'Sống động']]],
    ['Hiệu ứng', [['split', 'Điện ảnh (xanh – cam)', 0], ['fade', 'Phim mờ', 0], ['vignette', 'Viền tối', 0], ['sharpen', 'Làm nét', 0], ['grain', 'Hạt phim', 0]]],
  ];
  let box, api, mode, G = {}, looks = [], presets = [], dragging = false, lastJson = null;
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  function build() {
    box.innerHTML = `
      <div class="gcompare" aria-label="Xem trước màu: trái là gốc, phải là sau khi chỉnh">
        <img class="gb" alt=""><div class="gaw"><img class="ga" alt=""></div><div class="gline"></div>
        <span class="gtag l">Gốc</span><span class="gtag r">Sau chỉnh</span>
        <input type="range" class="gsplit" min="0" max="100" value="50" aria-label="Kéo để so sánh trước và sau">
      </div>
      <p class="hint gsrc"></p>
      <div class="glooks" role="list"></div>
      ${SLIDERS.map(([title, rows]) => `<h4 class="gh">${title}</h4>` + rows.map(([k, label, lo, hi]) => {
        const min = lo === 0 ? 0 : -100;
        return `<div class="grow"><label for="g-${mode}-${k}">${label}</label><output id="go-${k}">0</output>
          <input type="range" id="g-${mode}-${k}" data-g="${k}" min="${min}" max="100" step="1" value="0">
          ${typeof lo === 'string' ? `<div class="gends"><span>${lo}</span><span>${hi}</span></div>` : ''}</div>`;
      }).join('')).join('')}
      <label class="switch"><input type="checkbox" data-gbw><span></span>Trắng đen</label>
      <div class="row gap gact">
        <button class="btn small primary" data-gact="save">💾 Lưu thành mẫu</button>
        <button class="btn small" data-gact="reset">↺ Đặt lại</button>
      </div>`;
    const cmp = box.querySelector('.gcompare');
    box.querySelector('.gsplit').addEventListener('input', e => cmp.style.setProperty('--split', e.target.value + '%'));
    box.addEventListener('input', e => {
      const k = e.target.dataset.g; if (!k) return;
      dragging = true; G[k] = +e.target.value / 100; G.look = ''; paint(); save();
    });
    box.addEventListener('change', e => {
      if (e.target.dataset.g) dragging = false;
      if (e.target.matches('[data-gbw]')) { G.bw = e.target.checked ? 1 : 0; G.look = ''; paint(); save(); }
    });
    box.addEventListener('click', async e => {
      const lk = e.target.closest('[data-look]'), del = e.target.closest('[data-gdel]'), act = e.target.closest('[data-gact]');
      if (del) { e.stopPropagation(); if (confirm(`Xoá mẫu màu “${del.dataset.gdel}”?`)) await api('gradeDelete', {name: del.dataset.gdel}); return; }
      if (lk) {
        const src = lk.dataset.look.startsWith('mau:') ? presets.find(p => 'mau:' + p.name === lk.dataset.look)?.grade : looks.find(l => l.id === lk.dataset.look)?.grade;
        G = {...(src || {}), look: lk.dataset.look}; paint(); save(true); return;
      }
      if (act && act.dataset.gact === 'reset') { G = {look: 'goc'}; paint(); save(true); }
      if (act && act.dataset.gact === 'save') {
        const name = prompt('Tên mẫu màu (vd: Vườn sầu riêng, Quay trong nhà):', '');
        if (name && name.trim()) { const out = await api('gradeSave', {name: name.trim()}); if (out.error) alert(out.error); }
      }
    });
  }

  function paint() {
    box.querySelectorAll('[data-g]').forEach(r => {
      const v = Math.round((G[r.dataset.g] || 0) * 100);
      if (document.activeElement !== r) r.value = v;
      box.querySelector('#go-' + r.dataset.g).textContent = (v > 0 && +r.min < 0 ? '+' : '') + v;
    });
    box.querySelector('[data-gbw]').checked = (G.bw || 0) >= .5;
    box.querySelector('.glooks').innerHTML = looks.map(l => `<button role="listitem" class="glook ${G.look === l.id ? 'on' : ''}" data-look="${l.id}">${esc(l.name)}</button>`).join('')
      + presets.map(p => `<button role="listitem" class="glook mine ${G.look === 'mau:' + p.name ? 'on' : ''}" data-look="mau:${esc(p.name)}">★ ${esc(p.name)}<span class="gdel" data-gdel="${esc(p.name)}" title="Xoá mẫu" aria-label="Xoá mẫu ${esc(p.name)}">✕</span></button>`).join('');
  }

  const refresh = debounce(async () => {
    const out = await api('gradePreview', {mode});
    if (out.error) { box.querySelector('.gsrc').textContent = out.error; return; }
    const b = box.querySelector('.gb'), a = box.querySelector('.ga');
    if (b.dataset.src !== out.before) { b.src = out.before; b.dataset.src = out.before; }
    a.src = out.after; box.querySelector('.gsrc').textContent = 'Xem thử trên: ' + out.source + ' · kéo thanh giữa ảnh để so sánh';
  }, 250);
  const persist = debounce(() => api('set', {values: {grade: JSON.stringify(G)}}).then(refresh), 200);
  function save(now) { lastJson = JSON.stringify(G); if (now) { api('set', {values: {grade: lastJson}}).then(refresh); } else persist(); }

  return {
    init(el, apiFn) { box = el; api = apiFn; mode = el.dataset.mode || 'story'; build(); },
    update(st) {
      if (!box) return;
      looks = (st.grade && st.grade.looks) || looks; presets = (st.grade && st.grade.presets) || [];
      const json = st.settings.grade || '{}';
      if (!dragging && json !== lastJson) { try { G = JSON.parse(json) || {}; } catch (e) { G = {}; } lastJson = json; if (!G.look && !Object.keys(G).length) G.look = 'goc'; refresh(); }
      paint();
    },
    refresh,
  };
})();
