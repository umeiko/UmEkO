<script setup>
import { useAdminI18n } from '../../shared/adminI18n.js';
const { tr, date } = useAdminI18n();
import { ref, reactive, computed, onMounted } from 'vue';
import HelpTip from '../../shared/HelpTip.vue';
import UiModal from '../../shared/UiModal.vue';
import UiIcon from '../../shared/UiIcon.vue';
import { api, notify, run, confirm, admin } from '../state.js';
import { encode } from '../../shared/api.js';
const accounts = ref([]),
  mode = ref('required'),
  data = ref({ agents: [], skills: [], models: [] }),
  loading = ref(true),
  error = ref('');
const scopes = ['tasks:create', 'tasks:read', 'tasks:cancel', 'artifacts:read'];
const account = reactive({ name: '', expires_days: 90, scopes: [...scopes] });
const creating = ref(false),
  accountFeedback = ref(''),
  accountBad = ref(false),
  secret = ref(null),
  secretOpen = ref(false),
  secretTitle = ref('');
const editor = ref(false),
  editing = ref(null),
  saving = ref(false),
  feedback = ref(''),
  bad = ref(false),
  card = ref(''),
  endpoints = ref({});
const form = reactive({});
const visionModels = computed(() => data.value.models.filter((m) => m.vision));
const authHelp = computed(() =>
  mode.value === 'anonymous'
    ? tr(
        '免鉴权模式允许不带凭据调用智能体的 MCP、A2A 和任务 API。免鉴权调用共享任务和文件访问权限及队列额度。IP 只用于日志，无法获取时显示未知。网页登录仍需账号密码。',
      )
    : tr(
        '调用者需使用服务账号凭据。它与模型供应商 API Key 相互独立，服务对象不会拿到你的模型密钥。',
      ),
);
async function refresh() {
  error.value = '';
  try {
    const [a, b] = await Promise.all([
      api('GET', '/admin/v1/service-accounts'),
      api('GET', '/admin/v1/agents'),
    ]);
    accounts.value = a.accounts;
    mode.value = a.auth_mode;
    data.value = b;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
onMounted(refresh);
const modelName = (id) => data.value.models.find((m) => m.id === id)?.name || tr('模型已删除');
async function saveMode() {
  await run(async () => {
    await api('PUT', '/admin/v1/service-access', { auth_mode: mode.value });
    notify(tr('接入方式已保存，立即生效'));
  });
}
function showSecret(value, title) {
  secret.value = value;
  secretTitle.value = title;
  secretOpen.value = true;
}
function clearSecret() {
  secret.value = null;
}
async function copySecret() {
  try {
    await navigator.clipboard.writeText(secret.value.token);
    notify(tr('凭据已复制'));
  } catch {
    document.querySelector('#service-token')?.select();
    notify(tr('请复制选中的凭据'));
  }
}
async function createAccount() {
  if (creating.value) return;
  accountBad.value = true;
  const name = account.name.trim(),
    days = Number(account.expires_days);
  if (!name) {
    accountFeedback.value = tr('请输入服务账号名称');
    document.querySelector('#sa-name').focus();
    return;
  }
  if (name.length > 80) {
    accountFeedback.value = tr('服务账号名称不能超过 80 个字符');
    return;
  }
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    accountFeedback.value = tr('有效天数请输入 1–3650 之间的整数');
    return;
  }
  if (!account.scopes.length) {
    accountFeedback.value = tr('请至少选择一项权限');
    return;
  }
  creating.value = true;
  accountBad.value = false;
  accountFeedback.value = tr('正在创建…');
  try {
    showSecret(
      await api('POST', '/admin/v1/service-accounts', { ...account, name, expires_days: days }),
      tr('服务账号已创建'),
    );
    account.name = '';
    accountFeedback.value = tr('已创建，请在弹窗中复制凭据。');
    await refresh();
  } catch (e) {
    accountBad.value = true;
    accountFeedback.value = e.message;
    notify(e.message, true);
  } finally {
    creating.value = false;
  }
}
async function rotate(a) {
  if (
    !(await confirm(tr('更换服务凭据'), tr('更换“{p0}”的凭据？旧凭据会立即失效。', { p0: a.name })))
  )
    return;
  await run(async () => {
    showSecret(
      await api('PATCH', `/admin/v1/service-accounts/${encode(a.id)}`, {
        rotate: true,
        expires_days: 90,
      }),
      tr('新的服务凭据'),
    );
    await refresh();
  });
}
async function toggle(a) {
  await run(async () => {
    await api('PATCH', `/admin/v1/service-accounts/${encode(a.id)}`, { enabled: !a.enabled });
    await refresh();
    notify(tr('账号状态已更新'));
  });
}
async function remove(a) {
  if (
    !(await confirm(
      tr('删除服务账号'),
      tr('永久删除“{p0}”？相关调用历史、任务和文件会一并清理，凭据立即失效。', { p0: a.name }),
    ))
  )
    return;
  await run(async () => {
    await api('DELETE', `/admin/v1/service-accounts/${encode(a.id)}`);
    await refresh();
    notify(tr('服务账号及历史记录已删除'));
  });
}
async function edit(a = null) {
  card.value = '';
  feedback.value = '';
  await run(async () => {
    data.value = await api('GET', '/admin/v1/agents');
    editing.value = a?.id || null;
    Object.assign(
      form,
      {
        name: '',
        slug: '',
        description: '',
        version: data.value.default_version,
        system_prompt: '',
        default_model_id: '',
        default_vision_model_id: '',
        skill_names: [],
        enabled: true,
        documentationUrl: '',
        iconUrl: '',
        organization: '',
        providerUrl: '',
      },
      a
        ? {
            ...a,
            skill_names: [...a.skill_names],
            default_model_id: a.default_model_id || '',
            default_vision_model_id: a.default_vision_model_id || '',
            documentationUrl: a.documentationUrl || '',
            iconUrl: a.iconUrl || '',
            organization: a.provider?.organization || '',
            providerUrl: a.provider?.url || '',
          }
        : {},
    );
    feedback.value = '';
    bad.value = false;
    endpoints.value = a?.endpoints || {};
    card.value = '';
    editor.value = true;
    if (a) await loadCard();
  });
}
async function loadCard() {
  const value = await api('GET', `/admin/v1/agents/${encode(editing.value)}/card`);
  card.value = JSON.stringify(value.card, null, 2);
}
async function saveAgent() {
  if (saving.value) return;
  bad.value = true;
  for (const [key, label] of [
    ['name', tr('名称')],
    ['slug', tr('访问路径')],
    ['description', tr('介绍')],
    ['version', tr('版本')],
  ]) {
    if (!form[key].trim()) {
      feedback.value = tr('请填写') + label;
      document.querySelector('#agent-definition-' + key)?.focus();
      return;
    }
  }
  if (!/^[a-z0-9][a-z0-9-]{0,62}$/.test(form.slug)) {
    feedback.value = tr('访问路径请使用小写字母、数字和连字符，最多 63 位');
    return;
  }
  const organization = form.organization.trim(),
    url = form.providerUrl.trim();
  if (!!organization !== !!url) {
    feedback.value = tr('提供方名称和网址请同时填写，或同时留空');
    return;
  }
  const payload = {};
  for (const key of ['name', 'slug', 'description', 'version', 'system_prompt'])
    payload[key] = form[key].trim();
  for (const key of ['documentationUrl', 'iconUrl', 'default_model_id', 'default_vision_model_id'])
    payload[key] = form[key]?.trim() || null;
  Object.assign(payload, {
    skill_names: [...form.skill_names],
    enabled: form.enabled,
    provider: organization ? { organization, url } : null,
  });
  saving.value = true;
  bad.value = false;
  feedback.value = tr('正在保存…');
  try {
    const saved = await api(
      editing.value ? 'PUT' : 'POST',
      editing.value ? `/admin/v1/agents/${encode(editing.value)}` : '/admin/v1/agents',
      payload,
    );
    editing.value = saved.id;
    endpoints.value = saved.endpoints;
    await loadCard();
    await refresh();
    feedback.value = tr('已保存。新请求立即使用此配置。');
  } catch (e) {
    feedback.value = e.message;
    bad.value = true;
  } finally {
    saving.value = false;
  }
}
async function removeAgent(a) {
  if (
    !(await confirm(
      tr('删除智能体'),
      tr('删除“{p0}”的配置？存在保留任务时，需先停用并等待任务清理。', { p0: a.name }),
    ))
  )
    return;
  await run(async () => {
    await api('DELETE', `/admin/v1/agents/${encode(a.id)}`);
    await refresh();
    notify(tr('智能体已删除'));
  });
}
function manageSkills() {
  editor.value = false;
  admin.tab = 'dskills';
}
</script>
<template>
  <section id="page-access" class="stack">
    <p v-if="error" class="feedback bad" role="alert">
      {{ error }} <button @click="refresh">{{ tr('重试') }}</button>
    </p>
    <section class="card">
      <header class="card-head">
        <div class="heading-line">
          <UiIcon name="shield" :size="17" />
          <h2>{{ tr('接入方式') }}</h2>
          <HelpTip id="service-auth-help" :text="authHelp" :label="tr('接入方式说明')" />
        </div>
        <span class="badge" :class="{ on: mode === 'anonymous' }">{{
          mode === 'anonymous' ? tr('免鉴权') : tr('需要服务凭据')
        }}</span>
      </header>
      <div class="card-body row">
        <select
          id="service-auth-mode"
          v-model="mode"
          style="width: 260px; max-width: 100%"
          :aria-label="tr('接入方式')"
        >
          <option value="required">{{ tr('凭据鉴权') }}</option>
          <option value="anonymous">{{ tr('免鉴权（内网使用）') }}</option></select
        ><button class="primary" @click="saveMode">{{ tr('保存接入方式') }}</button>
      </div>
    </section>
    <section id="agent-management" class="card">
      <header class="card-head">
        <div class="heading-line">
          <UiIcon name="access" :size="17" />
          <h2>{{ tr('智能体') }}</h2>
          <HelpTip
            :text="
              tr(
                '同一基座可提供多个智能体。每个智能体独立配置介绍、默认模型和 Skill，调用入口为 /agent/<name>/a2a、/agent/<name>/mcp。',
              )
            "
            :label="tr('智能体说明')"
          /><span class="badge">{{ data.agents.length }}</span>
        </div>
        <button id="agent-new" class="primary" @click="edit()">
          <UiIcon name="plus" :size="15" />{{ tr('新建智能体') }}
        </button>
      </header>
      <div class="table-wrap">
        <table v-if="data.agents.length">
          <thead>
            <tr>
              <th>{{ tr('名称 / 介绍') }}</th>
              <th>{{ tr('访问路径') }}</th>
              <th>Skills</th>
              <th>{{ tr('主模型') }}</th>
              <th>{{ tr('视觉模型') }}</th>
              <th>{{ tr('状态') }}</th>
              <th>{{ tr('操作') }}</th>
            </tr>
          </thead>
          <tbody id="agent-definitions">
            <tr v-for="a in data.agents" :key="a.id">
              <td>
                <strong>{{ a.name }}</strong>
                <p>{{ a.description }}</p>
              </td>
              <td>
                <code>/agent/{{ a.slug }}/</code>
              </td>
              <td>{{ a.skill_names.length }}</td>
              <td>{{ a.default_model_id ? modelName(a.default_model_id) : tr('跟随平台') }}</td>
              <td>
                {{
                  a.default_vision_model_id ? modelName(a.default_vision_model_id) : tr('自动选择')
                }}
              </td>
              <td>
                <span class="badge" :class="{ on: a.enabled }">{{
                  a.enabled ? tr('已启用') : tr('已停用')
                }}</span>
              </td>
              <td>
                <div class="row">
                  <button @click="edit(a)">{{ tr('配置与入口') }}</button
                  ><button class="danger" @click="removeAgent(a)">{{ tr('删除') }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <UiIcon name="access" :size="28" /><strong>{{
            loading ? tr('正在读取…') : tr('创建你的第一个智能体')
          }}</strong
          >{{ tr('配置介绍与技能后，即可提供 MCP 和 A2A 调用入口。') }}
        </div>
      </div>
    </section>
    <section class="card">
      <header class="card-head">
        <div class="heading-line">
          <UiIcon name="users" :size="17" />
          <h2>{{ tr('服务账号') }}</h2>
          <HelpTip
            :text="
              tr(
                '服务账号用于程序接入。创建或更换凭据后只显示一次，请交给调用方保存。凭据与模型 API Key 无关；删除账号会清理其调用历史。免鉴权模式可以跳过此步骤。',
              )
            "
            :label="tr('服务账号说明')"
          />
        </div>
        <span class="badge">{{ accounts.length }}</span>
      </header>
      <div class="card-body">
        <form @submit.prevent="createAccount" novalidate>
          <div class="field-grid">
            <div class="field">
              <label for="sa-name">{{ tr('账号名称') }}</label
              ><input
                id="sa-name"
                v-model="account.name"
                :placeholder="tr('例如：内部应用')"
                maxlength="80"
              />
            </div>
            <div class="field">
              <div class="heading-line">
                <label for="sa-days">{{ tr('凭据有效天数') }}</label
                ><HelpTip :text="tr('有效期为 1–3650 天。凭据到期后需由管理员更换。')" />
              </div>
              <input
                id="sa-days"
                v-model="account.expires_days"
                type="number"
                min="1"
                max="3650"
                step="1"
              />
            </div>
            <div id="sa-scopes" class="checks full">
              <label v-for="scope in scopes" :key="scope" class="check"
                ><input v-model="account.scopes" type="checkbox" :value="scope" /><code>{{
                  scope
                }}</code></label
              >
            </div>
          </div>
          <div class="row" style="margin-top: 18px">
            <button id="sa-create" class="primary" :disabled="creating" :aria-busy="creating">
              <UiIcon name="plus" :size="15" />{{ creating ? tr('正在创建…') : tr('创建服务账号') }}
            </button>
            <p
              id="sa-feedback"
              class="feedback"
              :class="{ bad: accountBad }"
              role="status"
              style="margin: 0"
            >
              {{ accountFeedback }}
            </p>
          </div>
        </form>
      </div>
      <div class="table-wrap">
        <table v-if="accounts.length">
          <thead>
            <tr>
              <th>{{ tr('名称') }}</th>
              <th>{{ tr('权限') }}</th>
              <th>{{ tr('状态') }}</th>
              <th>{{ tr('到期时间') }}</th>
              <th>{{ tr('最近使用') }}</th>
              <th>{{ tr('操作') }}</th>
            </tr>
          </thead>
          <tbody id="service-accounts">
            <tr v-for="a in accounts" :key="a.id">
              <td>{{ a.name }}</td>
              <td>
                <span class="muted small">{{ a.scopes.join(', ') }}</span>
              </td>
              <td>
                <span
                  class="badge"
                  :class="{ on: a.enabled && new Date(a.expires_at) > new Date() }"
                  >{{
                    !a.enabled
                      ? tr('已停用')
                      : new Date(a.expires_at) < new Date()
                        ? tr('已过期')
                        : tr('可用')
                  }}</span
                >
              </td>
              <td>{{ date(a.expires_at) }}</td>
              <td>{{ a.last_used_at ? date(a.last_used_at) : tr('尚未使用') }}</td>
              <td>
                <div class="row">
                  <button @click="rotate(a)">{{ tr('更换凭据') }}</button
                  ><button @click="toggle(a)">{{ a.enabled ? tr('停用') : tr('启用') }}</button
                  ><button class="danger" @click="remove(a)">{{ tr('删除') }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">{{ tr('暂无服务账号') }}</div>
      </div>
    </section>
    <UiModal id="service-secret" v-model="secretOpen" :title="secretTitle" @closed="clearSecret"
      ><template #help
        ><HelpTip
          :text="tr('凭据仅在此显示一次。关闭后无法再次查看；如果遗失，请更换凭据。')"
          :label="tr('凭据保存说明')"
      /></template>
      <div class="stack" v-if="secret">
        <div class="field">
          <label for="service-client-id">Client ID</label
          ><input id="service-client-id" readonly :value="secret.id" />
        </div>
        <div class="field">
          <label for="service-token">{{ tr('服务凭据（只显示一次）') }}</label
          ><textarea id="service-token" readonly :value="secret.token" rows="4" class="mono" />
        </div>
      </div>
      <template #footer
        ><button @click="secretOpen = false">{{ tr('关闭') }}</button
        ><button class="primary" @click="copySecret">
          <UiIcon name="copy" :size="15" />{{ tr('复制凭据') }}
        </button></template
      ></UiModal
    >
    <UiModal
      id="agent-definition-editor"
      v-model="editor"
      :title="editing ? tr('配置智能体') : tr('新建智能体')"
      wide
      :busy="saving"
      ><template #help
        ><HelpTip
          :text="
            tr(
              '通用示例：名称为“我的智能体”，访问路径为 my-agent，对应 /agent/my-agent/。介绍公开展示，执行指令只在服务端使用。',
            )
          "
          :label="tr('智能体配置说明')"
      /></template>
      <form id="agent-definition-form" class="field-grid" @submit.prevent="saveAgent" novalidate>
        <div class="field">
          <label for="agent-definition-name">{{ tr('名称') }}</label
          ><input
            id="agent-definition-name"
            v-model="form.name"
            :placeholder="tr('例如：我的智能体')"
            maxlength="200"
            :disabled="saving"
          />
        </div>
        <div class="field">
          <div class="heading-line">
            <label for="agent-definition-slug">{{ tr('访问路径') }}</label
            ><HelpTip
              :text="
                tr(
                  '使用小写字母、数字和连字符，最多 63 位。创建后固定，用于 /agent/<name>/ 下的调用入口。',
                )
              "
              :label="tr('访问路径说明')"
            />
          </div>
          <input
            id="agent-definition-slug"
            v-model="form.slug"
            :placeholder="tr('例如：my-agent')"
            :readonly="!!editing"
            :disabled="saving"
          />
        </div>
        <div class="field full">
          <label for="agent-definition-description">{{ tr('介绍') }}</label
          ><textarea
            id="agent-definition-description"
            v-model="form.description"
            rows="3"
            :placeholder="tr('说明智能体提供的能力和适用场景')"
            :disabled="saving"
          />
        </div>
        <div class="field">
          <label for="agent-definition-version">{{ tr('版本') }}</label
          ><input id="agent-definition-version" v-model="form.version" :disabled="saving" />
        </div>
        <label class="check"
          ><input
            id="agent-definition-enabled"
            v-model="form.enabled"
            type="checkbox"
            :disabled="saving"
          />{{ tr('启用智能体') }}</label
        >
        <div class="field">
          <label for="agent-definition-model">{{ tr('默认主模型') }}</label
          ><select id="agent-definition-model" v-model="form.default_model_id" :disabled="saving">
            <option value="">{{ tr('跟随平台默认模型') }}</option>
            <option v-for="m in data.models" :key="m.id" :value="m.id">
              {{ m.provider }} / {{ m.name }}
            </option>
            <option
              v-if="
                form.default_model_id && !data.models.some((m) => m.id === form.default_model_id)
              "
              :value="form.default_model_id"
            >
              {{ tr('原模型已删除，请重新选择') }}
            </option>
          </select>
        </div>
        <div class="field">
          <div class="heading-line">
            <label for="agent-definition-vision-model">{{ tr('默认视觉模型') }}</label
            ><HelpTip
              :text="
                tr(
                  '图像推理工具使用的模型。自动选择时跟随平台视觉模型；只列出标记为具备视觉能力的模型。',
                )
              "
              :label="tr('默认视觉模型说明')"
            />
          </div>
          <select
            id="agent-definition-vision-model"
            v-model="form.default_vision_model_id"
            :disabled="saving"
          >
            <option value="">{{ tr('自动选择视觉模型') }}</option>
            <option v-for="m in visionModels" :key="m.id" :value="m.id">
              {{ m.provider }} / {{ m.name }}
            </option>
            <option
              v-if="
                form.default_vision_model_id &&
                !visionModels.some((m) => m.id === form.default_vision_model_id)
              "
              :value="form.default_vision_model_id"
            >
              {{ tr('原视觉模型不可用，请重新选择') }}
            </option>
          </select>
        </div>
        <div class="field full">
          <div class="heading-line">
            <label for="agent-definition-prompt">{{ tr('执行指令') }}</label
            ><HelpTip
              :text="tr('仅在服务端执行，不会公开到 Agent Card。为这个智能体补充角色和工作规则。')"
            />
          </div>
          <textarea
            id="agent-definition-prompt"
            v-model="form.system_prompt"
            rows="5"
            :placeholder="tr('定义角色、工作方式和输出要求（可选）')"
            :disabled="saving"
          />
        </div>
        <div class="field full">
          <div class="row between">
            <div class="heading-line">
              <label>{{ tr('Skills 披露与下发') }}</label
              ><HelpTip
                :text="
                  tr(
                    '选择平台技能。已启用技能才会下发；停用技能仍可保留选择，重新启用后恢复下发。公开 Card 与实际下发使用同一组选项。',
                  )
                "
              />
            </div>
            <button type="button" @click="manageSkills" :disabled="saving">
              {{ tr('管理技能库') }}
            </button>
          </div>
          <div id="agent-definition-skills" class="skill-choices">
            <div v-for="s in data.skills" :key="s.filename" class="skill-choice">
              <label
                ><input
                  v-model="form.skill_names"
                  type="checkbox"
                  :value="s.filename"
                  :disabled="saving"
                /><span
                  ><b>{{ s.name }}</b
                  ><small
                    >{{ s.filename }} ·
                    {{ s.enabled ? tr('已启用') : tr('已停用，当前不下发') }}</small
                  ></span
                ></label
              ><HelpTip :text="s.description" :label="s.name + tr(' 技能说明')" />
            </div>
            <p v-if="!data.skills.length" class="muted">{{ tr('暂无默认 Skill') }}</p>
          </div>
        </div>
        <details class="full">
          <summary class="muted" style="cursor: pointer">{{ tr('公开资料（可选）') }}</summary>
          <div class="field-grid" style="margin-top: 18px">
            <div class="field">
              <label for="agent-definition-documentation">{{ tr('文档网址') }}</label
              ><input
                id="agent-definition-documentation"
                v-model="form.documentationUrl"
                :disabled="saving"
                placeholder="https://…"
              />
            </div>
            <div class="field">
              <label for="agent-definition-icon">{{ tr('图标网址') }}</label
              ><input
                id="agent-definition-icon"
                v-model="form.iconUrl"
                :disabled="saving"
                placeholder="https://…"
              />
            </div>
            <div class="field">
              <label for="agent-definition-provider-name">{{ tr('提供方名称') }}</label
              ><input
                id="agent-definition-provider-name"
                v-model="form.organization"
                :disabled="saving"
              />
            </div>
            <div class="field">
              <label for="agent-definition-provider-url">{{ tr('提供方网址') }}</label
              ><input
                id="agent-definition-provider-url"
                v-model="form.providerUrl"
                :disabled="saving"
                placeholder="https://…"
              />
            </div>
          </div>
        </details>
        <div class="full">
          <hr style="margin: 4px 0 18px" />
          <div class="heading-line">
            <h3>{{ tr('调用入口') }}</h3>
            <HelpTip
              v-if="data.public_url_configured === false"
              id="public-url-warning"
              warning
              :label="tr('公开地址未配置')"
              :text="tr('未配置 UMEKO_PUBLIC_URL，是否已上线？')"
            />
          </div>
          <div id="agent-definition-endpoints" class="endpoint-list">
            <div v-for="(url, key) in endpoints" :key="key" class="endpoint">
              <span>{{ key === 'agent_card' ? 'Agent Card' : key.toUpperCase() }}</span
              ><a :href="url" target="_blank" rel="noopener">{{ url }}</a>
            </div>
            <p v-if="!Object.keys(endpoints).length" class="muted">
              {{ tr('保存后显示完整调用入口。') }}
            </p>
          </div>
        </div>
        <details id="agent-definition-card-preview" class="full">
          <summary style="cursor: pointer" class="muted">{{ tr('查看 Agent Card') }}</summary>
          <pre id="agent-definition-card" class="json-view">{{ card }}</pre>
        </details>
        <p id="agent-definition-feedback" class="feedback full" :class="{ bad }" role="status">
          {{ feedback }}
        </p>
      </form>
      <template #footer
        ><button :disabled="saving" @click="editor = false">{{ tr('关闭') }}</button
        ><button
          id="agent-definition-save"
          class="primary"
          form="agent-definition-form"
          :disabled="saving"
        >
          <UiIcon name="save" :size="15" />{{ saving ? tr('正在保存…') : tr('保存') }}
        </button></template
      ></UiModal
    >
  </section>
</template>
