// Selection follows the visible tree order; focus and the range anchor are independent.
export class TreeSelection {
  selected = new Set();
  anchor = null;
  focus = null;
  rangeBase = null;

  select(path, { toggle = false, range = false, additive = false } = {}, visible = []) {
    this.focus = path;
    const start = visible.indexOf(this.anchor);
    const end = visible.indexOf(path);
    if (range && start >= 0 && end >= 0) {
      if (!this.rangeBase || this.rangeBase.additive !== additive)
        this.rangeBase = { additive, selected: additive ? new Set(this.selected) : new Set() };
      this.selected.clear();
      for (const entry of this.rangeBase.selected) this.selected.add(entry);
      for (const entry of visible.slice(Math.min(start, end), Math.max(start, end) + 1))
        this.selected.add(entry);
      return;
    }
    this.rangeBase = null;
    this.anchor = path;
    if (toggle) {
      if (this.selected.has(path)) this.selected.delete(path);
      else this.selected.add(path);
    } else {
      this.selected.clear();
      this.selected.add(path);
    }
  }

  context(path) {
    if (!this.selected.has(path)) this.select(path);
    else this.focus = path;
  }

  retain(paths) {
    const present = new Set(paths);
    for (const path of this.selected) if (!present.has(path)) this.selected.delete(path);
    if (!present.has(this.anchor)) this.anchor = null;
    if (!present.has(this.focus)) this.focus = null;
    if (this.rangeBase)
      for (const path of this.rangeBase.selected)
        if (!present.has(path)) this.rangeBase.selected.delete(path);
  }

  clear() {
    this.selected.clear();
    this.anchor = this.focus = this.rangeBase = null;
  }
}

export function topLevelEntries(entries) {
  return entries.filter(
    (entry) =>
      !entries.some(
        (parent) => parent.type === 'directory' && entry.path.startsWith(parent.path + '/'),
      ),
  );
}

export function copyEntryName(entry, index) {
  const dot = entry.type === 'file' ? entry.name.lastIndexOf('.') : -1;
  const split = dot > 0 ? dot : entry.name.length;
  return `${entry.name.slice(0, split)}_copy${index > 1 ? `_${index}` : ''}${entry.name.slice(split)}`;
}
