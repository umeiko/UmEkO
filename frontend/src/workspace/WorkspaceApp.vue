<script setup>
import { onMounted, onBeforeUnmount } from 'vue';
import ThemeSwitch from '../shared/ThemeSwitch.vue';
import BrandMark from '../shared/BrandMark.vue';
import SessionBar from './components/SessionBar.vue';
import FileSidebar from './components/FileSidebar.vue';
import ConversationPane from './components/ConversationPane.vue';
import PreviewPane from './components/PreviewPane.vue';
import WorkspaceDialogs from './components/WorkspaceDialogs.vue';
import { mountWorkspaceRuntime } from './runtime.js';
let dispose;
onMounted(() => {
  dispose = mountWorkspaceRuntime();
});
onBeforeUnmount(() => dispose?.());
</script>
<template>
  <main class="shell">
    <header class="workbench-title">
      <div class="brand">
        <BrandMark /><strong>UMEKO</strong><span class="workbench-divider"></span
        ><span class="workbench-label">工作台</span>
      </div>
      <div class="workbench-actions">
        <ThemeSwitch localized />
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
      <PreviewPane /><button
        id="expand-preview"
        class="preview-expand-tab"
        type="button"
        data-i18n-title="preview.expandTitle"
        data-i18n-aria="preview.expandTitle"
        title="展开预览面板"
        aria-label="展开预览面板"
        aria-expanded="false"
      >
        <span class="expand-icon">‹</span>
      </button>
    </section>
  </main>
  <WorkspaceDialogs />
</template>
