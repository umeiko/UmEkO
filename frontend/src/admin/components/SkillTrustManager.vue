<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { api, confirm, notify } from '../state.js';
import { bytes } from '../../shared/api.js';
import { useAdminI18n } from '../../shared/adminI18n.js';
import UiModal from '../../shared/UiModal.vue';
import UiIcon from '../../shared/UiIcon.vue';
import HelpTip from '../../shared/HelpTip.vue';
const { tr, date } = useAdminI18n();
const props = defineProps({ modelValue: Boolean });
const emit = defineEmits(['update:modelValue']);
const data = ref(null),
  q = ref(''),
  pack = ref(''),
  status = ref(''),
  kind = ref('');
const offset = ref(0),
  limit = ref(50),
  loading = ref(false),
  busy = ref(false),
  selecting = ref(false);
const error = ref(''),
  selected = ref(new Map()),
  outcome = ref(null),
  processed = ref(0),
  planned = ref(0);
const labels = {
  trusted: '已信任',
  unlisted: '未加入白名单',
  changed: '文件已变化',
  revoked: '已移出可信区',
  missing: '文件缺失',
  invalid: '不可访问',
};
let sequence = 0,
  timer;
const blocked = computed(() => busy.value || selecting.value);
const key = (row) => JSON.stringify([row.pack, row.member]);
const snapshot = (row) => ({
  pack: row.pack,
  member: row.member,
  status: row.status,
  sha256: row.current?.sha256 ?? row.sha256,
  approved_sha256: row.approved?.sha256 ?? row.approved_sha256,
  approvable: row.approvable,
});
const selectable = (row) => {
  const item = snapshot(row);
  return Boolean((item.approvable && item.sha256) || item.approved_sha256);
};
const pageRows = computed(() => (data.value?.items || []).filter(selectable));
const pageSelected = computed(
  () => pageRows.value.filter((row) => selected.value.has(key(row))).length,
);
const approvalItems = computed(() =>
  [...selected.value.values()].filter(
    (row) => row.approvable && row.sha256 && row.status !== 'trusted',
  ),
);
const revokeItems = computed(() =>
  [...selected.value.values()].filter((row) => row.approved_sha256),
);
const query = () =>
  new URLSearchParams({ q: q.value, pack: pack.value, status: status.value, kind: kind.value });
async function load() {
  const ticket = ++sequence;
  loading.value = true;
  error.value = '';
  try {
    const params = query();
    params.set('offset', offset.value);
    params.set('limit', limit.value);
    const result = await api('GET', `/admin/v1/skill-security/catalog?${params}`);
    if (ticket === sequence) {
      data.value = result;
      if (offset.value && offset.value >= result.total) {
        offset.value = Math.max(0, Math.ceil(result.total / limit.value) - 1) * limit.value;
        await load();
      }
    }
  } catch (e) {
    if (ticket === sequence) error.value = e.message;
  } finally {
    if (ticket === sequence) loading.value = false;
  }
}
watch(
  () => props.modelValue,
  (open) => {
    sequence++;
    clearTimeout(timer);
    if (open) {
      selected.value = new Map();
      outcome.value = null;
      load();
    }
  },
);
watch([q, pack, status, kind], () => {
  if (!props.modelValue) return;
  sequence++;
  loading.value = true;
  selected.value = new Map();
  outcome.value = null;
  offset.value = 0;
  clearTimeout(timer);
  timer = setTimeout(load, 250);
});
watch(limit, () => {
  offset.value = 0;
  if (props.modelValue) load();
});
onBeforeUnmount(() => {
  clearTimeout(timer);
  sequence++;
});
function toggle(row, checked) {
  const next = new Map(selected.value);
  if (checked) next.set(key(row), snapshot(row));
  else next.delete(key(row));
  selected.value = next;
}
function togglePage(checked) {
  const next = new Map(selected.value);
  for (const row of pageRows.value) {
    if (checked) next.set(key(row), snapshot(row));
    else next.delete(key(row));
  }
  selected.value = next;
}
async function selectAll() {
  selecting.value = true;
  error.value = '';
  try {
    const result = await api('GET', `/admin/v1/skill-security/selection?${query()}`);
    selected.value = new Map(
      result.items.filter(selectable).map((row) => [key(row), snapshot(row)]),
    );
  } catch (e) {
    error.value = e.message;
  } finally {
    selecting.value = false;
  }
}
async function apply(action) {
  const items = (action === 'approve' ? approvalItems.value : revokeItems.value).map((row) => ({
    pack: row.pack,
    member: row.member,
    sha256: action === 'approve' ? row.sha256 : row.approved_sha256,
  }));
  if (!items.length || blocked.value) return;
  if (
    action === 'revoke' &&
    !(await confirm(
      tr('移出可信区'),
      tr('将 {count} 个文件移出可信区？已下发会话的后续调用也会被阻止，正在执行的脚本不受影响。', {
        count: items.length,
      }),
    ))
  )
    return;
  busy.value = true;
  error.value = '';
  outcome.value = null;
  processed.value = 0;
  planned.value = items.length;
  const result = { succeeded: 0, failed: 0, errors: [] };
  let requestError = '';
  try {
    for (let start = 0; start < items.length; start += 200) {
      const batch = await api('POST', '/admin/v1/skill-security/batch', {
        action,
        items: items.slice(start, start + 200),
      });
      result.succeeded += batch.succeeded;
      result.failed += batch.failed;
      result.errors.push(...batch.results.filter((row) => !row.ok));
      processed.value += batch.results.length;
    }
    notify(tr('操作完成：成功 {succeeded}，失败 {failed}', result), result.failed > 0);
  } catch (e) {
    requestError = e.message;
  } finally {
    result.unconfirmed = planned.value - processed.value;
    outcome.value = result;
    selected.value = new Map();
    await load();
    if (requestError) error.value = requestError;
    busy.value = false;
  }
}
async function page(delta) {
  offset.value = Math.max(0, offset.value + delta * limit.value);
  await load();
}
</script>
<template>
  <UiModal
    class="trust-manager"
    :model-value="modelValue"
    :title="tr('可信代码管理')"
    wide
    :busy="blocked"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #help
      ><HelpTip
        :text="
          tr(
            '管理整个技能库的 Python 与 config.json。展开文件可核对摘要；全选区分当前页与全部筛选结果。批准用于新会话，移出会阻止已下发版本的后续调用；不会改写会话文件。',
          )
        "
    /></template>
    <section class="trust-content" data-trust-manager>
      <div class="trust-filters">
        <label class="trust-search"
          ><UiIcon name="search" :size="18" /><input
            v-model="q"
            data-trust-search
            :disabled="blocked"
            :aria-label="tr('搜索可信代码')"
            :placeholder="tr('搜索技能名称或文件路径…')"
        /></label>
        <select v-model="pack" data-trust-pack :disabled="blocked" :aria-label="tr('筛选技能')">
          <option value="">{{ tr('全部技能') }}</option>
          <option v-for="name in data?.packs || []" :key="name" :value="name">{{ name }}</option>
        </select>
        <select
          v-model="status"
          data-trust-status-filter
          :disabled="blocked"
          :aria-label="tr('信任状态')"
        >
          <option value="">{{ tr('全部状态') }}</option>
          <option v-for="(label, value) in labels" :key="value" :value="value">
            {{ tr(label) }}
          </option>
        </select>
        <select v-model="kind" data-trust-kind :disabled="blocked" :aria-label="tr('文件类型')">
          <option value="">{{ tr('全部类型') }}</option>
          <option value="python">Python</option>
          <option value="config">config.json</option>
        </select>
        <button
          :disabled="loading || blocked"
          :aria-label="tr('刷新状态')"
          @click="
            selected = new Map();
            load();
          "
        >
          <UiIcon name="refresh" :size="18" />
        </button>
      </div>
      <p v-if="error" class="feedback bad" role="alert">{{ error }}</p>
      <div v-if="data" class="trust-summary">
        <span>{{ tr('共 {count} 个文件', { count: data.total }) }}</span>
        <span>{{ tr('已信任 {count}', { count: data.counts.trusted }) }}</span>
        <span>{{
          tr('待确认 {count}', { count: data.counts.unlisted + data.counts.changed })
        }}</span>
        <span>{{ tr('已移出 {count}', { count: data.counts.revoked }) }}</span>
      </div>
      <div class="trust-selection">
        <label
          ><input
            type="checkbox"
            data-trust-select-page
            :checked="pageRows.length > 0 && pageSelected === pageRows.length"
            :indeterminate="pageSelected > 0 && pageSelected < pageRows.length"
            :disabled="loading || blocked || !pageRows.length"
            @change="togglePage($event.target.checked)"
          />{{ tr('全选当前页') }}</label
        >
        <button
          class="text-button"
          data-trust-select-all
          :disabled="loading || blocked || !data?.total"
          @click="selectAll"
        >
          {{ tr('选择全部筛选结果（{count}）', { count: data?.total || 0 }) }}
        </button>
        <button
          v-if="selected.size"
          class="text-button"
          :disabled="blocked"
          @click="selected = new Map()"
        >
          {{ tr('清除选择') }}
        </button>
      </div>
      <div class="trust-list" :aria-busy="loading">
        <p v-if="loading && !data" class="empty-state">{{ tr('正在读取…') }}</p>
        <p v-else-if="data && !data.items.length" class="empty-state">
          {{ tr('未找到匹配的代码文件') }}
        </p>
        <article
          v-for="row in data?.items || []"
          :key="key(row)"
          class="trust-row"
          :class="{ selected: selected.has(key(row)) }"
          :data-trust-file="row.pack + '/' + row.member"
        >
          <input
            type="checkbox"
            :aria-label="tr('选择 {name}', { name: row.pack + '/' + row.member })"
            :checked="selected.has(key(row))"
            :disabled="loading || blocked || !selectable(row)"
            @change="toggle(row, $event.target.checked)"
          />
          <details class="trust-file">
            <summary>
              <UiIcon :name="row.kind === 'python' ? 'code' : 'file'" :size="20" /><span
                ><strong>{{ row.member.split('/').at(-1) }}</strong
                ><span class="trust-path">{{ row.pack }}/{{ row.member }}</span></span
              >
              <span class="trust-badge" :class="row.status">{{ tr(labels[row.status]) }}</span>
              <span class="trust-size">{{ row.current ? bytes(row.current.size) : '—' }}</span>
            </summary>
            <div class="trust-details">
              <p v-if="row.error" class="feedback bad">{{ tr(row.error) }}</p>
              <dl v-if="row.current">
                <dt>MD5</dt>
                <dd>
                  <code>{{ row.current.md5 }}</code>
                </dd>
                <dt>SHA-256</dt>
                <dd>
                  <code>{{ row.current.sha256 }}</code>
                </dd>
              </dl>
              <p v-if="row.approved">
                {{ tr('最近批准版本') }} · {{ row.approved.actor }} ·
                {{ date(row.approved.created_at) }}
              </p>
              <dl v-if="row.approved && !row.trusted">
                <dt>{{ tr('批准 MD5') }}</dt>
                <dd>
                  <code>{{ row.approved.md5 }}</code>
                </dd>
                <dt>{{ tr('批准 SHA-256') }}</dt>
                <dd>
                  <code>{{ row.approved.sha256 }}</code>
                </dd>
              </dl>
              <p v-if="row.revoked">
                {{ tr('最近移出') }} · {{ row.revoked.actor }} · {{ date(row.revoked.created_at) }}
              </p>
            </div>
          </details>
        </article>
      </div>
      <div class="trust-pagination" v-if="data">
        <select v-model.number="limit" :disabled="loading || blocked" :aria-label="tr('每页数量')">
          <option v-for="size in [25, 50, 100, 200]" :key="size" :value="size">
            {{ tr('每页 {count} 条', { count: size }) }}
          </option>
        </select>
        <span
          >{{ data.total ? offset + 1 : 0 }}–{{ Math.min(offset + limit, data.total) }} /
          {{ data.total }}</span
        >
        <button :disabled="!offset || loading || blocked" @click="page(-1)">
          {{ tr('上一页') }}
        </button>
        <button :disabled="offset + limit >= data.total || loading || blocked" @click="page(1)">
          {{ tr('下一页') }}
        </button>
      </div>
      <div v-if="outcome" class="trust-outcome" role="status">
        <p v-if="outcome.unconfirmed">
          {{
            tr('操作中断，尚有 {count} 项结果未确认，请刷新后核对。', {
              count: outcome.unconfirmed,
            })
          }}
        </p>
        <p>
          {{
            tr(
              outcome.unconfirmed
                ? '已确认结果：成功 {succeeded}，失败 {failed}'
                : '操作完成：成功 {succeeded}，失败 {failed}',
              outcome,
            )
          }}
        </p>
        <details v-if="outcome.errors.length">
          <summary>{{ tr('查看失败详情') }}</summary>
          <ul>
            <li v-for="item in outcome.errors" :key="key(item)">
              <code>{{ item.pack }}/{{ item.member }}</code> — {{ tr(item.error) }}
            </li>
          </ul>
        </details>
      </div>
    </section>
    <template #footer>
      <span class="trust-selected">{{
        busy
          ? tr('正在处理 {done}/{total}', { done: processed, total: planned })
          : tr('已选择 {count} 个文件', { count: selected.size })
      }}</span>
      <button
        class="danger"
        data-trust-revoke
        :disabled="!revokeItems.length || loading || blocked"
        @click="apply('revoke')"
      >
        <UiIcon name="close" :size="17" />{{
          tr('移出可信区（{count}）', { count: revokeItems.length })
        }}
      </button>
      <button
        class="primary"
        data-trust-approve
        :disabled="!approvalItems.length || loading || blocked"
        @click="apply('approve')"
      >
        <UiIcon name="shield" :size="18" />{{
          tr('加入可信区（{count}）', { count: approvalItems.length })
        }}
      </button>
    </template>
  </UiModal>
</template>
<style scoped>
.trust-manager[open] {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  width: min(1180px, calc(100vw - 32px));
  height: min(880px, calc(100dvh - 32px));
}
.trust-manager :deep(.modal-body) {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.trust-manager :deep(.modal-header),
.trust-manager :deep(.modal-footer) {
  flex-shrink: 0;
}
.trust-manager :deep(.modal-footer) {
  flex-wrap: wrap;
  gap: 10px;
}
.trust-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  gap: 16px;
  font-size: 14px;
}
.trust-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.trust-search {
  flex: 1 1 250px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 0 10px;
  background: var(--field);
}
.trust-search input {
  border: 0;
  min-width: 0;
  width: 100%;
  background: transparent;
  padding: 10px 0;
}
.trust-filters select {
  width: auto;
  max-width: 210px;
  flex: 0 1 auto;
}
.trust-filters input,
.trust-filters select,
.trust-pagination select {
  font-size: 14px;
  min-height: 40px;
}
.trust-summary,
.trust-selection,
.trust-pagination {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
}
.trust-summary,
.trust-size {
  color: var(--muted);
}
.trust-selection label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.trust-content input[type='checkbox'] {
  width: 17px;
  height: 17px;
  flex-shrink: 0;
  cursor: pointer;
}
.trust-selection button {
  font-size: 14px;
}
.trust-list {
  border: 1px solid var(--line);
  border-radius: 9px;
  overflow: auto;
  min-height: 90px;
  flex: 1;
}
.trust-row {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  align-items: start;
  gap: 14px;
  padding: 14px;
}
.trust-row + .trust-row {
  border-top: 1px solid var(--line);
}
.trust-row.selected {
  background: var(--accent-soft);
}
.trust-row > input {
  margin-top: 7px;
}
.trust-file {
  min-width: 0;
}
.trust-file summary {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) 130px 72px;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  list-style: none;
}
.trust-file summary::-webkit-details-marker {
  display: none;
}
.trust-file summary > svg {
  color: var(--accent);
  flex-shrink: 0;
}
.trust-file summary > span {
  min-width: 0;
}
.trust-file summary strong {
  font-size: 14px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.trust-path {
  display: block;
  margin-top: 4px;
  font-size: 13px;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.trust-badge {
  justify-self: start;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 4px 7px;
  font-size: 13px;
  margin-top: 2px;
}
.trust-badge.trusted {
  color: var(--success-ink);
  background: var(--success-bg);
}
.trust-badge.changed,
.trust-badge.unlisted {
  color: var(--warning);
}
.trust-badge.revoked,
.trust-badge.invalid {
  color: var(--danger);
}
.trust-size {
  text-align: right;
  font-size: 13px;
  padding-top: 7px;
  white-space: nowrap;
}
.trust-details {
  padding: 10px 0 0 30px;
  font-size: 13px;
  line-height: 1.6;
}
.trust-details dl {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr);
  gap: 7px;
  margin: 0;
}
.trust-details dt {
  color: var(--muted);
}
.trust-details dd {
  margin: 0;
}
.trust-details code,
.trust-outcome code {
  overflow-wrap: anywhere;
  font-size: 13px;
  user-select: all;
}
.trust-details p {
  margin: 8px 0;
  overflow-wrap: anywhere;
}
.trust-pagination {
  justify-content: flex-end;
}
.trust-pagination select {
  width: auto;
  margin-right: auto;
}
.trust-selected {
  margin-right: auto;
  font-size: 14px;
}
.trust-outcome {
  border: 1px solid var(--line);
  padding: 12px;
  border-radius: 7px;
  line-height: 1.6;
  max-height: 120px;
  overflow-y: auto;
}
.trust-outcome p {
  margin: 0;
}
.trust-outcome summary {
  margin-top: 8px;
  cursor: pointer;
}
.trust-outcome li {
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .trust-filters select {
    max-width: none;
    flex: 1 1 40%;
  }
  .trust-row {
    grid-template-columns: 18px minmax(0, 1fr);
    gap: 10px;
  }
  .trust-file summary {
    grid-template-columns: 20px minmax(0, 1fr);
  }
  .trust-badge {
    grid-column: 2;
  }
  .trust-size {
    display: none;
  }
  .trust-details {
    padding-left: 0;
  }
  .trust-details dl {
    grid-template-columns: 1fr;
  }
  .trust-pagination {
    gap: 8px;
  }
  .trust-selected {
    flex-basis: 100%;
  }
}
</style>
