<script setup>
import UiIcon from '../../shared/UiIcon.vue';
</script>
<template>
  <aside class="filebar">
    <div class="filebar-head">
      <div>
        <p class="eyebrow">CLIENT</p>
        <h2 id="sidebar-title">output</h2>
      </div>
      <div class="filebar-actions">
        <button
          id="file-actions"
          class="icon-button"
          type="button"
          data-i18n-title="filebar.newEntry"
          data-i18n-aria="filebar.newEntry"
          title="新建文件或目录"
          aria-label="新建文件或目录"
        >
          <UiIcon name="plus" :size="16" /></button
        ><button
          id="refresh-tree"
          class="icon-button"
          type="button"
          data-i18n-title="filebar.refresh"
          data-i18n-aria="filebar.refresh"
          title="刷新文件树"
          aria-label="刷新文件树"
        >
          <UiIcon name="refresh" :size="15" />
        </button>
      </div>
    </div>
    <nav class="sidebar-tabs" data-i18n-aria="sidebar.resourcesAria" aria-label="客户端资源">
      <button class="sidebar-tab active" data-section="workspace" type="button">Workspace</button>
      <button class="sidebar-tab" data-section="skills" type="button">Skills</button>
    </nav>
    <div id="workspace-panel" class="sidebar-panel active">
      <div class="tree-filter">
        <input
          id="tree-filter"
          type="search"
          data-i18n-placeholder="tree.filterPlaceholder"
          placeholder="过滤文件名，如 image-*"
          spellcheck="false"
        /><button
          id="tree-filter-clear"
          class="icon-button"
          type="button"
          data-i18n-title="tree.filterClear"
          title="清除过滤"
          aria-label="清除过滤"
          hidden
        >
          ×
        </button>
      </div>
      <div id="file-tree" class="file-tree">
        <p class="tree-empty" data-i18n="tree.loading">正在读取文件…</p>
      </div>
      <div class="drop-hint" data-i18n="drop.hint">拖入文件，保存到当前 Session</div>
    </div>
    <div id="skills-panel" class="sidebar-panel resource-list"></div>
  </aside>
</template>
