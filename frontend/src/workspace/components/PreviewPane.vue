<script setup>
import WorkspaceHelp from './WorkspaceHelp.vue';
import UiIcon from '../../shared/UiIcon.vue';
</script>
<template>
  <aside id="preview-panel" class="preview">
    <div class="preview-head">
      <div class="preview-heading">
        <p id="preview-kicker" class="hidden" aria-hidden="true"></p>
        <div class="panel-heading">
          <h2 id="preview-title">预览</h2>
          <WorkspaceHelp help-key="preview.help" />
        </div>
      </div>
      <div class="preview-actions">
        <button id="save-resource" class="text-button hidden" type="button" data-i18n="action.save">
          保存
        </button>
        <button
          id="delete-resource"
          class="danger-button hidden"
          type="button"
          data-i18n="action.delete"
        >
          删除
        </button>
        <button
          id="attach-workspace-file"
          class="attach-button hidden"
          type="button"
          data-i18n="preview.attach"
        >
          ＋ 加入聊天附件
        </button>
        <a
          id="download-file"
          class="file-download hidden"
          href="#"
          download
          data-i18n-title="preview.download"
          data-i18n-aria="preview.download"
          title="下载文件"
          aria-label="下载文件"
          ><UiIcon name="download" :size="19"
        /></a>
      </div>
    </div>
    <div id="canvas" class="canvas empty" data-i18n="canvas.empty">暂无预览</div>
    <div id="markdown-toolbar" class="preview-format-toolbar hidden">
      <div
        class="preview-modes"
        role="group"
        data-i18n-aria="preview.modeLabel"
        aria-label="Markdown 显示方式"
      >
        <button
          id="markdown-rendered"
          type="button"
          class="preview-mode-tab"
          aria-pressed="true"
          data-i18n="preview.rendered"
        >
          预览
        </button>
        <button
          id="markdown-source"
          type="button"
          class="preview-mode-tab"
          aria-pressed="false"
          data-i18n="preview.source"
        >
          原文
        </button>
      </div>
      <button id="copy-markdown" type="button" class="code-copy" data-code-copy>
        <UiIcon name="copy" :size="15" /><span class="copy-label" data-i18n="preview.copySource"
          >复制原文</span
        >
      </button>
    </div>
    <article id="markdown-view" class="document-view markdown-body hidden"></article>
    <section
      id="csv-view"
      class="csv-view hidden"
      data-i18n-aria="csv.aria"
      aria-label="CSV 表格预览"
    ></section>
    <section id="code-panel" class="file-code-panel hidden">
      <div class="code-toolbar">
        <span id="preview-code-language" class="code-language"></span
        ><button type="button" id="copy-file-code" class="code-copy" data-code-copy>
          <UiIcon name="copy" :size="15" /><span class="copy-label" data-i18n="code.copy"
            >复制代码</span
          >
        </button>
      </div>
      <pre id="code-view" class="code-view" tabindex="0"></pre>
    </section>
    <textarea id="resource-editor" class="resource-editor hidden" spellcheck="false"></textarea>
  </aside>
</template>
