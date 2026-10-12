import assert from 'node:assert/strict';

export async function checkModelDisclosureControls(page, state, prefix, screenshot) {
  await page.locator('[data-language-select]').selectOption(prefix ? 'en' : 'zh-CN');
  const picker = page.locator('#agent-definition-model-disclosure');
  assert.equal(
    await page.locator('#agent-model-disclosure-label').innerText(),
    prefix ? 'Main model disclosure' : '主模型披露',
  );
  await picker.locator('summary').click();
  const required = picker.locator(`input[value="${state.text_model}"]`);
  const optional = picker.locator(`input[value="${state.vision_model}"]`);
  assert.ok(await required.isDisabled());
  assert.ok(await required.isChecked());
  await picker
    .getByRole('button', { name: prefix ? 'All main models' : '全部主模型', exact: true })
    .click();
  assert.ok(await optional.isChecked());
  await picker
    .getByRole('button', { name: prefix ? 'Default main model only' : '仅默认主模型', exact: true })
    .click();
  assert.ok(!(await optional.isChecked()));
  await optional.check();
  await page.locator('#agent-model-search').fill('fixture-vision');
  assert.equal(await picker.locator('input[type=checkbox]').count(), 1);
  await page.locator('#agent-model-search').fill('');
  assert.equal(
    await picker.locator('.model-default-label').innerText(),
    prefix ? 'Default' : '默认',
  );
  await screenshot(page, 'agent-model-disclosure', prefix);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page
      .locator('#agent-definition-editor')
      .evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
  );
  await page.locator('#agent-model-search').scrollIntoViewIfNeeded();
  await screenshot(page, 'agent-model-disclosure-mobile', prefix);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await picker.press('Escape');
  assert.equal(await picker.getAttribute('open'), null);
  await page.locator('[data-language-select]').selectOption('zh-CN');
}

export async function checkModelDisclosure(page, context, adminBase, state, prefix, screenshot) {
  await page.locator('#tab-access').click();
  await page.locator('#agent-new').click();
  await page.locator('#agent-definition-name').fill('Model Disclosure Fixture');
  await page.locator('#agent-definition-slug').fill('model-disclosure-fixture');
  await page.locator('#agent-definition-description').fill('Scoped model fixture');
  await checkModelDisclosureControls(page, state, prefix, screenshot);
  await page.locator('#agent-definition-save').click();
  await page.locator('#agent-definition-feedback').filter({ hasText: '已保存' }).waitFor();
  const data = await (await context.request.get(adminBase + '/admin/v1/agents')).json();
  const agent = data.agents.find((a) => a.slug === 'model-disclosure-fixture');
  assert.deepEqual(agent.disclosed_model_ids, [state.vision_model]);
  await page.locator('#agent-definition-editor .modal-header button[aria-label="关闭"]').click();
  const row = page.locator('#agent-definitions tr').filter({ hasText: 'Model Disclosure Fixture' });
  await row.getByRole('button', { name: '配置与入口', exact: true }).click();
  await page.locator('#agent-definition-model-disclosure summary').click();
  assert.ok(
    await page
      .locator(`#agent-definition-model-disclosure input[value="${state.vision_model}"]`)
      .isChecked(),
  );
  await page.locator('#agent-definition-editor .modal-header button[aria-label="关闭"]').click();
}
