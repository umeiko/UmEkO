import assert from 'node:assert/strict';

export async function checkSkillLayout(context, publicBase, adminBase, state, prefix, screenshot) {
  for (const target of [adminBase + '/admin/login', publicBase + '/v1/auth/login']) {
    assert.ok(
      (
        await context.request.post(target, {
          data: { username: state.username, password: state.password },
        })
      ).ok(),
    );
  }
  const original = await (
    await context.request.get(
      adminBase + '/admin/v1/skill-scripts/drawio-correction/references/style.md',
    )
  ).json();
  const session = await (
    await context.request.post(publicBase + '/v1/sessions', {
      data: { title: 'Skill copy fixture' },
    })
  ).json();
  const errors = [];
  const admin = await context.newPage();
  const securityRequests = [];
  admin.on('request', (request) => {
    if (request.url().includes('/skill-security/')) securityRequests.push(request.url());
  });
  admin.on('pageerror', (error) => errors.push(error.message));
  await admin.goto(adminBase + '/');
  await admin.locator('#tab-dskills').click();
  const pack = admin
    .locator('.skill-pack')
    .filter({ has: admin.locator('.pack-name').getByText('drawio-correction', { exact: true }) });
  await pack.locator('.pack-button').click();
  await pack.locator('[data-skill-path="SKILL.md"]').click();
  await admin.locator('.skill-document h1').waitFor();
  await pack.locator('[data-skill-path="references"]').click();
  assert.ok(await pack.locator('[data-skill-path="references/style.md"]').isHidden());
  await pack.locator('[data-skill-path="references"]').click();
  await pack.locator('[data-skill-path="references/style.md"]').click();
  await admin.locator('.skill-document h1').filter({ hasText: '统一技术图表规范' }).waitFor();
  await screenshot(admin, 'skill-layout-admin', prefix);
  const work = await context.newPage();
  work.on('pageerror', (error) => errors.push(error.message));
  const requests = [];
  work.on('request', (request) => {
    if (request.url().includes('/skill-files/')) requests.push(request.url());
  });
  await work.goto(publicBase + '/');
  await work.locator('#status-dot.ready').waitFor();
  await work.locator('.sidebar-tab[data-section="skills"]').click();
  assert.equal(await work.locator('#skills-panel .resource-toolbar').count(), 0);
  assert.ok(await work.locator('#file-actions').isHidden());
  assert.equal(await work.locator('#resource-dialog').count(), 0);
  await work.locator('.resource-open').filter({ hasText: 'drawio-correction' }).click();
  const tree = work.locator('.session-skill-tree').filter({
    has: work.locator('.resource-name').getByText('drawio-correction', { exact: true }),
  });
  await tree.locator('[data-skill-path="references/style.md"]').click();
  await work.locator('#markdown-source').click();
  const content = '# Browser session style\n\nKeep this change in this session.\n';
  await work.locator('#resource-editor').fill(content);
  await work.locator('#save-resource').click();
  await work.waitForFunction(() => !document.querySelector('#save-resource').disabled);
  assert.equal(
    (
      await (
        await context.request.get(
          publicBase +
            `/v1/sessions/${session.id}/skill-files/drawio-correction/references/style.md`,
        )
      ).json()
    ).content,
    content,
  );
  assert.equal(
    (
      await (
        await context.request.get(
          adminBase + '/admin/v1/skill-scripts/drawio-correction/references/style.md',
        )
      ).json()
    ).content,
    original.content,
  );
  await work.reload();
  await work.locator('#status-dot.ready').waitFor();
  await work.locator('.sidebar-tab[data-section="skills"]').click();
  await work.locator('.resource-open').filter({ hasText: 'drawio-correction' }).click();
  await tree.locator('[data-skill-path="references/style.md"]').click();
  await work.locator('#markdown-view h1').getByText('Browser session style').waitFor();
  const menu = work.locator('#file-context-menu');
  const entry = (name) => tree.locator(`[data-skill-path="${name}"]`);
  for (const member of ['scripts/prepare_correction.py', 'assets/config.json']) {
    if (await entry(member).isHidden()) await entry(member.split('/')[0]).click();
    await entry(member).click();
    await work.locator('#preview-title').filter({ hasText: member }).waitFor();
    assert.ok(await work.locator('#resource-editor').evaluate((element) => element.readOnly));
    assert.ok(await work.locator('#save-resource').isHidden());
    assert.ok(await work.locator('#resource-readonly').isVisible());
    await entry(member).click({ button: 'right' });
    for (const action of ['cut', 'rename', 'delete']) {
      assert.ok(await menu.locator(`[data-file-action="${action}"]`).isDisabled());
    }
    await work.keyboard.press('Escape');
    const url = publicBase + `/v1/sessions/${session.id}/skill-files/drawio-correction/${member}`;
    assert.equal(
      (await context.request.put(url, { data: { content: 'forbidden' } })).status(),
      400,
    );
  }
  await entry('references/style.md').click();
  await work.locator('#preview-title').filter({ hasText: 'references/style.md' }).waitFor();
  await work.locator('#markdown-source').click();
  assert.equal(
    await work.locator('#resource-editor').evaluate((element) => element.readOnly),
    false,
  );
  assert.ok(await work.locator('#save-resource').isVisible());
  assert.ok(await work.locator('#resource-readonly').isHidden());
  const create = async (directory, action, name) => {
    await entry(directory).click({ button: 'right' });
    await menu.locator(`[data-file-action="${action}"]`).click();
    await work.locator('#file-entry-name').fill(name);
    await work.locator('#file-entry-form button[type="submit"]').click();
    await entry(`${directory}/${name}`).waitFor();
  };
  await create('references', 'new-directory', 'browser-fixture');
  await create('references/browser-fixture', 'new-file', 'notes.txt');
  await entry('references/browser-fixture/notes.txt').click();
  await work.locator('#resource-editor').fill('Plain session file\n');
  await work.locator('#save-resource').click();
  await work.waitForFunction(() => !document.querySelector('#save-resource').disabled);
  await work.locator('#markdown-rendered').click();
  await work.locator('#code-view').getByText('Plain session file').waitFor();
  await work.locator('#markdown-source').click();
  const upload = await work.evaluateHandle(() => {
    const data = new DataTransfer();
    data.items.add(new File(['Dropped session file'], 'dropped.txt', { type: 'text/plain' }));
    return data;
  });
  await entry('references/browser-fixture').dispatchEvent('drop', { dataTransfer: upload });
  await upload.dispose();
  await entry('references/browser-fixture/dropped.txt').waitFor();
  await entry('references/browser-fixture/notes.txt').press('Control+c');
  await entry('references/browser-fixture').click({ button: 'right' });
  await menu.locator('[data-file-action="paste"]').click();
  await entry('references/browser-fixture/notes_copy.txt').waitFor();
  await entry('references/browser-fixture/notes.txt').click();
  await entry('references/browser-fixture/notes_copy.txt').click({ modifiers: ['Shift'] });
  await entry('references/browser-fixture/notes.txt').click({ button: 'right' });
  assert.equal(await tree.locator('[aria-selected="true"]').count(), 2);
  assert.ok(await menu.locator('[data-file-action="rename"]').isHidden());
  assert.ok(await menu.locator('[data-file-action="copy"]').isEnabled());
  work.once('dialog', (dialog) => dialog.accept());
  await menu.locator('[data-file-action="delete"]').click();
  await entry('references/browser-fixture/notes.txt').waitFor({ state: 'detached' });
  await entry('references/browser-fixture/notes_copy.txt').waitFor({ state: 'detached' });
  await entry('SKILL.md').click({ button: 'right' });
  assert.ok(await menu.locator('[data-file-action="delete"]').isDisabled());
  assert.ok(await menu.locator('[data-file-action="rename"]').isDisabled());
  await work.keyboard.press('Escape');
  await entry('references/browser-fixture').click();
  await entry('references/browser-fixture').press('F2');
  await work.locator('#file-entry-name').fill('renamed-fixture');
  await work.locator('#file-entry-form button[type="submit"]').click();
  await entry('references/renamed-fixture').waitFor();
  await entry('references/renamed-fixture').click();
  work.once('dialog', (dialog) => dialog.accept());
  await entry('references/renamed-fixture').press('Delete');
  await entry('references/renamed-fixture').waitFor({ state: 'detached' });
  await work.locator('.sidebar-tab[data-section="workspace"]').click();
  assert.ok(await work.locator('#file-actions').isVisible());
  await work.locator('.sidebar-tab[data-section="skills"]').click();
  assert.ok(
    requests.every((url) => url.startsWith(publicBase + `/v1/sessions/${session.id}/skill-files/`)),
  );
  await screenshot(work, 'skill-layout-session', prefix);
  const configFile = pack.locator('[data-skill-path="assets/config.json"]');
  if (await configFile.isHidden()) await pack.locator('[data-skill-path="assets"]').click();
  await configFile.click();
  await admin.locator('#sk-content').waitFor();
  const configuration = JSON.parse(await admin.locator('#sk-content').inputValue());
  const changedConfiguration = JSON.stringify(
    { ...configuration, fixture_approval: 'reviewed' },
    null,
    2,
  );
  await admin.locator('#sk-content').fill(changedConfiguration);
  assert.ok(await admin.locator('#skill-security').isDisabled());
  await admin.locator('.editor-toolbar').getByRole('button', { name: '保存', exact: true }).click();
  await admin.locator('.editor-dirty').waitFor({ state: 'hidden' });
  await admin.locator('#skill-security').click();
  const security = admin
    .locator('dialog[open]')
    .filter({ has: admin.locator('[data-skill-security]') });
  await security.locator('[data-current-md5]').waitFor();
  const securityUrl = adminBase + '/admin/v1/skill-security/drawio-correction/assets/config.json';
  const beforeApproval = await (await context.request.get(securityUrl)).json();
  assert.equal(beforeApproval.trusted, false);
  assert.equal(await security.locator('[data-redispatch]').count(), 0);
  const firstApproval = admin.waitForResponse(
    (response) =>
      response.url().includes('/skill-security/') && response.request().method() === 'POST',
  );
  await security.locator('[data-approve-skill]').click();
  assert.equal((await (await firstApproval).json()).trusted, true);
  await admin.waitForFunction(() => document.querySelector('[data-approve-skill]').disabled);
  const safety = await (await context.request.get(securityUrl)).json();
  assert.equal(safety.status, 'trusted');
  assert.equal(safety.approved.actor, state.username);
  assert.equal(safety.approved.sha256, safety.current.sha256);
  const sessionConfig = await (
    await context.request.get(
      publicBase + `/v1/sessions/${session.id}/skill-files/drawio-correction/assets/config.json`,
    )
  ).json();
  assert.equal(JSON.parse(sessionConfig.content).fixture_approval, undefined);
  await security.getByRole('button', { name: '关闭', exact: true }).click();
  await admin.locator('#sk-content').fill(changedConfiguration + '\n');
  await admin.locator('.editor-toolbar').getByRole('button', { name: '保存', exact: true }).click();
  await admin.locator('.editor-dirty').waitFor({ state: 'hidden' });
  await admin.locator('#skill-security').click();
  await security.getByText('文件已变化，需重新确认', { exact: true }).waitFor();
  const renewedApproval = admin.waitForResponse(
    (response) =>
      response.url().includes('/skill-security/') && response.request().method() === 'POST',
  );
  await security.locator('[data-approve-skill]').click();
  assert.equal((await (await renewedApproval).json()).trusted, true);
  await security.getByText('当前版本已信任', { exact: true }).waitFor();
  await security.getByRole('button', { name: '关闭', exact: true }).click();
  await admin.locator('[data-language-select]').selectOption('en');
  await admin.locator('#skill-security').click();
  await security.getByRole('heading', { name: 'File security gates' }).waitFor();
  await security.locator('[data-current-md5]').waitFor();
  assert.equal(await security.locator('.security-hashes dt').count(), 4);
  assert.equal(await security.locator('.security-session').count(), 0);
  await security.getByText('Current version trusted', { exact: true }).waitFor();
  await screenshot(admin, 'skill-security-admin', prefix);
  await admin.setViewportSize({ width: 390, height: 844 });
  await admin.waitForTimeout(200);
  assert.ok(await security.evaluate((element) => element.scrollWidth <= element.clientWidth + 1));
  const approveBox = await security.locator('[data-approve-skill]').boundingBox();
  assert.ok(approveBox.y >= 0 && approveBox.y + approveBox.height <= 844);
  await screenshot(admin, 'skill-security-mobile', prefix);
  await security.getByRole('button', { name: 'Close', exact: true }).click();
  await admin.setViewportSize({ width: 1440, height: 1000 });
  await context.request.post(adminBase + '/admin/logout');
  assert.ok(
    securityRequests.length >= 4 &&
      securityRequests.every((url) => url.startsWith(adminBase + '/admin/v1/skill-security/')),
  );
  assert.equal((await context.request.get(securityUrl)).status(), 401);
  assert.equal(
    (await context.request.post(securityUrl, { data: { sha256: safety.current.sha256 } })).status(),
    401,
  );
  assert.deepEqual(errors, []);
  await work.close();
  await admin.close();
}
