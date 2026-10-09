<script setup>
import { onMounted, onBeforeUnmount } from 'vue';
import ThemeSwitch from '../shared/ThemeSwitch.vue';
import BrandMark from '../shared/BrandMark.vue';
import UiIcon from '../shared/UiIcon.vue';
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
