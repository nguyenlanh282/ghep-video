'use strict';
// "Dự án": everything worked on is kept automatically; this list opens a saved edit again (both modes).
(() => {
  const TOKEN = new URLSearchParams(location.search).get('t') || '';
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const call = async (name, body = {}) => (await fetch('/api/' + name, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': TOKEN}, body: JSON.stringify(body)})).json();
  const dlg = document.createElement('dialog'); dlg.className = 'projdlg'; dlg.setAttribute('aria-labelledby', 'projTitle');
  dlg.innerHTML = `<div class="row between"><h2 id="projTitle">📂 Dự án đã làm</h2><button class="btn small" data-close>Đóng</button></div>
    <p class="hint">Mọi video bạn làm đều được tự lưu (bản chữ, chỗ cắt, timeline, cài đặt). Bấm “Mở” để sửa tiếp.</p><div class="projlist"></div>`;
  document.body.appendChild(dlg);
  const list = dlg.querySelector('.projlist');
  function paint(items) {
    list.innerHTML = items.length ? items.map(p => `<div class="proj ${p.active ? 'on' : ''}" data-kind="${p.kind}" data-id="${esc(p.id)}">
        <span class="ptag ${p.kind}">${p.kind === 'talk' ? '✂ Video chia sẻ' : '🎬 Ghép ảnh'}</span>
        <div class="pinfo"><b>${esc(p.name)}</b><small>${esc(p.detail)} · ${p.kind === 'talk' ? p.shots + ' video' : p.shots ? p.shots + ' cảnh' : 'chưa có timeline'} · ${esc(p.updated || '')}${p.exported ? ' · đã xuất' : ''}${p.missing ? ' · <b class="warn">thiếu file gốc</b>' : ''}</small></div>
        <button class="btn small primary" data-do="open" ${p.missing ? 'disabled' : ''}>${p.active ? 'Đang mở' : 'Mở'}</button><button class="btn small" data-do="rename">Đổi tên</button><button class="btn small" data-do="delete" aria-label="Xoá dự án ${esc(p.name)}">🗑</button></div>`).join('')
      : '<p class="hint">Chưa có dự án nào. Dự án được tạo khi bạn lên timeline, dựng thử, xuất hoặc phân tích video.</p>';
  }
  const load = async () => paint((await call('projects')).projects || []);
  dlg.addEventListener('click', async e => {
    if (e.target.closest('[data-close]') || e.target === dlg) return dlg.close();
    const b = e.target.closest('[data-do]'); if (!b) return; const row = b.closest('.proj'), kind = row.dataset.kind, id = row.dataset.id, name = row.querySelector('b').textContent;
    if (b.dataset.do === 'open') {
      const out = await call('projectOpen', {kind, id}); if (out.error) return alert(out.error);
      const page = kind === 'talk' ? 'talk.html' : 'index.html'; location.href = `${page}?t=${TOKEN}`;
    }
    if (b.dataset.do === 'rename') { const n = prompt('Tên dự án:', name); if (n && n.trim()) paint((await call('projectRename', {kind, id, name: n.trim()})).projects || []); }
    if (b.dataset.do === 'delete') { if (confirm(`Xoá dự án “${name}”?\nChỉ xoá bản edit đã lưu (bản chữ, timeline, lựa chọn). Video gốc và video đã xuất không bị xoá.`)) paint((await call('projectDelete', {kind, id})).projects || []); }
  });
  document.addEventListener('click', e => { if (e.target.closest('#projBtn')) { load(); dlg.showModal(); } });
})();
