import test from 'node:test';
import assert from 'node:assert/strict';
import { renderMarkdown } from '../src/workspace/markdown.js';

test('render common Markdown rather than exposing formatting markers', () => {
  const html = renderMarkdown(
    '# 标题\n\n**粗体**、*斜体*、~~删除~~ 和 `code`\n\n1. 第一项\n2. 第二项\n   - 子项\n\n> 引用\n\n| 项目 | 结果 |\n| --- | --- |\n| 图像 | 通过 |',
  );
  for (const tag of ['h1', 'strong', 'em', 's', 'code', 'ol', 'ul', 'blockquote', 'table'])
    assert.match(html, new RegExp('<' + tag + '[ >]'));
  assert.ok(!html.includes('**粗体**'));
});

test('code blocks preserve whitespace, highlight known languages and handle unfinished fences', () => {
  const html = renderMarkdown('```python\ndef greet():\n    print("Hello")\n```');
  assert.match(html, /class="markdown-code"/);
  assert.match(html, /data-code-copy/);
  assert.match(html, /hljs-keyword/);
  assert.match(html, /    /);
  const partial = renderMarkdown('```unknown\n<x>\n', { highlight: false });
  assert.match(partial, /&lt;x&gt;/);
  assert.ok(!partial.includes('<x>'));
  assert.match(partial, /<\/code><\/pre>/);
});

test('raw HTML, executable links and code info cannot inject markup', () => {
  const html = renderMarkdown(
    '<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n```"><img src=x onerror=alert(1)>\n<svg onload=alert(1)>\n```',
  );
  assert.ok(!/<script|<img|href="javascript:/i.test(html));
  assert.ok(!/onload="|onerror="/i.test(html));
  assert.match(html, /&lt;script&gt;/);
});

test('session links and relative image paths retain the deployment prefix', () => {
  const html = renderMarkdown(
    '[文件](workspace-file:generate%2Freport.md)\n\n[表格](../attachments/table.csv)\n\n![图片](figure.png)\n\n[外链](https://example.com)',
    {
      path: 'generate/report.md',
      workspaceUrl: (path) => '/prefix/v1/file?path=' + encodeURIComponent(path),
    },
  );
  assert.match(html, /data-workspace-path="generate%2Freport.md"/);
  assert.match(html, /data-workspace-path="attachments%2Ftable.csv"/);
  assert.match(html, /src="\/prefix\/v1\/file\?path=generate%2Ffigure.png"/);
  assert.match(html, /rel="noopener noreferrer"/);
  const invalid = renderMarkdown(
    '[越界](workspace-file:..%2F..%2Fsecret)\n\n![越界](../../../secret.png)',
    { path: 'generate/report.md' },
  );
  assert.ok(!invalid.includes('data-workspace-path'));
  assert.ok(!invalid.includes('<img'));
});
