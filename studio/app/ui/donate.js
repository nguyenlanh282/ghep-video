'use strict';
// "Ủng hộ tuỳ tâm" card, shown after a video is exported. Hidden again for this session with ✕.
window.Donate = {
  show(on) {
    const el = document.getElementById('donate'); if (!el) return;
    let closed = false; try { closed = sessionStorage.getItem('gv_donate_closed') === '1'; } catch (e) {}
    el.hidden = !on || closed;
  },
};
document.addEventListener('click', e => {
  if (e.target.closest('[data-dclose]')) { document.getElementById('donate').hidden = true; try { sessionStorage.setItem('gv_donate_closed', '1'); } catch (x) {} }
  const c = e.target.closest('[data-dcopy]');
  if (c) navigator.clipboard.writeText(c.dataset.dcopy).then(() => { c.textContent = 'Đã chép ✓'; setTimeout(() => { c.textContent = 'Sao chép STK'; }, 1500); }).catch(() => {});
});
