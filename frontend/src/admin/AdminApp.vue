<script setup>
import { useAdminI18n } from '../shared/adminI18n.js';
const { tr } = useAdminI18n();
import { ref, computed, onMounted } from 'vue';
import UiIcon from '../shared/UiIcon.vue';
import BrandMark from '../shared/BrandMark.vue';
import ThemeSwitch from '../shared/ThemeSwitch.vue';
import LanguageSwitch from '../shared/LanguageSwitch.vue';
import UiModal from '../shared/UiModal.vue';
import HelpTip from '../shared/HelpTip.vue';
import { admin, api, notify, run, settleConfirm, settleFields } from './state.js';
import AccessView from './views/AccessView.vue';
import ProvidersView from './views/ProvidersView.vue';
import UsersView from './views/UsersView.vue';
import SessionsView from './views/SessionsView.vue';
import ResourcesView from './views/ResourcesView.vue';
import SkillsView from './views/SkillsView.vue';
const tabs = computed(() => [
  ['access', tr('服务接入'), 'access', tr('接入方式、智能体与服务账号')],
  ['providers', tr('模型与供应商'), 'providers', tr('供应商、模型能力与并发控制')],
  ['dskills', tr('技能库'), 'skills', tr('技能文件、脚本与下发管理')],
  ['users', tr('用户管理'), 'users', tr('用户账号与权限')],
  ['sessions', tr('会话管理'), 'sessions', tr('会话历史与内存状态')],
  ['resources', tr('资源监控'), 'resources', tr('服务器资源、模型队列与调用任务')],
]);
const views = {
  access: AccessView,
  providers: ProvidersView,
  users: UsersView,
  sessions: SessionsView,
  resources: ResourcesView,
  dskills: SkillsView,
};
const username = ref(''),
  password = ref(''),
  error = ref(''),
  busy = ref(false),
  nav = ref(false);
onMounted(async () => {
  try {
    admin.user = await api('GET', '/admin/v1/me');
  } catch {
  } finally {
    admin.ready = true;
  }
});
async function login() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    admin.user = await api('POST', '/admin/login', {
      username: username.value,
      password: password.value,
    });
    password.value = '';
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function logout() {
  await run(async () => {
    await api('POST', '/admin/logout');
    admin.user = null;
  });
}
function select(id) {
  admin.tab = id;
  nav.value = false;
}
</script>
<template>
  <div v-if="!admin.user" class="login-theme"><LanguageSwitch /><ThemeSwitch localized /></div>
  <div v-if="!admin.ready" class="admin-login muted">{{ tr('正在连接管理服务…') }}</div>
  <div v-else-if="!admin.user" class="admin-login">
    <section class="login-card">
      <div class="brand">
        <BrandMark />
        <div>UMEKO</div>
      </div>
      <h1>{{ tr('登录管理控制台') }}</h1>
      <form @submit.prevent="login">
        <div class="field">
          <label for="l-user">{{ tr('用户名') }}</label
          ><input id="l-user" v-model="username" autocomplete="username" required />
        </div>
        <div class="field">
          <label for="l-pass">{{ tr('密码') }}</label
          ><input
            id="l-pass"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
          />
        </div>
        <p v-if="error" class="feedback bad" role="alert">{{ error }}</p>
        <button class="primary" :disabled="busy">{{ busy ? tr('正在登录…') : tr('登录') }}</button>
      </form>
    </section>
  </div>
  <div v-else class="admin-layout">
    <div v-if="nav" class="nav-scrim" @click="nav = false"></div>
    <aside class="admin-sidebar" :class="{ open: nav }">
      <div class="brand">
        <BrandMark />
        <div>UMEKO</div>
      </div>
      <nav class="admin-nav" :aria-label="tr('管理导航')">
        <button
          v-for="[id, label, icon] in tabs"
          :id="'tab-' + id"
          :key="id"
          :class="{ active: admin.tab === id }"
          :aria-current="admin.tab === id ? 'page' : undefined"
          @click="select(id)"
        >
          <UiIcon :name="icon" /><span>{{ label }}</span>
        </button>
      </nav>
      <div class="sidebar-footer">
        <div class="admin-profile">
          <span class="admin-avatar"><UiIcon name="shield" :size="16" /></span>
          <div class="grow">
            <strong>{{ admin.user.username }}</strong>
            <div class="muted small">{{ tr('管理员') }}</div>
          </div>
          <button class="icon-button" :aria-label="tr('退出登录')" @click="logout">
            <UiIcon name="logout" :size="16" />
          </button>
        </div>
      </div>
    </aside>
    <main class="admin-content">
      <header class="admin-topbar">
        <div class="breadcrumb">
          <button
            class="icon-button mobile-nav-toggle"
            :aria-label="tr('打开导航')"
            @click="nav = true"
          >
            <UiIcon name="menu" /></button
          ><span>{{ tr('控制台') }}</span
          ><span>/</span><span>{{ tabs.find((t) => t[0] === admin.tab)?.[1] }}</span>
        </div>
        <div class="row">
          <span class="admin-connection"
            ><span class="connection-dot"></span>{{ tr('管理服务已连接') }}</span
          ><LanguageSwitch /><ThemeSwitch localized />
        </div>
      </header>
      <div class="page-title">
        <h1>{{ tabs.find((t) => t[0] === admin.tab)?.[1] }}</h1>
        <HelpTip :text="tabs.find((t) => t[0] === admin.tab)?.[3]" />
      </div>
      <component :is="views[admin.tab]" :key="admin.tab" />
    </main>
  </div>
  <UiModal
    :model-value="!!admin.confirm"
    :title="admin.confirm?.title"
    @update:model-value="
      (v) => {
        if (!v) settleConfirm(false);
      }
    "
    ><p style="line-height: 1.9; margin: 0">{{ admin.confirm?.text }}</p>
    <template #footer
      ><button @click="settleConfirm(false)">{{ tr('取消') }}</button
      ><button class="danger" @click="settleConfirm(true)">{{ tr('确认') }}</button></template
    ></UiModal
  >
  <UiModal
    :model-value="!!admin.fields"
    :title="admin.fields?.title"
    @update:model-value="
      (v) => {
        if (!v) settleFields(null);
      }
    "
    ><form id="fields-form" class="stack" @submit.prevent="settleFields({ ...admin.fields.value })">
      <div v-for="f in admin.fields?.fields" :key="f.name" class="field">
        <label :for="'field-' + f.name">{{ f.label }}</label
        ><textarea
          v-if="f.type === 'textarea'"
          :id="'field-' + f.name"
          v-model="admin.fields.value[f.name]"
          :rows="f.rows || 8"
          :required="f.required"
          :placeholder="f.placeholder"
        /><select
          v-else-if="f.options"
          :id="'field-' + f.name"
          v-model="admin.fields.value[f.name]"
        >
          <option v-for="o in f.options" :key="o.value" :value="o.value">
            {{ o.label }}
          </option></select
        ><input
          v-else
          :id="'field-' + f.name"
          v-model="admin.fields.value[f.name]"
          :type="f.type || 'text'"
          :required="f.required"
          :min="f.min"
          :step="f.step"
          :placeholder="f.placeholder"
          autocomplete="off"
        />
      </div>
    </form>
    <template #footer
      ><button @click="settleFields(null)">{{ tr('取消') }}</button
      ><button class="primary" form="fields-form">{{ tr('保存') }}</button></template
    ></UiModal
  >
  <div class="toast-stack" aria-live="polite">
    <div
      v-for="toast in admin.toasts"
      :key="toast.id"
      class="toast"
      :class="{ bad: toast.bad }"
      role="status"
    >
      {{ toast.message }}
    </div>
  </div>
</template>
