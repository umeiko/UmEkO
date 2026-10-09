export function errorMessage(
  detail,
  status,
  translate = (text, values = {}) =>
    text.replace(/\{(\w+)\}/g, (match, key) => String(values[key] ?? match)),
) {
  if (typeof detail === 'string') return translate(detail);
  if (Array.isArray(detail))
    return detail.map((item) => errorMessage(item, status, translate)).join(translate('；'));
  if (detail && typeof detail === 'object') {
    const names = {
      name: '名称',
      expires_days: '有效天数',
      scopes: '权限',
      username: '用户名',
      password: '密码',
      slug: '访问路径',
    };
    const field = translate(names[detail.loc?.at(-1)] || detail.loc?.at(-1) || '输入');
    const limits = detail.ctx || {};
    if (detail.type === 'missing') return translate('{field}不能为空', { field });
    if (detail.type === 'string_too_short')
      return translate('{field}至少需要 {min} 个字符', { field, min: limits.min_length });
    if (detail.type === 'string_too_long')
      return translate('{field}不能超过 {max} 个字符', { field, max: limits.max_length });
    if (detail.type === 'greater_than_equal')
      return translate('{field}不能小于 {min}', { field, min: limits.ge });
    if (detail.type === 'less_than_equal')
      return translate('{field}不能大于 {max}', { field, max: limits.le });
    if (detail.type?.startsWith('int_')) return translate('{field}必须是整数', { field });
    return translate('{field}：{message}', {
      field,
      message: detail.msg || translate('格式不正确'),
    });
  }
  return translate('请求失败（{status}）', { status });
}
export const deploymentPrefix = () => {
  const value = document.querySelector('meta[name="umeko-base-path"]')?.content || '';
  return value.startsWith('__') ? '' : value;
};
export const appUrl = (path) => deploymentPrefix() + path;
export const encode = encodeURIComponent;
export function bytes(value = 0) {
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(i ? 1 : 0)} ${units[i]}`;
}
export function date(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';
}
