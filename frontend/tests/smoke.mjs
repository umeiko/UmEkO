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
const normalizedText = (text) => text.replaceAll('\r\n', '\n');
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
async function dropFiles(page, selector, files, { folder = false, hover = null } = {}) {
  const transfer = await page.evaluateHandle(
    ({ files }) => {
      const data = new DataTransfer();
      for (const { name, content } of files) data.items.add(new File([content], name));
      return data;
    },
    { files, folder },
  );
  try {
    await page.locator(selector).dispatchEvent('dragenter', { dataTransfer: transfer });
    await page.locator(selector).dispatchEvent('dragover', { dataTransfer: transfer });
    if (hover) await hover();
    if (folder) {
      // OS folder entries cannot be created by File(); simulate their directory metadata.
      await page.locator(selector).evaluate((node, data) => {
        const event = new DragEvent('drop', { bubbles: true, cancelable: true });
        Object.defineProperty(event, 'dataTransfer', {
          value: {
            types: ['Files'],
            files: data.files,
            items: [{ webkitGetAsEntry: () => ({ isDirectory: true }) }],
          },
        });
        node.dispatchEvent(event);
      }, transfer);
    } else await page.locator(selector).dispatchEvent('drop', { dataTransfer: transfer });
  } finally {
    await transfer.dispose();
  }
}

async function workspaceDrops(page, context, publicBase, sid, prefix) {
  const base = publicBase + `/v1/sessions/${sid}/workspace`;
  const feedback = page.locator('#workspace-upload-feedback');
  const row = (filePath) => `.tree-file[data-path="${filePath}"]`;
  const folder = (dir) => `summary[data-path="${dir}"]`;
  const completed = () => page.locator('#workspace-upload-feedback[data-state=success]').waitFor();
  for (const dir of ['workspace', 'attachments', 'generate']) {
    const name = `desktop-${dir}.txt`,
      content = `Windows drag to ${dir}\nSecond line`;
    await dropFiles(page, folder(dir), [{ name, content }], {
      hover: async () => {
        assert.ok(await page.locator(folder(dir) + '.drag-target').isVisible());
        assert.match(await page.locator('.drop-hint').innerText(), new RegExp(dir));
        assert.ok(await page.locator('.drop-hint').isVisible());
      },
    });
    await completed();
    await page.locator(row(`${dir}/${name}`)).waitFor();
    assert.equal(
      await (await context.request.get(base + `/files/raw/${dir}/${name}`)).text(),
      content,
    );
    assert.equal(await page.locator('.drag-target, .drag-over').count(), 0);
    assert.match(await page.locator('#workspace-upload-summary').innerText(), new RegExp(dir));
  }
  // The parent directory also handles drops on its existing file rows.
  await dropFiles(page, row('attachments/desktop-attachments.txt'), [
    { name: 'desktop-attachments.txt', content: 'second version' },
  ]);
  await completed();
  await page.locator(row('attachments/desktop-attachments_1.txt')).waitFor();
  assert.match(
    await page.locator('#workspace-upload-details').innerText(),
    /desktop-attachments_1.txt/,
  );
  assert.match(
    await (
      await context.request.get(base + '/files/raw/attachments/desktop-attachments.txt')
    ).text(),
    /Windows drag/,
  );
  await page.locator(folder('generate/reports')).evaluate((node) => {
    node.parentElement.open = false;
  });
  await dropFiles(page, folder('generate/reports'), [
    { name: 'nested-desktop.txt', content: 'nested content' },
  ]);
  await completed();
  await page.locator(row('generate/reports/nested-desktop.txt')).waitFor();
  assert.ok(
    await page.locator(folder('generate/reports')).evaluate((node) => node.parentElement.open),
  );
  await dropFiles(page, '#file-tree', [{ name: 'blank-area.txt', content: 'default workspace' }]);
  await completed();
  await page.locator(row('workspace/blank-area.txt')).waitFor();
  await screenshot(page, 'workspace-upload-success', prefix);
  // Empty files are rejected by the real API. Other files in the batch must still save.
  await dropFiles(page, folder('generate'), [
    { name: 'empty.txt', content: '' },
    { name: 'valid.txt', content: 'keep going' },
  ]);
  await page.locator('#workspace-upload-feedback[data-state=error]').waitFor();
  await page.locator(row('generate/valid.txt')).waitFor();
  assert.match(await page.locator('#workspace-upload-summary').innerText(), /1.*1/);
  assert.match(
    await page.locator('#workspace-upload-details').innerText(),
    /empty.txt.*文件内容不能为空/,
  );
  assert.equal(
    await page
      .locator('#workspace-upload-details')
      .evaluate((node) => getComputedStyle(node).fontSize),
    '14px',
  );
  await screenshot(page, 'workspace-upload-error', prefix);
  await dropFiles(page, folder('attachments'), [{ name: 'folder', content: '' }], { folder: true });
  assert.match(
    await page.locator('#workspace-upload-details').innerText(),
    prefix ? /Folder drops/ : /整个文件夹/,
  );
  // A browser drag whose protected file list is empty must produce visible feedback.
  await page.locator(folder('attachments')).evaluate((node) => {
    const event = new DragEvent('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'dataTransfer', {
      value: { types: ['Files'], files: [], items: [] },
    });
    node.dispatchEvent(event);
  });
  assert.match(
    await page.locator('#workspace-upload-details').innerText(),
    prefix ? /No files received/ : /没有读取到文件/,
  );
  await page.locator('#workspace-upload-dismiss').click();
  assert.ok(await feedback.isHidden());
  // Keep internal moves working with the same directory drop handlers.
  const internal = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.setData('application/x-flowchart-path', 'workspace/blank-area.txt');
    return data;
  });
  await page.locator(folder('generate')).dispatchEvent('drop', { dataTransfer: internal });
  await internal.dispose();
  await page.locator(row('generate/blank-area.txt')).waitFor();
  assert.equal(await page.locator(row('workspace/blank-area.txt')).count(), 0);
  // A held request checks progress and prevents a session switch from redirecting the batch.
  const originalTitle = await page.locator('.session-tab.active').getAttribute('title');
  let release, started;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const ready = new Promise((resolve) => {
    started = resolve;
  });
  const uploadsUrl = publicBase + '/v1/sessions/*/workspace/files?*';
  const destinations = [];
  await page.route(uploadsUrl, async (route) => {
    destinations.push(route.request().url());
    if (destinations.length === 1) {
      started();
      await gate;
    }
    await route.continue();
  });
  try {
    await dropFiles(page, folder('attachments'), [
      { name: 'batch-first.txt', content: 'first' },
      { name: 'batch-second.txt', content: 'second' },
    ]);
    await ready;
    await page.locator('#workspace-upload-feedback[data-state=uploading]').waitFor();
    assert.ok(await page.locator('#workspace-upload-progress').isVisible());
    await screenshot(page, 'workspace-upload-progress', prefix);
    await page.locator('#new-session').click();
    await page.waitForFunction((id) => localStorage.getItem('umeko:last-session') !== id, sid);
    await page.locator('#new-session:enabled').waitFor();
    assert.ok(await feedback.isHidden());
    const otherSid = await page.evaluate(() => localStorage.getItem('umeko:last-session'));
    release();
    // Returning to the original chat restores its feedback and uploaded files.
    await page
      .locator('.session-tab')
      .filter({ has: page.locator('.session-label', { hasText: originalTitle }) })
      .click();
    await completed();
    await page.locator(row('attachments/batch-second.txt')).waitFor();
    assert.equal(destinations.length, 2);
    assert.ok(destinations.every((url) => url.includes(`/sessions/${sid}/workspace/files?`)));
    const other = await context.request.get(
      publicBase + `/v1/sessions/${otherSid}/workspace/files/raw/attachments/batch-second.txt`,
    );
    assert.equal(other.status(), 404);
  } finally {
    release();
    await page.unroute(uploadsUrl);
  }
}
async function confirm(page, yes = true) {
  await page
    .locator('dialog[open]')
    .getByRole('button', { name: yes ? '确认' : '取消', exact: true })
    .click();
}
async function checkThemes(page, toggle, wanted) {
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
  await page.locator(toggle).click();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
  await page.reload();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
  if (wanted === 'dark') {
    await page.locator(toggle).click();
    await page.reload();
  }
  assert.equal(await page.locator('html').getAttribute('data-theme'), wanted);
  assert.equal(
    await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme),
    wanted,
  );
}
async function composerButtonsFit(page) {
  const boxes = await page.evaluate(() => {
    const rect = (selector) => {
      const { top, bottom, left, right } = document.querySelector(selector).getBoundingClientRect();
      return { top, bottom, left, right };
    };
    return {
      input: rect('.composer-input'),
      textarea: rect('#prompt'),
      model: rect('#model-picker'),
      send: rect('#send'),
      form: rect('#composer'),
    };
  });
  for (const button of [boxes.model, boxes.send]) {
    assert.ok(
      button.bottom <= boxes.input.bottom && button.bottom <= boxes.form.bottom,
      'Composer buttons stay inside the input and form',
    );
    assert.ok(button.top >= boxes.textarea.bottom, 'Toolbar does not cover typing area');
    assert.ok(
      button.left >= boxes.input.left && button.right <= boxes.input.right,
      'Composer buttons fit horizontally',
    );
  }
  assert.ok(boxes.textarea.bottom - boxes.textarea.top >= 40, 'At least one input line remains');
  assert.ok(boxes.model.right <= boxes.send.left, 'Model picker and send do not overlap');
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
      const appearance = prefix ? 'dark' : 'light';
      context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale });
      const page = await context.newPage(),
        errors = [];
      page.on('pageerror', (e) => errors.push(e.message));
      await page.goto(adminBase + '/');
      await checkThemes(page, '[data-theme-toggle]', appearance);
      const otherTab = await context.newPage();
      await otherTab.goto(adminBase + '/');
      await otherTab.locator('[data-theme-toggle]').click();
      await page.waitForFunction(
        (value) => document.documentElement.dataset.theme === value,
        appearance === 'light' ? 'dark' : 'light',
      );
      await otherTab.locator('[data-theme-toggle]').click();
      await page.waitForFunction(
        (value) => document.documentElement.dataset.theme === value,
        appearance,
      );
      await otherTab.close();
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
      await page.getByRole('button', { name: '新建技能', exact: true }).click();
      await page.locator('#field-name').fill('ui-skill');
      await page.locator('dialog[open]').getByRole('button', { name: '保存', exact: true }).click();
      await page.locator('#sk-content').waitFor();
      const skillSample =
        '---\nname: ui-skill\ndescription: 通用文档检查\n---\n\n' + state.markdown_sample;
      await page.locator('#sk-content').fill(skillSample);
      await page
        .locator('#page-dskills .editor-toolbar')
        .getByRole('button', { name: '保存', exact: true })
        .click();
      await page.getByRole('status').filter({ hasText: '文件已保存' }).last().waitFor();
      await context.grantPermissions(['clipboard-read', 'clipboard-write'], {
        origin: new URL(adminBase).origin,
      });
      await page.locator('#skill-preview').click();
      await page.locator('.skill-document strong').filter({ hasText: '检查已完成' }).waitFor();
      assert.ok(await page.locator('.skill-document .hljs-keyword').count());
      assert.equal(await page.locator('.skill-document table tbody tr').count(), 2);
      await page.locator('.skill-document [data-code-copy]').click();
      await page.locator('.skill-document .code-copy.copied').waitFor();
      assert.equal(
        normalizedText(await page.evaluate(() => navigator.clipboard.readText())),
        'def greet(name):\n    print(f"Hello, {name}!")\n\ngreet("世界")\n',
      );
      assert.equal(await page.locator('.skill-metadata').evaluate((el) => el.open), false);
      await page.locator('.skill-metadata summary').click();
      assert.match(await page.locator('.skill-metadata').innerText(), /通用文档检查/);
      await page.locator('.skill-metadata summary').click();
      await page.locator('#skill-edit').click();
      assert.equal(await page.locator('#sk-content').inputValue(), skillSample);
      assert.equal(
        await page.locator('#sk-content').evaluate((el) => getComputedStyle(el).fontSize),
        '14px',
      );
      await page.getByRole('button', { name: '脚本', exact: true }).click();
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
      await page.getByRole('button', { name: '文件', exact: true }).click();
      await page.locator('#field-name').fill('ui_notes.md');
      await page.locator('dialog[open]').getByRole('button', { name: '保存', exact: true }).click();
      await page.locator('#sk-content').fill('## 成员文档\n\n**执行步骤**：检查图片。\n');
      await page
        .locator('.editor-toolbar')
        .getByRole('button', { name: '保存', exact: true })
        .click();
      await page.locator('.editor-dirty').waitFor({ state: 'hidden' });
      await page.locator('#skill-preview').click();
      await page.locator('.skill-document strong').filter({ hasText: '执行步骤' }).waitFor();
      await page.locator('.skill-file-button').filter({ hasText: 'ui-skill.md' }).click();
      await page.locator('.skill-document h1').waitFor();
      assert.equal(await page.locator('#skill-preview').getAttribute('aria-pressed'), 'true');
      const skillNames = await page.locator('.skill-file-name').evaluateAll((els) =>
        els.map((el) => ({
          x: el.getBoundingClientRect().x,
          font: getComputedStyle(el).fontSize,
        })),
      );
      assert.equal(skillNames.length, 3);
      assert.ok(
        skillNames.every((n) => n.font === '14px' && Math.abs(n.x - skillNames[0].x) < 1),
        'Skill files align at readable size',
      );
      await screenshot(page, 'skills-admin', prefix);
      await page.locator('#skill-edit').click();
      await screenshot(page, 'skills-editor', prefix);
      await page.locator('#skill-preview').click();
      await page.setViewportSize({ width: 390, height: 844 });
      assert.ok(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
        'Skill library fits mobile',
      );
      await page.setViewportSize({ width: 1440, height: 1000 });
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
      await checkThemes(work, '#auth-dialog[open] [data-theme-toggle]', appearance);
      await work.locator('#auth-username').fill('ui-browser');
      await work.locator('#auth-password').fill('fixture-browser-only');
      await work.locator('#register').click();
      await work.locator('#status-dot.ready').waitFor();
      assert.equal(await work.locator('html').getAttribute('lang'), prefix ? 'en' : 'zh-CN');
      assert.equal(await work.locator('#user-name').innerText(), 'ui-browser');
      assert.ok(
        assets.length >= 3 &&
          assets.every(
            (a) => [200, 304].includes(a.status) && a.path.startsWith(prefix + '/static/'),
          ),
        'Static assets: ' + JSON.stringify(assets),
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
        (await work.locator('#download-file').getAttribute('href')).startsWith(prefix + '/v1/'),
      );
      const [download] = await Promise.all([
        work.waitForEvent('download'),
        work.locator('#download-file').click(),
      ]);
      assert.equal(download.suggestedFilename(), 'table.csv');
      assert.equal(await download.failure(), null);
      // Long labels, mixed file types and shrinking the composer reproduce the reported layout bugs.
      const session = (await (await context.request.get(publicBase + '/v1/sessions')).json())[0];
      const longTitle = '超长会话标题与文件布局回归验证 '.repeat(4);
      assert.ok(
        (
          await context.request.patch(publicBase + `/v1/sessions/${session.id}/title`, {
            data: { title: longTitle },
          })
        ).ok(),
      );
      const entries = [
        'generate/01-notes.md',
        'generate/02-image.png',
        'generate/03-result.json',
        'generate/04-report.html',
        'generate/05-bundle.zip',
        'generate/reports',
        'generate/reports/nested.txt',
      ];
      for (const entry of entries) {
        assert.ok(
          (
            await context.request.post(
              publicBase + `/v1/sessions/${session.id}/workspace/entries`,
              { data: { path: entry, type: entry === 'generate/reports' ? 'directory' : 'file' } },
            )
          ).ok(),
        );
      }
      await work.reload();
      await work.locator('#status-dot.ready').waitFor();
      const tab = work.locator('.session-tab.active');
      assert.equal(await tab.getAttribute('title'), longTitle.trim());
      const titleSize = await tab
        .locator('.session-label')
        .evaluate((el) => ({ width: el.clientWidth, full: el.scrollWidth }));
      assert.ok(
        titleSize.full > titleSize.width && titleSize.width > 0,
        'Long session title is constrained for ellipsis',
      );
      const generate = work
        .locator('.tree-dir')
        .filter({ has: work.locator('summary[data-path="generate"]') })
        .first();
      const fileLabels = await generate
        .locator(':scope > .tree-children > .tree-file-row .file-name')
        .evaluateAll((els) => els.map((el) => el.getBoundingClientRect().x));
      assert.equal(fileLabels.length, 5);
      assert.ok(
        fileLabels.every((x) => Math.abs(x - fileLabels[0]) < 1),
        'Sibling names align across file types',
      );
      const folderLabel = await work
        .locator('summary[data-path="generate/reports"] .file-name')
        .boundingBox();
      assert.ok(
        Math.abs(folderLabel.x - fileLabels[0]) < 1,
        'Sibling folder and file labels align',
      );
      await work.locator('summary[data-path="generate/reports"]').click();
      const nested = await work
        .locator('.tree-file[data-path="generate/reports/nested.txt"] .file-name')
        .boundingBox();
      assert.ok(nested.x - fileLabels[0] >= 20, 'Nested files have a clear extra indent');
      assert.equal(await generate.locator('.tree-file .tree-icon').count(), 6);
      const iconSizes = await generate
        .locator('.tree-icon')
        .evaluateAll((els) => els.map((el) => el.getBoundingClientRect().width));
      assert.ok(
        iconSizes.every((width) => width === 20),
        'All file and folder icons have the same size',
      );
      await work.locator('#composer-resizer').focus();
      for (let i = 0; i < 15; i++) await work.keyboard.press('ArrowDown');
      await composerButtonsFit(work);
      await work.locator('#file').setInputFiles(
        ['first.txt', 'second.txt', 'third.txt'].map((name) => ({
          name,
          mimeType: 'text/plain',
          buffer: Buffer.from('layout fixture'),
        })),
      );
      await work.locator('#attachments .chip').nth(2).waitFor();
      await composerButtonsFit(work);
      await work.locator('#user-menu summary').click();
      await work.locator('#user-settings').click();
      await work.locator('#user-settings-dialog[open]').waitFor();
      await centered(work, '#user-settings-dialog');
      assert.equal(await work.locator('#user-settings-dialog .eyebrow').count(), 0);
      assert.equal(await work.locator('.help-popover:popover-open').count(), 0);
      await work.locator('#user-settings-dialog legend .help-trigger').hover();
      await work
        .locator('.help-popover:popover-open')
        .filter({ hasText: prefix ? 'default' : '跟随默认' })
        .waitFor();
      await work.keyboard.press('Escape');
      assert.ok(
        await work.locator('#user-settings-dialog').isVisible(),
        'Escape closes help before its dialog',
      );
      await screenshot(work, 'settings', prefix);
      await work.locator('#user-settings-cancel').click();
      await work.locator('.tree-file[data-path="attachments/table.csv"]').click();
      await work.locator('#csv-view').filter({ hasText: 'alpha' }).waitFor();
      await screenshot(work, 'layout', prefix);
      await work.locator('#composer-resizer').dblclick();
      await work.locator('#toggle-preview').click();
      await work.locator('#prompt').fill('Stream fixture');
      await work.locator('#send').click();
      await work.locator('#tool-activity:not(.hidden)').waitFor();
      await work.locator('#messages').filter({ hasText: 'STREAM_UI_OK' }).waitFor();
      await work.locator('#stop').waitFor({ state: 'hidden' });
      const deltas = await work.evaluate(() => window.uiDeltas);
      assert.equal(deltas.length, 3);
      assert.ok(
        deltas[2].time - deltas[0].time >= 500,
        `Live SSE deltas: ${JSON.stringify(deltas)}`,
      );
      assert.ok(requests.some((p) => p.startsWith(prefix + '/v1/runs/') && p.endsWith('/events')));
      assert.equal(await work.locator('.tool-history').count(), 1);
      assert.equal(await work.locator('.tool-history').evaluate((el) => el.open), false);
      await work.locator('.tool-history summary').click();
      assert.equal(await work.locator('.tool-history-list .agent-action').count(), 20);
      await work.locator('.tool-history-list .agent-action').first().click();
      await work.locator('#tool-detail-dialog[open]').waitFor();
      const directoryRequest = JSON.stringify({ directory: 'workspace' }, null, 2);
      assert.equal(await work.locator('#tool-detail-request').textContent(), directoryRequest);
      assert.equal(await work.locator('#tool-detail-result').textContent(), state.directory_sample);
      assert.equal(
        await work.locator('#tool-detail-title').innerText(),
        prefix ? 'List Directory' : '查看目录树',
      );
      assert.ok(await work.locator('#tool-detail-meta .tool-detail-status.completed').isVisible());
      const toolStyles = await work.locator('#tool-detail-dialog').evaluate((el) => {
        const style = (selector) => getComputedStyle(el.querySelector(selector));
        return {
          metadata: style('#tool-detail-meta').fontSize,
          name: style('#tool-detail-meta code').fontSize,
          request: style('#tool-detail-request').fontSize,
          result: style('#tool-detail-result').fontSize,
          whitespace: style('#tool-detail-result').whiteSpace,
        };
      });
      assert.ok(
        [toolStyles.metadata, toolStyles.name, toolStyles.request, toolStyles.result].every(
          (size) => parseFloat(size) >= 14,
        ),
      );
      assert.equal(toolStyles.whitespace, 'pre-wrap');
      await centered(work, '#tool-detail-dialog');
      await screenshot(work, 'tool-directory', prefix);
      await work.locator('#tool-detail-close').click();
      await work.locator('.tool-history-list .agent-action').nth(1).click();
      assert.equal(
        await work.locator('#tool-detail-title').innerText(),
        prefix ? 'Read Skill File' : '读取技能文件',
      );
      assert.equal(await work.locator('#tool-detail-result').textContent(), state.markdown_sample);
      assert.equal(
        await work.locator('#tool-detail-result').locator('h1, strong, script').count(),
        0,
        'Tool results stay plain text',
      );
      await screenshot(work, 'tool-skill', prefix);
      await work.locator('#tool-detail-close').click();
      await work.locator('.tool-history summary').click();
      await work.locator('.tree-file').filter({ hasText: 'table.csv' }).click();
      await work.locator('#csv-view').filter({ hasText: 'alpha' }).waitFor();
      await screenshot(work, 'workspace', prefix);
      await work.locator('#toggle-preview').click();
      await work.reload();
      await work.locator('#status-dot.ready').waitFor();
      assert.ok((await work.locator('#messages').innerText()).includes('STREAM_UI_OK'));
      assert.equal(await work.locator('.tool-history-list .agent-action').count(), 20);
      await work.locator('.tool-history summary').first().click();
      await work.locator('.tool-history-list .agent-action').first().click();
      assert.equal(await work.locator('#tool-detail-request').textContent(), directoryRequest);
      assert.equal(
        await work.locator('#tool-detail-result').textContent(),
        state.directory_sample,
        'Restored JSON-encoded tree has the same lines as live output',
      );
      await work.locator('#tool-detail-close').click();
      await work.locator('.tool-history summary').first().click();
      // Markdown files and streamed replies share the renderer and copy controls.
      await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
      await work.locator('#file').setInputFiles({
        name: 'report.md',
        mimeType: 'text/markdown',
        buffer: Buffer.from(state.markdown_sample),
      });
      await work.locator('.tree-file[data-path="attachments/report.md"]').click();
      await work.locator('#markdown-view strong').filter({ hasText: '检查已完成' }).waitFor();
      assert.equal(await work.locator('#markdown-view table tbody tr').count(), 2);
      assert.ok(await work.locator('#markdown-view .hljs-keyword').count());
      assert.equal(await work.locator('#markdown-rendered').getAttribute('aria-pressed'), 'true');
      const toggle = work.locator('#toggle-preview');
      const openBox = await toggle.boundingBox();
      await toggle.click();
      assert.ok(await work.locator('#preview-panel').isHidden());
      assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
      const closedBox = await toggle.boundingBox();
      assert.ok(
        Math.abs(openBox.y - closedBox.y) < 1 &&
          Math.abs(openBox.x + openBox.width - closedBox.x - closedBox.width) < 1,
        'Preview toggle stays in the same header position',
      );
      await toggle.click();
      assert.ok(
        await work.locator('#markdown-view').isVisible(),
        'Reopening preserves the selected file',
      );
      assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
      await work.locator('#markdown-source').click();
      assert.ok(
        await work.locator('#copy-file-code').isHidden(),
        'Source mode has one copy control',
      );
      assert.equal(
        normalizedText(await work.locator('#code-view').innerText()),
        state.markdown_sample,
      );
      assert.ok(await work.locator('#markdown-view').isHidden());
      await work.locator('#copy-markdown').click();
      await work.locator('#copy-markdown.copied').waitFor();
      assert.equal(
        normalizedText(await work.evaluate(() => navigator.clipboard.readText())),
        state.markdown_sample,
      );
      await screenshot(work, 'markdown-source', prefix);
      await work.locator('#markdown-rendered').click();
      const expectedCode = 'def greet(name):\n    print(f"Hello, {name}!")\n\ngreet("世界")\n';
      await work.locator('#markdown-view [data-code-copy]').click();
      await work.locator('#markdown-view .code-copy.copied').waitFor();
      assert.equal(
        normalizedText(await work.evaluate(() => navigator.clipboard.readText())),
        expectedCode,
      );
      await work.locator('#markdown-view .message-file-link').click();
      await work.locator('#csv-view').filter({ hasText: 'alpha' }).waitFor();
      assert.ok(
        await work.locator('#markdown-toolbar').isHidden(),
        'Markdown controls disappear for other file types',
      );
      const expectedFileCode = 'def greet(name):\n    print(f"Hello, {name}!")\n\ngreet("世界")\n';
      await work.locator('#file').setInputFiles({
        name: 'example.py',
        mimeType: 'text/plain',
        buffer: Buffer.from(expectedFileCode),
      });
      await work.locator('.tree-file[data-path="attachments/example.py"]').click();
      await work.locator('#code-panel .hljs-keyword').first().waitFor();
      await work.locator('#copy-file-code').click();
      await work.locator('#copy-file-code.copied').waitFor();
      assert.equal(
        normalizedText(await work.evaluate(() => navigator.clipboard.readText())),
        expectedFileCode,
      );
      await work.locator('#prompt').fill('MARKDOWN_TEST');
      await work.locator('#send').click();
      await work.locator('#messages strong').filter({ hasText: '检查已完成' }).waitFor();
      assert.ok(
        await work.locator('#stop').isVisible(),
        'Partial streamed Markdown renders before completion',
      );
      await work.locator('#stop').waitFor({ state: 'hidden' });
      const answer = work.locator('.message.assistant').last();
      assert.ok(await answer.locator('.hljs-keyword').count());
      assert.equal(await answer.locator('table tbody tr').count(), 2);
      await answer.locator('[data-code-copy]').click();
      await answer.locator('.code-copy.copied').waitFor();
      assert.equal(
        normalizedText(await work.evaluate(() => navigator.clipboard.readText())),
        expectedCode,
      );
      await work.locator('.tree-file[data-path="attachments/report.md"]').click();
      await work.locator('#markdown-view table').waitFor();
      await screenshot(work, 'markdown', prefix);
      await work.reload();
      await work.locator('#status-dot.ready').waitFor();
      assert.equal(
        await toggle.getAttribute('aria-expanded'),
        'true',
        'Preview open state survives refresh',
      );
      assert.ok(
        await work.locator('#messages .hljs-keyword').count(),
        'Persisted replies render with the same highlighting',
      );
      await toggle.click();
      await work.locator('.sidebar-tab[data-section="skills"]').click();
      const clientSkillName = 'browser-skill-with-a-long-name-for-document-image-checking.md';
      await work.locator('#skills-panel input[type=file]').setInputFiles({
        name: clientSkillName,
        mimeType: 'text/markdown',
        buffer: Buffer.from(skillSample),
      });
      const clientSkill = work.locator('.resource-open').filter({ hasText: clientSkillName });
      await clientSkill.click();
      const skillSwitch = work
        .locator('.resource-item')
        .filter({ has: clientSkill })
        .locator('.resource-mount');
      assert.equal(
        await skillSwitch.getAttribute('title'),
        prefix ? 'Enable on demand' : '启用按需使用',
      );
      await skillSwitch.click();
      await work.locator('.resource-mount.attached').waitFor();
      assert.equal(
        (
          await (
            await context.request.get(
              publicBase + `/v1/sessions/${session.id}/client/skills/${clientSkillName}`,
            )
          ).json()
        ).mounted,
        true,
      );
      await work.reload();
      await work.locator('#status-dot.ready').waitFor();
      await work.locator('.sidebar-tab[data-section="skills"]').click();
      await clientSkill.click();
      assert.equal(
        await skillSwitch.getAttribute('title'),
        prefix ? 'Disable on demand' : '停用按需使用',
      );
      await skillSwitch.click();
      await work.locator('.resource-mount.attached').waitFor({ state: 'hidden' });
      await work.locator('#markdown-view strong').filter({ hasText: '检查已完成' }).waitFor();
      assert.equal(
        await work.locator('#markdown-view .skill-metadata').evaluate((el) => el.open),
        false,
      );
      assert.ok(await work.locator('#resource-editor').isHidden());
      assert.equal(await clientSkill.locator('.tree-icon').count(), 1);
      assert.equal(await clientSkill.evaluate((el) => getComputedStyle(el).fontSize), '14px');
      assert.ok(
        await clientSkill
          .locator('.resource-name')
          .evaluate((el) => el.scrollWidth > el.clientWidth),
        'Long skill names have ellipsis',
      );
      await screenshot(work, 'skills-workspace', prefix);
      await work.locator('#markdown-source').click();
      assert.equal(await work.locator('#resource-editor').inputValue(), skillSample);
      assert.equal(
        await work.locator('#resource-editor').evaluate((el) => getComputedStyle(el).fontSize),
        '14px',
      );
      const editedSkill = skillSample + '\n**已补充步骤**：核对文件名。\n';
      await work.locator('#resource-editor').fill(editedSkill);
      await work.locator('#markdown-rendered').click();
      await work.locator('#markdown-view strong').filter({ hasText: '已补充步骤' }).waitFor();
      await work.locator('#save-resource').click();
      await work.waitForFunction(() => !document.querySelector('#save-resource').disabled);
      await clientSkill.click();
      await work.locator('#markdown-view strong').filter({ hasText: '已补充步骤' }).waitFor();
      await work.locator('#toggle-preview').click();
      await work.locator('#toggle-preview').click();
      assert.ok(await work.locator('#markdown-view').isVisible());
      await work.locator('#toggle-preview').click();
      await work.locator('.sidebar-tab[data-section="workspace"]').click();
      // Hold the creation response to reproduce a fast click before the Run ID arrives.
      let releaseCreation;
      const creationGate = new Promise((resolve) => {
        releaseCreation = resolve;
      });
      const runsUrl = publicBase + '/v1/sessions/*/runs';
      await work.route(runsUrl, async (route) => {
        const response = await route.fetch();
        await creationGate;
        await route.fulfill({ response });
      });
      try {
        await work.locator('#prompt').fill('STOP_TEST');
        await work.locator('#send').click();
        await work.locator('#stop:not(.hidden)').waitFor();
        assert.ok(await work.locator('#stop').isDisabled());
        releaseCreation();
        // Playwright waits for the button to become enabled after task creation.
        await work.locator('#stop').click();
        await work.locator('#stop').waitFor({ state: 'hidden' });
      } finally {
        releaseCreation();
        await work.unroute(runsUrl);
      }
      assert.match(await work.locator('#messages').innerText(), /任务已停止/);
      assert.ok(requests.some((p) => p.startsWith(prefix + '/v1/runs/') && p.endsWith('/cancel')));
      await workspaceDrops(work, context, publicBase, session.id, prefix);
      await work.setViewportSize({ width: 390, height: 844 });
      await work.locator('.workbench-title [data-theme-toggle]').click();
      assert.equal(
        await work.locator('html').getAttribute('data-theme'),
        appearance === 'light' ? 'dark' : 'light',
      );
      await work.locator('.workbench-title [data-theme-toggle]').click();
      assert.ok(await work.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      assert.ok(await work.locator('#prompt').isVisible());
      await composerButtonsFit(work);
      await work.locator('.tree-file[data-path="attachments/report.md"]').click();
      await work.locator('#markdown-view table').waitFor();
      assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
      assert.ok(await work.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await toggle.click();
      assert.ok(await work.locator('#preview-panel').isHidden());
      await work.locator('.tool-history summary').first().click();
      await work.locator('.tool-history-list .agent-action').first().click();
      await centered(work, '#tool-detail-dialog');
      assert.equal(await work.locator('#tool-detail-result').textContent(), state.directory_sample);
      assert.ok(await work.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await screenshot(work, 'tool-directory-mobile', prefix);
      await work.locator('#tool-detail-close').click();
      assert.deepEqual(errors, []);
      console.log(
        `Passed browser workflows: ${prefix || '/'} (${locale}, ${appearance}, Markdown preview/source, live rendering, highlighted code and clipboard, consistent preview toggle, skill tree/Markdown/edit/save/member files, long titles, file tree, composer, admin, files, external file drops/root/nested/blank/duplicates/partial failure/progress/session switching/internal move, 20 folded tools, cancellation, desktop/mobile)`,
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
