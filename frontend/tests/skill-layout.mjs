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
  assert.ok(
    requests.every((url) => url.startsWith(publicBase + `/v1/sessions/${session.id}/skill-files/`)),
  );
  await screenshot(work, 'skill-layout-session', prefix);
  assert.deepEqual(errors, []);
  await work.close();
  await admin.close();
}
