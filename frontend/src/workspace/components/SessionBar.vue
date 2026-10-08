<template>
  <nav v-once class="sessionbar" data-i18n-aria="session.navAria" aria-label="Session 管理">
    <div id="session-tabs" class="session-tabs"></div>
    <div class="status"><span id="status-dot"></span><span id="status">正在连接</span></div>
    <button id="new-session" class="session-action" type="button" data-i18n="session.new">
      ＋ 新建 Session
    </button>
    <details id="user-menu" class="user-menu">
      <summary class="user-summary" data-i18n-aria="user.menuAria" aria-label="打开用户菜单">
        <span class="user-avatar" aria-hidden="true"
          ><img id="user-avatar-image" class="hidden" alt="" /><span id="user-avatar-fallback"
            >账</span
          ></span
        >
        <span id="user-name" class="user-name">账户</span><span class="user-caret">⌄</span>
      </summary>
      <div class="session-menu user-menu-panel">
        <button id="user-settings" type="button" data-i18n="user.settings">用户设置</button
        ><button id="logout" class="logout-action" type="button" data-i18n="user.logout">
          退出登录
        </button>
      </div>
    </details>
  </nav>
</template>
