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
  assert.deepEqual(errors, []);
  await work.close();
  await admin.close();
}
