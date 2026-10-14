import assert from 'node:assert/strict';

export async function checkUserModelAccess(
  page,
  context,
  adminBase,
  userBase,
  state,
  prefix,
  screenshot,
) {
  const user = await context.browser().newContext();
  const ordinary = await context.browser().newContext();
  try {
    assert.ok(
      (
        await user.request.post(userBase + '/v1/auth/login', {
          data: { username: state.username, password: state.password },
        })
      ).ok(),
    );
    assert.ok(
      (
        await ordinary.request.post(userBase + '/v1/auth/login', {
          data: { username: 'ui-history', password: 'fixture-history-only' },
        })
      ).ok(),
    );
    const adminProviders = await (
      await context.request.get(adminBase + '/admin/v1/providers')
    ).json();
    const providerId = adminProviders.providers[0].id;
    await page.locator('#tab-providers').click();
    const dispatch = page.locator('#model-dispatch-' + state.vision_model);
    assert.ok(await dispatch.isChecked());
    await dispatch.uncheck();
    await page.getByRole('status').filter({ hasText: '模型下发设置已更新' }).waitFor();
    const models = async (reader = user) =>
      (await (await reader.request.get(userBase + '/v1/models')).json()).providers
        .flatMap((p) => p.models)
        .map((m) => m.id);
    assert.deepEqual(await models(), [state.text_model]);
    assert.equal(
      (
        await user.request.put(userBase + '/v1/auth/model-prefs', {
          data: { vision_model_id: state.vision_model },
        })
      ).status(),
      403,
    );
    await page.locator('#tab-users').click();
    const row = page
      .locator('#page-users tbody tr')
      .filter({ has: page.getByText(state.username, { exact: true }) });
    await row.getByRole('button', { name: '用户设置', exact: true }).click();
    const dialog = page.locator('#user-model-access[open]');
    await dialog.waitFor();
    assert.ok(await dialog.locator('#user-all-providers').isChecked());
    const privateModel = dialog.locator('#user-model-' + state.vision_model);
    assert.ok(!(await privateModel.isDisabled()));
    assert.ok(!(await privateModel.isChecked()));
    await privateModel.check();
    await dialog.getByText('当前开放 2 个模型', { exact: true }).waitFor();
    await dialog.locator('#user-model-access-save').click();
    await dialog.waitFor({ state: 'hidden' });
    assert.deepEqual(new Set(await models()), new Set([state.text_model, state.vision_model]));
    assert.deepEqual(await models(ordinary), [state.text_model]);
    const current = await (await context.request.get(adminBase + '/admin/v1/providers')).json();
    assert.equal(
      current.providers[0].models.find((m) => m.id === state.vision_model).user_enabled,
      false,
    );
    await row.getByRole('button', { name: '用户设置', exact: true }).click();
    await dialog.waitFor();
    assert.ok(await privateModel.isChecked());
    await privateModel.uncheck();
    await dialog.locator('#user-model-access-save').click();
    await dialog.waitFor({ state: 'hidden' });
    assert.deepEqual(await models(), [state.text_model]);
    await row.getByRole('button', { name: '用户设置', exact: true }).click();
    await dialog.waitFor();
    // A normal selection from inherited defaults must not grant every private model.
    await dialog.locator('#user-all-models').check();
    await dialog.locator('#user-model-' + state.text_model).uncheck();
    assert.ok(!(await privateModel.isChecked()));
    await dialog.getByText('当前开放 0 个模型', { exact: true }).waitFor();
    await dialog.getByRole('button', { name: '清空模型选择', exact: true }).click();
    await dialog.locator('#user-model-' + state.text_model).check();
    await dialog.locator('#user-provider-' + providerId).uncheck();
    assert.ok(await dialog.locator('#user-model-' + state.text_model).isDisabled());
    await dialog.getByText('当前开放 0 个模型', { exact: true }).waitFor();
    await screenshot(page, 'user-model-access', prefix);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1));
    await screenshot(page, 'user-model-access-mobile', prefix);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await dialog.locator('#user-model-access-save').click();
    await dialog.waitFor({ state: 'hidden' });
    const users = await (await context.request.get(adminBase + '/admin/v1/users')).json();
    const uid = users.find((u) => u.username === state.username).id;
    const url = adminBase + `/admin/v1/users/${uid}/model-access`;
    const saved = await (await context.request.get(url)).json();
    assert.deepEqual(saved.allowed_provider_ids, []);
    assert.deepEqual(saved.allowed_model_ids, [state.text_model]);
    assert.deepEqual(await models(), []);
    await row.getByRole('button', { name: '用户设置', exact: true }).click();
    await dialog.waitFor();
    assert.ok(!(await dialog.locator('#user-provider-' + providerId).isChecked()));
    await page.locator('[data-language-select]').selectOption('en');
    await dialog.getByText('Provider access', { exact: true }).waitFor();
    await page.locator('[data-language-select]').selectOption('zh-CN');
    await dialog.locator('#user-all-providers').check();
    await dialog.locator('#user-all-models').check();
    await dialog.locator('#user-model-access-save').click();
    await dialog.waitFor({ state: 'hidden' });
    await page.locator('#tab-providers').click();
    await dispatch.check();
    await page.getByRole('status').filter({ hasText: '模型下发设置已更新' }).waitFor();
    assert.deepEqual(new Set(await models()), new Set([state.text_model, state.vision_model]));
  } finally {
    await Promise.all([user.close(), ordinary.close()]);
  }
}
