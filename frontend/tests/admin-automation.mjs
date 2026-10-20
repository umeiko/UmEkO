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
  assert.equal(manifest.files.length, 9);
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
    ['en', 'Configure with AI'],
    ['zh-CN', '使用AI来配置'],
  ]) {
    await page.locator('[data-language-select]').selectOption(language);
    const button = page.getByRole('button', { name: label, exact: true });
    assert.equal(await page.locator('.admin-automation a').count(), 0);
    await button.click();
    const dialog = page.locator('[data-admin-automation-dialog][open]');
    await dialog.waitFor();
    await dialog
      .getByRole('heading', {
        name:
          language === 'en'
            ? 'Give this prompt to your local Agent'
            : '将这些提示词交给你的本地 Agent',
      })
      .waitFor();
    const prompt = dialog.locator('textarea');
    assert.equal(await prompt.getAttribute('readonly'), '');
    assert.ok((await prompt.inputValue()).includes(adminBase + '/admin/automation/skill.zip'));
    if (language === 'zh-CN')
      await page.evaluate(() => {
        window.umekoFixtureClipboardWrite = navigator.clipboard.writeText;
        navigator.clipboard.writeText = async () => {
          throw new Error('Fixture: clipboard API unavailable');
        };
      });
    await dialog
      .getByRole('button', { name: language === 'en' ? 'Copy prompt' : '复制提示词', exact: true })
      .click();
    await page.waitForFunction(
      async (start) => (await navigator.clipboard.readText()).startsWith(start),
      language === 'en' ? 'Help me manage' : '请通过 UMEKO',
    );
    const copied = (await page.evaluate(() => navigator.clipboard.readText())).replaceAll(
      '\r\n',
      '\n',
    );
    if (language === 'zh-CN')
      await page.evaluate(() => {
        navigator.clipboard.writeText = window.umekoFixtureClipboardWrite;
        delete window.umekoFixtureClipboardWrite;
      });
    assert.ok(copied.includes(adminBase + '\n'));
    for (const path of [
      '/admin/automation/skill/SKILL.md',
      '/admin/automation/skill.zip',
      '/admin/automation',
      '/admin/v1/openapi.json',
    ])
      assert.ok(copied.includes(adminBase + path));
    assert.ok(!copied.includes(state.password));
    assert.ok(!copied.includes(publicBase + '/admin/'));
    assert.ok(copied.includes('UMEKO_ADMIN_PASSWORD'));
    const download = dialog.locator('[data-admin-automation-download]');
    assert.equal(await download.getAttribute('href'), adminBase + '/admin/automation/skill.zip');
    assert.equal(await download.getAttribute('download'), 'umeko-server-admin.zip');
    const downloaded = page.waitForEvent('download');
    await download.click();
    const receipt = await downloaded;
    assert.equal(receipt.suggestedFilename(), 'umeko-server-admin.zip');
    assert.equal(await receipt.failure(), null);
    await receipt.delete();
    if (language === 'en') await dialog.locator('.modal-header button').click();
    else await page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'hidden' });
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
  const button = page.locator('[data-admin-automation-open]');
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
  await button.click();
  const dialog = page.locator('[data-admin-automation-dialog][open]');
  const box = await dialog.boundingBox();
  assert.ok(box.width <= 358 && Math.abs(box.x + box.width / 2 - 195) < 2);
  assert.ok(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1));
  const footer = await dialog.locator('.modal-footer').boundingBox();
  assert.ok(footer.y + footer.height <= box.y + box.height + 1);
  assert.equal(
    await dialog.locator('.modal-header button').evaluate((el) => el === document.activeElement),
    true,
  );
  await screenshot(page, name + '-mobile', prefix);
  await dialog.locator('[data-admin-automation-download]').scrollIntoViewIfNeeded();
  await screenshot(page, name + '-mobile-download', prefix);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await screenshot(page, name + '-dialog', prefix);
  await page.keyboard.press('Escape');
  await dialog.waitFor({ state: 'hidden' });
}
