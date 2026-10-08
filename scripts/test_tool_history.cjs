// Real project HTML/CSS/JS in Chromium, with deterministic API/SSE fixtures.
// No server, model, credentials or database is used. Install Playwright, then:
// node scripts/test_tool_history.cjs
// Or set LAB_PLAYWRIGHT to an existing Playwright package path.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.LAB_PLAYWRIGHT || 'playwright');
const staticDir = path.join(__dirname, '../umeko/server/static');
const prefix = '/doc-master/consistency/image-text';
const output = path.join(__dirname, 'tool-history-evidence.local');

async function check(browser, width) {
  const context = await browser.newContext({viewport: {width, height: 900}});
  await context.addInitScript(() => {
    localStorage.setItem('umeko:locale', 'zh-CN');
    window.__streams = [];
    window.EventSource = class extends EventTarget {
      constructor(url) {
        super(); this.url = url; this.readyState = 1;
        window.__streams.push(this);
        queueMicrotask(() => this.onopen?.());
      }
      close() { this.readyState = 2; }
      static CLOSED = 2;
    };
  });
  const sessions = ['a', 'b'].map(id => ({id, title: `会话 ${id}`, created_at: '2026-10-08T00:00:00Z'}));
  const history = {a: [], b: []}, messages = {a: [], b: []}, active = {a: null, b: null};
  let serial = 0;
  const errors = [];
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(String(error)));
  await page.route('http://umeko.test/**', async route => {
    const req = route.request();
    const pathname = new URL(req.url()).pathname;
    assert(pathname.startsWith(prefix + '/'), `Escaped deployment prefix: ${pathname}`);
    const url = pathname.slice(prefix.length);
    if (url === '/') return route.fulfill({contentType: 'text/html', body: fs.readFileSync(path.join(staticDir, 'index.html'), 'utf8').replaceAll('__UMEKO_BASE_PATH__', prefix)});
    if (url.startsWith('/static/')) {
      const filename = path.basename(url);
      return route.fulfill({contentType: filename.endsWith('.css') ? 'text/css' : 'application/javascript', body: fs.readFileSync(path.join(staticDir, filename))});
    }
    let result;
    if (url === '/v1/auth/me') result = {id: 'fixture', username: 'UI fixture'};
    else if (url === '/v1/models') result = {providers: [], prefs: {}, active_model_id: null};
    else if (url === '/v1/sessions') result = sessions;
    else if (/^\/v1\/runs\//.test(url)) result = {status: 'completed', reply: 'Polling answer'};
    else {
      const [, sid, sub] = url.match(/^\/v1\/sessions\/([^/]+)(.*)$/) || [];
      if (sub === '') result = sessions.find(item => item.id === sid);
      else if (sub === '/messages') result = messages[sid];
      else if (sub === '/tool-events') result = history[sid];
      else if (sub === '/active-run') result = active[sid];
      else if (sub === '/context') result = {used_tokens: 100, limit_tokens: 10000, percent: 1};
      else if (sub === '/runs' && req.method() === 'POST') {
        result = {id: `fixture_${++serial}`, session_id: sid, status: 'running'};
        active[sid] = result;
      } else if (sub === '/chat/clear') { history[sid] = []; messages[sid] = []; result = {}; }
      else if (sub === '/client/skills' || sub === '/workspace/tree') result = [];
      else throw new Error(`Unexpected API fixture: ${url}`);
    }
    return route.fulfill({contentType: 'application/json', body: JSON.stringify(result)});
  });
  const emit = (type, data = {}) => page.evaluate(({type, data}) => {
    const stream = window.__streams.findLast(item => item.readyState !== 2);
    if (!stream) throw new Error('No open stream');
    stream.dispatchEvent(new MessageEvent(type, {data: JSON.stringify({data})}));
  }, {type, data});
  const start = async text => {
    await page.locator('#prompt').fill(text);
    await page.locator('#send').click();
    await page.waitForFunction(() => window.__streams.some(item => item.readyState !== 2));
  };
  const finish = async (type, data = {}) => {
    active.a = null;
    await emit(type, data);
    await page.waitForFunction(() => !document.querySelector('#prompt').disabled);
    assert.equal(await page.locator('#tool-activity .agent-action').count(), 0);
    assert.equal(await page.locator('#tool-activity').isVisible(), false);
  };
  try {
    await page.goto(`http://umeko.test${prefix}/`);
    await page.waitForFunction(() => document.querySelector('#status').textContent === '已连接');
    // Empty activity must not collapse the composer or the messages grid row.
    assert((await page.locator('#prompt').boundingBox()).height >= 56);
    await start('连续检查很多文件，并汇总结果。');
    for (let i = 0; i < 60; i++) {
      await emit('reasoning.delta', {text: `检查文件 ${i}\n`});
      await emit('tool.started', {name: 'read_document', arguments: {path: `file-${i}.txt`}});
      await emit('tool.completed', {name: 'read_document', result: `RESULT_${i}`});
    }
    assert.equal(await page.locator('#messages > .agent-action').count(), 0);
    assert.equal(await page.locator('.tool-history').count(), 1);
    assert.equal(await page.locator('.tool-history[open]').count(), 0);
    assert.equal(await page.locator('#messages > .reasoning-line').count(), 1);
    assert.equal(await page.locator('.tool-history .agent-action:visible').count(), 0);
    // Two overlapping tools remain visible; completion order does not change history order.
    await emit('tool.started', {name: 'find_files', arguments: {pattern: '*.txt'}});
    await emit('tool.started', {name: 'run_command', arguments: {command: 'fixture only'}});
    assert.equal(await page.locator('#tool-activity .agent-action').count(), 2);
    if (width > 900) {
      await emit('assistant.delta', {text: '较长的中间说明\n'.repeat(90)});
      const top = (await page.locator('#tool-activity').boundingBox()).y;
      await page.locator('#messages').evaluate(el => { el.scrollTop = 0; });
      assert.equal((await page.locator('#tool-activity').boundingBox()).y, top);
      assert.equal(await page.locator('#tool-activity').isVisible(), true);
    }
    await page.locator('#tool-activity .agent-action').last().click();
    await emit('tool.progress', {name: 'run_command', output_delta: 'LIVE_OUTPUT'});
    assert.match(await page.locator('#tool-detail-result').innerText(), /LIVE_OUTPUT/);
    await emit('tool.completed', {name: 'run_command', result: 'FINAL_COMMAND'});
    assert.match(await page.locator('#tool-detail-result').innerText(), /FINAL_COMMAND/);
    await page.locator('#tool-detail-close').click();
    await emit('tool.completed', {name: 'find_files', result: 'FINAL_SEARCH'});
    if (width > 900) assert.equal(await page.locator('#messages').evaluate(el => el.scrollTop), 0);
    const names = await page.locator('.tool-history .agent-action-text').allTextContents();
    assert.match(names.at(-2), /查找文件/);
    assert.match(names.at(-1), /执行命令/);
    // Subagent live text stays in its pinned card, never as standalone chat bubbles.
    await emit('subagent.started', {task: '检查图片'});
    await emit('subagent.reasoning.delta', {text: '检查图片布局'});
    await emit('subagent.delta', {text: '第一张图片无异常'});
    for (let i = 0; i < 2; i++) {
      await emit('subagent.tool.started', {name: 'image_reasoning', arguments: {image_paths: []}});
      await emit('subagent.tool.progress', {name: 'image_reasoning', message: '读取图像', output_delta: 'VISION_LIVE'});
      await emit('subagent.tool.completed', {name: 'image_reasoning', result: 'VISION_DONE'});
    }
    assert.equal(await page.locator('#messages > .subagent-line').count(), 0);
    assert.equal(await page.locator('#tool-activity .agent-action').count(), 1);
    await page.screenshot({path: path.join(output, `running-${width}.png`), fullPage: true});
    await emit('subagent.completed', {result: 'SUBAGENT_DONE'});
    await finish('run.completed', {reply: '文件检查完成，这是最终回答。'});
    assert.equal(await page.locator('.tool-history .agent-action').count(), 65);
    assert.match(await page.locator('.message.assistant').last().innerText(), /最终回答/);
    await page.locator('.tool-history > summary').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('.tool-history[open]').count(), 1);
    const list = await page.locator('.tool-history-list').evaluate(el => ({height: el.clientHeight, scroll: el.scrollHeight}));
    assert(list.height <= 280 && list.scroll > list.height);
    await page.locator('.tool-history .agent-action').first().focus();
    await page.keyboard.press('Enter');
    assert.match(await page.locator('#tool-detail-request').innerText(), /file-0.txt/);
    assert.equal(await page.locator('#tool-detail-result').innerText(), 'RESULT_0');
    await page.locator('#tool-detail-close').click();
    await page.locator('.tool-history > summary').click();
    await page.screenshot({path: path.join(output, `completed-${width}.png`), fullPage: true});
    // Stop/failure must archive unfinished tools with a truthful status.
    for (const status of ['cancelled', 'failed']) {
      await start(status);
      await emit('tool.started', {name: 'run_command', arguments: {command: status}});
      await finish(`run.${status}`, {error: 'fixture failure', reply: '已停止。'});
      assert.equal(await page.locator(`.tool-history .agent-action.${status}`).count(), 1);
    }
    // A closed stream falls back to the task result and clears stale tool activity.
    await start('连接中断');
    await emit('tool.started', {name: 'run_command', arguments: {command: 'disconnected'}});
    await page.evaluate(() => {
      const stream = window.__streams.findLast(item => item.readyState !== 2);
      stream.readyState = 2; stream.onerror();
    });
    await page.waitForFunction(() => !document.querySelector('#prompt').disabled);
    assert.equal(await page.locator('#tool-activity').isVisible(), false);
    assert.equal(await page.locator('.tool-history .agent-action.unknown').count(), 1);
    // Reconnect from a DB snapshot + full SSE replay counts current calls once.
    const at = i => `2026-10-08T00:00:${String(i).padStart(2, '0')}Z`;
    messages.a = [{role: 'user', content: '旧问题', attachments: [], created_at: at(0)},
      {role: 'assistant', content: '旧回答', attachments: [], created_at: at(3)},
      {role: 'user', content: '当前问题', attachments: [], created_at: at(4)}];
    history.a = [{run_id: 'old', name: 'read_document', result: 'OLD', created_at: at(1)},
      {run_id: 'current', name: 'find_files', result: 'CURRENT', created_at: at(5)}];
    active.a = {id: 'current', status: 'running'};
    await page.reload();
    await page.waitForFunction(() => window.__streams.length === 1);
    await emit('tool.started', {name: 'find_files', arguments: {pattern: '*.png'}});
    await emit('tool.completed', {name: 'find_files', result: 'CURRENT'});
    await emit('tool.started', {name: 'read_image', arguments: {path: 'running.png'}});
    assert.equal(await page.locator('.tool-history').count(), 2);
    assert.equal(await page.locator('.tool-history .agent-action').count(), 2);
    assert.equal(await page.locator('#tool-activity .agent-action').count(), 1);
    // Keyboard switching also exercises focus handling on narrow screens.
    await page.locator('.session-tab').filter({hasText: '会话 b'}).focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#status').textContent === '已连接' && !document.querySelector('#prompt').disabled);
    assert.equal(await page.locator('.tool-history').count(), 0);
    assert.equal(await page.locator('#tool-activity').isVisible(), false);
    // Old records without a run id still group by user turn; missing results are unconfirmed.
    active.a = null;
    history.a = [{name: 'read_document', result: 'OLD', created_at: at(1)},
      {name: 'find_files', result: null, created_at: at(5)}];
    await page.locator('.session-tab').filter({hasText: '会话 a'}).focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelectorAll('.tool-history').length === 2);
    assert.equal(await page.locator('.tool-history[open]').count(), 0);
    assert.equal(await page.locator('.tool-history .agent-action.unknown').count(), 1);
    await page.evaluate(() => setLocale('en'));
    assert.match(await page.locator('.tool-history-label').first().innerText(), /Call history/);
    assert.equal(errors.length, 0, errors.join('\n'));
    return {width, calls: 65, pageErrors: errors, historyList: list};
  } finally { await context.close(); }
}

(async () => {
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true});
  try {
    const results = [];
    for (const width of [1440, 390]) {
      results.push(await check(browser, width));
      console.log(`PASS tool history ${width}px`);
    }
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
