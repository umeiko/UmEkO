<script setup>
import { useAdminI18n } from '../../shared/adminI18n.js';
const { tr } = useAdminI18n();
import { ref, reactive, computed, onMounted } from 'vue';
import HelpTip from '../../shared/HelpTip.vue';
import UiIcon from '../../shared/UiIcon.vue';
import { api, run, notify, ask, confirm } from '../state.js';
import { encode } from '../../shared/api.js';
const providers = ref([]),
  selected = ref(null),
  draft = reactive({}),
  showKey = ref(false),
  loading = ref(true),
  error = ref(''),
  busy = ref(false),
  limits = reactive({});
const current = computed(() => providers.value.find((p) => p.id === selected.value));
const model = reactive({ name: '', vision: false, max_concurrent_requests: 0 });
const iterations = ref(''),
  runtimeDefault = ref(32);
async function load(resetDraft = true) {
  try {
    const data = await api('GET', '/admin/v1/providers');
    providers.value = data.providers;
    if (!current.value) selected.value = providers.value[0]?.id || null;
    if (resetDraft) select(selected.value);
    for (const p of providers.value)
      for (const m of p.models) limits[m.id] = m.max_concurrent_requests || 0;
    error.value = '';
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
function select(id) {
  selected.value = id;
  showKey.value = false;
  const p = current.value;
  Object.assign(draft, {
    name: p?.name || '',
    base_url: p?.base_url || '',
    api_key: p?.api_key || '',
    proxy: p?.proxy || '',
  });
}
onMounted(async () => {
  await load();
  await run(async () => {
    const r = await api('GET', '/admin/v1/runtime-config');
    iterations.value = r.max_tool_iterations ?? '';
    runtimeDefault.value = r.default_max_tool_iterations || 32;
  });
});
async function create() {
  const value = await ask(tr('新建供应商'), [
    { name: 'name', label: tr('名称'), required: true, placeholder: tr('例如：内部模型服务') },
    {
      name: 'base_url',
      label: tr('API 地址'),
      required: true,
      placeholder: 'https://api.example.internal/v1',
    },
    { name: 'api_key', label: 'API Key', type: 'password', required: true },
    { name: 'proxy', label: tr('代理（可选）'), placeholder: 'http://127.0.0.1:7890' },
  ]);
  if (!value) return;
  await run(async () => {
    const p = await api('POST', '/admin/v1/providers', value);
    selected.value = p.id;
    await load();
    notify(tr('供应商已创建，可继续添加模型'));
  });
}
async function save() {
  if (busy.value) return;
  busy.value = true;
  await run(async () => {
    const body = { name: draft.name, base_url: draft.base_url, proxy: draft.proxy };
    if (draft.api_key.trim()) body.api_key = draft.api_key.trim();
    await api('PUT', `/admin/v1/providers/${encode(selected.value)}`, body);
    await load();
    notify(tr('供应商已保存'));
  });
  busy.value = false;
}
async function removeProvider() {
  if (
    !(await confirm(tr('删除供应商'), tr('删除“{p0}”及其全部模型？', { p0: current.value.name })))
  )
    return;
  await run(async () => {
    await api('DELETE', `/admin/v1/providers/${encode(selected.value)}`);
    selected.value = null;
    await load();
    notify(tr('供应商已删除'));
  });
}
async function addModel() {
  if (!model.name.trim()) {
    notify(tr('模型名不能为空'), true);
    return;
  }
  if (
    !Number.isSafeInteger(Number(model.max_concurrent_requests)) ||
    Number(model.max_concurrent_requests) < 0
  ) {
    notify(tr('并发上限请输入非负整数'), true);
    return;
  }
  await run(async () => {
    await api('POST', `/admin/v1/providers/${encode(selected.value)}/models`, {
      ...model,
      name: model.name.trim(),
      max_concurrent_requests: Number(model.max_concurrent_requests),
    });
    model.name = '';
    model.vision = false;
    model.max_concurrent_requests = 0;
    await load(false);
    notify(tr('模型已添加'));
  });
}
async function vision(m, event) {
  const value = event.target.checked;
  await run(async () => {
    await api('PUT', `/admin/v1/models/${encode(m.id)}`, { vision: value });
    m.vision = value;
    notify(tr('视觉能力已更新'));
  });
  event.target.checked = m.vision;
}
async function limit(m) {
  const raw = String(limits[m.id]).trim(),
    value = Number(raw);
  if (!raw || !Number.isSafeInteger(value) || value < 0) {
    notify(tr('请输入非负整数，0 表示不限制'), true);
    return;
  }
  await run(async () => {
    await api('PUT', `/admin/v1/models/${encode(m.id)}`, { max_concurrent_requests: value });
    m.max_concurrent_requests = value;
    notify(
      value ? tr('并发上限已设为 {p0}，超出调用自动排队', { p0: value }) : tr('已取消并发限制'),
    );
  });
}
async function activate(m) {
  if (
    !(await confirm(
      tr('切换默认模型'),
      tr('切换会重新加载在线会话中的模型配置。正在执行的请求也可能受影响，确认应用？'),
    ))
  )
    return;
  await run(async () => {
    await api('PUT', '/admin/v1/active-model', { model_id: m.id });
    await load(false);
    notify(tr('默认模型已更新'));
  });
}
async function removeModel(m) {
  if (!(await confirm(tr('删除模型'), tr('删除“{p0}”？', { p0: m.name })))) return;
  await run(async () => {
    await api('DELETE', `/admin/v1/models/${encode(m.id)}`);
    await load(false);
    notify(tr('模型已删除'));
  });
}
async function importJson(one = false) {
  const sample = one
    ? [
        { name: 'text-model', vision: false, max_concurrent_requests: 0 },
        { name: 'vision-model', vision: true, max_concurrent_requests: 0 },
      ]
    : {
        providers: [
          {
            name: 'ExampleProvider',
            base_url: 'https://api.example.internal/v1',
            api_key: 'replace-with-your-key',
            models: [{ name: 'text-model', vision: false, max_concurrent_requests: 0 }],
          },
        ],
      };
  const result = await ask(one ? tr('向当前供应商导入') : tr('导入供应商 JSON'), [
    {
      name: 'document',
      label: tr('JSON 配置'),
      type: 'textarea',
      rows: 14,
      required: true,
      value: JSON.stringify(sample, null, 2),
    },
  ]);
  if (!result) return;
  await run(async () => {
    let doc = JSON.parse(result.document);
    if (one) {
      if (Array.isArray(doc)) doc = { models: doc };
      doc = { providers: [{ ...doc, name: current.value.name }] };
    }
    const r = await api('POST', '/admin/v1/providers/import', { document: doc });
    await load();
    notify(tr('导入完成，新增 {p0} 个模型', { p0: r.models_created }));
  });
}
async function copyKey() {
  await run(async () => {
    await navigator.clipboard.writeText(draft.api_key);
    notify(tr('API Key 已复制'));
  });
}
async function saveRuntime() {
  const raw = String(iterations.value).trim(),
    value = raw === '' ? null : Number(raw);
  if (value !== null && (!Number.isSafeInteger(value) || value < 0)) {
    notify(tr('请输入非负整数，或留空使用默认值'), true);
    return;
  }
  await run(async () => {
    await api('PUT', '/admin/v1/runtime-config', { max_tool_iterations: value });
    notify(tr('工具调用设置已保存'));
  });
}
</script>
<template>
  <section id="page-providers" class="stack">
    <p v-if="error" class="feedback bad">
      {{ error }} <button @click="load()">{{ tr('重试') }}</button>
    </p>
    <div class="row between">
      <span class="muted">{{ tr('{count} 个供应商', { count: providers.length }) }}</span>
      <div class="row">
        <button @click="importJson(false)">
          <UiIcon name="upload" :size="15" />{{ tr('导入 JSON') }}</button
        ><button class="primary" @click="create">
          <UiIcon name="plus" :size="15" />{{ tr('新建供应商') }}
        </button>
      </div>
    </div>
    <div class="provider-layout">
      <aside class="card provider-list">
        <button
          v-for="p in providers"
          :key="p.id"
          class="provider-item"
          :class="{ active: p.id === selected }"
          @click="select(p.id)"
        >
          <span
            ><strong>{{ p.name }}</strong
            ><small>{{ tr('{count} 个模型', { count: p.models.length }) }}</small></span
          ><span v-if="p.models.some((m) => m.active)" class="badge on">{{ tr('当前') }}</span
          ><UiIcon v-else name="chevron" :size="14" />
        </button>
        <div v-if="!providers.length" class="empty-state">
          {{ loading ? tr('正在读取…') : tr('暂无供应商') }}
        </div>
      </aside>
      <div v-if="current" class="stack">
        <section class="card">
          <header class="card-head">
            <h2>{{ current.name }}</h2>
            <button class="danger" @click="removeProvider">
              <UiIcon name="trash" :size="14" />{{ tr('删除供应商') }}
            </button>
          </header>
          <form class="card-body field-grid" @submit.prevent="save">
            <div class="field">
              <label for="pd-name">{{ tr('名称') }}</label
              ><input id="pd-name" v-model="draft.name" required />
            </div>
            <div class="field">
              <label for="pd-base-url">{{ tr('API 地址') }}</label
              ><input id="pd-base-url" v-model="draft.base_url" required />
            </div>
            <div class="field">
              <div class="heading-line">
                <label for="pd-api-key">API Key</label
                ><HelpTip
                  :text="
                    tr(
                      '模型服务的密钥只保存在服务端。留空保存时保留已有密钥；不会出现在 Agent Card 中。',
                    )
                  "
                />
              </div>
              <div class="row" style="flex-wrap: nowrap">
                <input
                  id="pd-api-key"
                  v-model="draft.api_key"
                  :type="showKey ? 'text' : 'password'"
                  autocomplete="off"
                /><button
                  type="button"
                  class="icon-button"
                  :aria-label="tr('切换密钥可见性')"
                  @click="showKey = !showKey"
                >
                  <UiIcon name="eye" /></button
                ><button
                  type="button"
                  class="icon-button"
                  :aria-label="tr('复制密钥')"
                  @click="copyKey"
                >
                  <UiIcon name="copy" />
                </button>
              </div>
            </div>
            <div class="field">
              <label for="pd-proxy">{{ tr('代理（可选）') }}</label
              ><input id="pd-proxy" v-model="draft.proxy" placeholder="http://127.0.0.1:7890" />
            </div>
            <div class="full row">
              <button class="primary" :disabled="busy">
                <UiIcon name="save" :size="15" />{{ busy ? tr('正在保存…') : tr('保存供应商') }}
              </button>
            </div>
          </form>
        </section>
        <section class="card">
          <header class="card-head">
            <div class="heading-line">
              <h2>{{ tr('模型') }}</h2>
              <HelpTip
                :text="
                  tr(
                    '并发按模型计数。0 表示不限制；超出上限的网页、MCP 和 A2A 请求在服务端等待可用名额。',
                  )
                "
                :label="tr('模型并发说明')"
              />
            </div>
            <button @click="importJson(true)">{{ tr('导入模型 JSON') }}</button>
          </header>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{{ tr('模型名称') }}</th>
                  <th>{{ tr('视觉能力') }}</th>
                  <th>{{ tr('并发上限') }}</th>
                  <th>{{ tr('状态') }}</th>
                  <th>{{ tr('操作') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in current.models" :key="m.id">
                  <td>
                    <code>{{ m.name }}</code>
                  </td>
                  <td>
                    <label class="check"
                      ><input type="checkbox" :checked="m.vision" @change="vision(m, $event)" />{{
                        tr('视觉')
                      }}</label
                    >
                  </td>
                  <td>
                    <div class="row" style="flex-wrap: nowrap">
                      <input
                        :id="'ml-' + m.id"
                        v-model="limits[m.id]"
                        type="number"
                        min="0"
                        step="1"
                        style="width: 70px"
                        :aria-label="m.name + tr(' 并发上限')"
                      /><button @click="limit(m)">{{ tr('保存') }}</button>
                    </div>
                  </td>
                  <td>
                    <span v-if="m.active" class="badge on">{{ tr('默认模型') }}</span>
                  </td>
                  <td>
                    <div class="row">
                      <button v-if="!m.active" @click="activate(m)">{{ tr('设为默认') }}</button
                      ><button class="danger" @click="removeModel(m)">{{ tr('删除') }}</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="!current.models.length" class="empty-state">
              {{ tr('还没有模型，在下方添加。') }}
            </div>
          </div>
          <form class="card-body row" @submit.prevent="addModel">
            <input
              id="nm-name"
              v-model="model.name"
              :placeholder="tr('模型名称')"
              style="flex: 1; min-width: 150px"
              required
            /><label class="check"
              ><input id="nm-vision" v-model="model.vision" type="checkbox" />{{
                tr('视觉')
              }}</label
            ><input
              v-model="model.max_concurrent_requests"
              type="number"
              min="0"
              step="1"
              :aria-label="tr('新模型并发上限')"
              style="width: 75px"
            /><button><UiIcon name="plus" :size="15" />{{ tr('添加模型') }}</button>
          </form>
        </section>
      </div>
      <div v-else class="card empty-state">
        <strong>{{ tr('连接一个模型服务') }}</strong
        >{{ tr('新建供应商，配置 API 地址和模型，即可开始使用。') }}
      </div>
    </div>
    <section class="card">
      <header class="card-head">
        <div class="heading-line">
          <h2>{{ tr('工具调用') }}</h2>
          <HelpTip
            :text="
              tr(
                '每条消息的连续工具调用上限。留空使用默认值 {p0}；0 为无限制。保存会重新加载在线会话配置。',
                { p0: runtimeDefault },
              )
            "
          />
        </div>
      </header>
      <form class="card-body row" @submit.prevent="saveRuntime">
        <label for="max-iterations">{{ tr('连续调用上限') }}</label
        ><input
          id="max-iterations"
          v-model="iterations"
          type="number"
          min="0"
          step="1"
          :placeholder="tr('默认 ') + runtimeDefault"
          style="width: 145px"
        /><button>{{ tr('保存') }}</button>
      </form>
    </section>
  </section>
</template>
