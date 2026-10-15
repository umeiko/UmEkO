<script setup>
import { ref, computed, watch } from 'vue';
import UiModal from '../shared/UiModal.vue';
import { encode } from '../shared/api.js';
import { useAdminI18n } from '../shared/adminI18n.js';
import { api, notify } from './state.js';
const { tr } = useAdminI18n();
const props = defineProps({ modelValue: Boolean, user: Object });
const emit = defineEmits(['update:modelValue']);
const tools = ref([]),
  selected = ref(null),
  loading = ref(false),
  saving = ref(false),
  error = ref('');
const configurable = computed(() => tools.value.filter((t) => !t.required));
const globalNames = computed(() => configurable.value.filter((t) => t.enabled).map((t) => t.name));
const checked = (tool) =>
  tool.required || (selected.value === null ? tool.enabled : selected.value.includes(tool.name));
let requestVersion = 0;
function toggle(name, enabled) {
  const current = selected.value === null ? globalNames.value : selected.value;
  selected.value = enabled ? [...new Set([...current, name])] : current.filter((n) => n !== name);
}
watch(
  () => [props.modelValue, props.user?.id],
  async ([open, uid]) => {
    const version = ++requestVersion;
    if (!open || !uid) return;
    loading.value = true;
    error.value = '';
    tools.value = [];
    try {
      const data = await api('GET', `/admin/v1/users/${encode(uid)}/tool-access`);
      if (version === requestVersion) {
        tools.value = data.tools;
        selected.value = data.allowed_tool_names;
      }
    } catch (e) {
      if (version === requestVersion) error.value = e.message;
    } finally {
      if (version === requestVersion) loading.value = false;
    }
  },
);
async function save() {
  saving.value = true;
  error.value = '';
  try {
    await api('PUT', `/admin/v1/users/${encode(props.user.id)}/tool-access`, {
      allowed_tool_names: selected.value,
    });
    emit('update:modelValue', false);
    notify(tr('用户工具权限已保存'));
  } catch (e) {
    error.value = e.message;
  } finally {
    saving.value = false;
  }
}
</script>
<template>
  <UiModal
    id="user-tool-access"
    :model-value="modelValue"
    :busy="saving"
    wide
    :title="tr('工具权限') + ' · ' + (user?.username || '')"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <form id="user-tool-access-form" class="stack" @submit.prevent="save">
      <p class="muted">
        {{
          tr(
            '默认跟随全局下发。可单独授权未全局下发的工具；取消全部可配置工具不会禁用机器任务答案提交。',
          )
        }}
      </p>
      <fieldset :disabled="loading || saving" class="stack">
        <legend>{{ tr('用户工具开放范围') }}</legend>
        <div class="row">
          <label class="check"
            ><input
              id="user-inherit-tools"
              type="checkbox"
              :checked="selected === null"
              @change="selected = $event.target.checked ? null : globalNames"
            />{{ tr('跟随全局下发（含以后新增）') }}</label
          ><button type="button" @click="selected = []">{{ tr('清空工具选择') }}</button>
        </div>
        <label v-for="tool in tools" :key="tool.name" class="check"
          ><input
            :id="'user-tool-' + tool.name"
            type="checkbox"
            :checked="checked(tool)"
            :disabled="tool.required"
            @change="toggle(tool.name, $event.target.checked)"
          /><span
            >{{ tr(tool.title) }} <code>{{ tool.name }}</code></span
          ><small v-if="tool.required" class="badge">{{ tr('协议必需') }}</small
          ><small v-else-if="!tool.enabled" class="badge">{{ tr('未全局下发') }}</small></label
        >
      </fieldset>
      <p v-if="error" class="feedback bad" role="alert">{{ error }}</p>
    </form>
    <template #footer
      ><button :disabled="saving" @click="emit('update:modelValue', false)">{{ tr('取消') }}</button
      ><button
        id="user-tool-access-save"
        class="primary"
        form="user-tool-access-form"
        :disabled="loading || saving || !tools.length"
      >
        {{ tr('保存') }}
      </button></template
    >
  </UiModal>
</template>
<style scoped>
.check span {
  min-width: 0;
  overflow-wrap: anywhere;
}
fieldset {
  max-height: 55vh;
  overflow: auto;
}
</style>
