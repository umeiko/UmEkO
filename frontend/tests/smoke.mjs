import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtemp, readFile, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.UMEKO_PLAYWRIGHT || 'playwright');
const root = fileURLToPath(new URL('../../', import.meta.url));
const python = process.env.UMEKO_TEST_PYTHON || 'python';
const screenshotDir = process.env.UMEKO_UI_SCREENSHOTS;
async function screenshot(page, name, prefix) {
  if (!screenshotDir) return;
  await mkdir(screenshotDir, { recursive: true });
  await page.locator('.toast').last().waitFor({ state: 'hidden' });
  await page.screenshot({
    path: path.join(screenshotDir, name + (prefix ? '-prefix' : '') + '.png'),
  });
}
const freePort = () =>
  new Promise((resolve) => {
    const server = createServer();
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function ready(url, child) {
  for (let i = 0; i < 120; i++) {
    if (child.exitCode !== null) throw new Error('Fixture exited early');
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await wait(100);
  }
  throw new Error('Fixture startup timed out');
}
async function centered(page, id) {
  const box = await page.locator(id).boundingBox(),
    size = page.viewportSize();
  assert.ok(Math.abs(box.x + box.width / 2 - size.width / 2) < 2);
  assert.ok(Math.abs(box.y + box.height / 2 - size.height / 2) < 2);
  assert.ok(box.width <= size.width - 31);
}
async function confirm(page, yes = true) {
  await page
    .locator('dialog[open]')
    .getByRole('button', { name: yes ? '确认' : '取消', exact: true })
    .click();
}
const browser = await chromium.launch({ headless: true });
try {
  for (const prefix of ['', '/doc-master/consistency/image-text']) {
    const directory = await mkdtemp(path.join(tmpdir(), 'umeko-vue-')),
      port = await freePort(),
      adminPort = await freePort();
    const child = spawn(
      python,
      [
        path.join(root, 'frontend/tests/fixture.py'),
        '--port',
        String(port),
        '--admin-port',
        String(adminPort),
        '--directory',
        directory,
        '--prefix',
        prefix,
      ],
      {
        cwd: root,
        env: { ...process.env, PYTHONPATH: root, PYTHONUTF8: '1' },
        stdio: ['ignore', 'ignore', 'pipe'],
      },
    );
    let diagnostics = '';
    child.stderr.on('data', (chunk) => (diagnostics += chunk.toString()));
    let context;
    try {
      const base = `http://127.0.0.1:${port}`,
        publicBase = base + prefix,
        adminBase = `http://127.0.0.1:${adminPort}`;
      await ready(publicBase + '/health', child);
      await ready(adminBase + '/health', child);
      const state = JSON.parse(await readFile(path.join(directory, 'state.json'), 'utf8'));
      // Keep host OS language from changing selectors, and exercise both UI locales.
      const locale = prefix ? 'en-US' : 'zh-CN';
      context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale });
      const page = await context.newPage(),
        errors = [];
      page.on('pageerror', (e) => errors.push(e.message));
      await page.goto(adminBase + '/');
      await page.locator('#l-user').fill(state.username);
      await page.locator('#l-pass').fill(state.password);
      await page.getByRole('button', { name: '登录', exact: true }).click();
      await page.locator('#page-access').waitFor();
      // Account validation, one-off secret, a cancelled deletion and a blocked deletion.
      await page.locator('#sa-create').click();
      assert.match(await page.locator('#sa-feedback').innerText(), /请输入服务账号名称/);
      const accounts = (
        await (await context.request.get(adminBase + '/admin/v1/service-accounts')).json()
      ).accounts;
      await page.locator('#sa-name').fill('UI fixture "<account>"');
      await page.locator('#sa-create').click();
      await page.locator('#service-secret[open]').waitFor();
      await centered(page, '#service-secret');
      const id = await page.locator('#service-client-id').inputValue();
      assert.ok(id);
      assert.ok(await page.locator('#service-token').inputValue());
      assert.equal(await page.locator('.help-popover:popover-open').count(), 0);
      await page.getByRole('button', { name: '凭据保存说明', exact: true }).hover();
      await page.locator('.help-popover:popover-open').waitFor();
      assert.match(await page.locator('.help-popover:popover-open').innerText(), /一次/);
      assert.ok(
        await page.locator('.help-popover:popover-open').evaluate((el) => {
          const b = el.getBoundingClientRect();
          return document.elementFromPoint(b.x + 5, b.y + 5) === el;
        }),
      );
      await page.keyboard.press('Escape');
      assert.ok(await page.locator('#service-secret[open]').isVisible());
      await page.setViewportSize({ width: 390, height: 844 });
      await centered(page, '#service-secret');
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.locator('#service-secret .modal-header button[aria-label=关闭]').click();
      await page.locator('#service-token').waitFor({ state: 'detached' });
      const row = page.locator('#service-accounts tr').filter({ hasText: 'UI fixture' });
      await row.getByRole('button', { name: '删除', exact: true }).click();
      await confirm(page, false);
      assert.ok(await row.isVisible());
      const accountUrl = adminBase + '/admin/v1/service-accounts/' + id;
      await page.route(accountUrl, (r) =>
        r.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({ detail: '仍有执行任务，请在资源监控中停止' }),
        }),
      );
      await row.getByRole('button', { name: '删除', exact: true }).click();
      await confirm(page);
      await page.getByRole('status').filter({ hasText: '资源监控' }).waitFor();
      assert.ok(await row.isVisible());
      await page.unroute(accountUrl);
      await row.getByRole('button', { name: '删除', exact: true }).click();
      await confirm(page);
      await row.waitFor({ state: 'detached' });
      assert.deepEqual(
        (
          await (await context.request.get(adminBase + '/admin/v1/service-accounts')).json()
        ).accounts.map((a) => a.id),
        accounts.map((a) => a.id),
      );
      // Native Vue model settings persist in the real admin API.
      await page.locator('#tab-providers').click();
      await page.locator('#pd-name').waitFor();
      await page.locator('#ml-' + state.text_model).fill('2');
      await page
        .locator('#ml-' + state.text_model)
        .locator('..')
        .getByRole('button', { name: '保存', exact: true })
        .click();
      await page.getByRole('status').filter({ hasText: '并发上限已设为 2' }).waitFor();
      assert.equal(
        (
          await (await context.request.get(adminBase + '/admin/v1/providers')).json()
        ).providers[0].models.find((m) => m.id === state.text_model).max_concurrent_requests,
        2,
      );
      await page.locator('#pd-name').fill('Renamed Fixture');
      await page.getByRole('button', { name: '保存供应商', exact: true }).click();
      await page.getByRole('status').filter({ hasText: '供应商已保存' }).waitFor();
      assert.equal(
        (await (await context.request.get(adminBase + '/admin/v1/providers')).json()).providers[0]
          .name,
        'Renamed Fixture',
      );
      // Skill creation, dispatch, script editing and sandbox test in an isolated skill directory.
      await page.locator('#tab-dskills').click();
      await page.getByRole('button', { name: '新建 Skill', exact: true }).click();
      await page.locator('#field-name').fill('ui-skill');
      await page.locator('dialog[open]').getByRole('button', { name: '保存', exact: true }).click();
      await page.locator('#sk-content').waitFor();
      await page
        .locator('#page-dskills .editor-toolbar')
        .getByRole('button', { name: '保存', exact: true })
        .click();
      await page.getByRole('status').filter({ hasText: '文件已保存' }).last().waitFor();
      await page.locator('.pack-button').filter({ hasText: 'ui-skill' }).click();
      await page.getByRole('button', { name: '＋ 脚本', exact: true }).click();
      await page.locator('#field-name').fill('ui_script.py');
      await page.locator('dialog[open]').getByRole('button', { name: '保存', exact: true }).click();
      await page.locator('#sk-content').waitFor();
      await page
        .locator('.editor-toolbar')
        .getByRole('button', { name: '保存', exact: true })
        .click();
      await page.waitForFunction(
        () => !document.querySelector('.editor-toolbar').textContent.includes('●'),
      );
      await page
        .locator('.editor-toolbar')
        .getByRole('button', { name: '测试', exact: true })
        .click();
      await page.locator('dialog[open]').getByRole('button', { name: '保存', exact: true }).click();
      await page.locator('dialog[open] .json-view').filter({ hasText: '收到参数' }).waitFor();
      await page.locator('dialog[open] .modal-header button[aria-label=关闭]').click();
      // Agent fields and generated public Card agree, while private instructions stay private.
      await page.locator('#tab-access').click();
      await page.locator('#agent-new').click();
      await page.locator('#agent-definition-name').fill('UI Agent');
      await page.locator('#agent-definition-slug').fill('ui-agent');
      await page.locator('#agent-definition-description').fill('Generic agent fixture');
      await page.locator('#agent-definition-prompt').fill('PRIVATE_FIXTURE');
      await page.locator('#agent-definition-vision-model').selectOption(state.vision_model);
      await page.locator('#agent-definition-skills input').first().check();
      await page.locator('#agent-definition-save').click();
      await page.locator('#agent-definition-feedback').filter({ hasText: '已保存' }).waitFor();
      const agent = (
        await (await context.request.get(adminBase + '/admin/v1/agents')).json()
      ).agents.find((a) => a.slug === 'ui-agent');
      assert.equal(agent.default_vision_model_id, state.vision_model);
      const card = await (await context.request.get(agent.endpoints.agent_card)).json();
      assert.equal(card.name, 'UI Agent');
      assert.ok(!JSON.stringify(card).includes('PRIVATE_FIXTURE'));
      assert.ok(card.skills.length === 1);
      assert.equal(
        await page.locator('#agent-definition-slug').evaluate((el) => el.readOnly),
        true,
      );
      await centered(page, '#agent-definition-editor');
      await page.setViewportSize({ width: 390, height: 844 });
      await centered(page, '#agent-definition-editor');
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.locator('#agent-definition-editor .modal-header button[aria-label=关闭]').click();
      await page.mouse.move(1400, 980);
      await screenshot(page, 'admin', prefix);
      await page.locator('#tab-resources').click();
      await page.getByText('模型调用队列', { exact: true }).waitFor();
      await page.locator('#tab-users').click();
      await page.locator('#page-users h2').waitFor();
      await page.locator('#tab-sessions').click();
      await page.locator('#page-sessions').waitFor();
      // Browser registration, files, module assets, SSE increments, tool folding and cancellation.
      const work = await context.newPage(),
        requests = [],
        assets = [];
      work.on('pageerror', (e) => errors.push(e.message));
      work.on('request', (r) => requests.push(new URL(r.url()).pathname));
      work.on('response', (r) => {
        if (r.url().includes('/static/'))
          assets.push({ path: new URL(r.url()).pathname, status: r.status() });
      });
      await work.addInitScript(() => {
        window.uiDeltas = [];
        const Original = window.EventSource;
        window.EventSource = class extends Original {
          constructor(...args) {
            super(...args);
            this.addEventListener('assistant.delta', (e) =>
              window.uiDeltas.push({ time: performance.now(), text: JSON.parse(e.data).data.text }),
            );
          }
        };
      });
      await work.goto(publicBase + '/');
      await work.locator('#auth-username').fill('ui-browser');
      await work.locator('#auth-password').fill('fixture-browser-only');
      await work.locator('#register').click();
      await work.locator('#status-dot.ready').waitFor();
      assert.equal(await work.locator('html').getAttribute('lang'), prefix ? 'en' : 'zh-CN');
      assert.equal(await work.locator('#user-name').innerText(), 'ui-browser');
      assert.ok(
        assets.length >= 3 &&
          assets.every((a) => a.status === 200 && a.path.startsWith(prefix + '/static/')),
      );
      assert.ok(
        !requests.some((p) => prefix && !p.startsWith(prefix + '/') && p !== '/favicon.ico'),
      );
      await work.locator('#file-actions').click();
      await work.locator('[data-file-action=new-file]').click();
      await work.locator('#file-entry-name').fill('notes.txt');
      await work.locator('#file-entry-form button[type=submit]').click();
      await work.locator('.tree-file').filter({ hasText: 'notes.txt' }).waitFor();
      await work.locator('#file').setInputFiles({
        name: 'table.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from('name,value\nalpha,1\nbeta,2\n'),
      });
      await work.locator('.tree-file').filter({ hasText: 'table.csv' }).click();
      await work.locator('#csv-view').filter({ hasText: 'alpha' }).waitFor();
      assert.ok(
        (await work.locator('#open-file').getAttribute('href')).startsWith(prefix + '/v1/'),
      );
      await work.locator('#collapse-preview').click();
      await work.locator('#prompt').fill('Stream fixture');
      await work.locator('#send').click();
      await work.locator('#tool-activity:not(.hidden)').waitFor();
      await work.locator('#messages').filter({ hasText: 'STREAM_UI_OK' }).waitFor();
      await work.locator('#stop').waitFor({ state: 'hidden' });
      const deltas = await work.evaluate(() => window.uiDeltas);
      assert.equal(deltas.length, 3);
      assert.ok(deltas[2].time - deltas[0].time >= 500);
      assert.ok(requests.some((p) => p.startsWith(prefix + '/v1/runs/') && p.endsWith('/events')));
      assert.equal(await work.locator('.tool-history').count(), 1);
      assert.equal(await work.locator('.tool-history').evaluate((el) => el.open), false);
      await work.locator('.tool-history summary').click();
      assert.equal(await work.locator('.tool-history-list .agent-action').count(), 20);
      await work.locator('.tool-history-list .agent-action').first().click();
      await work.locator('#tool-detail-dialog[open]').waitFor();
      assert.match(await work.locator('#tool-detail-request').innerText(), /index/);
      await work.locator('#tool-detail-close').click();
      await work.locator('.tool-history summary').click();
      await work.locator('.tree-file').filter({ hasText: 'table.csv' }).click();
      await work.locator('#csv-view').filter({ hasText: 'alpha' }).waitFor();
      await screenshot(work, 'workspace', prefix);
      await work.locator('#collapse-preview').click();
      await work.reload();
      await work.locator('#status-dot.ready').waitFor();
      assert.ok((await work.locator('#messages').innerText()).includes('STREAM_UI_OK'));
      assert.equal(await work.locator('.tool-history-list .agent-action').count(), 20);
      await work.locator('#prompt').fill('STOP_TEST');
      await work.locator('#send').click();
      await work.locator('#stop:not(.hidden)').waitFor();
      await work.locator('#stop').click();
      await work.locator('#stop').waitFor({ state: 'hidden' });
      assert.match(await work.locator('#messages').innerText(), /任务已停止/);
      await work.setViewportSize({ width: 390, height: 844 });
      assert.ok(await work.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      assert.ok(await work.locator('#prompt').isVisible());
      assert.deepEqual(errors, []);
      console.log(
        `Passed browser workflows: ${prefix || '/'} (${locale}, admin, files, streaming, 20 folded tools, cancellation, desktop/mobile)`,
      );
    } catch (e) {
      if (diagnostics) console.error(diagnostics);
      throw e;
    } finally {
      await context?.close();
      if (child.exitCode === null) {
        child.kill();
        await Promise.race([new Promise((resolve) => child.once('exit', resolve)), wait(5000)]);
      }
      await rm(directory, { recursive: true, force: true, maxRetries: 3 });
    }
  }
} finally {
  await browser.close();
}
