import assert from 'node:assert/strict';

export async function checkToolAccess(page, context, adminBase, state, prefix, screenshot) {
  const users = await (await context.request.get(adminBase + '/admin/v1/users')).json();
  const uid = users.find((u) => u.username === state.username).id;
  const retiredUid = users.find((u) => u.username === 'ui-retired-tools').id;
  await checkRetiredToolScope(page, context, adminBase, retiredUid);
  const scope = adminBase + `/admin/v1/users/${uid}/tool-access`;
  const dispatchUrl = adminBase + '/admin/v1/tools/download_url';
  const expected = new Set([
    `GET ${adminBase}/admin/v1/tools`,
    `PUT ${dispatchUrl}`,
    `GET ${scope}`,
    `PUT ${scope}`,
  ]);
  const requests = [];
  const record = (request) => {
    const url = new URL(request.url());
    if (/\/admin\/v1\/(tools(?:\/|$)|users\/[^/]+\/tool-access$)/.test(url.pathname))
      requests.push(`${request.method()} ${url.origin}${url.pathname}`);
  };
  page.on('request', record);
  try {
    // These checks use the public gateway, not the backend's raw port.
    if (prefix) {
      const origin = new URL(adminBase).origin;
      for (const path of ['/admin/v1/tools', `/admin/v1/users/${uid}/tool-access`]) {
        assert.equal((await context.request.get(origin + path)).status(), 404);
        assert.equal((await context.request.get(origin + prefix + path)).status(), 404);
      }
      const adminPrefix = new URL(adminBase).pathname;
      assert.equal(
        (await context.request.get(origin + adminPrefix + '-other/admin/v1/tools')).status(),
        404,
      );
    }
    await page.locator('#tab-tools').click();
    const download = page.locator('#tool-dispatch-download_url');
    await download.waitFor();
    assert.ok(await download.isChecked());
    assert.equal(
      await page
        .locator('#tool-dispatch-write_working_doc, #tool-dispatch-read_working_doc')
        .count(),
      0,
    );
    assert.ok(await page.locator('#tool-dispatch-submit_results').isDisabled());
    await download.uncheck();
    await page.getByRole('status').filter({ hasText: '工具下发设置已更新' }).waitFor();
    await page.reload();
    await page.locator('#tab-tools').click();
    await download.waitFor();
    assert.equal(await download.isChecked(), false);
    await screenshot(page, 'tools-management', prefix);
    await page.locator('#tab-users').click();
    const row = page
      .locator('#page-users tbody tr')
      .filter({ has: page.getByText(state.username, { exact: true }) });
    await row.getByRole('button', { name: '工具权限', exact: true }).click();
    const dialog = page.locator('#user-tool-access[open]');
    await dialog.waitFor();
    await dialog.locator('#user-tool-download_url').waitFor();
    assert.ok(await dialog.locator('#user-inherit-tools').isChecked());
    assert.equal(await dialog.locator('#user-tool-download_url').isChecked(), false);
    assert.equal(await dialog.locator('#user-tool-download_url').isDisabled(), false);
    await dialog.locator('#user-tool-download_url').check();
    await dialog.locator('#user-tool-access-save').click();
    await dialog.waitFor({ state: 'hidden' });
    assert.ok(
      (await (await context.request.get(scope)).json()).allowed_tool_names.includes('download_url'),
    );
    assert.equal(
      (await (await context.request.get(adminBase + '/admin/v1/tools')).json()).tools.find(
        (t) => t.name === 'download_url',
      ).enabled,
      false,
    );
    await row.getByRole('button', { name: '工具权限', exact: true }).click();
    await dialog.waitFor();
    await dialog.locator('#user-tool-download_url').waitFor();
    assert.ok(await dialog.locator('#user-tool-download_url').isChecked());
    await dialog.getByRole('button', { name: '清空工具选择', exact: true }).click();
    assert.ok(await dialog.locator('#user-tool-submit_results').isChecked());
    assert.ok(await dialog.locator('#user-tool-submit_results').isDisabled());
    await screenshot(page, 'user-tool-access', prefix);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1));
    await screenshot(page, 'user-tool-access-mobile', prefix);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('[data-language-select]').selectOption('en');
    await dialog.getByText('User tool access scope', { exact: true }).waitFor();
    await page.locator('[data-language-select]').selectOption('zh-CN');
    await dialog.locator('#user-tool-access-save').click();
    await dialog.waitFor({ state: 'hidden' });
    assert.deepEqual((await (await context.request.get(scope)).json()).allowed_tool_names, []);
    assert.deepEqual(
      new Set(requests),
      expected,
      'Browser reads and writes use exactly the admin origin and prefix, independently of the user prefix',
    );
  } finally {
    page.off('request', record);
    await context.request.put(scope, { data: { allowed_tool_names: null } });
    await context.request.put(dispatchUrl, { data: { enabled: true } });
  }
}

async function checkRetiredToolScope(page, context, adminBase, uid) {
  await page.locator('#tab-users').click();
  const row = page.locator('#page-users tbody tr').filter({
    has: page.getByText('ui-retired-tools', { exact: true }),
  });
  await row.getByRole('button', { name: '工具权限', exact: true }).click();
  const dialog = page.locator('#user-tool-access[open]');
  await dialog.locator('#user-tool-read_document').waitFor();
  await dialog.locator('#retired-tool-notice').waitFor();
  assert.equal(await dialog.locator('#user-inherit-tools').isChecked(), false);
  assert.equal(await dialog.locator('#user-tool-write_file').isChecked(), false);
  assert.equal(
    await dialog.locator('#user-tool-write_working_doc, #user-tool-read_working_doc').count(),
    0,
  );
  await dialog.locator('#retired-tool-notice .help-trigger').hover();
  await page
    .getByText(
      '工作文档专用工具已移除。旧授权不会自动扩大为通用文件权限，请按需选择 read_document、write_file；保存后清理旧授权。',
      { exact: true },
    )
    .waitFor();
  await dialog.locator('#user-tool-read_document').check();
  await dialog.locator('#user-tool-access-save').click();
  await dialog.waitFor({ state: 'hidden' });
  const saved = await (
    await context.request.get(adminBase + `/admin/v1/users/${uid}/tool-access`)
  ).json();
  assert.deepEqual(saved.allowed_tool_names, ['read_document']);
  assert.deepEqual(saved.retired_tool_names, []);
  await page.reload();
  await page.locator('#tab-users').click();
  await row.getByRole('button', { name: '工具权限', exact: true }).click();
  await dialog.locator('#user-tool-read_document').waitFor();
  assert.ok(await dialog.locator('#user-tool-read_document').isChecked());
  assert.equal(await dialog.locator('#user-tool-write_file').isChecked(), false);
  assert.equal(await dialog.locator('#retired-tool-notice').count(), 0);
  await dialog.locator('#user-tool-access-save').click();
  await dialog.waitFor({ state: 'hidden' });
}
