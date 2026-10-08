<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, useId } from 'vue';
const props = defineProps({ text: String, label: { default: '查看说明' } });
const trigger = ref(),
  tip = ref();
let timer;
const tipId = useId();
function close() {
  clearTimeout(timer);
  if (tip.value?.matches(':popover-open')) tip.value.hidePopover();
}
async function open() {
  clearTimeout(timer);
  await nextTick();
  if (!tip.value || !trigger.value) return;
  if (!tip.value.matches(':popover-open')) tip.value.showPopover();
  const a = trigger.value.getBoundingClientRect(),
    b = tip.value.getBoundingClientRect();
  let x = Math.max(12, Math.min(a.left, innerWidth - b.width - 12)),
    y = a.top - b.height - 8;
  if (y < 12) {
    y = a.bottom + 8;
    if (a.right + b.width + 20 <= innerWidth) {
      x = a.right + 8;
      y = a.top;
    }
  }
  tip.value.style.left = x + 'px';
  tip.value.style.top = Math.max(12, Math.min(y, innerHeight - b.height - 12)) + 'px';
}
function later() {
  timer = setTimeout(() => {
    if (!trigger.value.matches(':hover,:focus-visible') && !tip.value.matches(':hover')) close();
  }, 180);
}
function keep() {
  clearTimeout(timer);
}
function outside(e) {
  if (!trigger.value?.contains(e.target) && !tip.value?.contains(e.target)) close();
}
function escape(e) {
  if (e.key === 'Escape' && tip.value?.matches(':popover-open')) {
    e.preventDefault();
    e.stopPropagation();
    close();
  }
}
function scroll(e) {
  if (!tip.value?.contains(e.target)) close();
}
onMounted(() => {
  document.addEventListener('pointerdown', outside);
  document.addEventListener('keydown', escape, true);
  window.addEventListener('resize', close);
  document.addEventListener('scroll', scroll, true);
  document.addEventListener('close', close, true);
});
onBeforeUnmount(() => {
  close();
  document.removeEventListener('pointerdown', outside);
  document.removeEventListener('keydown', escape, true);
  window.removeEventListener('resize', close);
  document.removeEventListener('scroll', scroll, true);
  document.removeEventListener('close', close, true);
});
</script>
<template>
  <span class="help-wrap"
    ><button
      ref="trigger"
      type="button"
      class="help-trigger"
      :aria-label="label"
      :aria-describedby="tipId"
      @mouseenter="open"
      @mouseleave="later"
      @focus="open"
      @blur="later"
      @click="open"
    >
      ?</button
    ><span
      ref="tip"
      :id="tipId"
      class="help-popover"
      popover="manual"
      role="tooltip"
      @mouseenter="keep"
      @mouseleave="later"
      >{{ text }}</span
    ></span
  >
</template>
