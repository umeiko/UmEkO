<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue';
import { api } from './state.js';
import { encode, bytes } from '../shared/api.js';
import { useAdminI18n } from '../shared/adminI18n.js';
import { prettyToolData } from '../workspace/toolData.js';
import UiModal from '../shared/UiModal.vue';
import UiIcon from '../shared/UiIcon.vue';
import HelpTip from '../shared/HelpTip.vue';
import MarkdownDocument from '../shared/MarkdownDocument.vue';
import TaskFileTree from './TaskFileTree.vue';
const { tr, date } = useAdminI18n();
const props = defineProps({ modelValue: Boolean, kind: String, recordId: String });
const emit = defineEmits(['update:modelValue']);
const detail = ref(null),
  loading = ref(false),
  error = ref(''),
  tab = ref('io'),
  raw = ref(false);
const fileRevision = ref(0);
let sequence = 0;
async function load() {
  if (!props.modelValue || !props.recordId) return;
  const seq = ++sequence;
  loading.value = true;
  error.value = '';
  try {
    const collection = props.kind === 'task' ? 'tasks' : 'sessions';
    const value = await api('GET', `/admin/v1/${collection}/${encode(props.recordId)}`);
    if (seq === sequence) {
      detail.value = value;
      fileRevision.value++;
    }
  } catch (e) {
    if (seq === sequence) error.value = e.message;
  } finally {
    if (seq === sequence) loading.value = false;
  }
}
watch(
  () => [props.modelValue, props.kind, props.recordId],
  () => {
    ++sequence;
    detail.value = null;
    error.value = '';
    raw.value = false;
    tab.value = props.kind === 'task' ? 'io' : 'messages';
    load();
  },
  { immediate: true },
);
onBeforeUnmount(() => ++sequence);
const title = computed(() => tr(props.kind === 'task' ? '任务详情' : '会话详情'));
const tabs = computed(() => [
  ...(props.kind === 'task' ? [{ id: 'io', label: tr('输入与输出'), icon: 'terminal' }] : []),
  {
    id: 'messages',
    label: tr('会话记录'),
    icon: 'sessions',
    count: detail.value?.messages.length || 0,
  },
  { id: 'tools', label: tr('工具调用'), icon: 'code', count: detail.value?.tools.length || 0 },
  { id: 'context', label: tr('上下文'), icon: 'skills' },
  ...(props.kind === 'task' ? [{ id: 'files', label: tr('文件树'), icon: 'folder' }] : []),
  ...(props.kind === 'task'
    ? [
        {
          id: 'events',
          label: tr('运行事件'),
          icon: 'resources',
          count: detail.value?.events.length || 0,
        },
      ]
    : []),
]);
const states = computed(() => ({
  queued: tr('排队'),
  running: tr('执行中'),
  cancelling: tr('正在停止'),
  completed: tr('已完成'),
  failed: tr('失败'),
  cancelled: tr('已取消'),
}));
const metadata = computed(() => {
  const record = detail.value?.record;
  if (!record) return [];
  return [
    [tr(props.kind === 'task' ? '任务 ID' : '会话 ID'), record.id],
    ...(props.kind === 'task'
      ? [
          [tr('智能体'), record.agent_name],
          [tr('调用者'), record.caller],
          ['IP', record.caller_ip || tr('未知')],
          [tr('协议'), record.source.toUpperCase()],
          [tr('状态'), states.value[record.status] || record.status],
          ['Context ID', record.context_id],
          ['Run ID', record.run_id || '—'],
        ]
      : [
          [tr('用户'), record.username],
          [tr('会话'), record.title],
        ]),
    [tr('创建时间'), date(record.created_at)],
    [tr('更新时间'), date(record.updated_at)],
  ];
});
const activeMessages = computed(() => detail.value?.messages.filter((m) => m.in_context) || []);
const snapshot = computed(() => detail.value?.context.agent_snapshot);
const skills = computed(
  () => snapshot.value?.skill_names || detail.value?.context.skill_names || [],
);
const format = (value) => prettyToolData(value, tr('未记录'));
const role = (name) =>
  ({ user: tr('用户'), assistant: tr('智能体'), system: tr('系统'), tool: tr('工具') })[name] ||
  name;
function tabKey(event, index) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const items = [...event.currentTarget.parentElement.querySelectorAll('[role=tab]')];
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? items.length - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
  items[next].click();
  items[next].focus();
}
</script>
<template>
  <UiModal
    :model-value="modelValue"
    :title="title"
    wide
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #help>
      <HelpTip
        :text="
          tr(
            '仅查看已保存的输入、会话、工具记录和配置快照，不会重新执行任务或加载模型。上下文不是每次模型请求的完整抓包；运行事件最多保留最近 500 条，大事件可能已缩略。',
          )
        "
      />
    </template>
    <div class="record-inspector">
      <p v-if="error" class="feedback bad" role="alert">
        {{ error }} <button @click="load">{{ tr('重试') }}</button>
      </p>
      <div v-if="loading && !detail" class="empty-state" role="status">{{ tr('正在读取…') }}</div>
      <template v-if="detail">
        <dl class="inspection-meta">
          <div v-for="[label, value] in metadata" :key="label">
            <dt>{{ label }}</dt>
            <dd>{{ value || '—' }}</dd>
          </div>
        </dl>
        <div class="inspection-tabs" role="tablist" :aria-label="title">
          <button
            v-for="(item, index) in tabs"
            :id="`inspection-tab-${item.id}`"
            :key="item.id"
            role="tab"
            :aria-selected="tab === item.id"
            :tabindex="tab === item.id ? 0 : -1"
            aria-controls="inspection-panel"
            :class="{ active: tab === item.id }"
            @click="tab = item.id"
            @keydown="tabKey($event, index)"
          >
            <UiIcon :name="item.icon" :size="16" />{{ item.label
            }}<span v-if="item.count !== undefined" class="badge">{{ item.count }}</span>
          </button>
        </div>
        <section
          id="inspection-panel"
          class="inspection-panel"
          role="tabpanel"
          :aria-labelledby="`inspection-tab-${tab}`"
        >
          <label v-if="['io', 'messages', 'context'].includes(tab)" class="inspection-raw"
            ><input v-model="raw" type="checkbox" />{{ tr('显示原文') }}</label
          >
          <template v-if="tab === 'io'">
            <section class="inspection-block">
              <h3>{{ tr('输入') }}</h3>
              <pre v-if="raw">{{ detail.input.prompt }}</pre>
              <MarkdownDocument v-else :content="detail.input.prompt" />
              <div v-if="detail.input.files?.length" class="inspection-attachments">
                <span v-for="(file, index) in detail.input.files" :key="index" class="badge"
                  ><UiIcon name="file" :size="15" />{{ file.name }} · {{ bytes(file.size) }}</span
                >
              </div>
              <details>
                <summary>{{ tr('请求参数') }}</summary>
                <pre>{{ format(detail.input) }}</pre>
              </details>
            </section>
            <section class="inspection-block">
              <h3>{{ tr('输出') }}</h3>
              <p v-if="detail.output.error" class="feedback bad" role="alert">
                {{ detail.output.error }}
              </p>
              <template v-if="detail.output.reply">
                <pre v-if="raw">{{ detail.output.reply }}</pre>
                <MarkdownDocument v-else :content="detail.output.reply"
              /></template>
              <p v-else class="muted">{{ tr('尚无输出') }}</p>
              <ul v-if="detail.output.artifacts.length" class="inspection-artifacts">
                <li v-for="file in detail.output.artifacts" :key="file.id">
                  <UiIcon name="file" :size="16" />{{ file.name
                  }}<span class="muted">{{ bytes(file.size) }}</span>
                </li>
              </ul>
            </section>
          </template>
          <template v-else-if="tab === 'messages'">
            <article
              v-for="message in detail.messages"
              :key="message.id"
              class="inspection-message"
              :class="message.role"
            >
              <header>
                <strong>{{ role(message.role) }}</strong
                ><span class="muted">{{ date(message.created_at) }}</span
                ><span v-if="!message.in_context" class="badge">{{ tr('已移出当前上下文') }}</span>
              </header>
              <pre v-if="raw">{{ message.content }}</pre>
              <MarkdownDocument v-else :content="message.content" />
              <div v-if="message.attachments.length" class="inspection-attachments">
                <span v-for="(file, index) in message.attachments" :key="index" class="badge"
                  ><UiIcon name="file" :size="15" />{{
                    typeof file === 'string' ? file : file.name
                  }}</span
                >
              </div>
            </article>
            <div v-if="!detail.messages.length" class="empty-state">{{ tr('暂无会话记录') }}</div>
          </template>
          <template v-else-if="tab === 'tools'">
            <details v-for="tool in detail.tools" :key="tool.id" class="inspection-tool">
              <summary>
                <UiIcon name="terminal" :size="18" /><strong>{{ tool.name }}</strong
                ><span class="badge">{{
                  tool.agent === 'subagent' ? tr('子 Agent') : tr('主 Agent')
                }}</span
                ><span class="muted">{{ date(tool.created_at) }}</span
                ><span class="badge">{{
                  tool.result === null ? tr('未记录返回结果') : tr('已返回')
                }}</span>
              </summary>
              <section>
                <h3>{{ tr('模型请求') }}</h3>
                <pre>{{ format(tool.arguments) }}</pre>
                <h3>{{ tr('工具返回') }}</h3>
                <pre>{{ format(tool.result) }}</pre>
              </section>
            </details>
            <div v-if="!detail.tools.length" class="empty-state">{{ tr('暂无工具调用记录') }}</div>
          </template>
          <template v-else-if="tab === 'context'">
            <div class="heading-line">
              <h3>{{ tr('已保存的上下文') }}</h3>
              <HelpTip
                :text="
                  tr(
                    '会话历史可能包含已经清空或压缩的旧消息。此处列出保留的消息、摘要、技能挂载；机器任务还展示提交时的智能体配置。模型基础提示词、临时消息和逐次模型请求没有完整持久化。',
                  )
                "
              />
            </div>
            <p v-if="!detail.context.session_available" class="feedback">
              {{ tr('执行会话尚未建立或已清理，输入与任务事件仍可查看。') }}
            </p>
            <section v-if="detail.context.summary" class="inspection-block">
              <h3>{{ tr('压缩摘要') }}</h3>
              <pre v-if="raw">{{ detail.context.summary }}</pre>
              <MarkdownDocument v-else :content="detail.context.summary" />
            </section>
            <section class="inspection-block">
              <h3>{{ tr('技能挂载') }}</h3>
              <div class="inspection-attachments">
                <span v-for="skill in skills" :key="skill" class="badge">{{ skill }}</span
                ><span v-if="!skills.length" class="muted">{{ tr('无') }}</span>
              </div>
            </section>
            <section v-if="snapshot" class="inspection-block">
              <div class="heading-line">
                <h3>{{ tr('提交时的智能体配置') }}</h3>
                <span class="badge">{{ snapshot.name }}</span>
              </div>
              <pre v-if="raw">{{ snapshot.system_prompt || tr('未配置工作指引') }}</pre>
              <MarkdownDocument v-else :content="snapshot.system_prompt || tr('未配置工作指引')" />
              <details v-for="skill in snapshot.dispatched_skills || []" :key="skill.name">
                <summary>{{ skill.name }}</summary>
                <pre v-if="raw">{{ skill.content }}</pre>
                <MarkdownDocument v-else :content="skill.content" skill />
              </details>
              <details>
                <summary>{{ tr('配置快照') }}</summary>
                <pre>{{ format(snapshot) }}</pre>
              </details>
            </section>
            <section class="inspection-block">
              <h3>{{ tr('保留的会话消息') }} · {{ activeMessages.length }}</h3>
              <details v-for="message in activeMessages" :key="message.id">
                <summary>{{ role(message.role) }} · {{ date(message.created_at) }}</summary>
                <pre v-if="raw">{{ message.content }}</pre>
                <MarkdownDocument v-else :content="message.content" />
              </details>
              <p v-if="!activeMessages.length" class="muted">{{ tr('暂无会话记录') }}</p>
            </section>
          </template>
          <TaskFileTree
            v-else-if="tab === 'files'"
            :task-id="recordId"
            :active="modelValue && tab === 'files'"
            :revision="fileRevision"
          />
          <template v-else-if="tab === 'events'">
            <details v-for="event in detail.events" :key="event.id" class="inspection-tool">
              <summary>
                <strong>{{ event.type }}</strong
                ><span class="muted">{{ date(event.created_at) }}</span>
              </summary>
              <pre>{{ format(event.data) }}</pre>
            </details>
            <div v-if="!detail.events.length" class="empty-state">{{ tr('暂无运行事件') }}</div>
          </template>
        </section>
      </template>
    </div>
    <template #footer
      ><button :disabled="loading" @click="load">
        <UiIcon name="refresh" :size="16" />{{ tr('刷新') }}</button
      ><button class="primary" @click="emit('update:modelValue', false)">
        {{ tr('关闭') }}
      </button></template
    >
  </UiModal>
</template>
<style scoped>
.record-inspector {
  min-width: 0;
}
.inspection-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 22px;
  margin: 0 0 20px;
}
.inspection-meta dt {
  color: var(--ink-secondary);
  font-size: 13px;
  margin-bottom: 4px;
}
.inspection-meta dd {
  margin: 0;
  font-size: 14px;
  overflow-wrap: anywhere;
}
.inspection-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 10px;
}
.inspection-tabs button {
  font-size: 14px;
}
.inspection-tabs button.active {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: var(--accent);
}
.inspection-panel {
  display: grid;
  gap: 14px;
  padding-top: 16px;
}
.inspection-raw {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-self: end;
  font-size: 14px;
  color: var(--ink-secondary);
}
.inspection-raw input {
  width: auto;
}
.inspection-block,
.inspection-message,
.inspection-tool {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px;
  min-width: 0;
}
.inspection-message.user {
  background: var(--accent-soft);
}
.inspection-message header {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  margin-bottom: 12px;
}
.inspection-panel h3 {
  font-size: 15px;
  margin: 0 0 12px;
}
.inspection-panel pre {
  font-size: 14px;
  line-height: 1.65;
  padding: 12px;
  border-radius: 8px;
  background: var(--raised);
  max-height: 480px;
  overflow: auto;
  margin: 10px 0;
}
.inspection-panel summary {
  cursor: pointer;
  font-size: 14px;
  overflow-wrap: anywhere;
}
.inspection-block details,
.inspection-tool section {
  margin-top: 14px;
}
.inspection-tool summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  list-style: none;
}
.inspection-tool summary::before {
  content: '›';
  font-size: 20px;
  line-height: 1;
  transition: transform 0.15s;
}
.inspection-tool[open] > summary::before {
  transform: rotate(90deg);
}
.inspection-attachments {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.inspection-artifacts {
  list-style: none;
  padding: 0;
  margin: 14px 0 0;
  display: grid;
  gap: 8px;
}
.inspection-artifacts li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  overflow-wrap: anywhere;
  font-size: 14px;
}
@media (max-width: 600px) {
  .inspection-meta {
    grid-template-columns: 1fr;
  }
  .inspection-tabs button {
    padding: 8px;
  }
  .inspection-block,
  .inspection-message,
  .inspection-tool {
    padding: 12px;
  }
}
</style>
