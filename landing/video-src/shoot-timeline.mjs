// Headless Chrome via the DevTools protocol: full pages and element crops of the app for the guide: timeline and projects (run the app from a clean copy with neutral demo data).
import { spawn } from 'node:child_process';
import { writeFileSync, readFileSync, mkdtempSync } from 'node:fs';
const [,, base, tok, out] = process.argv;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new', '--remote-debugging-port=9333', '--hide-scrollbars', '--mute-audio', '--autoplay-policy=no-user-gesture-required', '--user-data-dir=' + mkdtempSync('/tmp/cdp-'), 'about:blank'], {stdio: 'ignore'});
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pending = new Map();
for (let i = 0; i < 40; i++) { try { const t = await (await fetch('http://127.0.0.1:9333/json')).json(); const p = t.find(x => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (e) {} await sleep(250); }
await new Promise(r => ws.onopen = r);
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({id: i, method, params})); });
const evaluate = async expr => (await send('Runtime.evaluate', {expression: expr, awaitPromise: true, returnByValue: true})).result.result.value;
async function page(path, W, H) {
  await send('Emulation.setDeviceMetricsOverride', {width: W, height: H, deviceScaleFactor: 1.5, mobile: false});
  await send('Page.navigate', {url: `${base}/${path}?t=${tok}`}); await sleep(4500);
}
async function shot(name, clip) {
  const r = await send('Page.captureScreenshot', {format: 'png', clip: clip ? {...clip, scale: 1} : undefined, captureBeyondViewport: false});
  writeFileSync(`${out}/${name}.png`, Buffer.from(r.result.data, 'base64')); console.log(name, clip ? Object.values(clip).map(Math.round).join(',') : 'full');
}
async function rect(fromSel, toSel = fromSel, pad = 12) {
  return JSON.parse(await evaluate(`(()=>{const a=document.querySelector(${JSON.stringify(fromSel)}).getBoundingClientRect(),b=document.querySelector(${JSON.stringify(toSel)}).getBoundingClientRect();
    const x=Math.min(a.left,b.left)-${pad},y=a.top-${pad},w=Math.max(a.right,b.right)-x+${pad},h=b.bottom-y+${pad};return JSON.stringify({x,y,width:w,height:h})})()`));
}
const click = sel => evaluate(`(()=>{const b=document.querySelector(${JSON.stringify(sel)});const r=b.getBoundingClientRect();b.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:r.left+20,clientY:r.top+20,pointerId:1}));b.click();return 1})()`);
await page('index.html', 1400, 1300);
await evaluate(`document.querySelector('#player').pause(); 1`);
await click('.tl-block[data-i="0"]'); await sleep(1500);
await shot('tl-story', await rect('#tlPanel', '#tlPanel', 0));
await click('#projBtn'); await sleep(1200);
await shot('du-an', await rect('.projdlg', '.projdlg', 0));
await page('talk.html', 1400, 1300);
await click('.tl-block[data-br="0"]'); await sleep(1500);
await shot('tl-talk', await rect('#tlPanel', '#tlPanel', 0));
ws.close(); chrome.kill();
