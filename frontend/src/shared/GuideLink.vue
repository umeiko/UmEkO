<script setup>
import UiIcon from './UiIcon.vue';
import { guideUrl } from './api.js';
import { useAdminI18n } from './adminI18n.js';
defineProps({ localized: Boolean });
const { tr } = useAdminI18n();
</script>
<template>
  <a
    class="guide-link"
    :href="guideUrl()"
    target="_blank"
    rel="noopener noreferrer"
    :title="tr('使用文档')"
    :data-i18n-title="localized ? 'guide.title' : undefined"
  >
    <UiIcon name="book" :size="17" />
    <span :data-i18n="localized ? 'guide.title' : undefined">{{ tr('使用文档') }}</span>
  </a>
</template>
<style scoped>
.guide-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 9px;
  border-radius: 7px;
  font-size: 13px;
  line-height: 1.4;
  color: inherit;
  text-decoration: none;
  white-space: nowrap;
}
.guide-link:hover {
  background: color-mix(in srgb, currentColor 7%, transparent);
}
.guide-link:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
}
@media (max-width: 560px) {
  .guide-link span {
    display: none;
  }
}
</style>
