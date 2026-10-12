import assert from 'node:assert/strict';
import test from 'node:test';
import { TreeSelection, topLevelEntries, copyEntryName } from '../src/workspace/treeSelection.js';

const rows = ['a.txt', 'folder', 'folder/b.txt', 'c.txt', 'd.txt'];
const paths = (selection) => [...selection.selected];

test('ordinary click establishes the Shift anchor, ranges grow and shrink', () => {
  const state = new TreeSelection();
  state.select(rows[0]);
  state.select(rows[3], { range: true }, rows);
  assert.deepEqual(paths(state), rows.slice(0, 4));
  state.select(rows[1], { range: true }, rows);
  assert.deepEqual(paths(state), rows.slice(0, 2));
  assert.equal(state.anchor, rows[0]);
});

test('Ctrl toggles and Ctrl+Shift keeps unrelated selections while shrinking the range', () => {
  const state = new TreeSelection();
  state.select(rows[4]);
  state.select(rows[0], { toggle: true });
  state.select(rows[3], { range: true, additive: true }, rows);
  assert.equal(state.selected.size, 5);
  state.select(rows[1], { range: true, additive: true }, rows);
  assert.deepEqual(paths(state), [rows[4], rows[0], rows[1]]);
  state.select(rows[4], { toggle: true });
  assert.deepEqual(paths(state), [rows[0], rows[1]]);
});

test('context menu preserves the group on a selected item and replaces it on another item', () => {
  const state = new TreeSelection();
  state.select(rows[0]);
  state.select(rows[1], { toggle: true });
  state.context(rows[0]);
  assert.deepEqual(paths(state), rows.slice(0, 2));
  assert.equal(state.anchor, rows[1]);
  state.context(rows[4]);
  assert.deepEqual(paths(state), [rows[4]]);
});

test('Shift uses visible rows and safely recovers when its anchor was removed', () => {
  const state = new TreeSelection();
  state.select(rows[0]);
  state.select(
    rows[3],
    { range: true },
    rows.filter((path) => path !== rows[2]),
  );
  assert.deepEqual(paths(state), [rows[0], rows[1], rows[3]]);
  state.retain(rows.slice(1));
  assert.equal(state.anchor, null);
  state.select(rows[4], { range: true }, rows.slice(1));
  assert.deepEqual(paths(state), [rows[4]]);
  state.clear();
  assert.equal(state.selected.size, 0);
  assert.equal(state.anchor, null);
});

test('batch operations process selected parent directories only once', () => {
  const entries = [
    { path: 'workspace/folder', type: 'directory' },
    { path: 'workspace/folder/a.txt', type: 'file' },
    { path: 'workspace/folder/nested', type: 'directory' },
    { path: 'workspace/folder-two/a.txt', type: 'file' },
  ];
  assert.deepEqual(topLevelEntries(entries), [entries[0], entries[3]]);
});

test('duplicate copy names keep file extensions, dotfiles and directory names', () => {
  assert.equal(copyEntryName({ name: 'report.md', type: 'file' }, 1), 'report_copy.md');
  assert.equal(copyEntryName({ name: 'report.md', type: 'file' }, 2), 'report_copy_2.md');
  assert.equal(copyEntryName({ name: '.config', type: 'file' }, 1), '.config_copy');
  assert.equal(copyEntryName({ name: 'folder.v1', type: 'directory' }, 1), 'folder.v1_copy');
});
