<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { api, notify } from '../state.js';
import { encode } from '../../shared/api.js';
import { useAdminI18n } from '../../shared/adminI18n.js';
import UiIcon from '../../shared/UiIcon.vue';
import HelpTip from '../../shared/HelpTip.vue';
const { tr } = useAdminI18n();
const tools = ref([]),
  loading = ref(true),
  busy = ref(false),
  error = ref(''),
  query = ref(''),
  category = ref('all'),
  expanded = ref(new Set()),
  filteredExpanded = ref(new Set()),
  searchField = ref();
const categories = [
  { id: 'files', title: '文件操作', english: 'Files', icon: 'folder' },
  { id: 'vision', title: '图像理解', english: 'Vision', icon: 'eye' },
  { id: 'skills', title: '技能与脚本', english: 'Skills and scripts', icon: 'skills' },
  { id: 'coordination', title: '任务编排', english: 'Coordination', icon: 'sessions' },
  { id: 'protocol', title: '协议能力', english: 'Protocols', icon: 'shield' },
  { id: 'other', title: '其他工具', english: 'Other tools', icon: 'code' },
];
const groupId = (tool) => (categories.some((c) => c.id === tool.group) ? tool.group : 'other');
const groups = computed(() =>
  categories
    .map((c) => ({
      ...c,
      tools: tools.value.filter((tool) => groupId(tool) === c.id),
    }))
    .filter((c) => c.tools.length),
);
const keywords = computed(() => query.value.trim().toLowerCase().split(/\s+/).filter(Boolean));
const filtering = computed(() => keywords.value.length > 0 || category.value !== 'all');
const visible = computed(() =>
  groups.value
    .filter((g) => category.value === 'all' || g.id === category.value)
    .map((g) => ({
      ...g,
      tools: g.tools.filter((tool) => {
        const text =
          `${tool.name} ${tool.title} ${tool.title_en} ${tr(tool.title)} ${g.title} ${g.english} ${tr(g.title)}`.toLowerCase();
        return keywords.value.every((word) => text.includes(word));
      }),
    }))
    .filter((g) => g.tools.length),
);
const visibleCount = computed(() =>
  visible.value.reduce((count, group) => count + group.tools.length, 0),
);
const openGroups = computed(() => (filtering.value ? filteredExpanded.value : expanded.value));
const allOpen = computed(() => visible.value.every((group) => openGroups.value.has(group.id)));
const anyOpen = computed(() => visible.value.some((group) => openGroups.value.has(group.id)));
watch(
  [() => keywords.value.join(' '), category, () => visible.value.map((g) => g.id).join(',')],
  () => {
    if (filtering.value) filteredExpanded.value = new Set(visible.value.map((g) => g.id));
  },
);
function setExpanded(ids) {
  if (filtering.value) filteredExpanded.value = new Set(ids);
  else expanded.value = new Set(ids);
}
function toggleGroup(id) {
  const next = new Set(openGroups.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  setExpanded(next);
}
function clearQuery() {
  query.value = '';
  searchField.value?.focus();
}
function resetFilters() {
  category.value = 'all';
  clearQuery();
}
async function load() {
  loading.value = true;
  try {
    tools.value = (await api('GET', '/admin/v1/tools')).tools;
    error.value = '';
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
async function toggle(tool, enabled) {
  busy.value = true;
  error.value = '';
  const previous = tool.enabled;
  tool.enabled = enabled;
  try {
    Object.assign(tool, await api('PUT', `/admin/v1/tools/${encode(tool.name)}`, { enabled }));
    notify(tr('工具下发设置已更新'));
  } catch (e) {
    tool.enabled = previous;
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section id="page-tools" class="card">
    <header class="card-head">
      <h2>
        {{ tr('内置工具') }} <span class="badge">{{ tools.length }}</span>
        <HelpTip
          :text="
            tr(
              '控制平台主 Agent 和子 Agent 的工具下发。用户默认跟随全局设置，也可在用户管理中单独授权。模型能力和服务配置仍须满足工具要求。',
            ) +
            '\n' +
            tr(
              '保存后下一轮调用重新加载；已撤销的工具会在执行时拒绝。机器任务答案提交是协议必需能力，仅在机器任务中提供。',
            )
          "
        />
      </h2>
      <button @click="load" :disabled="loading || busy">{{ tr('刷新') }}</button>
    </header>
    <div class="card-body tools-body">
      <div class="tools-search">
        <UiIcon name="search" :size="20" />
        <input
          id="tools-search"
          ref="searchField"
          v-model="query"
          type="search"
          autocomplete="off"
          :aria-label="tr('搜索工具')"
          :placeholder="tr('按工具名称、标识或分类搜索…')"
          @keydown.esc="clearQuery"
        />
        <button
          v-if="query"
          class="icon-button"
          type="button"
          :aria-label="tr('清除搜索')"
          @click="clearQuery"
        >
          <UiIcon name="close" />
        </button>
      </div>
      <div class="tools-categories" role="group" :aria-label="tr('工具分类')">
        <button
          id="tools-category-all"
          type="button"
          :aria-pressed="category === 'all'"
          @click="category = 'all'"
        >
          {{ tr('全部工具') }} <span>{{ tools.length }}</span>
        </button>
        <button
          v-for="group in groups"
          :id="'tools-category-' + group.id"
          :key="group.id"
          type="button"
          :aria-pressed="category === group.id"
          @click="category = group.id"
        >
          {{ tr(group.title) }} <span>{{ group.tools.length }}</span>
        </button>
      </div>
      <div class="tools-controls">
        <span class="muted" role="status">{{
          loading ? tr('正在读取…') : tr('共 {count} 个工具', { count: visibleCount })
        }}</span>
        <div class="tools-actions">
          <button
            id="tools-expand-all"
            type="button"
            :disabled="!visible.length || allOpen"
            @click="setExpanded(visible.map((g) => g.id))"
          >
            {{ tr('展开全部') }}
          </button>
          <button
            id="tools-collapse-all"
            type="button"
            :disabled="!anyOpen"
            @click="setExpanded([])"
          >
            {{ tr('收起全部') }}
          </button>
        </div>
      </div>
      <p v-if="error" class="feedback bad" role="alert">{{ error }}</p>
      <div v-if="visible.length" class="tool-groups">
        <section
          v-for="group in visible"
          :key="group.id"
          class="tool-group"
          :data-tool-group="group.id"
        >
          <h3>
            <button
              :id="'tool-group-toggle-' + group.id"
              class="tool-group-toggle"
              type="button"
              :aria-expanded="openGroups.has(group.id)"
              :aria-controls="'tool-group-panel-' + group.id"
              @click="toggleGroup(group.id)"
            >
              <UiIcon
                name="chevron"
                :size="16"
                class="group-chevron"
                :class="{ expanded: openGroups.has(group.id) }"
              />
              <UiIcon :name="group.icon" :size="20" />
              <span class="group-title">{{ tr(group.title) }}</span
              ><span class="badge">{{ group.tools.length }}</span>
              <span class="group-dispatched">{{
                tr('{enabled}/{total} 已下发', {
                  enabled: group.tools.filter((t) => t.enabled).length,
                  total: group.tools.length,
                })
              }}</span>
            </button>
          </h3>
          <div
            v-show="openGroups.has(group.id)"
            :id="'tool-group-panel-' + group.id"
            role="region"
            :aria-labelledby="'tool-group-toggle-' + group.id"
          >
            <div v-for="tool in group.tools" :key="tool.name" class="tool-row">
              <div class="tool-identity">
                <span class="tool-title">{{ tr(tool.title) }}</span>
                <code>{{ tool.name }}</code>
                <div
                  v-if="
                    tool.required ||
                    tool.max_bytes ||
                    ['read_image', 'image_reasoning', 'run_command'].includes(tool.name)
                  "
                  class="tool-note"
                >
                  <span v-if="tool.required" class="badge">{{ tr('协议必需') }}</span>
                  <span v-else-if="tool.max_bytes">{{ tr('公网 HTTP/HTTPS，最大 20 MB') }}</span>
                  <span v-else-if="['read_image', 'image_reasoning'].includes(tool.name)">{{
                    tr('需要相应模型的视觉能力')
                  }}</span>
                  <span v-else-if="tool.name === 'run_command'">{{
                    tr('需要服务已配置命令执行器')
                  }}</span>
                </div>
              </div>
              <label class="check tool-dispatch">
                <input
                  :id="'tool-dispatch-' + tool.name"
                  type="checkbox"
                  :checked="tool.enabled"
                  :disabled="tool.required || busy || loading"
                  :aria-label="tr('下发') + ' ' + tool.name"
                  @change="toggle(tool, $event.target.checked)"
                />{{ tool.enabled ? tr('已下发') : tr('未下发') }}
              </label>
            </div>
          </div>
        </section>
      </div>
      <div v-else-if="!loading && !error" class="tools-empty">
        <UiIcon name="search" :size="28" />
        <p>{{ filtering ? tr('未找到匹配的工具') : tr('暂无工具') }}</p>
        <button v-if="filtering" type="button" @click="resetFilters">{{ tr('重置筛选') }}</button>
      </div>
    </div>
  </section>
</template>
<style scoped>
.card-head h2 {
  display: flex;
  align-items: center;
  gap: 9px;
}
.tools-body {
  display: grid;
  gap: 16px;
}
.tools-search {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 3px 10px 3px 14px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--field);
  color: var(--muted);
}
.tools-search:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}
.tools-search input {
  border: 0;
  background: transparent;
  box-shadow: none;
  padding: 10px 0;
}
.tools-search input::-webkit-search-cancel-button {
  display: none;
}
.tools-search > svg {
  flex-shrink: 0;
}
.tools-categories,
.tools-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tools-categories button {
  background: transparent;
  font-size: 14px;
  min-height: 36px;
}
.tools-categories button[aria-pressed='true'] {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--accent-border);
}
.tools-categories button span {
  color: var(--muted);
  font-size: 13px;
}
.tools-controls {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
}
.tools-controls .muted {
  font-size: 13px;
}
.tools-actions button {
  padding: 6px 10px;
}
.tool-groups {
  display: grid;
  gap: 10px;
}
.tool-group {
  border: 1px solid var(--line);
  border-radius: 9px;
  overflow: hidden;
}
.tool-group h3 {
  margin: 0;
}
.tool-group-toggle {
  width: 100%;
  justify-content: flex-start;
  gap: 10px;
  padding: 16px;
  border: 0;
  border-radius: 0;
  background: var(--raised);
  font-size: 15px;
}
.tool-group-toggle:focus-visible {
  outline-offset: -3px;
}
.tool-group-toggle > svg {
  flex-shrink: 0;
  color: var(--muted);
}
.group-chevron {
  transition: transform 0.15s;
}
.group-chevron.expanded {
  transform: rotate(90deg);
}
.group-title {
  min-width: 0;
  text-align: left;
}
.group-dispatched {
  margin-left: auto;
  font-size: 13px;
  font-weight: 400;
  color: var(--muted);
  white-space: nowrap;
}
.tool-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 16px 20px;
  border-top: 1px solid var(--line);
}
.tool-identity {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.tool-title {
  font-size: 15px;
  font-weight: 600;
}
.tool-identity code {
  font-size: 13px;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.tool-note {
  font-size: 13px;
  line-height: 1.6;
  color: var(--muted);
}
.tool-dispatch {
  min-height: 36px;
  font-size: 14px;
  cursor: pointer;
}
.tools-empty {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 28px 12px;
  color: var(--muted);
  text-align: center;
}
.tools-empty p {
  margin: 0;
}
@media (max-width: 560px) {
  .tools-body {
    padding: 14px;
  }
  .tool-group-toggle {
    padding: 13px 10px;
    gap: 7px;
    flex-wrap: wrap;
  }
  .group-dispatched {
    width: 100%;
    margin-left: 47px;
    text-align: left;
  }
  .tool-row {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
    padding: 14px;
  }
  .tool-dispatch {
    justify-self: start;
  }
}
</style>
