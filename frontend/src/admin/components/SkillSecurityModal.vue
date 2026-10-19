<script setup>
import { ref, watch } from 'vue';
import { api, confirm, notify } from '../state.js';
import { encode } from '../../shared/api.js';
import { useAdminI18n } from '../../shared/adminI18n.js';
import UiModal from '../../shared/UiModal.vue';
import UiIcon from '../../shared/UiIcon.vue';
import HelpTip from '../../shared/HelpTip.vue';
const { tr, date } = useAdminI18n();
const props = defineProps({ modelValue: Boolean, pack: String, member: String });
const emit = defineEmits(['update:modelValue']);
const data = ref(null),
  loading = ref(false),
  busy = ref(false),
  error = ref('');
let sequence = 0;
const labels = {
  trusted: '当前版本已信任',
  changed: '文件已变化，需重新确认',
  unlisted: '当前版本未加入白名单',
  revoked: '已移出可信区',
};
const endpoint = () => `/admin/v1/skill-security/${encode(props.pack)}/${encode(props.member)}`;
async function load() {
  const ticket = ++sequence;
  loading.value = true;
  error.value = '';
  try {
    const response = await api('GET', endpoint());
    if (ticket === sequence) data.value = response;
  } catch (e) {
    if (ticket === sequence) error.value = e.message;
  } finally {
    if (ticket === sequence) loading.value = false;
  }
}
watch(
  () => [props.modelValue, props.pack, props.member],
  () => {
    sequence++;
    if (!props.modelValue) return;
    data.value = null;
    load();
  },
);
async function approve() {
  if (!data.value || busy.value || loading.value || data.value.trusted) return;
  busy.value = true;
  error.value = '';
  try {
    data.value = await api('POST', endpoint(), { sha256: data.value.current.sha256 });
    if (data.value.trusted) notify(tr('当前文件版本已加入可信白名单'));
  } catch (e) {
    error.value = e.message;
    await load();
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function revoke() {
  if (!data.value?.approved || busy.value || loading.value) return;
  if (
    !(await confirm(
      tr('移出可信区'),
      tr('将 {count} 个文件移出可信区？已下发会话的后续调用也会被阻止，正在执行的脚本不受影响。', {
        count: 1,
      }),
    ))
  )
    return;
  busy.value = true;
  try {
    await api('DELETE', endpoint(), { sha256: data.value.approved.sha256 });
    await load();
    notify(tr('已移出可信区'));
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <UiModal
    class="skill-security-modal"
    :model-value="modelValue"
    :title="tr('文件安全门禁')"
    wide
    :busy="busy"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #help>
      <HelpTip
        :text="
          tr(
            '仅批准管理员库中已保存文件的当前版本，用于后续新会话下发与管理端测试。修改后需重新确认；入口、辅助模块和配置都必须通过校验。旧会话不重新下发。',
          )
        "
      />
    </template>
    <section class="skill-security" data-skill-security>
      <div class="security-heading">
        <strong class="security-path">{{ pack }}/{{ data?.member || member }}</strong>
        <span class="security-pill"
          ><UiIcon name="shield" :size="16" />{{ tr('用户与模型只读') }}</span
        >
      </div>
      <p v-if="error" class="feedback bad" role="alert">{{ error }}</p>
      <p v-if="loading && !data" role="status">{{ tr('正在读取…') }}</p>
      <template v-if="data">
        <div class="security-status" :class="data.status" data-trust-status role="status">
          <UiIcon name="shield" :size="20" />{{ tr(labels[data.status]) }}
        </div>
        <div class="security-section">
          <h3>{{ tr('管理员库当前摘要') }}</h3>
          <dl class="security-hashes">
            <dt>MD5</dt>
            <dd>
              <code data-current-md5>{{ data.current.md5 }}</code>
            </dd>
            <dt>SHA-256</dt>
            <dd>
              <code>{{ data.current.sha256 }}</code>
            </dd>
          </dl>
        </div>
        <div v-if="data.approved" class="security-section">
          <h3>{{ tr('最近批准版本') }}</h3>
          <p class="security-muted">
            {{ data.approved.actor }} · {{ date(data.approved.created_at) }}
          </p>
          <dl class="security-hashes">
            <dt>MD5</dt>
            <dd>
              <code>{{ data.approved.md5 }}</code>
            </dd>
            <dt>SHA-256</dt>
            <dd>
              <code>{{ data.approved.sha256 }}</code>
            </dd>
          </dl>
        </div>
        <p v-if="!data.approved && data.revoked" class="security-muted">
          {{ tr('最近移出') }} · {{ data.revoked.actor }} · {{ date(data.revoked.created_at) }}
        </p>
      </template>
    </section>
    <template #footer>
      <button
        v-if="data?.approved"
        class="danger"
        :disabled="loading || busy"
        data-revoke-skill
        @click="revoke"
      >
        {{ tr('移出可信区') }}
      </button>
      <button :disabled="loading || busy" @click="load">
        <UiIcon name="refresh" :size="16" />{{ tr('刷新状态') }}
      </button>
      <button
        class="primary"
        :disabled="!data || loading || busy || data.trusted"
        data-approve-skill
        @click="approve"
      >
        <UiIcon name="shield" :size="18" />{{
          busy ? tr('正在处理…') : data?.trusted ? tr('已在可信白名单') : tr('加入可信白名单')
        }}
      </button>
    </template>
  </UiModal>
</template>
<style scoped>
.skill-security-modal[open] {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.skill-security-modal :deep(.modal-body) {
  min-height: 0;
  overflow-y: auto;
}
.skill-security-modal :deep(.modal-header),
.skill-security-modal :deep(.modal-footer) {
  flex-shrink: 0;
}
.skill-security-modal :deep(.modal-footer) {
  flex-wrap: wrap;
}
.skill-security {
  display: grid;
  gap: 20px;
  font-size: 14px;
}
.security-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.security-path {
  overflow-wrap: anywhere;
  flex: 1;
  font-size: 15px;
}
.security-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  border-radius: 6px;
  padding: 4px 8px;
  background: var(--raised);
  color: var(--muted);
  white-space: nowrap;
}
.security-status {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 15px;
}
.security-status.trusted {
  color: var(--success-ink);
}
.security-status.changed,
.security-status.unlisted,
.security-status.revoked {
  color: var(--warning);
}
.security-section h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.security-hashes {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr);
  gap: 10px;
  margin: 12px 0 0;
}
.security-hashes dt,
.security-muted {
  color: var(--muted);
}
.security-hashes dd {
  margin: 0;
}
.security-hashes code {
  overflow-wrap: anywhere;
  font-size: 13px;
  line-height: 1.6;
  user-select: all;
}
.security-muted {
  margin: 0;
  line-height: 1.65;
}
@media (max-width: 600px) {
  .security-heading {
    flex-direction: column;
    align-items: flex-start;
  }
  .security-hashes {
    grid-template-columns: 1fr;
    gap: 5px;
  }
  .security-hashes dd {
    margin-bottom: 8px;
  }
}
</style>
