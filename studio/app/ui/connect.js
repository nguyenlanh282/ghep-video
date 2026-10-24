'use strict';
// "🔌 Kết nối AI": how to let Claude (Claude Code / Claude Desktop) drive this app through its MCP server.
(() => {
  const TOKEN = new URLSearchParams(location.search).get('t') || '';
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const call = async (name, body = {}) => (await fetch('/api/' + name, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': TOKEN}, body: JSON.stringify(body)})).json();
  const head = document.querySelector('#projBtn'); if (!head) return;
  const btn = document.createElement('button'); btn.className = 'btn small'; btn.id = 'mcpBtn'; btn.title = 'Cho Claude điều khiển app này'; btn.textContent = '🔌 Kết nối AI';
  head.before(btn);
  const dlg = document.createElement('dialog'); dlg.className = 'projdlg mcpdlg'; dlg.setAttribute('aria-labelledby', 'mcpTitle'); document.body.appendChild(dlg);
  const block = (label, text, id) => `<h3>${label}</h3><div class="mcpcode"><pre id="${id}">${esc(text)}</pre><button class="btn small" data-copy="${id}">Sao chép</button></div>`;
  btn.addEventListener('click', async () => {
    const m = await call('mcpInfo');
    dlg.innerHTML = `<div class="row between"><h2 id="mcpTitle">🔌 Kết nối AI với Ghép Video</h2><button class="btn small" data-close>Đóng</button></div>
      <p class="hint">Sau khi kết nối, bạn nói với Claude bằng lời thường, vd “dựng video ghép ảnh với file lời đọc này, khung 16:9”, “cắt câu thứ hai trong video chia sẻ”, “viết kịch bản quảng cáo cho sản phẩm X rồi xuất 2 hook”. App phải đang mở. API key không bao giờ đi qua Claude.</p>
      ${block('Claude Code: dán lệnh này vào Terminal (1 lần)', m.code, 'mcpCode')}
      ${block('Claude Desktop: thêm vào file cấu hình rồi mở lại Claude', m.desktop, 'mcpDesk')}
      <p class="hint">File cấu hình Claude Desktop: <code>${esc(m.desktopFile)}</code> (Claude Desktop → Settings → Developer → Edit Config). File đã có “mcpServers” thì chỉ thêm phần “ghep-video”.</p>`;
    dlg.showModal();
  });
  dlg.addEventListener('click', async e => {
    if (e.target.closest('[data-close]') || e.target === dlg) return dlg.close();
    const c = e.target.closest('[data-copy]'); if (!c) return;
    try { await navigator.clipboard.writeText(document.getElementById(c.dataset.copy).textContent); c.textContent = 'Đã chép ✓'; } catch (err) { c.textContent = 'Bôi đen để chép'; }
    setTimeout(() => c.textContent = 'Sao chép', 1500);
  });
})();
