<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue';
import hljs from 'highlight.js/lib/common';
const props = defineProps({
  modelValue: String,
  language: { default: 'plaintext' },
  id: String,
  disabled: Boolean,
});
const emit = defineEmits(['update:modelValue']);
const input = ref(),
  paint = ref();
let observer;
const highlighted = computed(
  () => hljs.highlight(props.modelValue || '', { language: props.language }).value + '\n',
);
function sync() {
  if (!input.value || !paint.value) return;
  paint.value.style.paddingRight = 20 + input.value.offsetWidth - input.value.clientWidth + 'px';
  paint.value.scrollTop = input.value.scrollTop;
  paint.value.scrollLeft = input.value.scrollLeft;
}
async function indent(e) {
  if (e.key !== 'Tab') return;
  e.preventDefault();
  const start = e.target.selectionStart,
    end = e.target.selectionEnd;
  emit(
    'update:modelValue',
    props.modelValue.slice(0, start) + '    ' + props.modelValue.slice(end),
  );
  await nextTick();
  input.value.selectionStart = input.value.selectionEnd = start + 4;
  sync();
}
watch(
  () => props.modelValue,
  () => nextTick(sync),
);
onMounted(() => {
  observer = new ResizeObserver(sync);
  observer.observe(input.value);
  sync();
});
onBeforeUnmount(() => observer?.disconnect());
</script>
<template>
  <div class="source-editor">
    <pre
      ref="paint"
      class="source-paint"
      aria-hidden="true"
    ><code class="hljs" v-html="highlighted"></code></pre>
    <textarea
      ref="input"
      :id="id"
      :value="modelValue"
      :disabled="disabled"
      class="source-input"
      spellcheck="false"
      aria-label="技能文件编辑器"
      @input="emit('update:modelValue', $event.target.value)"
      @scroll="sync"
      @keydown="indent"
    />
  </div>
</template>
<style scoped>
.source-editor {
  position: relative;
  flex: 1;
  min-height: 450px;
  background: var(--field);
  min-width: 0;
}
.source-paint,
.source-input {
  position: absolute;
  inset: 0;
  margin: 0;
  border: 0;
  border-radius: 0;
  padding: 20px;
  font: 14px/1.8 var(--mono);
  tab-size: 4;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  word-break: break-all;
  letter-spacing: normal;
}
.source-paint {
  overflow: hidden;
  pointer-events: none;
  max-height: none;
  color: var(--ink);
}
.source-input {
  width: 100%;
  height: 100%;
  resize: none;
  overflow: auto;
  background: transparent;
  color: transparent;
  -webkit-text-fill-color: transparent;
  caret-color: var(--ink);
  box-shadow: none;
}
.source-input::selection {
  background: var(--accent-border);
}
.source-input:focus {
  box-shadow: inset 0 0 0 1px var(--accent-border);
}
.source-paint .hljs {
  display: inline;
  padding: 0;
  background: transparent;
  font: inherit;
  white-space: inherit;
}
</style>
