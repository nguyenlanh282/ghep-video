// Push leads into a Lark Base table (Lark Suite international, open.larksuite.com).
// Needs a Lark custom app with Base (bitable) read/write permission, added to the base as an editor:
//   secrets  LARK_APP_ID, LARK_APP_SECRET        (npx wrangler secret put LARK_APP_ID …)
//   vars     LARK_BASE (app token from the base URL), LARK_TABLE (table id), LARK_FIELDS (optional JSON renames)
// Columns this code writes but the table lacks are created as text columns; existing columns keep their type and
// get the value in the matching format (date, phone, number, single select…).

const DEFAULT_API = 'https://open.larksuite.com/open-apis';
const api = env => env.LARK_API || DEFAULT_API;  // LARK_API only for local tests
const FIELD_NAMES = {
  name: 'Họ tên', phone: 'Số điện thoại / Zalo', email: 'Email', purpose: 'Nghề nghiệp / Mục đích',
  os: 'Máy tính', created: 'Thời gian đăng ký', source: 'Nguồn',
};
const OS_LABEL = { windows: 'Windows', mac: 'Mac', other: 'Khác' };
const READ_ONLY = new Set([19, 20, 1001, 1002, 1003, 1004, 1005]);  // lookup, formula, created/modified time & user, auto number

let tokenCache = { value: '', until: 0 };
let fieldCache = { key: '', until: 0, types: null };

export function larkReady(env) { return !!(env.LARK_APP_ID && env.LARK_APP_SECRET && env.LARK_BASE && env.LARK_TABLE); }

async function call(env, path, init = {}) {
  const r = await fetch(api(env) + path, { ...init, headers: { 'Content-Type': 'application/json; charset=utf-8', Authorization: `Bearer ${await token(env)}`, ...(init.headers || {}) } });
  const out = await r.json().catch(() => ({ code: -1, msg: `HTTP ${r.status}` }));
  if (out.code !== 0) throw new Error(`Lark ${path.split('?')[0].split('/').slice(-2).join('/')}: ${out.code} ${out.msg || ''}`.trim());
  return out.data || {};
}

async function token(env) {
  if (tokenCache.value && Date.now() < tokenCache.until) return tokenCache.value;
  const r = await fetch(`${api(env)}/auth/v3/tenant_access_token/internal`, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify({ app_id: env.LARK_APP_ID, app_secret: env.LARK_APP_SECRET }) });
  const out = await r.json();
  if (out.code !== 0) throw new Error(`Lark token: ${out.code} ${out.msg || ''}`);
  tokenCache = { value: out.tenant_access_token, until: Date.now() + (out.expire - 300) * 1000 };
  return tokenCache.value;
}

function names(env) {
  let extra = {};
  try { extra = JSON.parse(env.LARK_FIELDS || '{}'); } catch {}
  return { ...FIELD_NAMES, ...extra };
}

// {column name: type} for the table, creating the columns we write that are missing.
async function fieldTypes(env) {
  const key = `${env.LARK_BASE}/${env.LARK_TABLE}`;
  if (fieldCache.key === key && Date.now() < fieldCache.until) return fieldCache.types;
  const base = `/bitable/v1/apps/${env.LARK_BASE}/tables/${env.LARK_TABLE}/fields`;
  const types = {};
  let page = '';
  do {
    const d = await call(env, `${base}?page_size=100${page ? `&page_token=${page}` : ''}`);
    for (const f of d.items || []) types[f.field_name] = f.type;
    page = d.has_more ? d.page_token : '';
  } while (page);
  for (const n of Object.values(names(env))) {
    if (!(n in types)) { await call(env, base, { method: 'POST', body: JSON.stringify({ field_name: n, type: 1 }) }); types[n] = 1; }
  }
  fieldCache = { key, until: Date.now() + 10 * 60 * 1000, types };
  return types;
}

function format(type, value, when) {
  if (value === '' || value == null || READ_ONLY.has(type)) return undefined;
  switch (type) {
    case 2: { const n = Number(String(value).replace(/\D/g, '')); return Number.isFinite(n) ? n : undefined; }
    case 4: return [String(value)];
    case 5: return when;
    case 7: return !!value;
    case 15: return { link: String(value), text: String(value) };
    case 1: case 3: case 13: return String(value);
    default: return undefined;  // people, attachments, links to other tables… left alone
  }
}

function fieldsFor(lead, types, env) {
  const n = names(env);
  const when = Date.parse(String(lead.created_at).replace(' ', 'T') + 'Z') || Date.now();
  const local = new Date(when).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour12: false });
  const values = {
    name: lead.name, phone: lead.phone, email: lead.email || '', purpose: lead.purpose || '',
    os: OS_LABEL[lead.os] || lead.os || '', created: local, source: 'Landing Ghép Video',
  };
  const fields = {};
  for (const [k, v] of Object.entries(values)) {
    const f = format(types[n[k]], v, when);
    if (f !== undefined) fields[n[k]] = f;
  }
  return fields;
}

// Create or update one lead's row. Returns the Lark record id.
export async function pushLead(env, lead) {
  const types = await fieldTypes(env);
  const base = `/bitable/v1/apps/${env.LARK_BASE}/tables/${env.LARK_TABLE}/records`;
  const fields = fieldsFor(lead, types, env);
  if (lead.lark_record) {
    try { await call(env, `${base}/${lead.lark_record}`, { method: 'PUT', body: JSON.stringify({ fields }) }); return lead.lark_record; }
    catch (e) { if (!/RecordIdNotFound|1254043/.test(e.message)) throw e; }  // row deleted in Lark: add it again
  }
  const d = await call(env, base, { method: 'POST', body: JSON.stringify({ fields }) });
  return d.record.record_id;
}

// Many new leads in one request (the admin "sync" button). Returns record ids in the same order.
export async function pushMany(env, leads) {
  const types = await fieldTypes(env);
  const d = await call(env, `/bitable/v1/apps/${env.LARK_BASE}/tables/${env.LARK_TABLE}/records/batch_create`, {
    method: 'POST', body: JSON.stringify({ records: leads.map(l => ({ fields: fieldsFor(l, types, env) })) }),
  });
  return (d.records || []).map(r => r.record_id);
}
