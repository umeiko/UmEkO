import assert from 'node:assert/strict';

export async function checkTemporaryWorkspace(context, publicBase, state, prefix, screenshot) {
  const page = await context.newPage();
  const serverErrors = [];
  page.on('response', (response) => {
    if (response.status() >= 500) serverErrors.push(response.url());
  });
  const errors = [],
    requests = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('request', (r) => requests.push(new URL(r.url()).pathname));
  const url = publicBase + state.temporary.path;
  await page.goto(url);
  await page.locator('.temporary-workspace').waitFor({ state: 'visible' });
  await page.locator('#temporary-expiry').waitFor({ state: 'visible' });
  assert.match(await page.locator('#temporary-expiry').innerText(), /60/);
  assert.equal(await page.locator('#auth-dialog[open]').count(), 0);
  assert.equal(await page.locator('#session-tabs .session-tab').count(), 1);
  assert.ok(await page.locator('#new-session').isDisabled());
  assert.ok(await page.locator('#model-picker').isDisabled());
  assert.match(await page.locator('#model-picker').innerText(), /fixture-model/);
  assert.equal(await page.locator('#user-menu summary').getAttribute('aria-disabled'), 'true');
  await page.locator('#user-menu summary').click();
  assert.equal(await page.locator('#user-menu').getAttribute('open'), null);
  assert.equal(await page.locator('#session-tabs .session-more').count(), 0);
  await page.getByText('TEMPORARY_RESULT', { exact: true }).waitFor();
  await page.locator('button[data-section="skills"]').click();
  assert.equal(await page.locator('#skills-panel .resource-item').count(), 1);
  assert.equal(await page.locator('#skills-panel .resource-name').innerText(), 'doc-image-qc.md');
  assert.ok(await page.locator('#skills-panel .resource-mount.attached').isDisabled());
  assert.equal(await page.locator('#skills-panel .resource-toolbar').count(), 0);
  await page.locator('#skills-panel .resource-open').click();
  await page.locator('#markdown-view').waitFor({ state: 'visible' });
  assert.ok(await page.locator('#save-resource').isHidden());
  await page.locator('#markdown-source').click();
  assert.ok((await page.locator('#resource-editor').getAttribute('readonly')) !== null);
  await page.locator('button[data-section="workspace"]').click();
  await page.locator('.tree-file[data-path="generate/preview.md"] .file-name').click();
  await page.locator('#markdown-view h1').waitFor();
  assert.equal(await page.locator('#markdown-view h1').innerText(), '质检图片清单');
  const scope = state.temporary.path + '/v1/sessions/' + state.temporary.session_id;
  const response = await context.request.post(
    publicBase + scope + '/workspace/files?filename=followup.txt&path=attachments',
    { data: 'TEMP_FOLLOWUP_FILE' },
  );
  assert.equal(response.status(), 201);
  await page.reload();
  await page.locator('.temporary-workspace').waitFor({ state: 'visible' });
  await page.locator('.tree-file[data-path="attachments/followup.txt"]').waitFor();
  await page.locator('#prompt').fill('Continue in temporary workspace');
  await page.locator('#send').click();
  await page.getByText('STREAM_UI_OK', { exact: true }).waitFor();
  await page.locator('#stop').waitFor({ state: 'hidden' });
  await page.locator('#prompt').waitFor({ state: 'visible' });
  await page.reload();
  await page.getByText('Continue in temporary workspace', { exact: true }).waitFor();
  await page.getByText('STREAM_UI_OK', { exact: true }).waitFor();
  assert.equal(await page.getByText('Continue in temporary workspace', { exact: true }).count(), 1);
  assert.equal(await page.getByText('STREAM_UI_OK', { exact: true }).count(), 1);
  // An external caller continues the same session while the browser stays open.
  // Discovery must preserve a user's draft, pending attachment and file preview.
  await page.locator('.tree-file[data-path="generate/preview.md"] .file-name').click();
  await page.locator('#markdown-view h1').waitFor();
  await page.locator('#attach-workspace-file').click();
  await page.locator('#attachments .chip').waitFor();
  const pending = await page.locator('#attachments').innerText();
  await page.locator('#prompt').fill('UNSENT_USER_DRAFT');
  const external = await context.request.post(publicBase + scope + '/runs', {
    data: { input: 'EXTERNAL_SYNC_TEST', attachments: [] },
  });
  assert.equal(external.status(), 202, await external.text());
  await page.getByText('EXTERNAL_SYNC_TEST', { exact: true }).waitFor();
  await page.getByText('EXTERNAL_STREAM_', { exact: true }).waitFor();
  assert.ok(await page.locator('#stop').isVisible());
  assert.equal(await page.locator('#markdown-view h1').innerText(), '质检图片清单');
  await page.getByText('EXTERNAL_STREAM_UI_OK', { exact: true }).waitFor();
  await page.locator('#stop').waitFor({ state: 'hidden' });
  await page.locator('#prompt').waitFor({ state: 'visible' });
  assert.equal(await page.locator('#prompt').inputValue(), 'UNSENT_USER_DRAFT');
  assert.equal(await page.locator('#attachments').innerText(), pending);
  assert.equal(await page.locator('.tool-history').count(), 2);
  assert.equal(await page.locator('.tool-history').last().locator('.agent-action').count(), 20);
  // A run can finish before the browser discovers its ID; the saved reply still appears.
  const fast = await context.request.post(publicBase + scope + '/runs', {
    data: { input: 'FAST_SYNC_TEST', attachments: [] },
  });
  assert.equal(fast.status(), 202, await fast.text());
  await page.getByText('FAST_SYNC_OK', { exact: true }).waitFor();
  assert.equal(await page.getByText('EXTERNAL_SYNC_TEST', { exact: true }).count(), 1);
  assert.equal(await page.getByText('EXTERNAL_STREAM_UI_OK', { exact: true }).count(), 1);
  assert.equal(await page.getByText('FAST_SYNC_TEST', { exact: true }).count(), 1);
  assert.equal(await page.getByText('FAST_SYNC_OK', { exact: true }).count(), 1);
  assert.equal(await page.locator('#prompt').inputValue(), 'UNSENT_USER_DRAFT');
  assert.equal(await page.locator('#markdown-view h1').innerText(), '质检图片清单');
  await screenshot(page, 'temporary-workspace', prefix);
  await page.setViewportSize({ width: 390, height: 844 });
  const expiryBox = await page.locator('#temporary-expiry').boundingBox();
  const sessionBox = await page.locator('.sessionbar').boundingBox();
  assert.ok(
    expiryBox.y + expiryBox.height <= sessionBox.y,
    'Expiry label overlaps the session bar',
  );
  assert.ok(await page.locator('#new-session').isDisabled());
  assert.ok(await page.locator('#model-picker').isDisabled());
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await screenshot(page, 'temporary-workspace-mobile', prefix);
  // Expiration while the page is open, then a fresh expired-link navigation.
  await page.route(url + '/v1/temporary', (route) =>
    route.fulfill({
      status: 410,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 'temporary_workspace_expired',
        detail: '该节点已过期，请重新申请',
      }),
    }),
  );
  await page.locator('.temporary-page-card').waitFor({ state: 'visible', timeout: 20000 });
  const expired = prefix ? 'This workspace has expired' : '该节点已过期';
  await page.getByRole('heading', { name: expired, exact: true }).waitFor();
  assert.ok(await page.locator('.shell').isHidden());
  await page.unroute(url + '/v1/temporary');
  await page.goto(publicBase + '/TMP/unknown-workspace');
  await page.getByRole('heading', { name: expired, exact: true }).waitFor();
  assert.equal(await page.locator('dialog[open]').count(), 0);
  await screenshot(page, 'temporary-expired', prefix);
  assert.deepEqual(errors, []);
  assert.deepEqual(serverErrors, []);
  if (prefix) assert.ok(requests.every((p) => p.startsWith(prefix + '/') || p === '/favicon.ico'));
  await page.close();
}
