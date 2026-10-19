import assert from 'node:assert/strict';

export async function checkSkillTrust(admin, context, adminBase, prefix, screenshot) {
  await admin.locator('#skill-trust-manager').click();
  const manager = admin
    .locator('dialog[open]')
    .filter({ has: admin.locator('[data-trust-manager]') });
  const rows = manager.locator('[data-trust-file]');
  const waitCount = async (count) => {
    await admin.waitForFunction(
      (expected) =>
        document.querySelectorAll('[data-trust-file]').length === expected &&
        document.querySelector('.trust-list')?.getAttribute('aria-busy') === 'false',
      count,
    );
  };
  await manager.locator('[data-trust-pack]').selectOption('trust-fixture');
  await waitCount(50);
  await manager.getByLabel('Page size', { exact: true }).selectOption('25');
  await waitCount(25);
  await manager.locator('[data-trust-select-page]').check();
  await manager.getByText('25 files selected', { exact: true }).waitFor();
  await rows.first().locator('input[type=checkbox]').uncheck();
  assert.equal(
    await manager.locator('[data-trust-select-page]').evaluate((el) => el.indeterminate),
    true,
  );
  await rows.first().locator('input[type=checkbox]').check();
  await manager.getByRole('button', { name: 'Next page', exact: true }).click();
  await admin.waitForFunction(() =>
    document
      .querySelector('[data-trust-file]')
      ?.getAttribute('data-trust-file')
      .endsWith('unit-025.py'),
  );
  await rows.first().locator('input[type=checkbox]').check();
  await manager.getByText('26 files selected', { exact: true }).waitFor();
  await manager.getByRole('button', { name: 'Clear selection', exact: true }).click();
  await manager.locator('[data-trust-select-all]').click();
  await manager.getByText('205 files selected', { exact: true }).waitFor();
  await context.route('**/admin/v1/skill-security/batch', (route) => route.abort(), { times: 1 });
  await manager.locator('[data-trust-approve]').click();
  await manager
    .getByText('Operation interrupted. Results for 205 files are unconfirmed; refresh to check.', {
      exact: true,
    })
    .waitFor();
  await manager.locator('[data-trust-select-all]').click();
  await manager.getByText('205 files selected', { exact: true }).waitFor();
  const firstApproval = admin.waitForResponse(
    (response) =>
      response.url().endsWith('/skill-security/batch') &&
      response.request().method() === 'POST' &&
      response.request().postDataJSON().items.length === 200,
  );
  const lastApproval = admin.waitForResponse(
    (response) =>
      response.url().endsWith('/skill-security/batch') &&
      response.request().method() === 'POST' &&
      response.request().postDataJSON().items.length === 5,
  );
  await manager.locator('[data-trust-approve]').click();
  assert.equal((await (await firstApproval).json()).succeeded, 200);
  assert.equal((await (await lastApproval).json()).succeeded, 5);
  await manager.getByText('Completed: 205 succeeded, 0 failed', { exact: true }).waitFor();
  await manager.locator('[data-trust-search]').fill('unit-00');
  await manager.locator('[data-trust-status-filter]').selectOption('trusted');
  await waitCount(10);
  await manager.locator('[data-trust-select-page]').check();
  await manager.locator('[data-trust-revoke]').click();
  const confirmation = admin
    .locator('dialog[open]')
    .filter({ has: admin.getByRole('heading', { name: 'Remove from trust', exact: true }) });
  await confirmation.getByRole('button', { name: 'Confirm', exact: true }).click();
  await waitCount(0);
  await manager.locator('[data-trust-status-filter]').selectOption('revoked');
  await waitCount(10);
  await manager.locator('[data-trust-select-page]').check();
  await manager.locator('[data-trust-search]').fill('no-matching-file');
  await waitCount(0);
  await manager.getByText('0 files selected', { exact: true }).waitFor();
  assert.ok(await manager.locator('[data-trust-approve]').isDisabled());
  await manager.locator('[data-trust-search]').fill('');
  await waitCount(10);
  await manager.locator('[data-trust-select-page]').check();
  await manager.locator('[data-trust-approve]').click();
  await waitCount(0);
  await manager.locator('[data-trust-status-filter]').selectOption('');
  await waitCount(25);
  await rows.first().locator('summary').click();
  await screenshot(admin, 'skill-trust-manager', prefix);
  await admin.setViewportSize({ width: 390, height: 844 });
  await screenshot(admin, 'skill-trust-manager-mobile', prefix);
  assert.ok(await manager.evaluate((el) => el.scrollWidth <= el.clientWidth + 1));
  const button = await manager.locator('[data-trust-approve]').boundingBox();
  assert.ok(button.y >= 0 && button.y + button.height <= 844);
  await manager.getByRole('button', { name: 'Close', exact: true }).click();
  await admin.setViewportSize({ width: 1440, height: 1000 });
  const response = await context.request.get(
    adminBase + '/admin/v1/skill-security/catalog?pack=trust-fixture&status=trusted',
  );
  assert.equal((await response.json()).total, 205);
  await admin.locator('#skill-trust-manager').click();
  await waitCount(25);
  await manager.getByRole('button', { name: 'Close', exact: true }).click();
}
