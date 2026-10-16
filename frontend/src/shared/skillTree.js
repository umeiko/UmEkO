export function skillTree(files) {
  const root = { children: [] };
  for (const file of files) {
    const parts = (file.path || file.name).split('/');
    let node = root;
    parts.forEach((name, index) => {
      const path = parts.slice(0, index + 1).join('/');
      let child = node.children.find((item) => item.path === path);
      if (!child) {
        child = { name, path, children: [], directory: index < parts.length - 1 };
        node.children.push(child);
      }
      node = child;
      if (index === parts.length - 1) node.file = file;
    });
  }
  function sort(nodes) {
    nodes.sort((a, b) => Number(b.directory) - Number(a.directory) || a.name.localeCompare(b.name));
    nodes.forEach((node) => sort(node.children));
    return nodes;
  }
  return sort(root.children);
}
