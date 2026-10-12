import assert from 'node:assert/strict';

export async function checkRecordInspection(page, context, adminBase, state, prefix, screenshot) {
  const english = !!prefix;
  const label = (zh, en) => (english ? en : zh);
  const record = state.inspection;
  const get = async (url) => (await context.request.get(adminBase + url)).json();
  const sessionsBefore = await get('/admin/v1/users');
  await page.locator('#tab-resources').click();
  const taskRow = page
    .locator('#page-resources tr')
    .filter({ has: page.locator(`td[title="${record.task_id}"]`) });
  await taskRow.getByRole('button', { name: label('详情', 'Details'), exact: true }).click();
  const dialog = page.locator('dialog[open]').filter({ has: page.locator('.record-inspector') });
  await dialog.locator('.inspection-meta').waitFor();
  assert.match(await dialog.innerText(), /192\.0\.2\.15/);
  assert.match(await dialog.innerText(), /SAVED_MACHINE_INPUT/);
  assert.equal(await dialog.locator('.markdown-body strong').innerText(), 'SAVED_MACHINE_OUTPUT');
  assert.ok(await dialog.locator('.hljs-built_in').count());
  await dialog.getByRole('tab', { name: label('工具调用', 'Tool Calls') }).click();
  await dialog.locator('.inspection-tool summary').click();
  assert.equal(
    await dialog.locator('.inspection-tool pre').last().textContent(),
    state.directory_sample,
  );
  await dialog.getByRole('tab', { name: label('上下文', 'Context'), exact: true }).click();
  assert.match(await dialog.innerText(), /SAVED_AGENT_INSTRUCTION/);
  assert.ok(!(await dialog.innerText()).includes('CHANGED_AFTER_SUBMISSION'));
  await dialog.getByRole('tab', { name: label('运行事件', 'Run Events') }).click();
  assert.ok(await dialog.getByText('task.completed', { exact: true }).isVisible());
  await dialog.getByRole('tab', { name: label('会话记录', 'Conversation') }).click();
  assert.equal(await dialog.locator('.inspection-message').count(), 2);
  await dialog.getByLabel(label('显示原文', 'Show source')).check();
  assert.match(
    await dialog.locator('.inspection-message pre').last().textContent(),
    /\*\*SAVED_MACHINE_OUTPUT\*\*/,
  );
  await screenshot(page, 'task-details', prefix);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
    'Inspection fits mobile',
  );
  await page.keyboard.press('Escape');
  await dialog.waitFor({ state: 'hidden' });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .locator('#page-resources tr')
    .filter({ has: page.locator(`td[title="${record.failed_task_id}"]`) })
    .getByRole('button', { name: label('详情', 'Details'), exact: true })
    .click();
  await dialog.getByText('FIXTURE_EXECUTION_ERROR', { exact: true }).waitFor();
  assert.equal(await page.locator('.help-popover:popover-open').count(), 0);
  await page.keyboard.press('Escape');
  await dialog.waitFor({ state: 'hidden' });
  // Error and recovery use the same prefixed inspection endpoint.
  const taskUrl = adminBase + '/admin/v1/tasks/' + record.task_id;
  await page.route(taskUrl, (r) =>
    r.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '任务不存在' }),
    }),
  );
  await taskRow.locator('.record-link').click();
  await dialog.getByRole('alert').waitFor();
  await page.unroute(taskUrl);
  await dialog.getByRole('button', { name: label('重试', 'Retry'), exact: true }).click();
  await dialog.locator('.inspection-meta').waitFor();
  await page.keyboard.press('Escape');
  await page.locator('#tab-users').click();
  const historyUser = page.locator('#page-users tr').filter({ hasText: 'ui-history' });
  await historyUser
    .getByRole('button', { name: label('查看会话', 'View sessions'), exact: true })
    .click();
  await page
    .locator('#page-sessions .session-link')
    .filter({ hasText: 'Saved conversation fixture' })
    .click();
  await dialog.locator('.inspection-message').last().waitFor();
  assert.equal(await dialog.locator('.inspection-message').count(), 3);
  assert.equal(
    await dialog.locator('.inspection-message .markdown-body strong').first().innerText(),
    '检查已完成',
  );
  assert.match(await dialog.innerText(), /pasted\.png/);
  assert.ok(
    await dialog
      .getByText(label('已移出当前上下文', 'Outside current context'), { exact: true })
      .isVisible(),
  );
  await dialog.getByRole('tab', { name: label('工具调用', 'Tool Calls') }).click();
  await dialog.locator('.inspection-tool summary').click();
  assert.equal(
    await dialog.locator('.inspection-tool pre').last().textContent(),
    state.directory_sample,
  );
  await dialog.getByRole('tab', { name: label('上下文', 'Context'), exact: true }).click();
  assert.match(await dialog.innerText(), /SAVED_CONTEXT_SUMMARY/);
  await screenshot(page, 'session-details', prefix);
  await page.keyboard.press('Escape');
  await page.locator('#sessions-back').click();
  await page.locator('#page-users').waitFor();
  await historyUser.waitFor();
  assert.ok(await historyUser.isVisible(), 'Back button returns to user list');
  assert.deepEqual(
    await get('/admin/v1/users'),
    sessionsBefore,
    'Inspection does not change users or sessions',
  );
}
