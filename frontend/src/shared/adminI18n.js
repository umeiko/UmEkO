import { ref, readonly, watch } from 'vue';
import english from './admin.en.json';

export const adminLanguages = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en', label: 'English' },
];
const supported = (value) => adminLanguages.some((language) => language.value === value);
function detect() {
  try {
    const saved = localStorage.getItem('umeko:locale');
    if (supported(saved)) return saved;
    if (saved) return saved.startsWith('zh') ? 'zh-CN' : 'en';
  } catch {}
  return navigator.language.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
}
const locale = ref(detect());
function tr(source, values = {}) {
  const text = locale.value === 'en' ? (english[source] ?? source) : source;
  // Replace each placeholder once, without interpreting names or user data as code.
  return text.replace(/\{(\w+)\}/g, (match, key) => String(values[key] ?? match));
}
function setLocale(value) {
  locale.value = supported(value) ? value : 'zh-CN';
  try {
    localStorage.setItem('umeko:locale', locale.value);
  } catch {}
}
function date(value) {
  return value ? new Date(value).toLocaleString(locale.value, { hour12: false }) : '—';
}
export function useAdminI18n() {
  return { tr, locale: readonly(locale), setLocale, date };
}
// Only the admin entry point opts in; shared help components also appear in the workbench.
export function initAdminI18n() {
  const stop = watch(
    locale,
    (value) => {
      document.documentElement.lang = value;
      document.title = `UMEKO · ${tr('控制台')}`;
    },
    { immediate: true },
  );
  const storage = (event) => {
    if (event.key === 'umeko:locale')
      locale.value = supported(event.newValue) ? event.newValue : detect();
  };
  window.addEventListener('storage', storage);
  return () => {
    stop();
    window.removeEventListener('storage', storage);
  };
}
