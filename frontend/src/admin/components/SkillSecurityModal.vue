<script setup>
import { ref, watch } from 'vue';
import { api, notify } from '../state.js';
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
  error = ref(''),
  redispatch = ref(false),
  result = ref(null),
  offset = ref(0);
let sequence = 0;
const labels = {
  approved: '本文件已通过',
  old_version: '已批准旧版本',
  mismatch: '摘要不匹配',
  unlisted: '未加入白名单',
  missing: '文件缺失',
  invalid: '记录或路径异常',
};
const endpoint = () => `/admin/v1/skill-security/${encode(props.pack)}/${encode(props.member)}`;
async function load() {
  const ticket = ++sequence;
  loading.value = true;
  error.value = '';
  try {
    const response = await api('GET', `${endpoint()}?offset=${offset.value}`);
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
    offset.value = 0;
    data.value = null;
    result.value = null;
    redispatch.value = false;
    load();
  },
);
async function approve() {
  if (!data.value || busy.value || loading.value) return;
  busy.value = true;
  try {
    result.value = await api('POST', endpoint(), {
      sha256: data.value.current.sha256,
      redispatch: redispatch.value,
    });
    const skipped =
      result.value.skipped_mismatch +
      result.value.skipped_busy +
      result.value.skipped_invalid +
      result.value.failed;
    notify(
      tr('重算完成，更新 {updated}，跳过 {skipped}', { updated: result.value.updated, skipped }),
      result.value.failed > 0,
    );
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function page(delta) {
  offset.value = Math.max(0, offset.value + delta * data.value.limit);
  await load();
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
            '新会话下发时自动生成白名单。此操作从管理员库读取已保存文件，默认只同步内容一致的旧副本；不直接批准用户修改。文件通过仍需其他受保护文件同时通过整包校验。',
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
        <div v-if="data.events.length" class="security-section">
          <h3>
            {{ tr('最近管理员确认') }}
            <span
              class="security-pill"
              :class="data.events[0].matches_current ? 'approved' : 'mismatch'"
              >{{ data.events[0].matches_current ? tr('与当前文件一致') : tr('文件已变化') }}</span
            >
          </h3>
          <p>{{ data.events[0].actor }} · {{ date(data.events[0].created_at) }}</p>
          <dl class="security-hashes">
            <dt>MD5</dt>
            <dd>
              <code>{{ data.events[0].md5 }}</code>
            </dd>
            <dt>SHA-256</dt>
            <dd>
              <code>{{ data.events[0].sha256 }}</code>
            </dd>
          </dl>
        </div>
        <p v-else class="security-muted">
          {{ tr('尚无手动确认记录；新会话仍按管理员库自动下发批准。') }}
        </p>
        <div class="security-section">
          <h3>
            {{ tr('已有会话门禁') }} <span class="badge">{{ data.total }}</span>
          </h3>
          <p class="security-counts">
            {{
              tr('通过 {passed} · 旧版 {old} · 不匹配 {mismatch}', {
                passed: data.counts.approved,
                old: data.counts.old_version,
                mismatch: data.counts.mismatch,
              })
            }}
          </p>
          <p v-if="!data.total" class="security-muted">{{ tr('暂无已下发此技能的会话记录') }}</p>
          <details v-for="row in data.sessions" :key="row.session_id" class="security-session">
            <summary>
              <span class="security-session-name" :title="row.username + ' · ' + row.title"
                >{{ row.username }} · {{ row.title }}</span
              ><span class="security-pill" :class="row.status">{{
                tr(labels[row.status] || row.status)
              }}</span>
            </summary>
            <code class="security-session-id">{{ row.session_id }}</code>
            <dl class="security-hashes">
              <dt>{{ tr('批准 MD5') }}</dt>
              <dd>
                <code>{{ row.approved?.md5 || '—' }}</code>
              </dd>
              <dt>{{ tr('实际 MD5') }}</dt>
              <dd>
                <code>{{ row.actual?.md5 || '—' }}</code>
              </dd>
              <dt>{{ tr('批准 SHA-256') }}</dt>
              <dd>
                <code>{{ row.approved?.sha256 || '—' }}</code>
              </dd>
              <dt>{{ tr('实际 SHA-256') }}</dt>
              <dd>
                <code>{{ row.actual?.sha256 || '—' }}</code>
              </dd>
            </dl>
          </details>
          <div v-if="data.total > data.limit" class="security-pagination">
            <button :disabled="loading || busy || !offset" @click="page(-1)">
              {{ tr('上一页') }}
            </button>
            <span
              >{{ offset + 1 }}–{{ Math.min(offset + data.limit, data.total) }} /
              {{ data.total }}</span
            >
            <button
              :disabled="loading || busy || offset + data.limit >= data.total"
              @click="page(1)"
            >
              {{ tr('下一页') }}
            </button>
          </div>
        </div>
        <label class="security-redispatch"
          ><input v-model="redispatch" type="checkbox" :disabled="busy" data-redispatch />{{
            tr('重新下发管理员版本到旧会话')
          }}<HelpTip
            :text="
              tr(
                '替换已下发会话中的此文件，再更新其批准摘要。仅此文件生效；运行中的会话跳过。请确保入口、辅助模块和配置版本兼容。',
              )
            "
        /></label>
        <div v-if="result" class="security-result" role="status">
          <p>
            {{
              tr('已更新 {updated} · 已一致 {unchanged} · 运行中跳过 {busy}', {
                updated: result.updated,
                unchanged: result.unchanged,
                busy: result.skipped_busy,
              })
            }}
          </p>
          <p>
            {{
              tr('副本不同跳过 {mismatch} · 异常跳过 {invalid} · 失败 {failed}', {
                mismatch: result.skipped_mismatch,
                invalid: result.skipped_invalid,
                failed: result.failed,
              })
            }}
          </p>
        </div>
      </template>
    </section>
    <template #footer>
      <button :disabled="busy || loading" @click="load">
        <UiIcon name="refresh" :size="17" />{{ tr('刷新状态') }}
      </button>
      <button
        class="primary"
        :disabled="busy || loading || !data"
        data-approve-skill
        @click="approve"
      >
        <UiIcon name="shield" :size="18" />{{ busy ? tr('正在处理…') : tr('重算并加入白名单') }}
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
.security-heading,
.security-section h3,
.security-session summary,
.security-pagination,
.security-redispatch {
  display: flex;
  align-items: center;
  gap: 10px;
}
.security-heading {
  flex-wrap: wrap;
}
.security-path {
  overflow-wrap: anywhere;
  flex: 1;
  font-size: 15px;
}
.security-section h3 {
  margin: 0 0 12px;
  font-size: 15px;
  flex-wrap: wrap;
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
.security-pill.approved {
  color: var(--success-ink);
}
.security-pill.mismatch,
.security-pill.invalid,
.security-pill.missing {
  color: var(--danger);
}
.security-pill.old_version,
.security-pill.unlisted {
  color: var(--warning);
}
.security-hashes {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 10px;
  margin: 12px 0 0;
}
.security-hashes dt {
  color: var(--muted);
}
.security-hashes dd {
  margin: 0;
}
.security-hashes code,
.security-session-id {
  overflow-wrap: anywhere;
  font-size: 13px;
  line-height: 1.6;
  user-select: all;
}
.security-muted,
.security-counts {
  color: var(--muted);
  margin: 0;
  line-height: 1.65;
}
.security-session {
  border: 1px solid var(--line);
  padding: 12px;
  border-radius: 8px;
  margin-top: 10px;
}
.security-session summary {
  cursor: pointer;
}
.security-session-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.security-session-id {
  display: block;
  margin-top: 12px;
  color: var(--muted);
}
.security-pagination {
  margin-top: 12px;
  justify-content: flex-end;
}
.security-redispatch {
  align-items: center;
  flex-wrap: wrap;
  padding-top: 4px;
}
.security-result {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  background: var(--raised);
  line-height: 1.65;
}
.security-result p {
  margin: 0;
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
  .security-session summary {
    flex-wrap: wrap;
  }
  .security-session-name {
    flex-basis: 100%;
  }
}
</style>
