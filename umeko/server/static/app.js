const ui = {
  messages: document.querySelector("#messages"),
  composer: document.querySelector("#composer"),
  prompt: document.querySelector("#prompt"),
  send: document.querySelector("#send"),
  stop: document.querySelector("#stop"),
  file: document.querySelector("#file"),
  attachments: document.querySelector("#attachments"),
  contextStatus: document.querySelector("#context-status"),
  compactContext: document.querySelector("#compact-context"),
  contextMenu: document.querySelector("#context-menu"),
  contextMenuCompact: document.querySelector("#context-menu-compact"),
  contextMenuClear: document.querySelector("#context-menu-clear"),
  status: document.querySelector("#status"),
  statusDot: document.querySelector("#status-dot"),
  canvas: document.querySelector("#canvas"),
  tree: document.querySelector("#file-tree"),
  refreshTree: document.querySelector("#refresh-tree"),
  treeFilter: document.querySelector("#tree-filter"),
  treeFilterClear: document.querySelector("#tree-filter-clear"),
  previewKicker: document.querySelector("#preview-kicker"),
  previewTitle: document.querySelector("#preview-title"),
  openFile: document.querySelector("#open-file"),
  markdownView: document.querySelector("#markdown-view"),
  csvView: document.querySelector("#csv-view"),
  codeView: document.querySelector("#code-view"),
  filebar: document.querySelector(".filebar"),
  sidebarTitle: document.querySelector("#sidebar-title"),
  sidebarTabs: [...document.querySelectorAll(".sidebar-tab")],
  panels: {
    workspace: document.querySelector("#workspace-panel"),
    skills: document.querySelector("#skills-panel"),
  },
  saveResource: document.querySelector("#save-resource"),
  deleteResource: document.querySelector("#delete-resource"),
  resourceEditor: document.querySelector("#resource-editor"),
  attachWorkspaceFile: document.querySelector("#attach-workspace-file"),
  resourceDialog: document.querySelector("#resource-dialog"),
  resourceDialogForm: document.querySelector("#resource-dialog-form"),
  resourceDialogTitle: document.querySelector("#resource-dialog-title"),
  resourceName: document.querySelector("#resource-name"),
  resourceDescription: document.querySelector("#resource-description"),
  resourceDialogCancel: document.querySelector("#resource-dialog-cancel"),
  authDialog: document.querySelector("#auth-dialog"), authForm: document.querySelector("#auth-form"),
  authUsername: document.querySelector("#auth-username"), authPassword: document.querySelector("#auth-password"),
  authError: document.querySelector("#auth-error"), register: document.querySelector("#register"),
  sessionTabs: document.querySelector("#session-tabs"), newSession: document.querySelector("#new-session"),
  logout: document.querySelector("#logout"),
  userName: document.querySelector("#user-name"),
  userMenu: document.querySelector("#user-menu"), userSettings: document.querySelector("#user-settings"),
  userAvatarImage: document.querySelector("#user-avatar-image"), userAvatarFallback: document.querySelector("#user-avatar-fallback"),
  userSettingsDialog: document.querySelector("#user-settings-dialog"), userSettingsForm: document.querySelector("#user-settings-form"),
  settingsUsername: document.querySelector("#settings-username"), settingsAvatarImage: document.querySelector("#settings-avatar-image"),
  settingsAvatarFallback: document.querySelector("#settings-avatar-fallback"), avatarFile: document.querySelector("#avatar-file"),
  avatarRemove: document.querySelector("#avatar-remove"), userSettingsCancel: document.querySelector("#user-settings-cancel"),
  userSettingsError: document.querySelector("#user-settings-error"),
  modelPicker: document.querySelector("#model-picker"), modelMenu: document.querySelector("#model-menu"),
  modelSearch: document.querySelector("#model-search"), modelList: document.querySelector("#model-list"),
  prefMain: document.querySelector("#pref-main"), prefSub: document.querySelector("#pref-sub"),
  prefVision: document.querySelector("#pref-vision"), prefLanguage: document.querySelector("#pref-language"),
  renameSessionDialog: document.querySelector("#rename-session-dialog"), renameSessionForm: document.querySelector("#rename-session-form"),
  sessionTitleInput: document.querySelector("#session-title-input"), renameSessionCancel: document.querySelector("#rename-session-cancel"),
  deleteSessionDialog: document.querySelector("#delete-session-dialog"), deleteSessionForm: document.querySelector("#delete-session-form"),
  deleteSessionMessage: document.querySelector("#delete-session-message"), deleteSessionCancel: document.querySelector("#delete-session-cancel"),
  workspace: document.querySelector(".workspace"), conversation: document.querySelector(".conversation"), preview: document.querySelector(".preview"),
  collapsePreview: document.querySelector("#collapse-preview"), expandPreview: document.querySelector("#expand-preview"),
  leftResizer: document.querySelector("#left-resizer"), rightResizer: document.querySelector("#right-resizer"),
  composerResizer: document.querySelector("#composer-resizer"),
  fileActions: document.querySelector("#file-actions"), fileContextMenu: document.querySelector("#file-context-menu"),
  fileEntryDialog: document.querySelector("#file-entry-dialog"), fileEntryForm: document.querySelector("#file-entry-form"),
  fileEntryTitle: document.querySelector("#file-entry-title"), fileEntryName: document.querySelector("#file-entry-name"),
  fileEntryHelp: document.querySelector("#file-entry-help"), fileEntryCancel: document.querySelector("#file-entry-cancel"),
  toolDetailDialog: document.querySelector("#tool-detail-dialog"), toolDetailTitle: document.querySelector("#tool-detail-title"),
  toolDetailMeta: document.querySelector("#tool-detail-meta"), toolDetailRequest: document.querySelector("#tool-detail-request"),
  toolDetailResult: document.querySelector("#tool-detail-result"), toolDetailClose: document.querySelector("#tool-detail-close"),
};

let sessionId = null;
let pendingFiles = [];
let selectedFile = null;
let selectedResource = null;
let activeSection = "workspace";
let creatingResourceKind = null;
let managingSession = null;
let sessionLoadToken = 0;
let fileMenuTarget = null;
let fileClipboard = null;
let pendingFileDialog = null;
const resourceLoadTokens = {skills: 0};
const pendingResourceMutations = new Set();
let activeStream = null;
let activeRunId = null;
let activeRunSessionId = null;
let activeRunCleanup = null;
let currentUser = null;
let modelRegistry = null;
let sessionModelOverride = null;
let pendingAvatarFile = null;
let removeAvatarPending = false;
let avatarPreviewUrl = null;
let workspaceRefreshTimer = null;
let treeFilterTimer = null;
let renderedTreeSessionId = null;
let renderedTreeSignature = null;
let activeToolDetail = null;

const layoutDefaults = { filebar: 260, preview: 610, composer: 160 };
const layoutState = {...layoutDefaults};

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}

function saveLayout() {
  try { localStorage.setItem("umeko-layout-v1", JSON.stringify(layoutState)); } catch (_) {}
}

function applyLayout() {
  ui.workspace.style.setProperty("--filebar-width", `${layoutState.filebar}px`);
  ui.workspace.style.setProperty("--preview-width", `${layoutState.preview}px`);
  ui.conversation.style.setProperty("--composer-height", `${layoutState.composer}px`);
  ui.leftResizer.setAttribute("aria-valuenow", String(Math.round(layoutState.filebar)));
  ui.rightResizer.setAttribute("aria-valuenow", String(Math.round(layoutState.preview)));
  ui.composerResizer.setAttribute("aria-valuenow", String(Math.round(layoutState.composer)));
}

function updateLayoutPart(part, value) {
  const totalWidth = ui.workspace.getBoundingClientRect().width;
  const conversationHeight = ui.conversation.getBoundingClientRect().height;
  if (part === "filebar") layoutState.filebar = clamp(value, 190, Math.min(440, totalWidth - layoutState.preview - 340));
  if (part === "preview") layoutState.preview = clamp(value, 360, Math.min(760, totalWidth - layoutState.filebar - 340));
  if (part === "composer") layoutState.composer = clamp(value, 150, Math.min(430, conversationHeight * .58));
  applyLayout();
}

function makeResizable(handle, part, axis, direction = 1) {
  handle.addEventListener("pointerdown", event => {
    if (window.matchMedia("(max-width: 900px)").matches) return;
    event.preventDefault();
    const startPointer = axis === "x" ? event.clientX : event.clientY;
    const startValue = layoutState[part];
    handle.classList.add("dragging");
    handle.setPointerCapture(event.pointerId);
    const move = moveEvent => {
      const pointer = axis === "x" ? moveEvent.clientX : moveEvent.clientY;
      updateLayoutPart(part, startValue + (pointer - startPointer) * direction);
    };
    const finish = () => {
      handle.classList.remove("dragging");
      handle.removeEventListener("pointermove", move);
      saveLayout();
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", finish, {once: true});
    handle.addEventListener("pointercancel", finish, {once: true});
  });
  handle.addEventListener("dblclick", () => {
    layoutState[part] = layoutDefaults[part];
    applyLayout(); saveLayout();
  });
  handle.addEventListener("keydown", event => {
    const previous = axis === "x" ? "ArrowLeft" : "ArrowUp";
    const next = axis === "x" ? "ArrowRight" : "ArrowDown";
    if (event.key !== previous && event.key !== next) return;
    event.preventDefault();
    const delta = (event.key === next ? 12 : -12) * direction;
    updateLayoutPart(part, layoutState[part] + delta); saveLayout();
  });
}

function initializeResizableLayout() {
  try {
    const saved = JSON.parse(localStorage.getItem("flowchart-layout-v1") || "null");
    if (saved) Object.assign(layoutState, saved);
  } catch (_) {}
  updateLayoutPart("filebar", layoutState.filebar);
  updateLayoutPart("preview", layoutState.preview);
  updateLayoutPart("composer", layoutState.composer);
  makeResizable(ui.leftResizer, "filebar", "x", 1);
  makeResizable(ui.rightResizer, "preview", "x", -1);
  makeResizable(ui.composerResizer, "composer", "y", -1);
}

/* 预览面板折叠：默认收起（非常驻），浏览文件/资源或点开对话产物时自动展开 */
let previewCollapsed = true;

function setPreviewCollapsed(collapsed) {
  previewCollapsed = collapsed;
  ui.workspace.classList.toggle("preview-collapsed", collapsed);
  ui.expandPreview.setAttribute("aria-expanded", String(!collapsed));
  try {
    localStorage.setItem("umeko:preview-collapsed", collapsed ? "1" : "0");
  } catch (_) {}
}

function initializePreviewCollapse() {
  let stored = null;
  try {
    stored = localStorage.getItem("umeko:preview-collapsed");
  } catch (_) {}
  setPreviewCollapsed(stored !== "0");  // 默认收起
  ui.collapsePreview.addEventListener("click", () => setPreviewCollapsed(true));
  ui.expandPreview.addEventListener("click", () => setPreviewCollapsed(false));
}

initializeResizableLayout();
initializePreviewCollapse();

function setStatus(text, ready = false) {
  ui.status.textContent = text;
  ui.statusDot.classList.toggle("ready", ready);
}

function addMessage(text, role = "assistant", files = []) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  const body = document.createElement("div");
  body.className = "message-body";
  if (role === "assistant") body.innerHTML = renderMarkdown(text);
  else body.textContent = text;
  node.append(body);
  if (files.length) {
    const refs = document.createElement("div");
    refs.className = "message-files";
    for (const file of files) {
      const ref = document.createElement("span");
      ref.className = "message-file";
      ref.textContent = t("attachment.chip", {name: file.filename});
      ref.title = file.filename;
      refs.append(ref);
    }
    node.append(refs);
  }
  ui.messages.append(node);
  ui.messages.scrollTop = ui.messages.scrollHeight;
  return node;
}

function toolLabel(name) {
  const key = `tool.name.${name}`;
  const label = t(key);
  return label === key ? name : label;
}

// 历史回放：把一条持久化的 tool_events 记录渲染成已完成的工具 chip
function replayToolEvent(event) {
  const action = addAgentAction(event.name, event.agent || "main", event.arguments, null);
  action.node.classList.remove("running");
  action.node.classList.add("completed");
  action.icon.textContent = "✓";
  action.text.textContent = t("action.completed", {tool: toolLabel(event.name)});
  action.result = event.result ?? "";
  makeToolActionInspectable(action);
}

function prettyToolData(value, emptyText) {
  if (value === null || value === undefined || value === "") return emptyText;
  if (typeof value !== "string") return JSON.stringify(value, null, 2);
  try { return JSON.stringify(JSON.parse(value), null, 2); }
  catch (_error) { return value; }
}

function renderToolDetail(action) {
  if (!action) return;
  const owner = action.agent === "subagent" ? t("agent.sub") : t("agent.main");
  const status = action.result === null ? t("tool.statusRunning") : t("tool.statusDone");
  ui.toolDetailTitle.textContent = toolLabel(action.name);
  ui.toolDetailMeta.textContent = `${owner} · ${action.name} · ${status}`;
  ui.toolDetailRequest.textContent = prettyToolData(action.request, t("tool.noParams"));
  let liveResult = "";
  const isSubagentTask = action.name === "subagent_task";
  if (action.liveReasoning) {
    liveResult += `【${isSubagentTask ? t("tool.liveReasoningSub") : t("tool.liveReasoningVision")}】\n${action.liveReasoning}\n\n`;
  }
  if (action.liveOutput) {
    liveResult += `【${isSubagentTask ? t("tool.liveOutputSub") : t("tool.liveOutputVision")}】\n${action.liveOutput}`;
  }
  if (action.result === null) {
    ui.toolDetailResult.textContent = liveResult || t("tool.stillRunning");
  } else {
    const finalResult = prettyToolData(action.result, t("tool.noResult"));
    ui.toolDetailResult.textContent = liveResult
      ? `${liveResult}\n\n【${t("tool.finalReturn")}】\n${finalResult}`
      : finalResult;
  }
}

function openToolDetail(action) {
  activeToolDetail = action;
  renderToolDetail(action);
  if (!ui.toolDetailDialog.open) ui.toolDetailDialog.showModal();
}

function makeToolActionInspectable(action) {
  action.node.classList.add("inspectable");
  action.node.setAttribute("role", "button");
  action.node.setAttribute("tabindex", "0");
  action.node.title = t("tool.inspectTitle");
}

function addAgentAction(name, agent = "main", request = null, beforeNode = null) {
  const node = document.createElement("div");
  node.className = `agent-action running${agent === "subagent" ? " subagent" : ""}`;
  const icon = document.createElement("span"); icon.className = "agent-action-icon"; icon.textContent = "·";
  const prefixKey = agent === "subagent" ? "action.runningSub" : "action.runningMain";
  const text = document.createElement("span"); text.textContent = t(prefixKey, {tool: toolLabel(name)});
  node.append(icon, text);
  if (beforeNode?.parentNode === ui.messages) ui.messages.insertBefore(node, beforeNode);
  else ui.messages.append(node);
  ui.messages.scrollTop = ui.messages.scrollHeight;
  const action = {
    node, icon, text, name, agent, request, result: null,
    liveReasoning: "", liveOutput: "",
  };
  if (request !== null) makeToolActionInspectable(action);
  node.addEventListener("click", () => {
    if (node.classList.contains("inspectable")) openToolDetail(action);
  });
  node.addEventListener("keydown", event => {
    if (!node.classList.contains("inspectable") || !["Enter", " "].includes(event.key)) return;
    event.preventDefault(); openToolDetail(action);
  });
  return action;
}

ui.toolDetailClose.addEventListener("click", () => ui.toolDetailDialog.close());
ui.toolDetailDialog.addEventListener("close", () => { activeToolDetail = null; });
ui.toolDetailDialog.addEventListener("click", event => {
  if (event.target === ui.toolDetailDialog) ui.toolDetailDialog.close();
});

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    let detail = body.detail;
    if (Array.isArray(detail)) {
      const labels = {username: t("auth.username"), password: t("auth.password"), name: t("form.name"), description: t("skill.description")};
      detail = detail.map(item => {
        const field = item.loc?.[item.loc.length - 1];
        const label = labels[field] || field || t("error.input");
        const message = item.type === "string_too_short"
          ? t("error.tooShort", {n: item.ctx?.min_length || t("error.requiredN")})
          : (item.msg || t("error.invalid"));
        return `${label}：${message}`;
      }).join("；");
    } else if (detail && typeof detail === "object") {
      detail = detail.msg || JSON.stringify(detail);
    }
    throw new Error(detail || t("error.requestFailed", {status: response.status}));
  }
  return response.status === 204 ? null : response.json();
}

function compactTokenLabel(tokens) {
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}m`;
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(tokens >= 10000 ? 0 : 1)}k`;
  return String(tokens);
}

function renderContextStats(stats) {
  // 有供应商 usage 锚点时 used_tokens 为精确口径，不再加"≈"
  ui.contextStatus.textContent = t("context.stats", {
    approx: stats.exact ? "" : "≈",
    used: compactTokenLabel(stats.used_tokens),
    limit: compactTokenLabel(stats.limit_tokens),
    percent: stats.percent,
  });
  const controls = ui.contextStatus.closest(".context-controls");
  controls.classList.toggle("warning", stats.percent >= 70 && stats.percent < 90);
  controls.classList.toggle("danger", stats.percent >= 90);
}

async function refreshContext(targetSessionId = sessionId) {
  if (!targetSessionId) return;
  const stats = await api(`/v1/sessions/${targetSessionId}/context`);
  if (targetSessionId === sessionId) renderContextStats(stats);
  return stats;
}

// ---------- 模型选择（会话级覆盖 + 用户角色偏好） ----------

function modelInfo(modelId) {
  if (!modelRegistry || !modelId) return null;
  for (const provider of modelRegistry.providers) {
    const found = provider.models.find(item => item.id === modelId);
    if (found) return { ...found, provider: provider.name };
  }
  return null;
}

function effectiveMainModelId() {
  return sessionModelOverride
    || modelRegistry?.prefs?.main_model_id
    || modelRegistry?.active_model_id
    || null;
}

function modelMenuNote(text, retry = false) {
  const note = document.createElement("div");
  note.className = "model-menu-note";
  note.append(text);
  if (retry) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = t("action.retry");
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = t("action.loading");
      await refreshModels();
    });
    note.appendChild(document.createElement("br"));
    note.appendChild(button);
  }
  return note;
}

function modelMenuItem(label, { active = false, vision = false, onClick }) {
  const item = document.createElement("button");
  item.type = "button";
  item.className = "model-item";
  item.setAttribute("role", "menuitem");
  item.classList.toggle("active", active);
  const name = document.createElement("span");
  name.className = "model-item-name";
  name.textContent = label;
  item.appendChild(name);
  if (vision) {
    const mark = document.createElement("span");
    mark.className = "vision-mark";
    mark.textContent = t("model.visionMark");
    item.appendChild(mark);
  }
  const check = document.createElement("span");
  check.className = "model-check";
  check.textContent = "✓";
  item.appendChild(check);
  item.addEventListener("click", onClick);
  return item;
}

function renderModelMenuList() {
  const filter = ui.modelSearch.value.trim().toLowerCase();
  ui.modelList.replaceChildren();
  if (!modelRegistry) {
    ui.modelList.appendChild(
      modelMenuNote(t("model.registryMissing"), true)
    );
    return;
  }
  const hasModels = modelRegistry.providers.some(p => p.models.length);
  if (!hasModels) {
    ui.modelList.appendChild(modelMenuNote(t("model.noModels")));
    return;
  }
  ui.modelList.appendChild(modelMenuItem(t("model.followDefault"), {
    active: !sessionModelOverride,
    onClick: () => selectSessionModel(null),
  }));
  for (const provider of modelRegistry.providers) {
    const models = provider.models.filter(model =>
      !filter
      || model.name.toLowerCase().includes(filter)
      || provider.name.toLowerCase().includes(filter)
    );
    if (!models.length) continue;
    const group = document.createElement("div");
    group.className = "model-group";
    group.textContent = provider.name;
    ui.modelList.appendChild(group);
    for (const model of models) {
      ui.modelList.appendChild(modelMenuItem(model.name, {
        active: model.id === sessionModelOverride,
        vision: model.vision,
        onClick: () => selectSessionModel(model.id),
      }));
    }
  }
  if (filter && !ui.modelList.querySelector(".model-item")) {
    ui.modelList.appendChild(modelMenuNote(t("model.noMatch", {query: ui.modelSearch.value.trim()})));
  }
}

function renderModelPicker() {
  if (!modelRegistry) {
    ui.modelPicker.textContent = t("model.pickerEmpty");
  } else {
    const info = modelInfo(effectiveMainModelId());
    ui.modelPicker.textContent = `${info ? info.name : t("model.defaultModel")} ▾`;
    ui.modelPicker.title = info
      ? t(sessionModelOverride ? "model.sessionModelOverride" : "model.sessionModel", {provider: info.provider, name: info.name})
      : t("model.pickerTitle");
  }
  renderModelMenuList();
}

async function refreshModels() {
  try {
    modelRegistry = await api("/v1/models");
  } catch (_) {
    modelRegistry = null;
  }
  renderModelPicker();
}

async function selectSessionModel(modelId) {
  closeModelMenu();
  if (!sessionId) return;
  try {
    await api(`/v1/sessions/${sessionId}/model`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId }),
    });
    sessionModelOverride = modelId;
    renderModelPicker();
    const info = modelInfo(modelId);
    setStatus(
      modelId ? t("model.sessionModelSet", {name: info ? info.name : modelId}) : t("model.sessionModelReset"),
      true,
    );
  } catch (error) {
    setStatus(error.message);
  }
}

function closeModelMenu() {
  ui.modelMenu.classList.add("hidden");
  ui.modelPicker.setAttribute("aria-expanded", "false");
}

ui.modelPicker.addEventListener("click", async event => {
  event.stopPropagation();
  if (ui.modelMenu.classList.contains("hidden")) {
    // 每次打开都拉最新注册表：管理员改了配置、或之前加载失败，都能自愈
    await refreshModels();
    // fixed 浮层：按按钮视口坐标定位，不被 composer 的 overflow 截断
    const rect = ui.modelPicker.getBoundingClientRect();
    ui.modelMenu.style.left = `${Math.max(8, rect.left)}px`;
    ui.modelMenu.style.bottom = `${window.innerHeight - rect.top + 7}px`;
    ui.modelMenu.classList.remove("hidden");
    ui.modelPicker.setAttribute("aria-expanded", "true");
    ui.modelSearch.value = "";
    renderModelMenuList();
    ui.modelSearch.focus();
  } else {
    closeModelMenu();
  }
});

window.addEventListener("resize", closeModelMenu);

ui.modelSearch.addEventListener("input", renderModelMenuList);
ui.modelSearch.addEventListener("click", event => event.stopPropagation());
ui.modelSearch.addEventListener("keydown", event => {
  // 搜索框在 composer 表单内：Enter 不能触发表单提交（发送 Run）
  if (event.key === "Enter") event.preventDefault();
  if (event.key === "Escape") closeModelMenu();
  event.stopPropagation();
});

function fillPrefSelect(select, { visionOnly = false } = {}) {
  select.replaceChildren();
  const fallback = document.createElement("option");
  fallback.value = "";
  fallback.textContent = t("model.followDefaultShort");
  select.appendChild(fallback);
  if (!modelRegistry) return;
  for (const provider of modelRegistry.providers) {
    for (const model of provider.models) {
      if (visionOnly && !model.vision) continue;
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = `${provider.name} / ${model.name}`;
      select.appendChild(option);
    }
  }
}

function userInitial(username) {
  const fallbackChar = t("user.initialFallback");
  return [...(username || fallbackChar).trim()][0]?.toUpperCase() || fallbackChar;
}

function setAvatarView(image, fallback, username, source) {
  fallback.textContent = userInitial(username);
  if (!source) {
    image.removeAttribute("src"); image.classList.add("hidden"); fallback.classList.remove("hidden");
    return;
  }
  image.onload = () => { image.classList.remove("hidden"); fallback.classList.add("hidden"); };
  image.onerror = () => { image.classList.add("hidden"); fallback.classList.remove("hidden"); };
  image.src = source;
}

function renderCurrentUser(user, cacheBust = false) {
  currentUser = user;
  ui.userName.textContent = user.username;
  const source = user.avatar_url
    ? `${user.avatar_url}${user.avatar_url.includes("?") ? "&" : "?"}t=${cacheBust ? Date.now() : "current"}`
    : null;
  setAvatarView(ui.userAvatarImage, ui.userAvatarFallback, user.username, source);
}

function resetAvatarPreview() {
  if (avatarPreviewUrl) URL.revokeObjectURL(avatarPreviewUrl);
  avatarPreviewUrl = null;
  pendingAvatarFile = null;
  removeAvatarPending = false;
  ui.avatarFile.value = "";
  ui.userSettingsError.textContent = "";
}

async function openUserSettings() {
  if (!currentUser) return;
  resetAvatarPreview();
  ui.userMenu.open = false;
  ui.settingsUsername.textContent = currentUser.username;
  setAvatarView(
    ui.settingsAvatarImage, ui.settingsAvatarFallback, currentUser.username,
    currentUser.avatar_url ? `${currentUser.avatar_url}?t=${Date.now()}` : null,
  );
  ui.avatarRemove.disabled = !currentUser.avatar_url;
  await refreshModels();
  fillPrefSelect(ui.prefMain);
  fillPrefSelect(ui.prefSub);
  fillPrefSelect(ui.prefVision, { visionOnly: true });
  ui.prefLanguage.value = currentLocale();
  const prefs = modelRegistry?.prefs || {};
  ui.prefMain.value = prefs.main_model_id || "";
  ui.prefSub.value = prefs.sub_model_id || "";
  ui.prefVision.value = prefs.vision_model_id || "";
  ui.userSettingsDialog.showModal();
}

// 语言切换即时生效（不需要点保存）
ui.prefLanguage.addEventListener("change", () => setLocale(ui.prefLanguage.value));

// 语言切换后重渲染动态文案（模型胶囊、上下文统计等由 JS 设置的文本）
document.addEventListener("localechange", () => {
  renderModelPicker();
  refreshContext().catch(() => {});
  if (!selectedFile && !selectedResource) clearPreview();
  const welcomeNode = ui.messages.querySelector("[data-welcome]");
  if (welcomeNode) welcomeNode.querySelector(".message-body").textContent = t("message.welcome");
  if (!activeRunId) setStatus(t("status.connected"), true);
});

async function createSession() {
  const session = await api("/v1/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  await loadSession(session.id);
  return session;
}

async function refreshSessionTabs() {
  const sessions = await api("/v1/sessions");
  document.querySelectorAll(".session-floating-menu").forEach(node => node.remove());
  ui.sessionTabs.replaceChildren();
  for (const item of sessions) {
    const wrapper = document.createElement("div");
    wrapper.className = "session-item";
    const button = document.createElement("button");
    button.type = "button";
    button.className = `session-tab${item.id === sessionId ? " active" : ""}`;
    button.textContent = item.title;
    button.addEventListener("click", () => loadSession(item.id).catch(error => setStatus(error.message)));
    const more = document.createElement("button");
    more.type = "button"; more.className = "session-more"; more.textContent = "⋯"; more.title = t("session.manage");
    const menu = document.createElement("div"); menu.className = "session-menu session-floating-menu hidden";
    const rename = document.createElement("button"); rename.type = "button"; rename.textContent = t("fileMenu.rename");
    rename.addEventListener("click", () => { menu.classList.add("hidden"); openRenameSession(item); });
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = t("session.delete");
    remove.addEventListener("click", () => { menu.classList.add("hidden"); openDeleteSession(item); });
    more.addEventListener("click", event => {
      event.stopPropagation();
      document.querySelectorAll(".session-floating-menu").forEach(node => { if (node !== menu) node.classList.add("hidden"); });
      const opening = menu.classList.contains("hidden");
      menu.classList.toggle("hidden", !opening);
      if (opening) {
        const rect = more.getBoundingClientRect();
        menu.style.top = `${rect.bottom + 6}px`;
        menu.style.left = `${Math.max(8, Math.min(rect.right - 132, window.innerWidth - 140))}px`;
      }
    });
    menu.addEventListener("click", event => event.stopPropagation());
    menu.append(rename, remove); wrapper.append(button, more); ui.sessionTabs.append(wrapper); document.body.append(menu);
  }
  return sessions;
}
document.addEventListener("click", () => document.querySelectorAll(".session-floating-menu").forEach(node => node.classList.add("hidden")));

async function loadSession(id) {
  const loadToken = ++sessionLoadToken;
  if (activeRunCleanup) activeRunCleanup();
  else if (activeStream) activeStream.close();
  if (workspaceRefreshTimer) clearTimeout(workspaceRefreshTimer);
  workspaceRefreshTimer = null;
  activeStream = null;
  activeRunCleanup = null;
  activeRunId = null;
  activeRunSessionId = null;
  setRunControls(false);
  sessionId = id;
  localStorage.setItem("umeko:last-session", id);
  clearPreview();
  const [sessionView, messages] = await Promise.all([
    api(`/v1/sessions/${id}`),
    api(`/v1/sessions/${id}/messages`),
  ]);
  sessionModelOverride = sessionView?.model_override_id || null;
  renderModelPicker();
  if (loadToken !== sessionLoadToken || sessionId !== id) return;
  pendingFiles = [];
  ui.attachments.replaceChildren();
  selectedFile = null;
  selectedResource = null;
  ui.messages.replaceChildren();
  if (!messages.length) {
    const welcomeNode = addMessage(t("message.welcome"));
    welcomeNode.dataset.welcome = "1";
  }
  // 回放工具调用历史：按时间归并到消息流（tool_events 与 messages 各自按时间排序）
  let toolEvents = [];
  try { toolEvents = await api(`/v1/sessions/${id}/tool-events`); } catch (_) { toolEvents = []; }
  if (loadToken !== sessionLoadToken || sessionId !== id) return;
  const timeline = [
    ...messages.map(m => ({kind: "message", at: m.created_at, m})),
    ...toolEvents.map(e => ({kind: "tool", at: e.created_at, e})),
  ].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
  for (const item of timeline) {
    if (item.kind === "message") {
      const m = item.m;
      addMessage(m.content, m.role, m.attachments.map(filename => ({filename})));
    } else {
      replayToolEvent(item.e);
    }
  }
  await Promise.all([
    refreshTree(), refreshResources("skills"), refreshContext(id),
  ]);
  if (loadToken !== sessionLoadToken || sessionId !== id) return;
  const activeRun = await api(`/v1/sessions/${id}/active-run`);
  if (loadToken !== sessionLoadToken || sessionId !== id) return;
  if (activeRun) followRun(activeRun.id, id);
  await refreshSessionTabs();
  if (!activeRun) setStatus(t("status.connected"), true);
}

async function boot() {
  let user;
  try { user = await api("/v1/auth/me"); }
  catch (_) { ui.authDialog.showModal(); return; }
  renderCurrentUser(user);
  await refreshModels();
  const sessions = await refreshSessionTabs();
  const last = localStorage.getItem("umeko:last-session");
  const chosen = sessions.find(item => item.id === last) || sessions[0];
  if (chosen) await loadSession(chosen.id);
  else await createSession();
}

async function authenticate(mode) {
  ui.authError.textContent = "";
  try {
    await api(`/v1/auth/${mode}`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:ui.authUsername.value,password:ui.authPassword.value})});
    ui.authDialog.close(); await boot();
  } catch (error) { ui.authError.textContent = error.message; }
}
ui.authForm.addEventListener("submit", event => { event.preventDefault(); authenticate("login"); });
ui.register.addEventListener("click", () => authenticate("register"));
ui.newSession.addEventListener("click", async () => {
  ui.newSession.disabled = true;
  try { await createSession(); } catch (error) { setStatus(error.message); }
  finally { ui.newSession.disabled = false; }
});
ui.logout.addEventListener("click", async () => { await api("/v1/auth/logout", {method:"POST"}); location.reload(); });
ui.userSettings.addEventListener("click", openUserSettings);
ui.userSettingsCancel.addEventListener("click", () => { resetAvatarPreview(); ui.userSettingsDialog.close(); });
ui.avatarFile.addEventListener("change", () => {
  const file = ui.avatarFile.files?.[0];
  if (!file) return;
  const allowed = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
  if (!allowed.has(file.type) || file.size > 2 * 1024 * 1024) {
    ui.userSettingsError.textContent = !allowed.has(file.type) ? t("settings.avatarTypeError") : t("settings.avatarSizeError");
    ui.avatarFile.value = ""; return;
  }
  if (avatarPreviewUrl) URL.revokeObjectURL(avatarPreviewUrl);
  avatarPreviewUrl = URL.createObjectURL(file);
  pendingAvatarFile = file; removeAvatarPending = false;
  ui.avatarRemove.disabled = false;
  ui.userSettingsError.textContent = "";
  setAvatarView(ui.settingsAvatarImage, ui.settingsAvatarFallback, currentUser.username, avatarPreviewUrl);
});
ui.avatarRemove.addEventListener("click", () => {
  if (avatarPreviewUrl) URL.revokeObjectURL(avatarPreviewUrl);
  avatarPreviewUrl = null; pendingAvatarFile = null; removeAvatarPending = true;
  ui.avatarFile.value = ""; ui.avatarRemove.disabled = true;
  setAvatarView(ui.settingsAvatarImage, ui.settingsAvatarFallback, currentUser.username, null);
});
ui.userSettingsForm.addEventListener("submit", async event => {
  event.preventDefault();
  const submit = ui.userSettingsForm.querySelector('button[type="submit"]');
  submit.disabled = true; ui.userSettingsError.textContent = "";
  try {
    let user = currentUser;
    if (pendingAvatarFile) {
      user = await api("/v1/auth/avatar", {method: "PUT", headers: {"Content-Type": pendingAvatarFile.type}, body: pendingAvatarFile});
    } else if (removeAvatarPending) {
      user = await api("/v1/auth/avatar", {method: "DELETE"});
    }
    const prefs = await api("/v1/auth/model-prefs", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        main_model_id: ui.prefMain.value || null,
        sub_model_id: ui.prefSub.value || null,
        vision_model_id: ui.prefVision.value || null,
      }),
    });
    if (modelRegistry) modelRegistry.prefs = prefs;
    renderModelPicker();
    renderCurrentUser(user, true); resetAvatarPreview(); ui.userSettingsDialog.close();
    setStatus(t("settings.saved"), true);
  } catch (error) { ui.userSettingsError.textContent = error.message; }
  finally { submit.disabled = false; }
});

function openRenameSession(item) {
  managingSession = item;
  ui.sessionTitleInput.value = item.title;
  ui.renameSessionDialog.showModal();
  ui.sessionTitleInput.select();
}
function openDeleteSession(item) {
  managingSession = item;
  ui.deleteSessionMessage.textContent = t("deleteSession.message", {title: item.title});
  ui.deleteSessionDialog.showModal();
}
ui.renameSessionCancel.addEventListener("click", () => ui.renameSessionDialog.close());
ui.deleteSessionCancel.addEventListener("click", () => ui.deleteSessionDialog.close());
ui.renameSessionForm.addEventListener("submit", async event => {
  event.preventDefault(); if (!managingSession) return;
  try {
    await api(`/v1/sessions/${managingSession.id}/title`, {method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:ui.sessionTitleInput.value})});
    ui.renameSessionDialog.close(); await refreshSessionTabs(); setStatus(t("session.renamed"), true);
  } catch (error) { setStatus(error.message); }
});
ui.deleteSessionForm.addEventListener("submit", async event => {
  event.preventDefault(); if (!managingSession) return;
  const deletingId = managingSession.id;
  try {
    await api(`/v1/sessions/${deletingId}`, {method:"DELETE"});
    ui.deleteSessionDialog.close();
    const sessions = await refreshSessionTabs();
    if (deletingId === sessionId) {
      if (sessions.length) await loadSession(sessions[0].id); else await createSession();
    }
    setStatus(t("session.deleted"), true);
  } catch (error) { setStatus(error.message); }
});

function switchSection(section) {
  activeSection = section;
  for (const tab of ui.sidebarTabs) tab.classList.toggle("active", tab.dataset.section === section);
  for (const [name, panel] of Object.entries(ui.panels)) panel.classList.toggle("active", name === section);
  ui.sidebarTitle.textContent = section === "workspace" ? "output" : section;
}

for (const tab of ui.sidebarTabs) {
  tab.addEventListener("click", () => switchSection(tab.dataset.section));
}

async function refreshResources(kind, targetSessionId = sessionId) {
  if (!targetSessionId) return;
  const requestToken = ++resourceLoadTokens[kind];
  const resources = await api(`/v1/sessions/${targetSessionId}/client/${kind}`);
  if (targetSessionId !== sessionId || requestToken !== resourceLoadTokens[kind]) return;
  const panel = ui.panels[kind];
  panel.replaceChildren();
  const toolbar = document.createElement("div");
  toolbar.className = "resource-toolbar";
  const create = document.createElement("button");
  create.type = "button";
  create.className = "resource-tool";
  create.textContent = t("resource.create");
  create.addEventListener("click", () => openCreateResourceDialog(kind));
  const importLabel = document.createElement("label");
  importLabel.className = "resource-tool";
  importLabel.textContent = t("resource.import");
  const importInput = document.createElement("input");
  importInput.type = "file";
  importInput.accept = ".md,text/markdown";
  importInput.multiple = true;
  importInput.addEventListener("change", () => {
    importResources(kind, [...importInput.files]);
    importInput.value = "";
  });
  importLabel.append(importInput);
  toolbar.append(create, importLabel);
  panel.append(toolbar);
  if (!resources.length) {
    const empty = document.createElement("p");
    empty.className = "resource-empty";
    empty.textContent = t("resource.empty", {kind});
    panel.append(empty);
  }
  for (const resource of resources) {
    const row = document.createElement("div");
    row.className = "resource-item";
    const mounted = document.createElement("button");
    mounted.type = "button";
    mounted.className = `tree-attach resource-mount${resource.mounted ? " attached" : ""}`;
    const renderMounted = () => {
      mounted.textContent = resource.mounted ? "✓" : "+";
      mounted.title = resource.mounted ? t("resource.unmount") : t("resource.mount");
      mounted.setAttribute("aria-label", t(resource.mounted ? "resource.unmountAria" : "resource.mountAria", {name: resource.name}));
      mounted.classList.toggle("attached", resource.mounted);
    };
    renderMounted();
    mounted.addEventListener("click", async () => {
      mounted.disabled = true;
      const nextMounted = !resource.mounted;
      const mutation = (async () => {
        try {
          await api(
            `/v1/sessions/${targetSessionId}/client/${kind}/${encodeURIComponent(resource.name)}`,
            {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ mounted: nextMounted }),
            }
          );
          await refreshResources(kind, targetSessionId);
          setStatus(nextMounted ? t("resource.mounted", {name: resource.name}) : t("resource.unmounted", {name: resource.name}), true);
        } catch (error) {
          setStatus(error.message);
        } finally {
          mounted.disabled = false;
        }
      })();
      pendingResourceMutations.add(mutation);
      try { await mutation; } finally { pendingResourceMutations.delete(mutation); }
    });
    const open = document.createElement("button");
    open.type = "button";
    open.className = "resource-open";
    open.textContent = resource.name;
    open.title = resource.name;
    open.addEventListener("click", () => openResource(kind, resource.name, row));
    row.append(open, mounted);
    panel.append(row);
  }
  const hint = document.createElement("div");
  hint.className = "resource-drop-hint";
  hint.textContent = t("resource.dropHint", {kind});
  panel.append(hint);
}

function resourceTemplate(kind, name) {
  return `---\nname: ${name}\ndescription: ${t("resource.templateDescription")}\n---\n\n${t("resource.templateBody")}\n`;
}

async function uploadResource(kind, file) {
  if (!file.name.toLowerCase().endsWith(".md")) throw new Error(t("resource.notMarkdown", {name: file.name}));
  const content = await file.text();
  return api(`/v1/sessions/${sessionId}/client/${kind}?filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": "text/markdown; charset=utf-8" },
    body: content,
  });
}

async function importResources(kind, files) {
  if (!files.length) return;
  try {
    for (const file of files) await uploadResource(kind, file);
    await refreshResources(kind);
    setStatus(t("resource.imported", {count: files.length, kind}), true);
  } catch (error) {
    setStatus(error.message);
  }
}

function openCreateResourceDialog(kind) {
  creatingResourceKind = kind;
  ui.resourceDialogTitle.textContent = t("skill.new");
  ui.resourceName.value = "my-skill";
  ui.resourceDescription.value = "";
  ui.resourceDialog.showModal();
  ui.resourceName.select();
}

ui.resourceDialogCancel.addEventListener("click", () => ui.resourceDialog.close());
ui.resourceDialogForm.addEventListener("submit", async event => {
  event.preventDefault();
  const kind = creatingResourceKind;
  const entered = ui.resourceName.value;
  const action = event.submitter?.value || "generate";
  if (!kind || !entered) return;
  const key = entered.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  if (!key) return setStatus(t("resource.nameInvalid"));
  try {
    let resource;
    if (action === "generate") {
      const description = ui.resourceDescription.value.trim();
      if (!description) return setStatus(t("resource.descriptionRequired"));
      setStatus(t("resource.generating", {name: key}));
      resource = await api(`/v1/sessions/${sessionId}/client/${kind}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: key, description }),
      });
    } else {
      resource = await api(
        `/v1/sessions/${sessionId}/client/${kind}?filename=${encodeURIComponent(`${key}.md`)}`,
        { method: "POST", headers: { "Content-Type": "text/markdown; charset=utf-8" }, body: resourceTemplate(kind, key) }
      );
    }
    await refreshResources(kind);
    const row = [...ui.panels[kind].querySelectorAll(".resource-item")]
      .find(node => node.querySelector(".resource-open")?.textContent === resource.name);
    if (row) await openResource(kind, resource.name, row);
    ui.resourceDialog.close();
    setStatus(t(action === "generate" ? "resource.generated" : "resource.created", {name: resource.name}), true);
  } catch (error) {
    setStatus(error.message);
  }
});

for (const kind of ["skills"]) {
  const panel = ui.panels[kind];
  for (const eventName of ["dragenter", "dragover"]) {
    panel.addEventListener(eventName, event => {
      event.preventDefault();
      panel.classList.add("dragging");
    });
  }
  panel.addEventListener("dragleave", event => {
    if (!panel.contains(event.relatedTarget)) panel.classList.remove("dragging");
  });
  panel.addEventListener("drop", event => {
    event.preventDefault();
    event.stopPropagation();
    panel.classList.remove("dragging");
    importResources(kind, [...event.dataTransfer.files]);
  });
}

async function openResource(kind, name, row) {
  if (previewCollapsed) setPreviewCollapsed(false);  // 浏览资源，自动展开
  const resource = await api(`/v1/sessions/${sessionId}/client/${kind}/${encodeURIComponent(name)}`);
  selectedResource = resource;
  document.querySelectorAll(".resource-item.active").forEach(node => node.classList.remove("active"));
  row.classList.add("active");
  ui.previewKicker.textContent = "CLIENT SKILL";
  ui.previewTitle.textContent = name;
  ui.saveResource.classList.remove("hidden");
  ui.deleteResource.classList.toggle("hidden", resource.builtin);
  ui.attachWorkspaceFile.classList.add("hidden");
  ui.openFile.classList.add("hidden");
  resetPreviewViews();
  ui.resourceEditor.value = resource.content || "";
  ui.resourceEditor.classList.remove("hidden");
}

function fileIcon(name) {
  const ext = name.split(".").pop().toLowerCase();
  if (["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"].includes(ext)) return "◫";
  if (["md", "markdown"].includes(ext)) return "M";
  if (["xml", "json", "yaml", "yml"].includes(ext)) return "<>";
  return "·";
}

function entryName(path) { return path.split("/").filter(Boolean).pop() || path; }
function entryParent(path) { const parts = path.split("/").filter(Boolean); parts.pop(); return parts.join("/"); }
function entryJoin(directory, name) { return `${directory.replace(/\/$/, "")}/${name}`; }
function isWorkspaceRoot(path) { return !path.includes("/"); }

function validateEntryName(name) {
  const clean = name.trim();
  if (!clean || clean === "." || clean === ".." || /[\\/\0]/.test(clean)) {
    throw new Error(t("file.nameInvalid"));
  }
  return clean;
}

function closeFileMenu() { ui.fileContextMenu.classList.add("hidden"); }

// 可解压的压缩包后缀（与后端 ARCHIVE_SUFFIXES 对齐）
const ARCHIVE_RE = /\.(zip|7z|rar|tar|gz|bz2|xz|tgz)$/i;

function openFileMenu(target, x, y) {
  fileMenuTarget = target;
  const root = isWorkspaceRoot(target.path);
  for (const button of ui.fileContextMenu.querySelectorAll("button[data-file-action]")) {
    const action = button.dataset.fileAction;
    button.disabled = (
      (["new-file", "new-directory", "paste"].includes(action) && target.type !== "directory") ||
      (action === "paste" && !fileClipboard) ||
      (["copy", "cut", "rename", "delete"].includes(action) && root) ||
      (action === "download" && !["file", "directory"].includes(target.type)) ||
      (action === "extract" && !(target.type === "file" && ARCHIVE_RE.test(target.name)))
    );
    if (action === "download") {
      button.textContent = target.type === "directory" ? t("file.downloadDir") : t("file.downloadFile");
    }
  }
  ui.fileContextMenu.classList.remove("hidden");
  const width = 168;
  const height = ui.fileContextMenu.offsetHeight;
  ui.fileContextMenu.style.left = `${Math.max(6, Math.min(x, innerWidth - width - 6))}px`;
  ui.fileContextMenu.style.top = `${Math.max(6, Math.min(y, innerHeight - height - 6))}px`;
}

function openFileEntryDialog(action, target) {
  pendingFileDialog = {action, target};
  const labels = {"new-file": t("fileMenu.newFile"), "new-directory": t("fileMenu.newDir"), rename: t("fileMenu.rename")};
  ui.fileEntryTitle.textContent = labels[action];
  ui.fileEntryName.value = action === "new-file" ? "untitled.txt" : action === "new-directory" ? "new-folder" : target.name;
  ui.fileEntryHelp.textContent = action === "rename" ? t("file.currentLocation", {path: entryParent(target.path)}) : t("file.createIn", {path: target.path});
  ui.fileEntryDialog.showModal();
  ui.fileEntryName.select();
}

async function transferWorkspace(source, target, operation) {
  if (source === target) return;
  await api(`/v1/sessions/${sessionId}/workspace/transfer`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({source, target, operation}),
  });
  const selectedAffected = operation === "move" && selectedFile && (selectedFile === source || selectedFile.startsWith(`${source}/`));
  if (operation === "move") {
    for (const file of pendingFiles) {
      if (file.workspacePath === source || file.workspacePath?.startsWith(`${source}/`)) {
        file.workspacePath = `${target}${file.workspacePath.slice(source.length)}`;
      }
    }
  }
  if (selectedAffected) { selectedFile = null; clearPreview(); }
  await refreshTree();
  setStatus(t(operation === "move" ? "file.moved" : "file.copiedTo", {name: entryName(target)}), true);
}

async function executeFileAction(action, target) {
  closeFileMenu();
  if (["new-file", "new-directory", "rename"].includes(action)) return openFileEntryDialog(action, target);
  if (action === "copy" || action === "cut") {
    fileClipboard = {path: target.path, type: target.type, operation: action === "copy" ? "copy" : "move"};
    await refreshTree();
    return setStatus(t(action === "copy" ? "file.copied" : "file.cut", {name: target.name}), true);
  }
  if (action === "paste") {
    if (!fileClipboard) return;
    const targetPath = entryJoin(target.path, entryName(fileClipboard.path));
    await transferWorkspace(fileClipboard.path, targetPath, fileClipboard.operation);
    if (fileClipboard.operation === "move") fileClipboard = null;
    return;
  }
  if (action === "extract") {
    if (!ARCHIVE_RE.test(target.name)) return setStatus(t("file.notArchive"), true);
    setStatus(t("file.extracting", {name: target.name}), true);
    try {
      const result = await api(`/v1/sessions/${sessionId}/workspace/extract`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({path: target.path}),
      });
      await refreshTree();
      setStatus(t("file.extracted", {name: result.filename}), true);
    } catch (error) {
      setStatus(error.message);
    }
    return;
  }
  if (action === "download") {
    const link = document.createElement("a");
    link.href = `/v1/sessions/${sessionId}/workspace/files/download?path=${encodeURIComponent(target.path)}`;
    link.download = target.type === "directory" ? `${target.name}.zip` : target.name;
    document.body.appendChild(link); link.click(); link.remove();
    setStatus(t("file.downloading", {name: link.download}), true);
    return;
  }
  if (action === "delete") {
    const description = target.type === "directory" ? t("file.dirAndContents") : t("file.fileNoun");
    if (!confirm(t("file.deleteConfirm", {description, name: target.name}))) return;
    await api(`/v1/sessions/${sessionId}/workspace/entries?path=${encodeURIComponent(target.path)}`, {method: "DELETE"});
    if (selectedFile === target.path) { selectedFile = null; clearPreview(); }
    if (fileClipboard?.path === target.path || fileClipboard?.path.startsWith(`${target.path}/`)) fileClipboard = null;
    await refreshTree(); setStatus(t("file.deleted", {name: target.name}), true);
  }
}

ui.fileEntryCancel.addEventListener("click", () => ui.fileEntryDialog.close());
ui.fileEntryForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (!pendingFileDialog) return;
  try {
    const name = validateEntryName(ui.fileEntryName.value);
    const {action, target} = pendingFileDialog;
    if (action === "rename") {
      await transferWorkspace(target.path, entryJoin(entryParent(target.path), name), "move");
    } else {
      const path = entryJoin(target.path, name);
      await api(`/v1/sessions/${sessionId}/workspace/entries`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({path, type: action === "new-file" ? "file" : "directory"}),
      });
      await refreshTree(); setStatus(t("file.created", {name}), true);
    }
    ui.fileEntryDialog.close();
  } catch (error) { ui.fileEntryHelp.textContent = error.message; }
});

ui.fileContextMenu.addEventListener("click", event => {
  const button = event.target.closest("button[data-file-action]");
  if (!button || button.disabled || !fileMenuTarget) return;
  executeFileAction(button.dataset.fileAction, fileMenuTarget).catch(error => setStatus(error.message));
});
ui.fileActions.addEventListener("click", event => {
  const rect = event.currentTarget.getBoundingClientRect();
  openFileMenu({path: "workspace", name: "workspace", type: "directory"}, rect.left, rect.bottom + 4);
  event.stopPropagation();
});
document.addEventListener("click", event => { if (!ui.fileContextMenu.contains(event.target)) closeFileMenu(); });
document.addEventListener("keydown", event => { if (event.key === "Escape") closeFileMenu(); });
ui.treeFilter?.addEventListener("input", () => {
  ui.treeFilterClear.hidden = !(ui.treeFilter.value || "").trim();
  if (treeFilterTimer) clearTimeout(treeFilterTimer);
  treeFilterTimer = setTimeout(() => {
    treeFilterTimer = null;
    renderedTreeSignature = ""; // 过滤串变化，强制重渲染
    refreshTree(sessionId).catch(error => setStatus(error.message));
  }, 300);
});
ui.treeFilter?.addEventListener("keydown", event => {
  if (event.key === "Enter") { event.preventDefault(); refreshTree(sessionId).catch(error => setStatus(error.message)); }
});
ui.treeFilterClear?.addEventListener("click", () => {
  ui.treeFilter.value = "";
  ui.treeFilterClear.hidden = true;
  renderedTreeSignature = "";
  refreshTree(sessionId).catch(error => setStatus(error.message));
});
ui.tree.addEventListener("contextmenu", event => {
  if (event.target.closest(".tree-file, .tree-dir > summary")) return;
  event.preventDefault(); openFileMenu({path: "workspace", name: "workspace", type: "directory"}, event.clientX, event.clientY);
});

function bindTreeEntry(element, node, {dropDirectory = false} = {}) {
  const root = isWorkspaceRoot(node.path);
  element.dataset.path = node.path;
  element.addEventListener("contextmenu", event => {
    event.preventDefault(); event.stopPropagation();
    openFileMenu(node, event.clientX, event.clientY);
  });
  if (!root) {
    element.draggable = true;
    element.addEventListener("dragstart", event => {
      event.stopPropagation();
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("application/x-flowchart-path", node.path);
      event.dataTransfer.setData("text/plain", node.path);
    });
  }
  if (dropDirectory) {
    element.addEventListener("dragover", event => {
      const hasFiles = event.dataTransfer?.types.includes("Files");
      const hasMove = event.dataTransfer?.types.includes("application/x-flowchart-path");
      if (!hasFiles && !hasMove) return;
      event.preventDefault(); event.stopPropagation(); element.classList.add("drag-target");
      event.dataTransfer.dropEffect = hasFiles ? "copy" : "move";
    });
    element.addEventListener("dragleave", () => {
      element.classList.remove("drag-target");
      // 兜底：拖拽目标移出整棵树时清掉外层 dropzone 高亮（子元素 drop 会 stopPropagation，
      // 外层 dragleave 计数可能残留 drag-over）
      if (!element.matches(":hover") && ui.filebar?.classList.contains("drag-over")) {
        setTimeout(() => {
          if (!ui.filebar.matches(":hover")) ui.filebar.classList.remove("drag-over");
        }, 120);
      }
    });
    element.addEventListener("drop", event => {
      event.preventDefault(); event.stopPropagation(); element.classList.remove("drag-target");
      // 目录 drop 拦截了冒泡，外层 filebar 的 drop 收不到 → 主动清它的拖放高亮
      ui.filebar?.classList.remove("drag-over");
      // 外部文件拖入具体目录 → 上传到该目录
      if (event.dataTransfer?.types.includes("Files")) {
        const files = [...(event.dataTransfer.files || [])];
        if (files.length) {
          uploadWorkspaceFiles(files, node.path).catch(error => setStatus(error.message));
        }
        return;
      }
      // 内部拖拽 → 移动
      const source = event.dataTransfer.getData("application/x-flowchart-path");
      if (!source) return;
      transferWorkspace(source, entryJoin(node.path, entryName(source)), "move").catch(error => setStatus(error.message));
    });
  }
}

function renderTreeNodes(nodes, parent) {
  for (const node of nodes) {
    if (node.virtual) {
      const hint = document.createElement("p");
      hint.className = "tree-truncated";
      hint.textContent = node.name;
      parent.append(hint);
      continue;
    }
    if (node.type === "directory") {
      const details = document.createElement("details");
      details.className = "tree-dir";
      details.open = node.path.split("/").length <= 1;
      const summary = document.createElement("summary");
      summary.textContent = node.name;
      summary.title = node.path;
      bindTreeEntry(summary, node, {dropDirectory: true});
      if (fileClipboard?.operation === "move" && fileClipboard.path === node.path) summary.classList.add("clipboard-cut");
      const children = document.createElement("div");
      children.className = "tree-children";
      renderTreeNodes(node.children, children);
      details.append(summary, children);
      parent.append(details);
    } else {
      const row = document.createElement("div");
      row.className = "tree-file-row";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tree-file";
      button.dataset.path = node.path;
      button.title = `${node.path} · ${node.size} bytes`;
      const icon = document.createElement("span");
      icon.className = "file-icon";
      icon.textContent = fileIcon(node.name);
      const name = document.createElement("span");
      name.className = "file-name";
      name.textContent = node.name;
      button.append(icon, name);
      bindTreeEntry(button, node);
      if (fileClipboard?.operation === "move" && fileClipboard.path === node.path) button.classList.add("clipboard-cut");
      button.addEventListener("click", () => previewFile(node.path, button));
      button.addEventListener("dblclick", event => {
        event.preventDefault();
        // HTML 双击 = 新标签页整页渲染（相对路径图片由 raw 端点解析）
        if (node.name.toLowerCase().endsWith(".html")) {
          window.open(
            `/v1/sessions/${sessionId}/workspace/files/raw/${node.path}`,
            "_blank", "noopener");
          return;
        }
        toggleWorkspaceAttachment(node.path, attach);
      });
      const attach = document.createElement("button");
      attach.type = "button";
      attach.className = "tree-attach";
      attach.dataset.path = node.path;
      attach.textContent = "+";
      attach.title = t("attachment.add");
      attach.setAttribute("aria-label", t("attachment.addAria", {name: node.name}));
      attach.addEventListener("click", () => toggleWorkspaceAttachment(node.path, attach));
      row.append(button, attach);
      parent.append(row);
    }
  }
}

function treeStructureSignature(nodes) {
  const entries = [];
  const walk = items => items.forEach(node => {
    entries.push(`${node.type}:${node.path}`);
    if (node.children?.length) walk(node.children);
  });
  walk(nodes);
  return entries.join("\n");
}

function scheduleWorkspaceRefresh(targetSessionId, delay = 180) {
  if (!targetSessionId || targetSessionId !== sessionId) return;
  if (workspaceRefreshTimer) clearTimeout(workspaceRefreshTimer);
  workspaceRefreshTimer = setTimeout(async () => {
    workspaceRefreshTimer = null;
    if (targetSessionId !== sessionId) return;
    try {
      await refreshTree(targetSessionId);
    } catch (error) {
      console.warn("自动刷新 Workspace 失败", error);
    }
  }, delay);
}

async function refreshTree(targetSessionId = sessionId) {
  if (!targetSessionId) return;
  const expanded = new Set([...ui.tree.querySelectorAll(".tree-dir[open] > summary")].map(node => node.dataset.path));
  const scrollTop = ui.tree.scrollTop;
  const filter = (ui.treeFilter?.value || "").trim();
  const query = filter ? `?filter=${encodeURIComponent(filter)}` : "";
  const nodes = await api(`/v1/sessions/${targetSessionId}/workspace/tree${query}`);
  if (targetSessionId !== sessionId) return;
  const signature = treeStructureSignature(nodes);
  if (renderedTreeSessionId === targetSessionId && renderedTreeSignature === signature) {
    updateWorkspaceAttachButtons();
    return;
  }
  renderedTreeSessionId = targetSessionId;
  renderedTreeSignature = signature;
  ui.tree.replaceChildren();
  if (!nodes.length) {
    const empty = document.createElement("p");
    empty.className = "tree-empty";
    empty.textContent = t("tree.empty");
    ui.tree.append(empty);
    return;
  }
  renderTreeNodes(nodes, ui.tree);
  for (const summary of ui.tree.querySelectorAll(".tree-dir > summary")) {
    if (expanded.has(summary.dataset.path)) summary.parentElement.open = true;
  }
  ui.tree.scrollTop = scrollTop;
  updateWorkspaceAttachButtons();
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
}

function renderMarkdown(source) {
  const escaped = escapeHtml(source);
  const lines = escaped.split(/\r?\n/);
  let html = "";
  let inCode = false;
  let inList = false;
  for (const line of lines) {
    if (line.startsWith("```")) {
      if (inList) { html += "</ul>"; inList = false; }
      html += inCode ? "</code></pre>" : "<pre><code>";
      inCode = !inCode;
      continue;
    }
    if (inCode) { html += `${line}\n`; continue; }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      if (inList) { html += "</ul>"; inList = false; }
      const level = heading[1].length;
      html += `<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`;
      continue;
    }
    const item = line.match(/^[-*]\s+(.+)$/);
    if (item) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${renderInlineMarkdown(item[1])}</li>`;
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    if (line.startsWith("&gt; ")) html += `<blockquote>${renderInlineMarkdown(line.slice(5))}</blockquote>`;
    else if (line.trim()) html += `<p>${renderInlineMarkdown(line)}</p>`;
  }
  if (inList) html += "</ul>";
  if (inCode) html += "</code></pre>";
  return html;
}

function renderInlineMarkdown(source) {
  return source
    .replace(
      /\[([^\]]+)\]\(workspace-file:([A-Za-z0-9%._~-]+)\)/g,
      '<a href="#workspace-file" class="message-file-link" data-workspace-path="$2">$1</a>',
    )
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

const CSV_PREVIEW_MAX_ROWS = 500;
const CSV_PREVIEW_MAX_COLUMNS = 80;

function parseCsv(source, maxRows = CSV_PREVIEW_MAX_ROWS, maxColumns = CSV_PREVIEW_MAX_COLUMNS) {
  const text = source.replace(/^\uFEFF/, "");
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  let rowsTruncated = false;
  let columnsTruncated = false;

  const finishRow = () => {
    row.push(field);
    if (row.length > maxColumns) columnsTruncated = true;
    rows.push(row.slice(0, maxColumns));
    row = [];
    field = "";
    return rows.length >= maxRows;
  };

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"'; index += 1;
      } else if (char === '"') quoted = false;
      else field += char;
      continue;
    }
    if (char === '"' && field === "") quoted = true;
    else if (char === ",") { row.push(field); field = ""; }
    else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[index + 1] === "\n") index += 1;
      if (finishRow()) {
        rowsTruncated = index < text.length - 1;
        break;
      }
    } else field += char;
  }
  if (!rowsTruncated && (field !== "" || row.length || text.endsWith(","))) finishRow();
  return {rows, rowsTruncated, columnsTruncated};
}

function renderCsvPreview(source) {
  const {rows, rowsTruncated, columnsTruncated} = parseCsv(source);
  ui.csvView.replaceChildren();
  const summary = document.createElement("div");
  summary.className = "csv-preview-summary";
  if (!rows.length) {
    summary.textContent = t("csv.empty");
    ui.csvView.append(summary);
    return;
  }
  const columnCount = Math.max(...rows.map(row => row.length));
  const limited = rowsTruncated || columnsTruncated;
  summary.textContent = limited
    ? t("csv.summaryTruncated", {rows: rows.length.toLocaleString(), columns: columnCount.toLocaleString()})
    : t("csv.summary", {rows: rows.length.toLocaleString(), columns: columnCount.toLocaleString()});

  const wrap = document.createElement("div");
  wrap.className = "csv-table-wrap";
  const table = document.createElement("table");
  table.className = "csv-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  const corner = document.createElement("th");
  corner.className = "csv-row-number";
  corner.textContent = "#";
  headRow.append(corner);
  for (const value of rows[0]) {
    const cell = document.createElement("th");
    cell.textContent = value;
    headRow.append(cell);
  }
  head.append(headRow);
  const body = document.createElement("tbody");
  rows.slice(1).forEach((values, rowIndex) => {
    const tableRow = document.createElement("tr");
    const number = document.createElement("th");
    number.className = "csv-row-number";
    number.scope = "row";
    number.textContent = String(rowIndex + 1);
    tableRow.append(number);
    for (let column = 0; column < columnCount; column += 1) {
      const cell = document.createElement("td");
      cell.textContent = values[column] ?? "";
      tableRow.append(cell);
    }
    body.append(tableRow);
  });
  table.append(head, body);
  wrap.append(table);
  ui.csvView.append(summary, wrap);
}

function resetPreviewViews() {
  ui.canvas.classList.add("hidden");
  ui.markdownView.classList.add("hidden");
  ui.csvView.classList.add("hidden");
  ui.codeView.classList.add("hidden");
  ui.resourceEditor.classList.add("hidden");
}

// 预览策略：可预览的文本/文档后缀；二进制一律不进预览（防炸页面）
const BINARY_EXTS = new Set([
  "zip", "7z", "rar", "tar", "gz", "bz2", "xz", "tgz", "jar", "war",
  "exe", "dll", "so", "dylib", "bin", "o", "a", "lib", "msi", "apk",
  "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods",
  "mp3", "mp4", "avi", "mov", "mkv", "wav", "flac", "webm",
  "ttf", "otf", "woff", "woff2", "eot", "ico", "psd", "ai",
  "db", "sqlite", "sqlite3", "pyc", "class", "wasm",
]);
const PREVIEW_MAX_BYTES = 2 * 1024 * 1024;  // 预览文本上限 2MB，超出提示下载

function previewBinary(ext) { return BINARY_EXTS.has(ext); }

function hljsHighlight(text, ext) {
  const code = ui.codeView;
  if (window.hljs) {
    const language = hljs.getLanguage(ext) ? ext : undefined;
    code.innerHTML = hljs.highlight(text, {language}).value;
  } else {
    code.textContent = text;
  }
}

async function previewFile(path, button) {
  if (previewCollapsed) setPreviewCollapsed(false);  // 用户在文件树浏览，自动展开
  selectedFile = path;
  selectedResource = null;
  document.querySelectorAll(".tree-file.active").forEach(node => node.classList.remove("active"));
  button.classList.add("active");
  const url = `/v1/sessions/${sessionId}/workspace/files/content?path=${encodeURIComponent(path)}`;
  const name = path.split("/").pop();
  const ext = name.split(".").pop().toLowerCase();
  ui.previewKicker.textContent = "OUTPUT FILE";
  ui.previewTitle.textContent = name;
  ui.saveResource.classList.add("hidden");
  ui.deleteResource.classList.add("hidden");
  ui.attachWorkspaceFile.classList.remove("hidden");
  updateWorkspaceAttachButtons();
  ui.openFile.href = url;
  ui.openFile.classList.remove("hidden");
  resetPreviewViews();
  setStatus(t("preview.reading", {name}));
  try {
    if (["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"].includes(ext)) {
      ui.canvas.replaceChildren();
      ui.canvas.classList.remove("hidden", "empty");
      const image = new Image();
      image.alt = name;
      image.src = `${url}&t=${Date.now()}`;
      ui.canvas.append(image);
    } else if (previewBinary(ext)) {
      // 二进制文件不进预览：提示并提供下载
      ui.canvas.replaceChildren();
      ui.canvas.classList.remove("hidden");
      ui.canvas.classList.add("empty");
      const note = document.createElement("p");
      note.className = "preview-note";
      note.textContent = t("preview.binary", {ext: ext.toUpperCase()});
      const hint = document.createElement("p");
      hint.className = "preview-note muted";
      hint.textContent = t("preview.binaryHint");
      ui.canvas.append(note, hint);
    } else {
      // 文本预览：先探大小（该端点不支持 HEAD，用 Range GET 只拉 1 字节拿总长）
      const size = await new Promise((resolve) => {
        fetch(url, {headers: {Range: "bytes=0-0"}})
          .then(r => {
            const total = r.headers.get("Content-Range");  // "bytes 0-0/3000002"
            resolve(total ? Number(total.split("/")[1]) : 0);
          })
          .catch(() => resolve(0));
      });
      if (size > PREVIEW_MAX_BYTES) {
        ui.codeView.textContent = t("preview.tooLarge", {
          size: (size / 1024 / 1024).toFixed(1),
        });
        ui.codeView.classList.remove("hidden");
        setStatus(t("preview.tooLargeShort"), true);
        return;
      }
      const response = await fetch(url);
      if (!response.ok) throw new Error(t("error.readFailed", {status: response.status}));
      const text = await response.text();
      if (["md", "markdown"].includes(ext)) {
        ui.markdownView.innerHTML = renderMarkdown(text);
        ui.markdownView.classList.remove("hidden");
      } else if (ext === "csv") {
        renderCsvPreview(text);
        ui.csvView.classList.remove("hidden");
      } else if (ext === "html" || ext === "htm") {
        // HTML：源码高亮 + 顶部提示条（双击/按钮可在新标签页整页渲染）
        ui.codeView.textContent = text;
        ui.codeView.classList.remove("hidden");
        const banner = document.createElement("p");
        banner.className = "preview-note";
        const link = document.createElement("a");
        link.href = `/v1/sessions/${sessionId}/workspace/files/raw/${path}`;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = t("preview.openHtml");
        banner.append(link);
        ui.codeView.parentElement.insertBefore(banner, ui.codeView);
      } else {
        hljsHighlight(text, ext);
        ui.codeView.classList.remove("hidden");
      }
    }
    setStatus(t("status.connected"), true);
  } catch (error) {
    ui.codeView.textContent = error.message;
    ui.codeView.classList.remove("hidden");
    setStatus(t("preview.readFailed"));
  }
}

async function openMessageFile(path) {
  switchSection("workspace");
  await refreshTree();
  const button = [...ui.tree.querySelectorAll(".tree-file")]
    .find(node => node.dataset.path === path);
  if (!button) throw new Error(t("file.notFound", {path}));
  let parent = button.parentElement;
  while (parent && parent !== ui.tree) {
    if (parent.matches?.("details.tree-dir")) parent.open = true;
    parent = parent.parentElement;
  }
  await previewFile(path, button);
  button.scrollIntoView({block: "nearest"});
}

ui.messages.addEventListener("click", event => {
  const link = event.target.closest(".message-file-link");
  if (!link) return;
  event.preventDefault();
  let path;
  try {
    path = decodeURIComponent(link.dataset.workspacePath || "");
  } catch (_) {
    setStatus(t("file.linkInvalid"));
    return;
  }
  openMessageFile(path).catch(error => setStatus(error.message));
});

ui.refreshTree.addEventListener("click", () => {
  const refresh = activeSection === "workspace" ? refreshTree() : refreshResources(activeSection);
  refresh.catch(error => setStatus(error.message));
});
ui.saveResource.addEventListener("click", async () => {
  if (!selectedResource) return;
  ui.saveResource.disabled = true;
  try {
    selectedResource = await api(
      `/v1/sessions/${sessionId}/client/${selectedResource.kind}/${encodeURIComponent(selectedResource.name)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: ui.resourceEditor.value }),
      }
    );
    setStatus(t("resource.saved", {name: selectedResource.name}), true);
  } catch (error) {
    setStatus(error.message);
  } finally {
    ui.saveResource.disabled = false;
  }
});

ui.deleteResource.addEventListener("click", async () => {
  if (!selectedResource || selectedResource.builtin) return;
  ui.deleteResource.disabled = true;
  try {
    const kind = selectedResource.kind;
    await api(`/v1/sessions/${sessionId}/client/${kind}/${encodeURIComponent(selectedResource.name)}`, { method: "DELETE" });
    selectedResource = null;
    await refreshResources(kind);
    clearPreview();
    setStatus(t("resource.deleted"), true);
  } catch (error) {
    setStatus(error.message);
  } finally {
    ui.deleteResource.disabled = false;
  }
});

function addAttachmentChip(uploaded) {
  pendingFiles.push(uploaded);
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.title = uploaded.filename;
  const name = document.createElement("span");
  name.className = "chip-name";
  name.textContent = uploaded.filename;
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "chip-remove";
  remove.textContent = "×";
  remove.title = t("attachment.removeTitle", {name: uploaded.filename});
  remove.setAttribute("aria-label", t("attachment.removeAria", {name: uploaded.filename}));
  remove.addEventListener("click", () => removePendingAttachment(uploaded));
  chip.append(name, remove);
  ui.attachments.append(chip);
}

function removePendingAttachment(uploaded) {
  pendingFiles = pendingFiles.filter(file => file !== uploaded && file.id !== uploaded.id);
  renderPendingAttachments();
  updateWorkspaceAttachButtons();
  setStatus(t("attachment.removed", {name: uploaded.filename}), true);
}

function renderPendingAttachments() {
  const files = [...pendingFiles];
  ui.attachments.replaceChildren();
  pendingFiles = [];
  files.forEach(addAttachmentChip);
}

function workspaceAttachment(path) {
  return pendingFiles.find(file => file.workspacePath === path);
}

function updateWorkspaceAttachButtons() {
  ui.tree.querySelectorAll(".tree-attach").forEach(button => {
    const attached = Boolean(workspaceAttachment(button.dataset.path));
    button.classList.toggle("attached", attached);
    button.textContent = attached ? "✓" : "+";
    button.title = attached ? t("attachment.remove") : t("attachment.add");
    button.setAttribute("aria-label", attached ? t("attachment.removePathAria", {path: button.dataset.path}) : t("attachment.addPathAria", {path: button.dataset.path}));
    button.disabled = false;
  });
  const selectedAttached = selectedFile && workspaceAttachment(selectedFile);
  ui.attachWorkspaceFile.disabled = false;
  ui.attachWorkspaceFile.textContent = selectedAttached ? t("attachment.removeButton") : t("preview.attach");
}

async function toggleWorkspaceAttachment(path, button = null) {
  const attached = workspaceAttachment(path);
  if (attached) {
    removePendingAttachment(attached);
    return;
  }
  await attachWorkspacePath(path, button);
}

async function attachWorkspacePath(path, button = null) {
  if (!path || !sessionId || workspaceAttachment(path)) return;
  if (button) button.disabled = true;
  try {
    const uploaded = await api(`/v1/sessions/${sessionId}/files/from-workspace`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    uploaded.workspacePath = path;
    addAttachmentChip(uploaded);
    updateWorkspaceAttachButtons();
    setStatus(t("attachment.added", {name: uploaded.filename}), true);
    ui.prompt.focus();
  } catch (error) {
    setStatus(error.message);
  } finally {
    if (button && !workspaceAttachment(path)) button.disabled = false;
  }
}

ui.attachWorkspaceFile.addEventListener("click", async () => {
  ui.attachWorkspaceFile.disabled = true;
  try {
    await toggleWorkspaceAttachment(selectedFile);
  } finally {
    ui.attachWorkspaceFile.disabled = false;
  }
});

async function uploadAttachmentFiles(files) {
  if (!sessionId) return;
  for (const file of files) {
    setStatus(t("upload.uploading", {name: file.name}));
    try {
      const uploaded = await api(`/v1/sessions/${sessionId}/files?filename=${encodeURIComponent(file.name)}`, {
        method: "POST",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      addAttachmentChip(uploaded);
    } catch (error) {
      addMessage(error.message, "assistant");
    }
  }
  setStatus(t("status.connected"), true);
  await refreshTree();
}

async function uploadWorkspaceFiles(files, targetDir = "") {
  const dirQuery = targetDir ? `&path=${encodeURIComponent(targetDir)}` : "";
  for (const file of files) {
    setStatus(t("upload.saving", {name: file.name}));
    await api(`/v1/sessions/${sessionId}/workspace/files?filename=${encodeURIComponent(file.name)}${dirQuery}`, {
      method: "POST",
      headers: { "Content-Type": file.type || "application/octet-stream" },
      body: file,
    });
  }
  await refreshTree();
  setStatus(targetDir ? t("upload.savedToDir", {dir: targetDir}) : t("upload.savedToOutput"), true);
}

ui.file.addEventListener("change", async () => {
  await uploadAttachmentFiles([...ui.file.files]);
  ui.file.value = "";
});

function bindDropZone(element, onFiles) {
  let dragDepth = 0;
  element.addEventListener("dragenter", event => {
    if (!event.dataTransfer?.types.includes("Files")) return;
    event.preventDefault();
    dragDepth += 1;
    element.classList.add("drag-over");
  });
  element.addEventListener("dragover", event => {
    if (!event.dataTransfer?.types.includes("Files")) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });
  element.addEventListener("dragleave", () => {
    dragDepth -= 1;
    if (dragDepth <= 0) {
      dragDepth = 0;
      element.classList.remove("drag-over");
    }
  });
  element.addEventListener("drop", async event => {
    event.preventDefault();
    event.stopPropagation();
    dragDepth = 0;
    element.classList.remove("drag-over");
    const files = [...(event.dataTransfer?.files || [])];
    if (!files.length) return;
    try {
      await onFiles(files);
    } catch (error) {
      addMessage(t("upload.failedMessage", {error: error.message}), "assistant");
      setStatus(t("upload.failed"));
    }
  });
}

bindDropZone(ui.filebar, uploadWorkspaceFiles);
bindDropZone(ui.composer, uploadAttachmentFiles);
// 全局兜底：拖拽结束/取消（含 OS 层取消、Esc）后清掉所有 dropzone 高亮
for (const eventName of ["dragend", "drop"]) {
  window.addEventListener(eventName, () => {
    document.querySelectorAll(".drag-over").forEach(node => node.classList.remove("drag-over"));
    document.querySelectorAll(".drag-target").forEach(node => node.classList.remove("drag-target"));
  }, true);  // capture：在 stopPropagation 的子 handler 之前也能收到
}

function setRunControls(running, stopping = false) {
  ui.send.classList.toggle("hidden", running);
  ui.stop.classList.toggle("hidden", !running);
  ui.stop.disabled = stopping;
  ui.stop.textContent = stopping ? t("composer.stopping") : t("composer.stop");
  ui.prompt.disabled = running;
  ui.compactContext.disabled = running;
}

function followRun(runId, runSessionId = sessionId) {
  if (activeRunCleanup) activeRunCleanup();
  else if (activeStream) activeStream.close();
  const stream = new EventSource(`/v1/runs/${runId}/events`);
  activeStream = stream;
  activeRunId = runId;
  activeRunSessionId = runSessionId;
  setRunControls(true);
  setStatus(t("run.running"));
  let assistant = null;
  let streamedText = "";
  let generation = null;
  const pendingTools = new Map();
  const pendingSubagentTools = new Map();
  let reasoningAction = null;
  let reasoningBuffer = "";
  let usageChars = 0;
  let subagentTaskAction = null;
  let subagentReasoning = null;
  let subagentReasoningBuffer = "";
  let subagentOutput = null;
  let subagentOutputBuffer = "";
  const startedAt = Date.now();
  const metrics = document.createElement("div");
  metrics.className = "run-metrics";
  ui.messages.append(metrics);
  const updateMetrics = () => {
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    metrics.textContent = t("run.metrics", {tokens: Math.ceil(usageChars / 4).toLocaleString(), seconds});
  };
  const timer = setInterval(updateMetrics, 1000);
  // SSE is authoritative; this low-frequency refresh is only a safety net for
  // files written by extensions that do not emit a workspace milestone yet.
  const workspaceFallback = setInterval(
    () => scheduleWorkspaceRefresh(runSessionId, 0), 2500
  );
  const cleanup = () => {
    stream.close();
    clearInterval(timer);
    clearInterval(workspaceFallback);
    if (activeStream === stream) activeStream = null;
    if (activeRunCleanup === cleanup) activeRunCleanup = null;
  };
  activeRunCleanup = cleanup;
  updateMetrics();
  const finishReasoning = () => {
    if (!reasoningAction || reasoningAction.classList.contains("completed")) return;
    reasoningAction.classList.add("completed");
    reasoningAction.textContent = reasoningAction.textContent.replace(t("run.reasoningPrefix"), t("run.reasoningDone"));
  };
  const ensureReasoningLine = () => {
    if (!reasoningAction || reasoningAction.classList.contains("completed")) {
      reasoningBuffer = "";
      reasoningAction = document.createElement("div");
      reasoningAction.className = "reasoning-line";
      reasoningAction.textContent = t("run.reasoning");
      ui.messages.append(reasoningAction);
    }
    return reasoningAction;
  };

  stream.addEventListener("assistant.delta", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    if (!assistant) assistant = addMessage("", "assistant");
    streamedText += payload.data.text;
    usageChars += payload.data.text.length;
    finishReasoning(); updateMetrics();
    assistant.querySelector(".message-body").textContent = streamedText;
  });
  stream.addEventListener("workspace.changed", event => {
    if (sessionId !== runSessionId) return;
    scheduleWorkspaceRefresh(runSessionId);
  });
  stream.addEventListener("reasoning.status", () => {
    if (sessionId !== runSessionId) return;
    ensureReasoningLine();
  });
  stream.addEventListener("reasoning.delta", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    reasoningBuffer = (reasoningBuffer + (payload.data.text || "")).slice(-1200);
    const lines = reasoningBuffer.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const tail = lines.at(-1) || t("run.reasoningFallback");
    const visible = tail.length > 110 ? `…${tail.slice(-110)}` : tail;
    ensureReasoningLine().textContent = t("run.reasoningLine", {text: visible});
    ui.messages.scrollTop = ui.messages.scrollHeight;
  });
  stream.addEventListener("usage.delta", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    usageChars += payload.data.chars || 0; updateMetrics();
  });
  stream.addEventListener("progress.updated", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    if (!generation) generation = addMessage("", "progress");
    generation.textContent = payload.data.message;
  });
  stream.addEventListener("tool.started", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    const name = payload.data.name;
    finishReasoning();
    const action = addAgentAction(name, "main", payload.data.arguments ?? "", assistant);
    const queue = pendingTools.get(name) || [];
    queue.push(action); pendingTools.set(name, queue);
  });
  stream.addEventListener("tool.progress", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    const name = payload.data.name;
    const queue = pendingTools.get(name) || [];
    const action = queue[queue.length - 1];
    if (!action) return;
    // 流式中间输出：滚进工具卡片的 liveOutput，点开可见实时滚动
    action.liveOutput = (action.liveOutput + (payload.data.output_delta || "")).slice(-12000);
    if (activeToolDetail === action) renderToolDetail(action);
  });
  stream.addEventListener("resource.activated", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    const action = addAgentAction("use_skill", "main", null, assistant);
    action.node.classList.remove("running"); action.node.classList.add("completed");
    action.icon.textContent = "✓";
    action.text.textContent = t("run.skillLoaded", {name: payload.data.name});
  });
  stream.addEventListener("tool.completed", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    const name = payload.data.name;
    const queue = pendingTools.get(name) || [];
    const action = queue.shift();
    if (!action) return;
    action.node.classList.remove("running"); action.node.classList.add("completed");
    action.icon.textContent = "✓"; action.text.textContent = t("action.completed", {tool: toolLabel(name)});
    action.result = payload.data.result ?? "";
    makeToolActionInspectable(action);
    if (activeToolDetail === action) renderToolDetail(action);
    scheduleWorkspaceRefresh(runSessionId);
  });
  stream.addEventListener("subagent.started", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    const task = payload.data.task || t("subagent.defaultTask");
    subagentTaskAction = addAgentAction("subagent_task", "subagent", task, assistant);
    subagentTaskAction.text.textContent = t("subagent.tookOver", {task: task.length > 90 ? `${task.slice(0, 90)}…` : task});
    subagentTaskAction.node.title = task;
  });
  stream.addEventListener("subagent.reasoning.delta", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    subagentReasoningBuffer = (subagentReasoningBuffer + (payload.data.text || "")).slice(-1200);
    if (!subagentReasoning) {
      subagentReasoning = document.createElement("div");
      subagentReasoning.className = "subagent-line";
      ui.messages.append(subagentReasoning);
    }
    const lines = subagentReasoningBuffer.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const latest = lines.at(-1) || t("subagent.reasoningFallback");
    subagentReasoning.textContent = t("subagent.reasoningLine", {text: latest});
    if (subagentTaskAction) {
      subagentTaskAction.liveReasoning = (
        subagentTaskAction.liveReasoning + (payload.data.text || "")
      ).slice(-12000);
      if (activeToolDetail === subagentTaskAction) renderToolDetail(subagentTaskAction);
    }
    // 兼容仍在旧服务进程中运行的长工具：旧后端把工具内部进度发成 reasoning.delta。
    const checkAction = (pendingSubagentTools.get("image_reasoning") || [])[0];
    if (checkAction && latest) {
      const visibleLatest = latest.length > 140 ? `…${latest.slice(-140)}` : latest;
      checkAction.text.textContent = t("subagent.toolLine", {tool: toolLabel("image_reasoning"), text: visibleLatest});
      checkAction.node.title = latest;
    }
    ui.messages.scrollTop = ui.messages.scrollHeight;
  });
  stream.addEventListener("subagent.delta", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    subagentOutputBuffer = (subagentOutputBuffer + (payload.data.text || "")).slice(-1600);
    if (!subagentOutput) {
      subagentOutput = document.createElement("div");
      subagentOutput.className = "subagent-line";
      ui.messages.append(subagentOutput);
    }
    const lines = subagentOutputBuffer.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const tail = lines.at(-1) || t("subagent.outputFallback");
    subagentOutput.textContent = t("subagent.outputLine", {text: tail.length > 120 ? `…${tail.slice(-120)}` : tail});
    if (subagentTaskAction) {
      subagentTaskAction.liveOutput = (
        subagentTaskAction.liveOutput + (payload.data.text || "")
      ).slice(-12000);
      if (activeToolDetail === subagentTaskAction) renderToolDetail(subagentTaskAction);
    }
    ui.messages.scrollTop = ui.messages.scrollHeight;
  });
  stream.addEventListener("subagent.tool.started", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    const name = payload.data.name;
    const action = addAgentAction(name, "subagent", payload.data.arguments ?? "", assistant);
    const queue = pendingSubagentTools.get(name) || [];
    queue.push(action); pendingSubagentTools.set(name, queue);
  });
  stream.addEventListener("subagent.tool.progress", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    const name = payload.data.name;
    const queue = pendingSubagentTools.get(name) || [];
    const action = queue[0];
    if (!action) return;
    const message = payload.data.message || t("tool.running");
    if (payload.data.reasoning_delta) {
      action.liveReasoning = (action.liveReasoning + payload.data.reasoning_delta).slice(-12000);
    }
    if (payload.data.output_delta) {
      action.liveOutput = (action.liveOutput + payload.data.output_delta).slice(-12000);
    }
    action.text.textContent = t("subagent.toolLine", {tool: toolLabel(name), text: message});
    action.node.title = message;
    if (activeToolDetail === action) renderToolDetail(action);
  });
  stream.addEventListener("subagent.tool.completed", event => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    const name = payload.data.name;
    const queue = pendingSubagentTools.get(name) || [];
    const action = queue.shift();
    if (!action) return;
    action.node.classList.remove("running"); action.node.classList.add("completed");
    action.icon.textContent = "✓"; action.text.textContent = t("subagent.completed", {tool: toolLabel(name)});
    action.result = payload.data.result ?? "";
    makeToolActionInspectable(action);
    if (activeToolDetail === action) renderToolDetail(action);
    scheduleWorkspaceRefresh(runSessionId);
  });
  const finishSubagent = (status, data = {}) => {
    if (subagentReasoning) subagentReasoning.classList.add("completed");
    if (subagentOutput) subagentOutput.classList.add("completed");
    if (!subagentTaskAction) return;
    subagentTaskAction.node.classList.remove("running");
    subagentTaskAction.node.classList.add("completed");
    subagentTaskAction.icon.textContent = status === "completed" ? "✓" : "!";
    subagentTaskAction.text.textContent = status === "completed" ? t("subagent.workDone") : t("subagent.status", {status});
    subagentTaskAction.result = data.result ?? data.error ?? subagentTaskAction.liveOutput ?? "";
    makeToolActionInspectable(subagentTaskAction);
    if (activeToolDetail === subagentTaskAction) renderToolDetail(subagentTaskAction);
  };
  const finishSubagentEvent = (event, status) => {
    if (sessionId !== runSessionId) return;
    const payload = JSON.parse(event.data);
    finishSubagent(status, payload.data || {});
  };
  stream.addEventListener("subagent.completed", event => finishSubagentEvent(event, "completed"));
  stream.addEventListener("subagent.failed", event => finishSubagentEvent(event, t("subagent.failed")));
  stream.addEventListener("subagent.cancelled", event => finishSubagentEvent(event, t("subagent.cancelled")));
  stream.addEventListener("run.completed", async event => {
    if (sessionId !== runSessionId) { stream.close(); return; }
    const payload = JSON.parse(event.data);
    const reply = payload.data.reply || t("run.done");
    if (!assistant || !streamedText.trim()) {
      assistant = addMessage(reply, "assistant");
    }
    assistant.querySelector(".message-body").innerHTML = renderMarkdown(reply);
    cleanup(); finishReasoning(); updateMetrics();
    activeStream = null; activeRunId = null; activeRunSessionId = null;
    setRunControls(false);
    setStatus(t("status.connected"), true);
    await refreshTree();
    await refreshContext(runSessionId);
    await refreshSessionTabs();
  });
  stream.addEventListener("run.failed", async event => {
    if (sessionId !== runSessionId) { stream.close(); return; }
    const payload = JSON.parse(event.data);
    addMessage(t("run.failedMessage", {error: payload.data.error}), "assistant");
    cleanup(); finishReasoning(); updateMetrics();
    activeStream = null; activeRunId = null; activeRunSessionId = null;
    setRunControls(false);
    setStatus(t("run.failed"));
    await refreshTree(runSessionId);
    await refreshContext(runSessionId);
  });
  stream.addEventListener("run.cancelling", () => {
    if (sessionId !== runSessionId) return;
    setRunControls(true, true);
    setStatus(t("run.stopping"));
  });
  stream.addEventListener("run.cancelled", async event => {
    if (sessionId !== runSessionId) { stream.close(); return; }
    const payload = JSON.parse(event.data);
    const reply = payload.data.reply || t("run.stoppedReply");
    addMessage(reply, "assistant");
    cleanup(); finishReasoning(); updateMetrics();
    activeStream = null; activeRunId = null; activeRunSessionId = null;
    setRunControls(false);
    setStatus(t("run.stopped"), true);
    await refreshTree();
    await refreshContext(runSessionId);
  });
  stream.onerror = () => {
    if (stream.readyState === EventSource.CLOSED) return;
    setStatus(t("run.reconnecting"));
  };
}

function clearPreview() {
  ui.previewKicker.textContent = "PREVIEW";
  ui.previewTitle.textContent = t("preview.title");
  ui.saveResource.classList.add("hidden");
  ui.deleteResource.classList.add("hidden");
  ui.attachWorkspaceFile.classList.add("hidden");
  ui.openFile.classList.add("hidden");
  resetPreviewViews();
  ui.canvas.replaceChildren();
  ui.canvas.textContent = t("canvas.empty");
  ui.canvas.classList.add("empty");
  ui.canvas.classList.remove("hidden");
}

ui.composer.addEventListener("submit", async event => {
  event.preventDefault();
  const input = ui.prompt.value.trim();
  if (!input || !sessionId) return;
  if (pendingResourceMutations.size) {
    setStatus(t("run.confirmingMounts"));
    await Promise.allSettled([...pendingResourceMutations]);
  }
  const attachmentsForRun = [...pendingFiles];
  addMessage(input, "user", attachmentsForRun);
  ui.prompt.value = "";
  setRunControls(true);
  setStatus(t("run.submitted"));
  try {
    const run = await api(`/v1/sessions/${sessionId}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input, attachments: attachmentsForRun.map(file => file.id) }),
    });
    pendingFiles = [];
    ui.attachments.replaceChildren();
    updateWorkspaceAttachButtons();
    followRun(run.id, sessionId);
  } catch (error) {
    addMessage(error.message, "assistant");
    setRunControls(false);
    setStatus(t("run.submitFailed"));
  }
});

ui.prompt.addEventListener("keydown", event => {
  if (
    event.key !== "Enter" ||
    event.shiftKey ||
    event.isComposing ||
    event.keyCode === 229
  ) return;
  event.preventDefault();
  if (!activeRunId && ui.prompt.value.trim()) {
    ui.composer.requestSubmit();
  }
});

ui.stop.addEventListener("click", async () => {
  if (!activeRunId || activeRunSessionId !== sessionId) return;
  setRunControls(true, true);
  setStatus(t("run.stopping"));
  try {
    await api(`/v1/runs/${activeRunId}/cancel`, {method: "POST"});
  } catch (error) {
    setRunControls(true, false);
    setStatus(error.message);
  }
});

function closeContextMenu() {
  ui.contextMenu.classList.add("hidden");
  ui.compactContext.setAttribute("aria-expanded", "false");
}

ui.compactContext.addEventListener("click", (event) => {
  event.stopPropagation();
  if (ui.compactContext.disabled) return;
  const opened = ui.contextMenu.classList.toggle("hidden") === false;
  ui.compactContext.setAttribute("aria-expanded", String(opened));
});

document.addEventListener("click", (event) => {
  if (!ui.contextMenu.classList.contains("hidden") && !event.target.closest(".context-menu-wrap")) {
    closeContextMenu();
  }
  if (!ui.modelMenu.classList.contains("hidden") && !event.target.closest(".model-menu-wrap, #model-menu")) {
    closeModelMenu();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeContextMenu();
    closeModelMenu();
  }
});

ui.contextMenuCompact.addEventListener("click", async () => {
  closeContextMenu();
  if (!sessionId || activeRunId) return;
  const targetSessionId = sessionId;
  ui.compactContext.disabled = true;
  ui.compactContext.textContent = t("context.compacting");
  setStatus(t("context.compactingStatus"));
  try {
    const stats = await api(`/v1/sessions/${targetSessionId}/context/compact`, {method: "POST"});
    if (targetSessionId !== sessionId) return;
    renderContextStats(stats);
    if (stats.compressed) {
      addMessage(t("context.compactedMessage", {before: compactTokenLabel(stats.before_tokens), after: compactTokenLabel(stats.used_tokens)}), "progress");
      setStatus(t("context.compacted"), true);
    } else {
      addMessage(stats.reason || t("context.noCompactNeeded"), "progress");
      setStatus(t("context.noCompactNeededStatus"), true);
    }
  } catch (error) {
    setStatus(error.message);
  } finally {
    ui.compactContext.textContent = t("context.menu");
    ui.compactContext.disabled = Boolean(activeRunId);
  }
});

ui.contextMenuClear.addEventListener("click", async () => {
  closeContextMenu();
  if (!sessionId || activeRunId) return;
  if (!confirm(t("context.clearConfirm"))) return;
  const targetSessionId = sessionId;
  ui.compactContext.disabled = true;
  setStatus(t("context.clearing"));
  try {
    const stats = await api(`/v1/sessions/${targetSessionId}/context/clear`, {method: "POST"});
    if (targetSessionId !== sessionId) return;
    renderContextStats(stats);
    addMessage(t("context.clearedMessage"), "progress");
    setStatus(t("context.cleared"), true);
  } catch (error) {
    setStatus(error.message);
  } finally {
    ui.compactContext.disabled = Boolean(activeRunId);
  }
});

boot().catch(error => {
  setStatus(t("status.connectFailed"));
  addMessage(t("session.createFailed", {error: error.message}), "assistant");
});
