<template>
  <aside class="preview">
    <div class="preview-head">
      <div>
        <p id="preview-kicker" class="eyebrow">PREVIEW</p>
        <h2 id="preview-title">预览</h2>
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
          id="open-file"
          class="text-link hidden"
          href="#"
          target="_blank"
          data-i18n="preview.openFile"
          >打开原文件</a
        >
        <button
          id="collapse-preview"
          class="text-button"
          type="button"
          data-i18n="preview.collapse"
          data-i18n-title="preview.collapseTitle"
          data-i18n-aria="preview.collapseTitle"
          title="收起预览面板"
          aria-label="收起预览面板"
        >
          收起 ›
        </button>
      </div>
    </div>
    <div id="canvas" class="canvas empty" data-i18n="canvas.empty">
      点击左侧文件预览；对话中的产物也会出现在这里。
    </div>
    <article id="markdown-view" class="document-view hidden"></article>
    <section
      id="csv-view"
      class="csv-view hidden"
      data-i18n-aria="csv.aria"
      aria-label="CSV 表格预览"
    ></section>
    <pre id="code-view" class="code-view hidden"></pre>
    <textarea id="resource-editor" class="resource-editor hidden" spellcheck="false"></textarea>
  </aside>
</template>
