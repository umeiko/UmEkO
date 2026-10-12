<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue';
import { api, notify } from './state.js';
import { encode } from '../shared/api.js';
import { copyText } from '../shared/clipboard.js';
import { useAdminI18n } from '../shared/adminI18n.js';
import UiTabs from '../shared/UiTabs.vue';
import UiIcon from '../shared/UiIcon.vue';
import HelpTip from '../shared/HelpTip.vue';
const { tr } = useAdminI18n();
const props = defineProps({ agentId: String, active: Boolean, revision: Number });
const data = ref(null),
  loading = ref(false),
  error = ref(''),
  tab = ref('tools'),
  selected = ref(''),
  search = ref('');
let sequence = 0;
async function load() {
  if (!props.active || !props.agentId || loading.value) return;
  const seq = ++sequence;
  loading.value = true;
  error.value = '';
  try {
    const result = await api('GET', `/admin/v1/agents/${encode(props.agentId)}/mcp`);
    if (seq !== sequence) return;
    data.value = result;
    if (!result.tools.some((tool) => tool.name === selected.value))
      selected.value =
        result.tools.find((tool) => tool.name === 'submit_task')?.name ||
        result.tools[0]?.name ||
        '';
  } catch (e) {
    if (seq === sequence) error.value = e.message;
  } finally {
    if (seq === sequence) loading.value = false;
  }
}
watch(
  () => [props.agentId, props.revision],
  () => {
    ++sequence;
    data.value = null;
    error.value = '';
    loading.value = false;
    selected.value = '';
    search.value = '';
    tab.value = 'tools';
    load();
  },
  { immediate: true },
);
watch(
  () => props.active,
  (active) => {
    if (active && !data.value) load();
  },
);
onBeforeUnmount(() => ++sequence);
const tabs = computed(() => [
  { id: 'tools', label: tr('工具'), icon: 'terminal', count: data.value?.tools.length || 0 },
  {
    id: 'resources',
    label: tr('资源'),
    icon: 'file',
    count: (data.value?.resources.length || 0) + (data.value?.resourceTemplates.length || 0),
  },
  { id: 'prompts', label: tr('提示词'), icon: 'sessions', count: data.value?.prompts.length || 0 },
  { id: 'json', label: tr('原始 JSON'), icon: 'code' },
]);
const tools = computed(
  () =>
    data.value?.tools.filter((tool) =>
      `${tool.name} ${tool.description || ''}`
        .toLowerCase()
        .includes(search.value.toLowerCase().trim()),
    ) || [],
);
const tool = computed(
  () => tools.value.find((item) => item.name === selected.value) || tools.value[0],
);
const parameters = computed(() => Object.entries(tool.value?.inputSchema?.properties || {}));
const format = (value) => JSON.stringify(value, null, 2);
function typeOf(schema) {
  if (schema.anyOf || schema.oneOf) return (schema.anyOf || schema.oneOf).map(typeOf).join(' / ');
  if (schema.$ref) return schema.$ref.split('/').at(-1);
  if (Array.isArray(schema.type)) return schema.type.join(' / ');
  if (schema.type === 'array') return `array<${typeOf(schema.items || {})}>`;
  return schema.type || 'any';
}
async function copy(value) {
  try {
    await copyText(value);
    notify(tr('已复制'));
  } catch {
    notify(tr('复制失败'), true);
  }
}
const listing = computed(() => ({ jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} }));
const call = computed(() => ({
  jsonrpc: '2.0',
  id: 2,
  method: 'tools/call',
  params: { name: tool.value?.name, arguments: {} },
}));
</script>
<template>
  <div class="mcp-disclosure">
    <div v-if="!agentId" class="empty-state">{{ tr('先保存智能体，再查看 MCP 披露详情。') }}</div>
    <template v-else>
      <div class="row between mcp-heading">
        <div class="heading-line">
          <h3>{{ tr('MCP 披露') }}</h3>
          <HelpTip
            :text="
              tr(
                '这里展示外部 MCP 客户端通过 tools/list 看到的工具，不是 Agent 内部工具或 Skill 清单。各智能体共享服务接口，任务执行使用各自的模型和技能。tools/list 是发送到 MCP 地址的 JSON-RPC 方法，不是 /mcp/tools/list 网页路径。此处读取 SDK 注册定义，不执行工具或调用模型。',
              )
            "
          />
        </div>
        <button :disabled="loading" @click="load">
          <UiIcon name="refresh" :size="16" />{{ tr('刷新') }}
        </button>
      </div>
      <p v-if="error" class="feedback bad" role="alert">
        {{ error }} <button @click="load">{{ tr('重试') }}</button>
      </p>
      <div v-if="loading && !data" class="empty-state" role="status">{{ tr('正在读取…') }}</div>
      <template v-if="data">
        <div class="mcp-endpoint">
          <span class="badge">POST</span><code>{{ data.endpoint }}</code
          ><button
            class="icon-button"
            :aria-label="tr('复制 MCP 地址')"
            @click="copy(data.endpoint)"
          >
            <UiIcon name="copy" :size="16" />
          </button>
        </div>
        <div class="row mcp-status">
          <span class="badge">{{ data.transport }}</span
          ><span class="badge">{{
            data.auth_mode === 'anonymous' ? tr('免鉴权') : tr('需要服务凭据')
          }}</span
          ><span v-if="!data.enabled" class="badge bad">{{ tr('已停用，实际调用返回 404') }}</span>
        </div>
        <UiTabs
          v-model="tab"
          :items="tabs"
          id-prefix="mcp-disclosure"
          :label="tr('MCP 披露内容')"
        />
        <section
          id="mcp-disclosure-panel-tools"
          v-show="tab === 'tools'"
          role="tabpanel"
          aria-labelledby="mcp-disclosure-tab-tools"
        >
          <label class="mcp-filter"
            ><UiIcon name="search" :size="17" /><input
              v-model="search"
              :placeholder="tr('搜索工具名称或说明')"
              :aria-label="tr('搜索 MCP 工具')"
          /></label>
          <div v-if="tools.length" class="mcp-layout">
            <nav class="mcp-tool-list" :aria-label="tr('MCP 工具列表')">
              <button
                v-for="item in tools"
                :key="item.name"
                type="button"
                :class="{ active: item.name === tool?.name }"
                :aria-pressed="item.name === tool?.name"
                @click="selected = item.name"
              >
                <UiIcon name="terminal" :size="17" /><span>{{ item.name }}</span>
              </button>
            </nav>
            <article v-if="tool" class="mcp-tool-detail">
              <h3>{{ tool.title || tool.name }}</h3>
              <p class="mcp-description">{{ tool.description }}</p>
              <div class="row mcp-annotations">
                <span v-if="tool.annotations?.readOnlyHint === true" class="badge">{{
                  tr('只读')
                }}</span
                ><span v-if="tool.annotations?.readOnlyHint === false" class="badge">{{
                  tr('可修改任务')
                }}</span
                ><span v-if="tool.annotations?.destructiveHint === true" class="badge">{{
                  tr('含停止或删除行为')
                }}</span
                ><span v-if="tool.annotations?.openWorldHint === true" class="badge">{{
                  tr('可访问外部服务')
                }}</span>
              </div>
              <h4>{{ tr('参数') }}</h4>
              <div v-if="parameters.length" class="table-wrap">
                <table class="mcp-parameters">
                  <thead>
                    <tr>
                      <th>{{ tr('名称') }}</th>
                      <th>{{ tr('类型') }}</th>
                      <th>{{ tr('要求') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="[name, schema] in parameters" :key="name">
                      <td>
                        <code>{{ name }}</code>
                        <p v-if="schema.description" class="muted">{{ schema.description }}</p>
                      </td>
                      <td>
                        <code>{{ typeOf(schema) }}</code>
                      </td>
                      <td>
                        {{ tool.inputSchema.required?.includes(name) ? tr('必填') : tr('可选') }}
                        <p v-if="'default' in schema" class="muted">
                          {{ tr('默认值') }}: {{ JSON.stringify(schema.default) }}
                        </p>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else class="muted">{{ tr('无需参数') }}</p>
              <details>
                <summary>{{ tr('输入结构') }} · inputSchema</summary>
                <pre>{{ format(tool.inputSchema) }}</pre>
              </details>
              <details>
                <summary>{{ tr('返回结构') }} · outputSchema</summary>
                <pre v-if="tool.outputSchema">{{ format(tool.outputSchema) }}</pre>
                <p v-else class="muted">{{ tr('未声明返回结构') }}</p>
              </details>
              <details>
                <summary>{{ tr('工具标注') }} · annotations</summary>
                <pre>{{ format(tool.annotations || {}) }}</pre>
              </details>
              <details>
                <summary>
                  {{ tr('调用格式') }} · tools/call<HelpTip
                    :text="
                      tr(
                        '这是请求结构示例，arguments 需要按照参数表补充；不会在这里执行调用。需要凭据模式下还要附带 Authorization。',
                      )
                    "
                  />
                </summary>
                <pre>{{ format(call) }}</pre>
              </details>
            </article>
          </div>
          <div v-else class="empty-state">{{ tr('没有匹配的 MCP 工具') }}</div>
          <details class="mcp-list-request">
            <summary>{{ tr('工具发现请求') }} · tools/list</summary>
            <pre>{{ format(listing) }}</pre>
            <button @click="copy(format(listing))">
              <UiIcon name="copy" :size="16" />{{ tr('复制请求') }}
            </button>
          </details>
        </section>
        <section
          id="mcp-disclosure-panel-resources"
          v-show="tab === 'resources'"
          role="tabpanel"
          aria-labelledby="mcp-disclosure-tab-resources"
        >
          <h3>{{ tr('资源模板') }} · resources/templates/list</h3>
          <article
            v-for="resource in data.resourceTemplates"
            :key="resource.uriTemplate"
            class="mcp-resource"
          >
            <h4>{{ resource.title || resource.name }}</h4>
            <code>{{ resource.uriTemplate }}</code>
            <p v-if="resource.description">{{ resource.description }}</p>
            <details>
              <summary>{{ tr('完整定义') }}</summary>
              <pre>{{ format(resource) }}</pre>
            </details>
          </article>
          <p v-if="!data.resourceTemplates.length" class="muted">{{ tr('未披露资源模板') }}</p>
          <h3>{{ tr('固定资源') }} · resources/list</h3>
          <article v-for="resource in data.resources" :key="resource.uri" class="mcp-resource">
            <code>{{ resource.uri }}</code>
            <pre>{{ format(resource) }}</pre>
          </article>
          <p v-if="!data.resources.length" class="muted">{{ tr('未披露固定资源') }}</p>
          <HelpTip
            :text="
              tr(
                'umeko:// 是 MCP 逻辑资源 URI，不是 HTTP 下载地址，不添加部署前缀。产物下载地址从 get_task 的返回结果获取。',
              )
            "
            :label="tr('MCP 资源说明')"
          />
        </section>
        <section
          id="mcp-disclosure-panel-prompts"
          v-show="tab === 'prompts'"
          role="tabpanel"
          aria-labelledby="mcp-disclosure-tab-prompts"
        >
          <h3>prompts/list</h3>
          <article v-for="prompt in data.prompts" :key="prompt.name" class="mcp-resource">
            <h4>{{ prompt.name }}</h4>
            <pre>{{ format(prompt) }}</pre>
          </article>
          <div v-if="!data.prompts.length" class="empty-state">
            {{ tr('当前没有对外披露 MCP 提示词') }}
          </div>
        </section>
        <section
          id="mcp-disclosure-panel-json"
          v-show="tab === 'json'"
          role="tabpanel"
          aria-labelledby="mcp-disclosure-tab-json"
        >
          <div class="row between">
            <h3>{{ tr('SDK 披露定义') }}</h3>
            <button @click="copy(format(data))">
              <UiIcon name="copy" :size="16" />{{ tr('复制 JSON') }}
            </button>
          </div>
          <pre class="mcp-raw">{{ format(data) }}</pre>
        </section>
      </template>
    </template>
  </div>
</template>
<style scoped>
.mcp-heading {
  margin-bottom: 14px;
}
h3 {
  font-size: 16px;
  margin: 0;
}
h4 {
  font-size: 14px;
  margin: 16px 0 10px;
}
.mcp-endpoint {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.mcp-endpoint code {
  flex: 1;
  overflow-wrap: anywhere;
  font-size: 14px;
  min-width: 0;
}
.mcp-status {
  flex-wrap: wrap;
  margin: 12px 0 18px;
}
.mcp-filter {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.mcp-filter input {
  flex: 1;
  min-width: 0;
}
.mcp-layout {
  display: grid;
  grid-template-columns: 185px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}
.mcp-tool-list {
  display: grid;
  gap: 7px;
}
.mcp-tool-list button {
  justify-content: start;
  padding: 10px;
  font-size: 14px;
  text-align: left;
  min-width: 0;
}
.mcp-tool-list button span {
  overflow-wrap: anywhere;
}
.mcp-tool-list button.active {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}
.mcp-tool-detail {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px;
}
.mcp-description {
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.7;
}
.mcp-annotations {
  flex-wrap: wrap;
}
.mcp-parameters {
  table-layout: fixed;
  min-width: 0;
  font-size: 14px;
}
.mcp-parameters td {
  padding: 12px 8px;
  overflow-wrap: anywhere;
}
.mcp-parameters th {
  padding: 10px 8px;
}
.mcp-parameters code {
  font-size: 13px;
}
.mcp-disclosure pre {
  background: var(--raised);
  padding: 14px;
  border-radius: 8px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 14px;
  line-height: 1.6;
  max-height: 460px;
  overflow: auto;
}
.mcp-disclosure summary {
  cursor: pointer;
  font-size: 14px;
}
.mcp-tool-detail details {
  margin-top: 16px;
}
.mcp-list-request {
  margin-top: 20px;
}
.mcp-resource {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
  margin: 14px 0 24px;
  overflow-wrap: anywhere;
}
.mcp-resource code {
  font-size: 14px;
}
.mcp-resource h4 {
  margin-top: 0;
}
.mcp-raw {
  max-height: 560px;
}
@media (max-width: 700px) {
  .mcp-layout {
    grid-template-columns: 1fr;
  }
  .mcp-tool-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
