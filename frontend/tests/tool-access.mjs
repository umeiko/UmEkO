import assert from 'node:assert/strict';

export async function checkToolAccess(page, context, adminBase, state, prefix, screenshot) {
  const users = await (await context.request.get(adminBase + '/admin/v1/users')).json();
  const uid = users.find((u) => u.username === state.username).id;
  const scope = adminBase + `/admin/v1/users/${uid}/tool-access`;
  const dispatchUrl = adminBase + '/admin/v1/tools/download_url';
  try {
    await page.locator('#tab-tools').click();
    const download = page.locator('#tool-dispatch-download_url');
    await download.waitFor();
    assert.ok(await download.isChecked());
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
  } finally {
    await context.request.put(scope, { data: { allowed_tool_names: null } });
    await context.request.put(dispatchUrl, { data: { enabled: true } });
  }
}
