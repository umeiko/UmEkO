import assert from 'node:assert/strict';

export async function checkAgentModelControls(page, state, prefix, screenshot) {
  await page.locator('[data-language-select]').selectOption(prefix ? 'en' : 'zh-CN');
  assert.equal(await page.locator('#agent-definition-model-disclosure').count(), 0);
  await page
    .getByLabel(prefix ? 'Default text model' : '默认主模型', { exact: true })
    .selectOption(state.text_model);
  await page
    .getByLabel(prefix ? 'Default vision model' : '默认视觉模型', { exact: true })
    .selectOption(state.vision_model);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page
      .locator('#agent-definition-editor')
      .evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
  );
  await screenshot(page, 'agent-model-settings-mobile', prefix);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator('[data-language-select]').selectOption('zh-CN');
}

export async function checkAgentModelSettings(page, context, adminBase, state, prefix, screenshot) {
  await page.locator('#tab-access').click();
  await page.locator('#agent-new').click();
  await page.locator('#agent-definition-name').fill('Model Settings Fixture');
  await page.locator('#agent-definition-slug').fill('model-settings-fixture');
  await page.locator('#agent-definition-description').fill('Agent defaults fixture');
  await checkAgentModelControls(page, state, prefix, screenshot);
  await page.locator('#agent-definition-save').click();
  await page.locator('#agent-definition-feedback').filter({ hasText: '已保存' }).waitFor();
  let data = await (await context.request.get(adminBase + '/admin/v1/agents')).json();
  const agent = data.agents.find((a) => a.slug === 'model-settings-fixture');
  assert.equal(agent.default_model_id, state.text_model);
  assert.equal(agent.default_vision_model_id, state.vision_model);
  await page.locator('#agent-definition-editor .modal-header button[aria-label="关闭"]').click();
  // Old stored fields remain compatible; an unrelated UI save must preserve them.
  const updated = await context.request.put(adminBase + '/admin/v1/agents/' + agent.id, {
    data: {
      ...Object.fromEntries(
        [
          'slug',
          'name',
          'description',
          'version',
          'system_prompt',
          'default_model_id',
          'default_vision_model_id',
          'skill_names',
          'enabled',
        ].map((key) => [key, agent[key]]),
      ),
      disclosed_model_ids: [state.vision_model],
    },
  });
  assert.ok(updated.ok());
  await page.reload();
  await page.locator('#page-access').waitFor();
  const row = page.locator('#agent-definitions tr').filter({ hasText: 'Model Settings Fixture' });
  await row.getByRole('button', { name: '配置与入口', exact: true }).click();
  await page.locator('#agent-definition-editor[open]').waitFor();
  assert.equal(await page.locator('#agent-definition-model').inputValue(), state.text_model);
  assert.equal(
    await page.locator('#agent-definition-vision-model').inputValue(),
    state.vision_model,
  );
  assert.equal(await page.locator('#agent-definition-model-disclosure').count(), 0);
  await page.locator('#agent-definition-description').fill('Updated description');
  await page.locator('#agent-definition-save').click();
  await page.locator('#agent-definition-feedback').filter({ hasText: '已保存' }).waitFor();
  data = await (await context.request.get(adminBase + '/admin/v1/agents')).json();
  assert.deepEqual(data.agents.find((a) => a.id === agent.id).disclosed_model_ids, [
    state.vision_model,
  ]);
  await page.locator('#agent-editor-tab-config').scrollIntoViewIfNeeded();
  await screenshot(page, 'agent-model-settings', prefix);
  await page.locator('#agent-definition-editor .modal-header button[aria-label="关闭"]').click();
}
