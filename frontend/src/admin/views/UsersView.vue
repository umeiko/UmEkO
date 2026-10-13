<script setup>
import { useAdminI18n } from '../../shared/adminI18n.js';
const { tr, date } = useAdminI18n();
import { ref, reactive, computed, onMounted } from 'vue';
import { api, ask, confirm, notify, run, sessionsFor } from '../state.js';
import UiIcon from '../../shared/UiIcon.vue';
import UiModal from '../../shared/UiModal.vue';
import { encode } from '../../shared/api.js';
const users = ref([]),
  error = ref(''),
  loading = ref(true);
const settingsUser = ref(null),
  settingsOpen = ref(false),
  settingsLoading = ref(false),
  settingsSaving = ref(false),
  settingsError = ref(''),
  providers = ref([]);
const access = reactive({ allowed_provider_ids: null, allowed_model_ids: null });
const allModels = computed(() => providers.value.flatMap((p) => p.models));
const providerAllowed = (id) =>
  access.allowed_provider_ids === null || access.allowed_provider_ids.includes(id);
const modelAllowed = (id) =>
  access.allowed_model_ids === null || access.allowed_model_ids.includes(id);
const availableCount = computed(
  () =>
    providers.value
      .filter((p) => providerAllowed(p.id))
      .flatMap((p) => p.models)
      .filter((m) => m.user_enabled && modelAllowed(m.id)).length,
);
function selectScope(key, ids, id, checked) {
  const selected = access[key] === null ? ids : access[key];
  access[key] = checked
    ? [...new Set([...selected, id])]
    : selected.filter((value) => value !== id);
}
async function userSettings(u) {
  settingsLoading.value = true;
  await run(async () => {
    const data = await api('GET', `/admin/v1/users/${encode(u.id)}/model-access`);
    providers.value = data.providers;
    access.allowed_provider_ids = data.allowed_provider_ids;
    access.allowed_model_ids = data.allowed_model_ids;
    settingsUser.value = u;
    settingsError.value = '';
    settingsOpen.value = true;
  });
  settingsLoading.value = false;
}
async function saveSettings() {
  if (settingsSaving.value) return;
  settingsSaving.value = true;
  settingsError.value = '';
  try {
    await api('PUT', `/admin/v1/users/${encode(settingsUser.value.id)}/model-access`, {
      ...access,
    });
    settingsOpen.value = false;
    notify(tr('用户模型权限已保存'));
  } catch (e) {
    settingsError.value = e.message;
  } finally {
    settingsSaving.value = false;
  }
}
async function load() {
  try {
    users.value = await api('GET', '/admin/v1/users');
    error.value = '';
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
async function create() {
  const r = await ask(tr('新建用户'), [
    { name: 'username', label: tr('用户名'), required: true },
    { name: 'password', label: tr('密码'), type: 'password', required: true },
    {
      name: 'role',
      label: tr('角色'),
      value: 'user',
      options: [
        { value: 'user', label: tr('用户') },
        { value: 'admin', label: tr('管理员') },
      ],
    },
  ]);
  if (!r) return;
  await run(async () => {
    await api('POST', '/admin/v1/users', r);
    await load();
    notify(tr('用户已创建'));
  });
}
async function password(u) {
  const r = await ask(tr('重置 ') + u.username + tr(' 的密码'), [
    { name: 'password', label: tr('新密码'), type: 'password', required: true },
  ]);
  if (!r) return;
  await run(async () => {
    await api('PUT', `/admin/v1/users/${encode(u.id)}/password`, r);
    notify(tr('密码已重置'));
  });
}
async function role(u) {
  const r = await ask(tr('修改用户角色'), [
    {
      name: 'role',
      label: tr('角色'),
      value: u.role,
      options: [
        { value: 'user', label: tr('用户') },
        { value: 'admin', label: tr('管理员') },
      ],
    },
  ]);
  if (!r) return;
  await run(async () => {
    await api('PUT', `/admin/v1/users/${encode(u.id)}/role`, r);
    await load();
    notify(tr('角色已更新'));
  });
}
async function remove(u) {
  if (
    !(await confirm(
      tr('删除用户'),
      tr('永久删除“{p0}”及其全部会话、附件和历史记录？', { p0: u.username }),
    ))
  )
    return;
  await run(async () => {
    await api('DELETE', `/admin/v1/users/${encode(u.id)}`);
    await load();
    notify(tr('用户已删除'));
  });
}
</script>
<template>
  <section id="page-users" class="card">
    <header class="card-head">
      <h2>
        {{ tr('用户账号') }} <span class="badge">{{ users.length }}</span>
      </h2>
      <button class="primary" @click="create">
        <UiIcon name="plus" :size="15" />{{ tr('新建用户') }}
      </button>
    </header>
    <p v-if="error" class="feedback bad card-body">
      {{ error }} <button @click="load">{{ tr('重试') }}</button>
    </p>
    <div class="table-wrap">
      <table v-if="users.length">
        <thead>
          <tr>
            <th>{{ tr('用户名') }}</th>
            <th>{{ tr('角色') }}</th>
            <th>{{ tr('会话数') }}</th>
            <th>{{ tr('创建时间') }}</th>
            <th>{{ tr('操作') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>
              <strong>{{ u.username }}</strong>
            </td>
            <td>
              <span class="badge" :class="{ on: u.role === 'admin' }">{{
                u.role === 'admin' ? tr('管理员') : tr('用户')
              }}</span>
            </td>
            <td>{{ u.session_count }}</td>
            <td>{{ date(u.created_at) }}</td>
            <td>
              <div class="row">
                <button :disabled="settingsLoading" @click="userSettings(u)">
                  {{ tr('用户设置') }}
                </button>
                <button @click="sessionsFor(u)">{{ tr('查看会话') }}</button
                ><button @click="password(u)">{{ tr('重置密码') }}</button
                ><button @click="role(u)">{{ tr('修改角色') }}</button
                ><button class="danger" @click="remove(u)">{{ tr('删除') }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">{{ loading ? tr('正在读取…') : tr('暂无用户') }}</div>
    </div>
    <UiModal
      id="user-model-access"
      v-model="settingsOpen"
      :busy="settingsSaving"
      wide
      :title="tr('用户设置') + ' · ' + (settingsUser?.username || '')"
    >
      <form id="user-model-access-form" class="stack" @submit.prevent="saveSettings">
        <p class="muted">
          {{ tr('选择该用户可用的供应商与模型。只有已下发且在两个开放范围内的模型可以使用。') }}
        </p>
        <fieldset :disabled="settingsSaving" class="stack">
          <legend>{{ tr('供应商开放范围') }}</legend>
          <div class="row">
            <label class="check"
              ><input
                id="user-all-providers"
                type="checkbox"
                :checked="access.allowed_provider_ids === null"
                @change="
                  access.allowed_provider_ids = $event.target.checked
                    ? null
                    : providers.map((p) => p.id)
                "
              />
              {{ tr('全部供应商（含以后新增）') }}</label
            >
            <button type="button" @click="access.allowed_provider_ids = []">
              {{ tr('清空供应商选择') }}
            </button>
          </div>
          <label v-for="p in providers" :key="p.id" class="check">
            <input
              :id="'user-provider-' + p.id"
              type="checkbox"
              :checked="providerAllowed(p.id)"
              @change="
                selectScope(
                  'allowed_provider_ids',
                  providers.map((p) => p.id),
                  p.id,
                  $event.target.checked,
                )
              "
            />
            <span>{{ p.name }}</span>
          </label>
          <p v-if="!providers.length" class="muted">{{ tr('尚未配置供应商') }}</p>
        </fieldset>
        <fieldset :disabled="settingsSaving" class="stack">
          <legend>{{ tr('模型开放范围') }}</legend>
          <div class="row">
            <label class="check"
              ><input
                id="user-all-models"
                type="checkbox"
                :checked="access.allowed_model_ids === null"
                @change="
                  access.allowed_model_ids = $event.target.checked
                    ? null
                    : allModels.map((m) => m.id)
                "
              />
              {{ tr('全部下发模型（含以后新增）') }}</label
            >
            <button type="button" @click="access.allowed_model_ids = []">
              {{ tr('清空模型选择') }}
            </button>
          </div>
          <section v-for="p in providers" :key="p.id" class="model-access-provider">
            <strong>{{ p.name }}</strong>
            <div class="model-access-models">
              <label v-for="m in p.models" :key="m.id" class="check">
                <input
                  :id="'user-model-' + m.id"
                  type="checkbox"
                  :checked="providerAllowed(p.id) && m.user_enabled && modelAllowed(m.id)"
                  :disabled="!providerAllowed(p.id) || !m.user_enabled"
                  @change="
                    selectScope(
                      'allowed_model_ids',
                      allModels.map((item) => item.id),
                      m.id,
                      $event.target.checked,
                    )
                  "
                />
                <span>{{ m.name }}</span
                ><small v-if="!m.user_enabled" class="badge">{{ tr('未下发') }}</small>
              </label>
            </div>
          </section>
        </fieldset>
        <p>{{ tr('当前开放 {count} 个模型', { count: availableCount }) }}</p>
        <p class="muted">
          {{
            tr(
              '保存后从下一轮调用生效。已选但不再开放的模型会回退到可用模型；没有可用模型时暂停调用。',
            )
          }}
        </p>
        <p v-if="settingsError" class="feedback bad" role="alert">{{ settingsError }}</p>
      </form>
      <template #footer>
        <button :disabled="settingsSaving" @click="settingsOpen = false">{{ tr('取消') }}</button>
        <button
          id="user-model-access-save"
          class="primary"
          type="submit"
          form="user-model-access-form"
          :disabled="settingsSaving"
        >
          {{ tr('保存') }}
        </button>
      </template>
    </UiModal>
  </section>
</template>
<style scoped>
.model-access-provider {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.model-access-models {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr));
}
.check span {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
