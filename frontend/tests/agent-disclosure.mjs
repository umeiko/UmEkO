import assert from 'node:assert/strict';

export async function checkAgentDisclosure(page, context, adminBase, agent, prefix, screenshot) {
  const english = !!prefix;
  const label = (zh, en) => (english ? en : zh);
  await page.locator('[data-language-select]').selectOption(english ? 'en' : 'zh-CN');
  const dialog = page.locator('#agent-definition-editor[open]');
  await page.locator('#agent-definition-name').fill('UNSAVED_AGENT_NAME');
  await page.locator('#agent-editor-tab-mcp').click();
  const mcp = dialog.locator('.mcp-disclosure');
  await mcp.locator('.mcp-tool-list button').first().waitFor();
  assert.equal(await mcp.locator('.mcp-tool-list button').count(), 7);
  assert.equal(await mcp.locator('.mcp-tool-detail h3').innerText(), 'submit_task');
  assert.match(
    await mcp.locator('.mcp-endpoint').innerText(),
    new RegExp(prefix + '/agent/ui-agent/mcp'),
  );
  const expected = await (
    await context.request.get(adminBase + '/admin/v1/agents/' + agent.id + '/mcp')
  ).json();
  assert.equal(expected.endpoint, agent.endpoints.mcp);
  await mcp.getByRole('button', { name: 'get_task', exact: true }).click();
  const parameter = mcp.locator('.mcp-parameters tbody tr').filter({ hasText: 'task_id' });
  assert.ok((await parameter.innerText()).includes(label('必填', 'Required')));
  await mcp.locator('.mcp-tool-detail summary').filter({ hasText: 'inputSchema' }).click();
  const schema = JSON.parse(await mcp.locator('.mcp-tool-detail details[open] pre').textContent());
  assert.deepEqual(schema.required, ['task_id']);
  await mcp
    .getByLabel(label('搜索 MCP 工具', 'Search MCP tools'), { exact: true })
    .fill('read_artifact');
  assert.equal(await mcp.locator('.mcp-tool-list button').count(), 1);
  assert.equal(await mcp.locator('.mcp-tool-detail h3').innerText(), 'read_artifact');
  await mcp.getByLabel(label('搜索 MCP 工具', 'Search MCP tools'), { exact: true }).fill('');
  await mcp.getByRole('button', { name: 'submit_task', exact: true }).click();
  await screenshot(page, 'agent-mcp-tools', prefix);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
    'MCP disclosure fits mobile',
  );
  await screenshot(page, 'agent-mcp-tools-mobile', prefix);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator('#mcp-disclosure-tab-resources').click();
  assert.match(await mcp.innerText(), /umeko:\/\/tasks\/\{task_id\}\/artifacts\/\{artifact_id\}/);
  await page.locator('#mcp-disclosure-tab-prompts').click();
  assert.ok(
    await mcp
      .getByText(label('当前没有对外披露 MCP 提示词', 'No MCP prompts are currently disclosed'), {
        exact: true,
      })
      .isVisible(),
  );
  await page.locator('#mcp-disclosure-tab-json').click();
  const raw = JSON.parse(await mcp.locator('.mcp-raw').textContent());
  assert.deepEqual(raw, expected);
  assert.ok(!JSON.stringify(raw).includes('PRIVATE_FIXTURE'));
  await mcp.getByRole('button', { name: label('复制 JSON', 'Copy JSON'), exact: true }).click();
  assert.deepEqual(JSON.parse(await page.evaluate(() => navigator.clipboard.readText())), raw);
  const endpoint = adminBase + '/admin/v1/agents/' + agent.id + '/mcp';
  await page.route(endpoint, (r) =>
    r.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'DISCLOSURE_UNAVAILABLE' }),
    }),
  );
  await mcp.getByRole('button', { name: label('刷新', 'Refresh'), exact: true }).click();
  await mcp.getByRole('alert').waitFor();
  await page.unroute(endpoint);
  await mcp.getByRole('button', { name: label('重试', 'Retry'), exact: true }).click();
  await mcp.getByRole('alert').waitFor({ state: 'hidden' });
  await page.locator('#agent-editor-tab-card').click();
  const card = JSON.parse(await page.locator('#agent-definition-card').textContent());
  assert.equal(card.name, 'UI Agent', 'Public card uses saved configuration');
  await page.locator('#agent-editor-tab-endpoints').click();
  assert.ok(
    (await page.locator('#agent-definition-endpoints').innerText()).includes(agent.endpoints.mcp),
  );
  await page.locator('#agent-editor-tab-config').click();
  assert.equal(
    await page.locator('#agent-definition-name').inputValue(),
    'UNSAVED_AGENT_NAME',
    'Tab switching preserves the draft',
  );
  await page.locator('#agent-definition-name').fill('UI Agent');
  await page.locator('[data-language-select]').selectOption('zh-CN');
}
