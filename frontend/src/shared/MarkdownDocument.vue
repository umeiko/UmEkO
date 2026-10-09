<script setup>
import { computed, onBeforeUnmount } from 'vue';
import { renderSkillMarkdown, renderMarkdown } from './markdown.js';
import { copyText } from './clipboard.js';
const props = defineProps({ content: String, skill: Boolean });
const translate = (key) =>
  ({
    'code.copy': '复制代码',
    'skill.metadata': '技能信息',
  })[key] || key;
const rendered = computed(() =>
  (props.skill ? renderSkillMarkdown : renderMarkdown)(props.content, { translate }),
);
const timers = new Set();
async function copy(event) {
  const button = event.target.closest('[data-code-copy]');
  if (!button || button.disabled) return;
  const label = button.querySelector('.copy-label');
  button.disabled = true;
  try {
    await copyText(button.closest('.markdown-code').querySelector('pre code').textContent);
    label.textContent = '已复制';
    button.classList.add('copied');
  } catch {
    label.textContent = '复制失败';
  } finally {
    button.disabled = false;
    const timer = setTimeout(() => {
      timers.delete(timer);
      if (button.isConnected) {
        label.textContent = '复制代码';
        button.classList.remove('copied');
      }
    }, 1500);
    timers.add(timer);
  }
}
onBeforeUnmount(() => {
  for (const timer of timers) clearTimeout(timer);
});
</script>
<template>
  <article class="markdown-body" v-html="rendered" @click="copy"></article>
</template>
