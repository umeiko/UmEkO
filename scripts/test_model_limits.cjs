// Production admin page with deterministic API fixtures; no model or credentials used.
// node scripts/test_model_limits.cjs (or set LAB_PLAYWRIGHT to an existing package)
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.LAB_PLAYWRIGHT || 'playwright');
const staticDir = path.join(__dirname, '../umeko/server/static');
const output = path.join(__dirname, 'model-limits-evidence.local');

async function check(browser, width) {
  const context = await browser.newContext({viewport: {width, height: 900}});
  const page = await context.newPage();
  const errors = [], writes = [];
  const provider = {id: 'p_company', name: 'Company LiteLLM', base_url: 'https://models.example.com/v1',
    api_key: 'fixture-key', models: [
      {id: 'm_text', name: 'document-text-model', vision: false, active: true, max_concurrent_requests: 0},
      {id: 'm_vision', name: 'document-vision-model', vision: true, active: false, max_concurrent_requests: 5}
    ]};
  page.on('pageerror', error => errors.push(String(error)));
  await page.route('http://umeko-admin.test/**', async route => {
    const request = route.request(), pathname = new URL(request.url()).pathname;
    if (pathname === '/') return route.fulfill({contentType: 'text/html', body: fs.readFileSync(path.join(staticDir, 'admin.html'))});
    if (pathname.startsWith('/static/')) return route.fulfill({contentType: 'application/javascript', body: fs.readFileSync(path.join(staticDir, path.basename(pathname)))});
    let result;
    if (pathname === '/admin/v1/me') result = {id: 'fixture', username: 'UI fixture', role: 'admin'};
    else if (pathname === '/admin/v1/users') result = [];
    else if (pathname === '/admin/v1/runtime-config') result = {max_tool_iterations: 32};
    else if (pathname === '/admin/v1/providers') result = {providers: [provider], active_model_id: 'm_text'};
    else if (pathname.startsWith('/admin/v1/models/') && request.method() === 'PUT') {
      const document = request.postDataJSON();
      writes.push(document);
      assert(Number.isSafeInteger(document.max_concurrent_requests) && document.max_concurrent_requests >= 0);
      Object.assign(provider.models.find(model => model.id === pathname.split('/').pop()), document);
      return route.fulfill({status: 204});
    } else if (pathname === '/admin/v1/providers/import') {
      const document = request.postDataJSON().document;
      assert.equal(document.providers[0].name, provider.name);
      for (const model of document.providers[0].models) Object.assign(provider.models.find(item => item.name === model.name), model);
      result = {models_created: 0, providers_merged: 1};
    } else throw new Error(`Unexpected admin API: ${request.method()} ${pathname}`);
    return route.fulfill({contentType: 'application/json', body: JSON.stringify(result)});
  });
  await page.goto('http://umeko-admin.test/');
  await page.locator('#tab-config').click();
  assert.equal(await page.locator('#ml-m_text').inputValue(), '0');
  assert.equal(await page.locator('#ml-m_vision').inputValue(), '5');
  const save = () => page.locator('#ml-m_text').locator('..').getByRole('button', {name: '保存', exact: true}).click();
  await page.locator('#ml-m_text').fill('2');
  await save();
  await page.waitForFunction(() => document.querySelector('#toast').textContent.includes('并发上限已设为 2'));
  await page.reload();
  await page.locator('#tab-config').click();
  assert.equal(await page.locator('#ml-m_text').inputValue(), '2');
  assert.equal(await page.locator('#ml-m_vision').inputValue(), '5');
  for (const invalid of ['-1', '1.5', '']) {
    await page.locator('#ml-m_text').fill(invalid);
    await save();
    assert.equal(await page.locator('#toast').textContent(), '请输入非负整数，0 表示不限制');
    assert.equal(writes.length, 1);
  }
  await page.locator('#ml-m_text').fill('0');
  await save();
  await page.waitForFunction(() => document.querySelector('#toast').textContent === '已取消并发限制');
  assert.equal(writes.at(-1).max_concurrent_requests, 0);
  await page.locator('#prv-imp-toggle').click();
  await page.locator('#prv-import-text').fill(JSON.stringify([{name: 'document-text-model', max_concurrent_requests: 3}]));
  await page.locator('#prv-import-panel').getByRole('button', {name: '导入', exact: true}).click();
  await page.waitForFunction(() => document.querySelector('#ml-m_text').value === '3');
  assert.equal(await page.locator('#ml-m_vision').inputValue(), '5');
  await page.screenshot({path: path.join(output, `admin-${width}.png`), fullPage: true});
  assert.deepEqual(errors, []);
  await context.close();
  return {width, checks: 'per-model save, defaults, refresh, validation, unlimited, JSON import', errors};
}

(async () => {
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true});
  try {
    const results = [];
    for (const width of [1440, 1000]) results.push(await check(browser, width));
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
