<script setup>
import BrandMark from '../../shared/BrandMark.vue';
import ThemeSwitch from '../../shared/ThemeSwitch.vue';
import WorkspaceHelp from './WorkspaceHelp.vue';
</script>
<template>
  <div id="file-context-menu" class="file-context-menu hidden" role="menu">
    <button type="button" data-file-action="new-file" data-i18n="fileMenu.newFile">
      新建文本文件
    </button>
    <button type="button" data-file-action="new-directory" data-i18n="fileMenu.newDir">
      新建目录
    </button>
    <button type="button" data-file-action="paste" data-i18n="fileMenu.paste">粘贴</button>
    <hr />
    <button type="button" data-file-action="copy" data-i18n="fileMenu.copy">复制</button>
    <button type="button" data-file-action="cut" data-i18n="fileMenu.cut">剪切</button>
    <button type="button" data-file-action="rename" data-i18n="fileMenu.rename">重命名</button>
    <button type="button" data-file-action="extract" data-i18n="fileMenu.extract">
      解压到此处
    </button>
    <button type="button" data-file-action="download" data-i18n="fileMenu.download">下载</button>
    <hr />
    <button
      type="button"
      class="danger-menu-item"
      data-file-action="delete"
      data-i18n="action.delete"
    >
      删除
    </button>
  </div>
  <dialog id="file-entry-dialog" class="resource-dialog">
    <form id="file-entry-form">
      <h2 id="file-entry-title">新建文件</h2>
      <label for="file-entry-name" data-i18n="form.name">名称</label
      ><input id="file-entry-name" maxlength="180" required autocomplete="off" />
      <p id="file-entry-help" class="dialog-help"></p>
      <div class="dialog-actions">
        <button id="file-entry-cancel" class="text-button" type="button" data-i18n="action.cancel">
          取消</button
        ><button class="attach-button" type="submit" data-i18n="action.confirm">确认</button>
      </div>
    </form>
  </dialog>
  <dialog id="resource-dialog" class="resource-dialog">
    <form id="resource-dialog-form" method="dialog">
      <div class="panel-heading">
        <h2 id="resource-dialog-title" data-i18n="skill.new">新建 Skill</h2>
        <WorkspaceHelp help-key="skill.help" />
      </div>
      <label for="resource-name" data-i18n="form.name">名称</label>
      <input
        id="resource-name"
        name="name"
        autocomplete="off"
        required
        pattern="[A-Za-z0-9_-]+"
        autofocus
      />
      <label for="resource-description" data-i18n="skill.description">需求描述</label>
      <textarea
        id="resource-description"
        rows="6"
        data-i18n-placeholder="skill.descPlaceholder"
        placeholder="描述适用场景、触发条件、操作规范或直接粘贴完整需求"
      ></textarea>
      <div class="dialog-actions">
        <button
          id="resource-dialog-cancel"
          class="text-button"
          type="button"
          data-i18n="action.cancel"
        >
          取消
        </button>
        <button class="text-button" type="submit" value="blank" data-i18n="skill.blank">
          空白模板
        </button>
        <button class="attach-button" type="submit" value="generate" data-i18n="skill.generate">
          AI 生成
        </button>
      </div>
    </form>
  </dialog>
  <dialog id="tool-detail-dialog" class="tool-detail-dialog">
    <div class="tool-detail-shell">
      <header class="tool-detail-head">
        <div>
          <h2 id="tool-detail-title" data-i18n="tool.detail">工具调用详情</h2>
          <p id="tool-detail-meta" class="tool-detail-meta"></p>
        </div>
        <button
          id="tool-detail-close"
          class="tool-detail-close"
          type="button"
          data-i18n-aria="tool.closeAria"
          aria-label="关闭工具调用详情"
        >
          ×
        </button>
      </header>
      <section id="tool-images-section" class="tool-detail-section hidden">
        <div class="tool-detail-section-head">
          <span data-i18n="tool.images">涉及图片</span><WorkspaceHelp help-key="tool.imagesSub" />
        </div>
        <div id="tool-images" class="tool-images"></div>
      </section>
      <section class="tool-detail-section">
        <div class="tool-detail-section-head">
          <span data-i18n="tool.request">模型请求</span><WorkspaceHelp help-key="tool.requestSub" />
        </div>
        <pre id="tool-detail-request" tabindex="0"></pre>
      </section>
      <section class="tool-detail-section">
        <div class="tool-detail-section-head">
          <span data-i18n="tool.result">工具返回</span><WorkspaceHelp help-key="tool.resultSub" />
        </div>
        <pre id="tool-detail-result" tabindex="0"></pre>
      </section>
    </div>
  </dialog>
  <dialog id="auth-dialog" class="resource-dialog auth-dialog">
    <form id="auth-form">
      <div class="auth-brand"><BrandMark /><strong>UMEKO</strong><ThemeSwitch localized /></div>
      <h2 data-i18n="auth.title">登录工作台</h2>
      <label for="auth-username" data-i18n="auth.username">用户名</label
      ><input id="auth-username" autocomplete="username" required minlength="3" autofocus />
      <label for="auth-password" data-i18n="auth.password">密码</label
      ><input
        id="auth-password"
        type="password"
        autocomplete="current-password"
        required
        minlength="4"
      />
      <p id="auth-error" class="dialog-help"></p>
      <div class="dialog-actions">
        <button id="register" class="text-button" type="button" data-i18n="auth.register">
          注册</button
        ><button class="attach-button" type="submit" data-i18n="auth.login">登录</button>
      </div>
    </form>
  </dialog>
  <dialog id="user-settings-dialog" class="resource-dialog user-settings-dialog">
    <form id="user-settings-form">
      <h2 data-i18n="settings.title">用户设置</h2>
      <div class="avatar-editor">
        <span class="settings-avatar" aria-hidden="true"
          ><img id="settings-avatar-image" class="hidden" alt="" /><span
            id="settings-avatar-fallback"
            >账</span
          ></span
        >
        <div class="avatar-editor-copy">
          <strong id="settings-username">账户</strong>
          <WorkspaceHelp help-key="settings.avatarHint" />
        </div>
      </div>
      <label class="avatar-file-button" for="avatar-file"
        ><span data-i18n="settings.chooseAvatar">选择头像</span
        ><input id="avatar-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif"
      /></label>
      <fieldset class="model-prefs">
        <legend data-i18n="settings.general">通用</legend>
        <label for="pref-language" data-i18n="settings.language">界面语言</label>
        <select id="pref-language" autofocus>
          <option value="zh-CN">简体中文</option>
          <option value="zh-TW">繁體中文</option>
          <option value="en">English</option>
          <option value="ko">한국어</option>
          <option value="fr">Français</option>
          <option value="de">Deutsch</option>
          <option value="it">Italiano</option>
        </select>
      </fieldset>
      <fieldset class="model-prefs">
        <legend>
          <span data-i18n="settings.modelPrefs">模型偏好</span>
          <WorkspaceHelp help-key="settings.prefsHelp" />
        </legend>
        <label for="pref-main" data-i18n="settings.mainAgent">主智能体</label>
        <select id="pref-main"></select>
        <label for="pref-sub" data-i18n="settings.subAgent">子智能体</label>
        <select id="pref-sub"></select>
        <label for="pref-vision" data-i18n="settings.visionAgent">视觉智能体</label>
        <select id="pref-vision"></select>
      </fieldset>
      <p id="user-settings-error" class="dialog-help"></p>
      <div class="dialog-actions avatar-actions">
        <button
          id="avatar-remove"
          class="danger-button"
          type="button"
          data-i18n="settings.removeAvatar"
        >
          移除头像</button
        ><span></span
        ><button
          id="user-settings-cancel"
          class="text-button"
          type="button"
          data-i18n="action.cancel"
        >
          取消</button
        ><button class="attach-button" type="submit" data-i18n="action.save">保存</button>
      </div>
    </form>
  </dialog>
  <dialog id="rename-session-dialog" class="resource-dialog">
    <form id="rename-session-form">
      <h2 data-i18n="rename.title">重命名会话</h2>
      <label for="session-title-input" data-i18n="rename.name">会话名称</label
      ><input id="session-title-input" maxlength="80" required />
      <div class="dialog-actions">
        <button
          id="rename-session-cancel"
          class="text-button"
          type="button"
          data-i18n="action.cancel"
        >
          取消</button
        ><button class="attach-button" type="submit" data-i18n="action.save">保存</button>
      </div>
    </form>
  </dialog>
  <dialog id="delete-session-dialog" class="resource-dialog danger-dialog">
    <form id="delete-session-form">
      <h2 data-i18n="deleteSession.title">永久删除会话？</h2>
      <p id="delete-session-message" class="dialog-warning"></p>
      <p class="dialog-help" data-i18n="deleteSession.help">
        会话历史、附件、生成文件及客户端资源将被永久删除，此操作不可恢复。
      </p>
      <div class="dialog-actions">
        <button
          id="delete-session-cancel"
          class="text-button"
          type="button"
          data-i18n="action.cancel"
        >
          取消</button
        ><button class="danger-confirm" type="submit" data-i18n="deleteSession.confirm">
          永久删除
        </button>
      </div>
    </form>
  </dialog>
  <div id="model-menu" class="model-menu hidden" role="menu">
    <div class="model-search">
      <input
        id="model-search"
        data-i18n-placeholder="model.search"
        placeholder="搜索模型"
        autocomplete="off"
      />
    </div>
    <div id="model-list" class="model-list"></div>
  </div>
</template>
