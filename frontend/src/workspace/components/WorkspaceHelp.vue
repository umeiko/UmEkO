<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import HelpTip from '../../shared/HelpTip.vue';
import { t, currentLocale } from '../i18n.js';
const props = defineProps({ helpKey: String, vars: Object });
const locale = ref(currentLocale());
const text = computed(() => {
  locale.value;
  return t(props.helpKey, props.vars);
});
const label = computed(() => {
  locale.value;
  return t('help.label');
});
function changed() {
  locale.value = currentLocale();
}
onMounted(() => document.addEventListener('localechange', changed));
onBeforeUnmount(() => document.removeEventListener('localechange', changed));
</script>
<template><HelpTip :text="text" :label="label" /></template>
