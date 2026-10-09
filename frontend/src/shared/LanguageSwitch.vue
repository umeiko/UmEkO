<script setup>
import { adminLanguages, useAdminI18n } from './adminI18n.js';
const { tr, locale, setLocale } = useAdminI18n();
</script>
<template>
  <select
    class="language-switch"
    data-language-select
    :value="locale"
    :aria-label="tr('界面语言')"
    :title="tr('界面语言')"
    @change="setLocale($event.target.value)"
  >
    <option v-for="language in adminLanguages" :key="language.value" :value="language.value">
      {{ language.label }}
    </option>
  </select>
</template>
<style scoped>
.language-switch {
  width: auto;
  min-width: 112px;
  max-width: 150px;
  min-height: 34px;
  padding: 6px 10px;
  font-size: 13px;
}
</style>
