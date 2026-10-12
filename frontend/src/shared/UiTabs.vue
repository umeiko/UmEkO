<script setup>
import UiIcon from './UiIcon.vue';
const props = defineProps({ modelValue: String, items: Array, idPrefix: String, label: String });
const emit = defineEmits(['update:modelValue']);
function navigate(event, index) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const buttons = [...event.currentTarget.parentElement.querySelectorAll('[role=tab]')];
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? buttons.length - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
  emit('update:modelValue', props.items[next].id);
  buttons[next].focus();
}
</script>
<template>
  <nav class="ui-tabs" role="tablist" :aria-label="label">
    <button
      v-for="(item, index) in items"
      :id="`${idPrefix}-tab-${item.id}`"
      :key="item.id"
      type="button"
      role="tab"
      :aria-selected="modelValue === item.id"
      :aria-controls="`${idPrefix}-panel-${item.id}`"
      :tabindex="modelValue === item.id ? 0 : -1"
      :class="{ active: modelValue === item.id }"
      @click="emit('update:modelValue', item.id)"
      @keydown="navigate($event, index)"
    >
      <UiIcon v-if="item.icon" :name="item.icon" :size="16" />{{ item.label }}
      <span v-if="item.count !== undefined" class="badge">{{ item.count }}</span>
    </button>
  </nav>
</template>
<style scoped>
.ui-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--line);
  padding-bottom: 12px;
  margin-bottom: 18px;
}
.ui-tabs button {
  font-size: 14px;
}
.ui-tabs button.active {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}
@media (max-width: 600px) {
  .ui-tabs button {
    padding: 8px;
  }
}
</style>
