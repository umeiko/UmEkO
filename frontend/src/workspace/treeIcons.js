// Fixed-size SVGs for controller-rendered tree rows. No HTML from file names.
const file = 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z M14 2v6h6';
const paths = {
  folder: 'M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z',
  image: 'M3 3h18v18H3Z M8 7h.01 M3 17l6-6 4 4 3-3 5 5',
  text: file + ' M8 12h8 M8 16h6',
  code: file + ' M10 12l-3 3 3 3 M14 12l3 3-3 3',
  archive: file + ' M10 3v2 M10 7v2 M10 11v2 M9 16h3v3H9Z',
  table: file + ' M7 12h10v7H7Z M7 15h10 M11 12v7',
  document: file,
};
function fileType(name) {
  const ext = name.split('.').pop().toLowerCase();
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'tiff', 'tif'].includes(ext))
    return 'image';
  if (['md', 'markdown', 'txt', 'log'].includes(ext)) return 'text';
  if (['xml', 'json', 'yaml', 'yml', 'html', 'htm', 'py', 'js', 'ts', 'css', 'sh'].includes(ext))
    return 'code';
  if (['zip', '7z', 'rar', 'tar', 'gz', 'bz2', 'xz', 'tgz', 'wim', 'jar', 'war'].includes(ext))
    return 'archive';
  if (['csv', 'tsv', 'xlsx', 'xls'].includes(ext)) return 'table';
  return 'document';
}
export function treeIcon(name, directory = false) {
  const type = directory ? 'folder' : fileType(name);
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.classList.add('tree-icon', `tree-icon-${type}`);
  for (const [key, value] of Object.entries({
    viewBox: '0 0 24 24',
    width: 20,
    height: 20,
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': 1.6,
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'aria-hidden': 'true',
    focusable: 'false',
  }))
    svg.setAttribute(key, value);
  const path = document.createElementNS(ns, 'path');
  path.setAttribute('d', paths[type]);
  svg.append(path);
  return svg;
}
