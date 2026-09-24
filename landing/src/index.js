// Ghép Video landing page backend (Cloudflare Worker + D1).
//   POST /api/lead        save the download form, set a 24 h download cookie
//   GET  /d/<kind>        send a visitor who filled the form to the latest installer on GitHub Releases
//   GET  /admin           password-protected list of leads;  /admin/leads.csv  Excel-friendly export
// Static files (the page itself) come from ./public.

const REPO = 'nguyenlanh282/ghep-video';
// Installer files of the latest GitHub release, matched by name.
const KINDS = {
  windows: /^GhepVideo-Setup-.*\.exe$/,
  mac: /^GhepVideo-.*\.pkg$/,
  'windows-script': /^Cai-dat-Ghep-Video-Windows\.bat$/,
  'mac-script': /^Cai-dat-Ghep-Video-Mac\.command$/,
};
const COOKIE = 'gv_dl';
const DAY = 86400;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    try {
      if (url.pathname === '/api/lead' && request.method === 'POST') return await saveLead(request, env);
      if (url.pathname.startsWith('/d/')) return await download(request, env, ctx, url.pathname.slice(3));
      if (url.pathname === '/admin' || url.pathname === '/admin/leads.csv') return await admin(request, env, url.pathname.endsWith('.csv'));
      return env.ASSETS.fetch(request);
    } catch (err) {
      console.error(err);
      return json({ ok: false, error: 'Có lỗi máy chủ, vui lòng thử lại sau ít phút.' }, 500);
    }
  },
};

// ---------------- form ----------------

async function saveLead(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: 'Dữ liệu không hợp lệ.' }, 400); }
  // Honeypot: a hidden field real people never fill.
  if (body.website) return json({ ok: true, token: 'x' });

  const name = clean(body.name, 80);
  const phone = normalisePhone(body.phone);
  const email = clean(body.email, 120).toLowerCase();
  const purpose = clean(body.purpose, 200);
  const os = ['windows', 'mac', 'other'].includes(body.os) ? body.os : 'other';
  const errors = {};
  if (name.length < 2) errors.name = 'Vui lòng nhập họ tên.';
  if (!phone) errors.phone = 'Số điện thoại / Zalo chưa đúng (vd 0912 345 678).';
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) errors.email = 'Email chưa đúng.';
  if (!purpose) errors.purpose = 'Vui lòng chọn hoặc ghi mục đích dùng.';
  if (Object.keys(errors).length) return json({ ok: false, errors }, 400);

  const ipHash = await sha256((request.headers.get('CF-Connecting-IP') || '') + env.SECRET);
  const recent = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM leads WHERE ip_hash = ? AND created_at > datetime('now', '-1 hour')"
  ).bind(ipHash).first();
  if (recent.n >= 8) return json({ ok: false, error: 'Bạn gửi quá nhiều lần. Vui lòng thử lại sau.' }, 429);

  // The same phone filling the form again updates its row instead of creating duplicates.
  const existing = await env.DB.prepare('SELECT id FROM leads WHERE phone = ? ORDER BY id DESC LIMIT 1').bind(phone).first();
  let id;
  if (existing) {
    id = existing.id;
    await env.DB.prepare("UPDATE leads SET name=?, email=?, purpose=?, os=?, ip_hash=?, user_agent=?, created_at=datetime('now') WHERE id=?")
      .bind(name, email || null, purpose, os, ipHash, clean(request.headers.get('User-Agent'), 300), id).run();
  } else {
    const r = await env.DB.prepare('INSERT INTO leads (name, phone, email, purpose, os, ip_hash, user_agent) VALUES (?,?,?,?,?,?,?)')
      .bind(name, phone, email || null, purpose, os, ipHash, clean(request.headers.get('User-Agent'), 300)).run();
    id = r.meta.last_row_id;
  }
  const token = await sign(env, `${id}.${Math.floor(Date.now() / 1000) + DAY}`);
  return json({ ok: true, token }, 200, { 'Set-Cookie': `${COOKIE}=${token}; Path=/; Max-Age=${DAY}; HttpOnly; Secure; SameSite=Lax` });
}

function clean(v, max) { return String(v ?? '').replace(/[\u0000-\u001f<>]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, max); }

function normalisePhone(v) {
  let d = String(v ?? '').replace(/[^\d+]/g, '');
  if (d.startsWith('+84')) d = '0' + d.slice(3); else if (d.startsWith('84') && d.length === 11) d = '0' + d.slice(2);
  return /^0[35789]\d{8}$/.test(d) ? d : '';
}

// ---------------- downloads ----------------

async function download(request, env, ctx, kind) {
  if (!KINDS[kind]) return new Response('Không có file này.', { status: 404 });
  const lead = await verify(env, cookie(request, COOKIE));
  if (!lead) return Response.redirect(new URL('/#tai-ve', request.url).toString(), 302);
  const asset = await latestAsset(ctx, KINDS[kind]);
  if (!asset) return new Response('Bản cài đặt đang được chuẩn bị. Vui lòng thử lại sau ít phút.', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  ctx.waitUntil(env.DB.prepare("UPDATE leads SET downloads = downloads + 1, last_download = ? WHERE id = ?").bind(`${kind} ${asset.name}`, lead).run());
  return Response.redirect(asset.url, 302);
}

async function latestAsset(ctx, pattern, fresh = false) {
  // Cached for 5 minutes so every download does not hit the GitHub API. A file missing from the cached list
  // (e.g. an installer attached after the list was cached) triggers one fresh lookup.
  const cacheKey = new Request('https://cache.ghepvideo/latest-release');
  let res = fresh ? null : await caches.default.match(cacheKey);
  if (!res) {
    const gh = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`, { headers: { 'User-Agent': 'ghepvideo-landing', Accept: 'application/vnd.github+json' } });
    if (!gh.ok) return null;
    res = new Response(await gh.text(), { headers: { 'Cache-Control': 'max-age=300', 'Content-Type': 'application/json' } });
    ctx.waitUntil(caches.default.put(cacheKey, res.clone()));
    fresh = true;
  }
  const release = await res.json();
  const a = (release.assets || []).find(x => pattern.test(x.name));
  if (!a && !fresh) return latestAsset(ctx, pattern, true);
  return a ? { name: a.name, url: a.browser_download_url } : null;
}

// ---------------- admin ----------------

async function admin(request, env, csv) {
  const auth = request.headers.get('Authorization') || '';
  const [user, pass] = auth.startsWith('Basic ') ? atob(auth.slice(6)).split(/:(.*)/s) : [];
  if (!env.ADMIN_PASSWORD || user !== 'admin' || !(await same(pass || '', env.ADMIN_PASSWORD))) {
    return new Response('Cần đăng nhập.', { status: 401, headers: { 'WWW-Authenticate': 'Basic realm="Ghep Video admin", charset="UTF-8"' } });
  }
  const { results } = await env.DB.prepare('SELECT id, created_at, name, phone, email, purpose, os, downloads, last_download FROM leads ORDER BY id DESC LIMIT 5000').all();
  if (csv) {
    const cols = ['id', 'created_at', 'name', 'phone', 'email', 'purpose', 'os', 'downloads', 'last_download'];
    const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const body = '﻿' + ['STT,Thời gian (UTC),Họ tên,Điện thoại,Email,Mục đích,Máy,Lượt tải,Tải gần nhất', ...results.map(r => cols.map(c => esc(r[c])).join(','))].join('\r\n');
    return new Response(body, { headers: { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="khach-ghep-video.csv"' } });
  }
  const h = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const rows = results.map(r => `<tr><td>${r.id}</td><td>${h(r.created_at)}</td><td>${h(r.name)}</td><td><a href="https://zalo.me/${h(r.phone)}">${h(r.phone)}</a></td><td>${h(r.email)}</td><td>${h(r.purpose)}</td><td>${h(r.os)}</td><td>${r.downloads}</td></tr>`).join('');
  return new Response(`<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Khách tải Ghép Video</title>
<style>body{font:14px system-ui,sans-serif;margin:24px;background:#0b0f14;color:#eef1f5}a{color:#baf25e}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #2a3140;padding:8px;text-align:left;vertical-align:top}th{color:#9ca8ba;font-weight:600}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.btn{background:#baf25e;color:#0b0f14;padding:8px 14px;border-radius:8px;text-decoration:none;font-weight:600}.wrap{overflow-x:auto}</style></head>
<body><div class="top"><h1>Khách tải Ghép Video · ${results.length}</h1><a class="btn" href="/admin/leads.csv">Tải file Excel (CSV)</a></div>
<div class="wrap"><table><tr><th>#</th><th>Thời gian (UTC)</th><th>Họ tên</th><th>Điện thoại / Zalo</th><th>Email</th><th>Mục đích</th><th>Máy</th><th>Lượt tải</th></tr>${rows || '<tr><td colspan="8">Chưa có ai điền form.</td></tr>'}</table></div></body></html>`,
    { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex' } });
}

// ---------------- helpers ----------------

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...headers } });
}
function cookie(request, name) {
  const m = (request.headers.get('Cookie') || '').match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`));
  return m ? m[1] : '';
}
async function sha256(text) {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
}
async function hmac(env, text) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const b = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(text));
  return btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
async function sign(env, payload) { return `${payload}.${await hmac(env, payload)}`; }
async function verify(env, token) {
  const [id, exp, mac] = String(token).split('.');
  if (!id || !exp || !mac || Number(exp) < Date.now() / 1000) return null;
  return (await same(mac, await hmac(env, `${id}.${exp}`))) ? Number(id) : null;
}
async function same(a, b) {
  // Constant-time comparison via hashing both sides.
  return (await sha256('c' + a)) === (await sha256('c' + b));
}
