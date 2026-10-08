<template>
  <article class="conversation">
    <section id="tool-activity" class="tool-activity hidden" aria-live="polite">
      <div id="tool-activity-title" class="tool-activity-title"></div>
      <div id="tool-activity-list" class="tool-activity-list"></div>
    </section>
    <div id="messages" class="messages" aria-live="polite">
      <div class="message assistant" data-i18n="message.welcome">
        描述你的任务，可以附带文档或图片。
      </div>
    </div>
    <div
      id="composer-resizer"
      class="layout-resizer horizontal"
      role="separator"
      data-i18n-aria="resizer.composer"
      aria-label="调整输入区高度"
      aria-orientation="horizontal"
      tabindex="0"
    ></div>
    <form id="composer" class="composer">
      <label class="file-button" data-i18n-title="composer.attachTitle" title="添加附件">
        <input id="file" type="file" multiple />
        <span data-i18n="composer.attach">＋ 附件</span>
      </label>
      <div id="attachments" class="attachments"></div>
      <div
        class="context-controls"
        data-i18n-title="context.hintTitle"
        title="上下文长度为近似估算，不代表供应商计费 token"
      >
        <span id="context-status">上下文 --</span>
        <div class="context-menu-wrap">
          <button
            id="compact-context"
            type="button"
            aria-haspopup="menu"
            aria-expanded="false"
            data-i18n="context.menu"
          >
            上下文 ▾
          </button>
          <div id="context-menu" class="context-menu hidden" role="menu">
            <button
              id="context-menu-compact"
              type="button"
              role="menuitem"
              data-i18n="context.compact"
            >
              压缩上下文
            </button>
            <button id="context-menu-clear" type="button" role="menuitem" data-i18n="context.clear">
              强制清空上下文
            </button>
            <button
              id="context-menu-clear-chat"
              type="button"
              role="menuitem"
              class="danger"
              data-i18n="context.clearChat"
            >
              清空聊天记录
            </button>
          </div>
        </div>
      </div>
      <div class="composer-input">
        <textarea
          id="prompt"
          rows="3"
          data-i18n-placeholder="composer.placeholder"
          placeholder="例如：帮我汇总这几个文档的要点（Enter 发送，Shift+Enter 换行）"
          required
        ></textarea>
        <div class="composer-toolbar">
          <div class="model-menu-wrap">
            <button
              id="model-picker"
              class="model-pill"
              type="button"
              aria-haspopup="menu"
              aria-expanded="false"
              data-i18n-title="model.pickerTitle"
              title="选择本会话使用的主模型"
            >
              默认模型 ▾
            </button>
          </div>
          <button id="send" type="submit" data-i18n="composer.send">发送</button>
          <button id="stop" class="stop-run hidden" type="button" data-i18n="composer.stop">
            停止
          </button>
        </div>
      </div>
      <div class="composer-drop-hint" data-i18n="composer.dropHint">
        松开后保存到 output，并添加为对话附件
      </div>
    </form>
  </article>
</template>
