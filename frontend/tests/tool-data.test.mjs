import test from 'node:test';
import assert from 'node:assert/strict';
import { prettyToolData } from '../src/workspace/toolData.js';

test('live and persisted directory trees preserve real line breaks and indentation', () => {
  const tree = 'workspace/\n├── fig7_2.png (22.7 KB)\n└── reports/\n    └── output.md';
  assert.equal(prettyToolData(tree, 'empty'), tree);
  assert.equal(prettyToolData(JSON.stringify(tree), 'empty'), tree);
});

test('persisted parameters unwrap their JSON string before formatting the object', () => {
  const params = { directory: 'workspace', path: 'C:\\new\\test.txt' };
  const expected = JSON.stringify(params, null, 2);
  for (const value of [params, JSON.stringify(params), JSON.stringify(JSON.stringify(params))])
    assert.equal(prettyToolData(value, 'empty'), expected);
});

test('plain text, Markdown and literal backslashes are not interpreted as markup or escapes', () => {
  for (const text of [
    'C:\\new\\test.txt',
    'literal \\n text',
    '**标题**\n<script>unsafe()</script>',
    '[section]\n  item',
  ]) {
    assert.equal(prettyToolData(text, 'empty'), text);
    assert.equal(prettyToolData(JSON.stringify(text), 'empty'), text);
  }
});

test('structured and empty tool values retain their meaning', () => {
  assert.equal(prettyToolData('[1,2]', 'empty'), '[\n  1,\n  2\n]');
  assert.equal(prettyToolData(false, 'empty'), 'false');
  assert.equal(prettyToolData(0, 'empty'), '0');
  for (const value of [null, undefined, '']) assert.equal(prettyToolData(value, 'empty'), 'empty');
});
