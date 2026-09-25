// Ghép Video landing page backend (Cloudflare Worker + D1).
//   POST /api/lead        save the sign-up form and answer with the Zalo group link
//   GET  /d/<kind>        old download links: back to the sign-up form (the software is shared in the Zalo group)
//   GET  /admin           password-protected list of leads;  /admin/leads.csv  Excel-friendly export
//   POST /admin/sync-lark push leads not yet in Lark Base (every new lead is also pushed right after the form)
// Static files (the page itself) come from ./public.

import { larkReady, pushLead, pushMany, ROLES } from './lark.js';

const COOKIE = 'gv_dl';
const DAY = 86400;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    try {
      if (url.pathname === '/api/lead' && request.method === 'POST') return await saveLead(request, env, ctx);
      if (url.pathname === '/admin/sync-lark' && request.method === 'POST') return await syncLark(request, env);
      // Downloads are no longer offered on the page: the software is shared inside the Zalo group.
      if (url.pathname.startsWith('/d/')) return Response.redirect(new URL('/#dang-ky', request.url).toString(), 302);
      if (url.pathname === '/admin' || url.pathname === '/admin/leads.csv') return await admin(request, env, url.pathname.endsWith('.csv'), url);
      return env.ASSETS.fetch(request);
    } catch (err) {
      console.error(err);
      return json({ ok: false, error: 'Có lỗi máy chủ, vui lòng thử lại sau ít phút.' }, 500);
    }
  },
  // Every 15 minutes: push leads that are not in Lark yet (older sign-ups, or a push that failed).
  async scheduled(event, env, ctx) { if (larkReady(env)) ctx.waitUntil(syncPending(env).catch(e => console.error('lark cron', e.message))); },
};

// ---------------- form ----------------

async function saveLead(request, env, ctx) {
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: 'Dữ liệu không hợp lệ.' }, 400); }
  // Honeypot: a hidden field real people never fill.
  if (body.website) return json({ ok: true, token: 'x', zalo: '' });

  const name = clean(body.name, 80);
  const phone = normalisePhone(body.phone);
  const email = clean(body.email, 120).toLowerCase();
  const purpose = ROLES.includes(body.purpose) ? body.purpose : '';
  const os = ['windows', 'mac', 'both', 'unknown'].includes(body.os) ? body.os : 'unknown';
  const niche = clean(body.niche, 200);
  const errors = {};
  if (name.length < 2) errors.name = 'Vui lòng nhập họ tên.';
  if (!phone) errors.phone = 'Số điện thoại / Zalo chưa đúng (vd 0912 345 678).';
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) errors.email = 'Email chưa đúng.';
  if (!purpose) errors.purpose = 'Vui lòng chọn bạn đang là ai.';
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
    await env.DB.prepare("UPDATE leads SET name=?, email=?, purpose=?, os=?, niche=?, ip_hash=?, user_agent=?, created_at=datetime('now') WHERE id=?")
      .bind(name, email || null, purpose, os, niche || null, ipHash, clean(request.headers.get('User-Agent'), 300), id).run();
  } else {
    const r = await env.DB.prepare('INSERT INTO leads (name, phone, email, purpose, os, niche, ip_hash, user_agent) VALUES (?,?,?,?,?,?,?,?)')
      .bind(name, phone, email || null, purpose, os, niche || null, ipHash, clean(request.headers.get('User-Agent'), 300)).run();
    id = r.meta.last_row_id;
  }
  ctx.waitUntil(syncOne(env, id));  // to Lark Base, after the answer is sent
  const token = await sign(env, `${id}.${Math.floor(Date.now() / 1000) + DAY}`);
  // Invite to the Zalo group (set ZALO_GROUP in wrangler.jsonc vars); shown only after the form is filled.
  const zalo = /^https:\/\/zalo\.me\//.test(env.ZALO_GROUP || '') ? env.ZALO_GROUP : '';
  return json({ ok: true, token, zalo }, 200, { 'Set-Cookie': `${COOKIE}=${token}; Path=/; Max-Age=${DAY}; HttpOnly; Secure; SameSite=Lax` });
}

function clean(v, max) { return String(v ?? '').replace(/[\u0000-\u001f<>]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, max); }

function normalisePhone(v) {
  let d = String(v ?? '').replace(/[^\d+]/g, '');
  if (d.startsWith('+84')) d = '0' + d.slice(3); else if (d.startsWith('84') && d.length === 11) d = '0' + d.slice(2);
  return /^0[35789]\d{8}$/.test(d) ? d : '';
}

// ---------------- Lark Base ----------------

async function syncOne(env, id) {
  if (!larkReady(env)) return;
  const lead = await env.DB.prepare('SELECT * FROM leads WHERE id = ?').bind(id).first();
  try {
    const rec = await pushLead(env, lead);
    await env.DB.prepare('UPDATE leads SET lark_record = ?, lark_error = NULL WHERE id = ?').bind(rec, id).run();
  } catch (e) {
    console.error('lark', e.message);
    await env.DB.prepare('UPDATE leads SET lark_error = ? WHERE id = ?').bind(String(e.message).slice(0, 300), id).run();
  }
}

async function syncPending(env) {
  const { results } = await env.DB.prepare('SELECT * FROM leads WHERE lark_record IS NULL ORDER BY id LIMIT 500').all();
  for (let i = 0; i < results.length; i += 100) {
    const chunk = results.slice(i, i + 100), ids = await pushMany(env, chunk);
    await env.DB.batch(chunk.map((l, k) => env.DB.prepare('UPDATE leads SET lark_record = ?, lark_error = NULL WHERE id = ?').bind(ids[k], l.id)));
  }
  return results.length;
}

async function syncLark(request, env) {
  if (!(await isAdmin(request, env))) return needLogin();
  if (!larkReady(env)) return new Response('Chưa cấu hình Lark (LARK_APP_ID, LARK_APP_SECRET).', { status: 400, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  let note;
  try { note = `Đã đẩy ${await syncPending(env)} khách lên Lark.`; } catch (e) { note = 'Lỗi khi đẩy lên Lark: ' + e.message; }
  return Response.redirect(new URL('/admin?note=' + encodeURIComponent(note), request.url).toString(), 303);
}

// ---------------- admin ----------------

async function isAdmin(request, env) {
  const auth = request.headers.get('Authorization') || '';
  const [user, pass] = auth.startsWith('Basic ') ? atob(auth.slice(6)).split(/:(.*)/s) : [];
  return !!env.ADMIN_PASSWORD && user === 'admin' && (await same(pass || '', env.ADMIN_PASSWORD));
}
function needLogin() {
  return new Response('Cần đăng nhập.', { status: 401, headers: { 'WWW-Authenticate': 'Basic realm="Ghep Video admin", charset="UTF-8"' } });
}

async function admin(request, env, csv, url) {
  if (!(await isAdmin(request, env))) return needLogin();
  const { results } = await env.DB.prepare('SELECT id, created_at, name, phone, email, purpose, os, niche, downloads, last_download, lark_record, lark_error FROM leads ORDER BY id DESC LIMIT 5000').all();
  if (csv) {
    const cols = ['id', 'created_at', 'name', 'phone', 'email', 'purpose', 'os', 'niche'];
    const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const body = '﻿' + ['STT,Thời gian (UTC),Họ tên,Điện thoại,Email,Bạn đang là,Máy,Lĩnh vực', ...results.map(r => cols.map(c => esc(r[c])).join(','))].join('\r\n');
    return new Response(body, { headers: { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="khach-ghep-video.csv"' } });
  }
  const h = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const rows = results.map(r => `<tr><td>${r.id}</td><td>${h(r.created_at)}</td><td>${h(r.name)}</td><td><a href="https://zalo.me/${h(r.phone)}">${h(r.phone)}</a></td><td>${h(r.email)}</td><td>${h(r.purpose)}</td><td>${h(r.os)}</td><td>${h(r.niche)}</td><td>${r.lark_record ? '✓' : r.lark_error ? `<span title="${h(r.lark_error)}" style="color:#ffb057">lỗi</span>` : '–'}</td></tr>`).join('');
  return new Response(`<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Khách đăng ký Ghép Video</title>
<style>body{font:14px system-ui,sans-serif;margin:24px;background:#0b0f14;color:#eef1f5}a{color:#baf25e}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #2a3140;padding:8px;text-align:left;vertical-align:top}th{color:#9ca8ba;font-weight:600}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.btn{background:#baf25e;color:#0b0f14;padding:8px 14px;border-radius:8px;text-decoration:none;font-weight:600}.wrap{overflow-x:auto}</style></head>
<body><div class="top"><h1>Khách đăng ký Ghép Video · ${results.length}</h1><div style="display:flex;gap:8px;flex-wrap:wrap">${larkReady(env) ? '<form method="post" action="/admin/sync-lark" style="margin:0"><button class="btn" style="border:0;cursor:pointer;font:inherit;font-weight:600">Đẩy khách còn thiếu lên Lark</button></form>' : ''}<a class="btn" href="/admin/leads.csv">Tải file Excel (CSV)</a></div></div>
${url.searchParams.get('note') ? `<p style="background:#1a2230;padding:10px 14px;border-radius:8px">${h(url.searchParams.get('note'))}</p>` : ''}
<div class="wrap"><table><tr><th>#</th><th>Thời gian (UTC)</th><th>Họ tên</th><th>Điện thoại / Zalo</th><th>Email</th><th>Bạn đang là</th><th>Máy</th><th>Lĩnh vực</th><th>Lark</th></tr>${rows || '<tr><td colspan="9">Chưa có ai điền form.</td></tr>'}</table></div></body></html>`,
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
async function same(a, b) {
  // Constant-time comparison via hashing both sides.
  return (await sha256('c' + a)) === (await sha256('c' + b));
}
