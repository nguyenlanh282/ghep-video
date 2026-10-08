// Guide screenshot of the Video quảng cáo page (run the app from a clean copy with neutral demo data).
import { spawn } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
const [,, base, tok, out] = process.argv;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new', '--remote-debugging-port=9333', '--hide-scrollbars', '--mute-audio', '--user-data-dir=' + mkdtempSync('/tmp/cdp-'), 'about:blank'], {stdio: 'ignore'});
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pending = new Map();
for (let i = 0; i < 40; i++) { try { const t = await (await fetch('http://127.0.0.1:9333/json')).json(); const p = t.find(x => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (e) {} await sleep(250); }
await new Promise(r => ws.onopen = r);
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({id: i, method, params})); });
await send('Emulation.setDeviceMetricsOverride', {width: 1600, height: 1000, deviceScaleFactor: 1.5, mobile: false});
await send('Page.navigate', {url: `${base}/ads.html?t=${tok}`}); await sleep(4000);
const r = await send('Page.captureScreenshot', {format: 'png'});
writeFileSync(`${out}/ads.png`, Buffer.from(r.result.data, 'base64')); console.log('ads');
ws.close(); chrome.kill();
