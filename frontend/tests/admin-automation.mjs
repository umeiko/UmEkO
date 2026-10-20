import assert from 'node:assert/strict';

export async function checkAdminAutomation(
  page,
  context,
  adminBase,
  publicBase,
  state,
  { loggedIn = false } = {},
) {
  const manifest = await (await context.request.get(adminBase + '/admin/automation')).json();
  assert.equal(manifest.name, 'umeko-server-admin');
  assert.equal(manifest.files.length, 3);
  const base = new URL(adminBase);
  for (const entry of manifest.files) {
    assert.equal(
      entry.url,
      base.pathname.replace(/\/$/, '') + '/admin/automation/skill/' + entry.path,
    );
    const response = await context.request.get(base.origin + entry.url);
    assert.equal(response.status(), 200);
    assert.ok((await response.body()).length > 0);
  }
  assert.equal((await context.request.get(publicBase + '/admin/automation')).status(), 404);
  assert.equal(
    (await context.request.get(adminBase + '/admin/v1/openapi.json')).status(),
    loggedIn ? 200 : 401,
  );
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base.origin });
  for (const [language, label] of [
    ['en', 'Copy AI admin prompt'],
    ['zh-CN', '复制 AI 管理提示词'],
  ]) {
    await page.locator('[data-language-select]').selectOption(language);
    const button = page.getByRole('button', { name: label, exact: true });
    await button.click();
    await page.waitForFunction(
      async (start) => (await navigator.clipboard.readText()).startsWith(start),
      language === 'en' ? 'Help me manage' : '请通过 UMEKO',
    );
    const copied = (await page.evaluate(() => navigator.clipboard.readText())).replaceAll(
      '\r\n',
      '\n',
    );
    assert.ok(copied.includes(adminBase + '\n'));
    for (const path of [
      '/admin/automation/skill/SKILL.md',
      '/admin/automation',
      '/admin/v1/openapi.json',
    ])
      assert.ok(copied.includes(adminBase + path));
    assert.ok(!copied.includes(state.password));
    assert.ok(!copied.includes(publicBase + '/admin/'));
    assert.ok(copied.includes('UMEKO_ADMIN_PASSWORD'));
    const download = page.locator('.admin-automation a[download]');
    assert.equal(
      await download.getAttribute('href'),
      adminBase + '/admin/automation/skill/SKILL.md',
    );
    assert.equal(await download.getAttribute('download'), 'SKILL.md');
  }
  if (loggedIn) {
    const schema = await (await context.request.get(adminBase + '/admin/v1/openapi.json')).json();
    assert.equal(schema.servers[0].url, base.pathname || '/');
    assert.ok(schema.paths['/admin/v1/skill-security/{pack}/{member}'].post.requestBody);
  }
}

export async function checkAdminAutomationLayout(page, prefix, screenshot, name) {
  await screenshot(page, name, prefix);
  await page.setViewportSize({ width: 390, height: 844 });
  const button = page.locator('[data-admin-automation-copy]');
  await button.scrollIntoViewIfNeeded();
  const bounds = await button.boundingBox();
  assert.ok(bounds.width >= 32 && bounds.height >= 28);
  assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 391);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  if (await page.locator('.admin-topbar').count()) {
    const header = await page.locator('.admin-topbar').boundingBox();
    const controls = await page.locator('.admin-topbar > .row').boundingBox();
    const breadcrumb = await page.locator('.breadcrumb').boundingBox();
    assert.ok(controls.y + controls.height <= header.y + header.height);
    assert.ok(breadcrumb.height <= 40, 'Breadcrumb remains a readable single row');
  }
  await screenshot(page, name + '-mobile', prefix);
  await page.setViewportSize({ width: 1440, height: 1000 });
}
