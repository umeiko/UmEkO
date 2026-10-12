<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue';
import ThemeSwitch from '../shared/ThemeSwitch.vue';
import BrandMark from '../shared/BrandMark.vue';
import UiIcon from '../shared/UiIcon.vue';
import SessionBar from './components/SessionBar.vue';
import FileSidebar from './components/FileSidebar.vue';
import ConversationPane from './components/ConversationPane.vue';
import PreviewPane from './components/PreviewPane.vue';
import WorkspaceDialogs from './components/WorkspaceDialogs.vue';
import { mountWorkspaceRuntime } from './runtime.js';
import { temporaryWorkspacePath } from '../shared/api.js';
const temporaryState = ref(temporaryWorkspacePath() ? 'pending' : 'ready');
const reconnect = () => window.location.reload();
let dispose;
onMounted(() => {
  dispose = mountWorkspaceRuntime({
    onTemporaryState: (state) => {
      temporaryState.value = state;
    },
  });
});
onBeforeUnmount(() => dispose?.());
</script>
<template>
  <section v-show="temporaryState !== 'ready'" class="temporary-page" aria-live="polite">
    <header class="temporary-page-header">
      <div class="brand"><BrandMark /><strong>UMEKO</strong></div>
      <ThemeSwitch v-if="temporaryState !== 'ready'" localized />
    </header>
    <article class="temporary-page-card">
      <UiIcon name="panelRight" :size="36" />
      <div v-show="temporaryState === 'expired'">
        <h1 data-i18n="temporary.expiredTitle">该节点已过期</h1>
        <p data-i18n="temporary.expiredHint">请重新申请临时工作台。</p>
      </div>
      <div v-show="temporaryState === 'pending'">
        <h1 data-i18n="temporary.pendingTitle">正在准备临时工作台</h1>
        <p data-i18n="temporary.pendingHint">任务已接收，工作台准备好后将自动打开。</p>
      </div>
      <div v-show="temporaryState === 'error'">
        <h1 data-i18n="temporary.errorTitle">暂时无法连接</h1>
        <p data-i18n="temporary.errorHint">请检查连接，刷新页面重试。</p>
        <button type="button" @click="reconnect" data-i18n="temporary.retry">重新连接</button>
      </div>
    </article>
  </section>
  <main
    v-show="temporaryState === 'ready'"
    class="shell"
    :class="{ 'temporary-workspace': Boolean(temporaryWorkspacePath()) }"
  >
    <header class="workbench-title">
      <div class="brand">
        <BrandMark /><strong>UMEKO</strong><span class="workbench-divider"></span
        ><span class="workbench-label" data-i18n="workbench.title">工作台</span>
      </div>
      <div class="workbench-actions">
        <button
          id="toggle-preview"
          class="preview-toggle"
          type="button"
          aria-controls="preview-panel"
          aria-expanded="false"
        >
          <UiIcon name="panelRight" :size="18" /><span
            id="preview-toggle-label"
            class="preview-toggle-label"
            >展开预览</span
          >
        </button>
        <ThemeSwitch localized />
      </div>
      <div id="temporary-expiry" class="temporary-expiry hidden" role="status">
        <span id="temporary-expiry-label"></span>
      </div>
    </header>
    <SessionBar />
    <section class="workspace">
      <FileSidebar />
      <div
        id="left-resizer"
        class="layout-resizer vertical"
        role="separator"
        data-i18n-aria="resizer.filebar"
        aria-label="调整文件栏宽度"
        aria-orientation="vertical"
        tabindex="0"
      ></div>
      <ConversationPane />
      <div
        id="right-resizer"
        class="layout-resizer vertical"
        role="separator"
        data-i18n-aria="resizer.preview"
        aria-label="调整预览栏宽度"
        aria-orientation="vertical"
        tabindex="0"
      ></div>
      <PreviewPane />
    </section>
  </main>
  <WorkspaceDialogs />
</template>
