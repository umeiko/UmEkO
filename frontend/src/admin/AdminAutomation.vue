<script setup>
import UiIcon from '../shared/UiIcon.vue';
import { copyText } from '../shared/clipboard.js';
import { useAdminI18n } from '../shared/adminI18n.js';
import { notify } from './state.js';
import { adminAutomationPrompt, adminAutomationUrls } from './automation.js';
defineProps({ compact: Boolean });
const { tr } = useAdminI18n();
async function copy() {
  try {
    await copyText(adminAutomationPrompt(tr));
    notify(tr('AI 管理接入提示词已复制'));
  } catch {
    notify(tr('复制失败'), true);
  }
}
</script>
<template>
  <div class="admin-automation" :class="{ compact }">
    <button
      type="button"
      data-admin-automation-copy
      :title="tr('复制 AI 管理提示词')"
      :aria-label="tr('复制 AI 管理提示词')"
      @click="copy"
    >
      <UiIcon name="copy" :size="16" /><span>{{
        compact ? tr('AI 管理') : tr('复制 AI 管理提示词')
      }}</span>
    </button>
    <a
      :href="adminAutomationUrls().skill"
      class="icon-button"
      :title="tr('下载管理 Skill')"
      :aria-label="tr('下载管理 Skill')"
      download="SKILL.md"
      ><UiIcon name="download" :size="17"
    /></a>
  </div>
</template>
<style scoped>
.admin-automation {
  display: flex;
  align-items: center;
  gap: 5px;
}
.admin-automation > button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
}
.admin-automation:not(.compact) {
  margin-top: 12px;
}
.admin-automation:not(.compact) > button {
  flex: 1;
}
.admin-automation a {
  color: var(--muted);
  text-decoration: none;
}
@media (max-width: 760px) {
  .compact > button span {
    display: none;
  }
}
</style>
