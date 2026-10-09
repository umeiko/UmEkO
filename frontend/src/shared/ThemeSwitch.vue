<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { theme, setTheme } from './theme.js';
import UiIcon from './UiIcon.vue';
const props = defineProps({ localized: Boolean });
const locale = ref(document.documentElement.lang);
const labels = {
  'zh-CN': ['浅色', '深色', '切换为'],
  'zh-TW': ['淺色', '深色', '切換為'],
  en: ['Light', 'Dark', 'Switch to'],
  ko: ['라이트', '다크', '전환:'],
  fr: ['Clair', 'Sombre', 'Passer au thème'],
  de: ['Hell', 'Dunkel', 'Wechseln zu'],
  it: ['Chiaro', 'Scuro', 'Passa a'],
};
const next = computed(() => (theme.value === 'dark' ? 'light' : 'dark'));
const words = computed(() => labels[props.localized ? locale.value : 'zh-CN'] || labels.en);
const caption = computed(() => words.value[next.value === 'light' ? 0 : 1]);
let observer;
onMounted(() => {
  observer = new MutationObserver(() => {
    locale.value = document.documentElement.lang;
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
});
onBeforeUnmount(() => observer?.disconnect());
</script>
<template>
  <button
    type="button"
    class="theme-switch"
    data-theme-toggle
    :title="words[2] + ' ' + caption"
    :aria-label="words[2] + ' ' + caption"
    @click="setTheme(next)"
  >
    <UiIcon :name="next === 'light' ? 'sun' : 'moon'" :size="15" /><span>{{ caption }}</span>
  </button>
</template>
