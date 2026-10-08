<script setup>
import { ref, watch, onMounted } from 'vue';
import UiIcon from './UiIcon.vue';
const props = defineProps({ modelValue: Boolean, title: String, wide: Boolean, busy: Boolean });
const emit = defineEmits(['update:modelValue', 'closed']);
const dialog = ref();
function sync() {
  if (!dialog.value) return;
  if (props.modelValue && !dialog.value.open) {
    const field = dialog.value.querySelector('input:not([type="checkbox"]),textarea,select');
    field?.setAttribute('autofocus', '');
    dialog.value.showModal();
    field?.focus();
    field?.removeAttribute('autofocus');
  } else if (!props.modelValue && dialog.value.open) dialog.value.close();
}
function close() {
  if (!props.busy) emit('update:modelValue', false);
}
watch(() => props.modelValue, sync, { flush: 'post' });
onMounted(sync);
</script>
<template>
  <dialog
    ref="dialog"
    class="ui-modal"
    :class="{ wide }"
    @cancel.prevent="close"
    @click="
      (e) => {
        if (e.target === dialog) close();
      }
    "
    @close="
      emit('update:modelValue', false);
      emit('closed');
    "
  >
    <div class="modal-header">
      <div class="heading-line">
        <h2>{{ title }}</h2>
        <slot name="help" />
      </div>
      <button type="button" class="icon-button" aria-label="关闭" :disabled="busy" @click="close">
        <UiIcon name="close" />
      </button>
    </div>
    <div class="modal-body"><slot /></div>
    <div v-if="$slots.footer" class="modal-footer"><slot name="footer" /></div>
  </dialog>
</template>
