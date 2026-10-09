import { ref } from 'vue';

export const theme = ref(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark');
export function setTheme(value) {
  theme.value = value === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme.value;
  try {
    localStorage.setItem('umeko:theme', theme.value);
  } catch {}
}
// Keep other tabs on this origin in sync with the preference.
function syncStorage(event) {
  if (event.key === 'umeko:theme') {
    theme.value = event.newValue === 'light' ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme.value;
  }
}
window.addEventListener('storage', syncStorage);
if (import.meta.hot)
  import.meta.hot.dispose(() => window.removeEventListener('storage', syncStorage));
