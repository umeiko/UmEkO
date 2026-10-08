// Real production UI against published Docker ports. Use bundled Playwright or NODE_PATH.
const fs = require('fs');
const path = require('path');
const {chromium} = require(process.env.LAB_PLAYWRIGHT || 'playwright');
const prefix = '/doc-master/consistency/image-text';
const output = path.join(__dirname, 'docker-evidence.local');

async function check(browser, base, mount, scenario) {
  const context = await browser.newContext({viewport: {width:1400, height:960}});
  await context.addInitScript(() => {
    window.__deltas = [];
    const Original = window.EventSource;
    window.EventSource = class extends Original {
      constructor(...args) {
        super(...args);
        this.addEventListener('assistant.delta', event => window.__deltas.push({at:performance.now(), text:JSON.parse(event.data).data.text}));
      }
    };
  });
  const page = await context.newPage();
  const errors = [], requests = [], assets = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('request', r => requests.push(new URL(r.url()).pathname));
  page.on('response', r => {
    if (new URL(r.url()).pathname.includes('/static/')) assets.push({url:r.url(),status:r.status()});
  });
  try {
    const endpoint = base + mount;
    const auth = await context.request.post(endpoint + '/v1/auth/register', {data:{username:'ui_' + Date.now() + Math.random().toString(36).slice(2,7), password:'local-test-only'}});
    if (auth.status() !== 201) throw new Error(await auth.text());
    const sessionResponse = await context.request.post(endpoint + '/v1/sessions', {data:{}});
    const session = await sessionResponse.json();
    // Avatar is an API-returned root-relative URL, not a fetch through api().
    const avatar = await context.request.put(endpoint + '/v1/auth/avatar', {
      headers:{'Content-Type':'image/png'},
      data:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l7sAAAAASUVORK5CYII=', 'base64')
    });
    if (!avatar.ok()) throw new Error(await avatar.text());
    if (scenario !== 'normal') {
      await page.route('**/v1/runs/*/events', route => route.fulfill({status:404, body:'simulated missing stream route'}));
      if (scenario === 'both-fail') await page.route(/\/v1\/runs\/[^/]+$/, route => route.fulfill({status:404, contentType:'application/json', body:'{"detail":"simulated unavailable task status"}'}));
    }
    await page.goto(endpoint + '/', {waitUntil:'networkidle'});
    await page.locator('#prompt').waitFor();
    if (assets.length < 3 || assets.some(a => a.status !== 200)) throw new Error(JSON.stringify(assets));
    await page.waitForFunction(() => !document.querySelector('#user-avatar-image').classList.contains('hidden'));
    const uploaded = await context.request.post(endpoint + `/v1/sessions/${session.id}/workspace/files?filename=preview.txt`, {data:'LOCAL_PREVIEW_OK'});
    const file = await uploaded.json();
    if (!uploaded.ok()) throw new Error(JSON.stringify(file));
    await page.locator('#refresh-tree').click();
    await page.locator('.tree-file').filter({hasText:'preview.txt'}).click();
    await page.waitForFunction(() => document.querySelector('#code-view').textContent.includes('LOCAL_PREVIEW_OK'));
    const previewUrl = await page.locator('#open-file').getAttribute('href');
    if (!previewUrl.startsWith(mount + '/v1/')) throw new Error('Wrong preview URL: ' + previewUrl);
    await page.locator('#prompt').fill('Reply with LOCAL_MODEL_OK.');
    await page.locator('#send').click();
    if (scenario === 'both-fail') {
      await page.waitForFunction(() => document.querySelector('#messages').textContent.includes('回答连接失败'));
    } else {
      await page.waitForFunction(() => document.querySelector('#messages').textContent.includes('LOCAL_MODEL_OK'));
    }
    await page.waitForFunction(() => !document.querySelector('#send').disabled && document.querySelector('#stop').classList.contains('hidden'));
    const deltas = await page.evaluate(() => window.__deltas);
    if (scenario === 'normal' && (deltas.length !== 3 || deltas.at(-1).at - deltas[0].at < 500)) throw new Error('UI did not receive incremental model output: ' + JSON.stringify(deltas));
    if (scenario === 'stream-fail' && !requests.some(p => /\/v1\/runs\/[^/]+$/.test(p))) throw new Error('Task status fallback was not used');
    const escaped = mount ? requests.filter(p => p.startsWith('/v1/') || p.startsWith('/static/')) : [];
    if (escaped.length || errors.length) throw new Error(JSON.stringify({escaped, errors}));
    await page.screenshot({path:path.join(output, 'fixed-ui-' + scenario + (mount ? '-prefix' : '-root') + '.png'),fullPage:true});
    return {url:endpoint+'/', scenario, assets, requests, deltas, previewUrl, pageErrors:errors};
  } finally { await context.close(); }
}

(async () => {
  fs.mkdirSync(output, {recursive:true});
  const browser = await chromium.launch({headless:true});
  try {
    const results = [];
    for (const [base, mount, scenario] of [
      ['http://localhost:28081', '', 'normal'],
      ['http://localhost:28080', prefix, 'normal'],
      ['http://localhost:28080', prefix, 'stream-fail'],
      ['http://localhost:28080', prefix, 'both-fail'],
    ]) {
      results.push(await check(browser,base,mount,scenario));
      console.log('PASS browser', mount || '/', scenario);
    }
    fs.writeFileSync(path.join(output,'browser-fix-report.json'), JSON.stringify({scope:'actual UmEkO UI over Docker HTTP ports; strict HTTPS covered separately by verify.py', results},null,2));
  } finally { await browser.close(); }
})().catch(e => {console.error(e);process.exit(1);});
