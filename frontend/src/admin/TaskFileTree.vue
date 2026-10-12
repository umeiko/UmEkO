<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue';
import { api } from './state.js';
import { bytes, encode } from '../shared/api.js';
import { useAdminI18n } from '../shared/adminI18n.js';
import UiIcon from '../shared/UiIcon.vue';
import HelpTip from '../shared/HelpTip.vue';
import TaskFileNode from './TaskFileNode.vue';
const { tr, date } = useAdminI18n();
const props = defineProps({ taskId: String, active: Boolean, revision: Number });
const manifest = ref(null),
  loading = ref(false),
  error = ref('');
let sequence = 0;
async function load() {
  if (!props.taskId || !props.active || loading.value) return;
  const seq = ++sequence;
  loading.value = true;
  error.value = '';
  try {
    const result = await api('GET', `/admin/v1/tasks/${encode(props.taskId)}/files`);
    if (seq === sequence) manifest.value = result;
  } catch (e) {
    if (seq === sequence) error.value = e.message;
  } finally {
    if (seq === sequence) loading.value = false;
  }
}
watch(
  () => [props.taskId, props.revision],
  () => {
    ++sequence;
    manifest.value = null;
    error.value = '';
    loading.value = false;
    load();
  },
  { immediate: true },
);
watch(
  () => props.active,
  (active) => {
    if (active && !manifest.value) load();
  },
);
onBeforeUnmount(() => ++sequence);
const source = computed(
  () =>
    ({
      snapshot: tr('任务结束时快照'),
      current: tr('当前目录'),
      records: tr('历史元数据清单'),
      submitted: tr('提交文件清单'),
    })[manifest.value?.source] || '',
);
</script>
<template>
  <section class="task-file-tree">
    <div class="row between">
      <div class="heading-line">
        <h3>{{ tr('会话文件树') }}</h3>
        <HelpTip
          :text="
            tr(
              '仅展示 workspace、attachments、generate 的名称、相对路径、大小和修改时间，不读取、预览或下载文件内容。新任务结束后保存目录快照，文件移除后仍可查看元数据，随任务保留期清理。旧任务没有快照时查看当前目录；目录已清理则只展示已有上传和产物清单，路径仅作分组。符号链接不跟随；大量或过深目录会标记记录不完整。',
            )
          "
        />
      </div>
      <button :disabled="loading" @click="load">
        <UiIcon name="refresh" :size="16" />{{ tr('刷新文件树') }}
      </button>
    </div>
    <p v-if="error" class="feedback bad" role="alert">
      {{ error }} <button @click="load">{{ tr('重试') }}</button>
    </p>
    <div v-if="loading && !manifest" class="empty-state" role="status">{{ tr('正在读取…') }}</div>
    <template v-if="manifest">
      <div class="row file-tree-meta">
        <span class="badge">{{ source }}</span
        ><span class="muted"
          >{{ tr('{count} 个文件', { count: manifest.file_count }) }} ·
          {{ tr('{count} 个目录', { count: manifest.directory_count }) }} ·
          {{ bytes(manifest.total_size) }}</span
        ><span v-if="!manifest.complete" class="badge">{{ tr('记录不完整') }}</span>
      </div>
      <p class="muted file-tree-time">{{ tr('记录时间') }} · {{ date(manifest.captured_at) }}</p>
      <div class="file-tree-scroll">
        <div class="file-tree-columns">
          <span>{{ tr('名称') }}</span
          ><span>{{ tr('大小') }}</span
          ><span class="file-tree-date-column">{{ tr('修改时间') }}</span>
        </div>
        <ul class="metadata-tree">
          <TaskFileNode v-for="node in manifest.roots" :key="node.path" :node="node" />
        </ul>
      </div>
      <div v-if="!manifest.roots.length" class="empty-state">{{ tr('暂无文件元数据') }}</div>
    </template>
  </section>
</template>
<style scoped>
h3 {
  font-size: 16px;
  margin: 0;
}
.file-tree-meta {
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
  font-size: 14px;
}
.file-tree-time {
  font-size: 13px;
  margin: 12px 0;
}
.file-tree-scroll {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px;
  overflow: auto;
  max-height: 520px;
}
.metadata-tree {
  list-style: none;
  padding: 0;
  margin: 4px 0 0;
}
.file-tree-columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 86px 170px;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid var(--line);
  color: var(--ink-secondary);
  font-size: 13px;
}
.file-tree-columns span:not(:first-child) {
  text-align: right;
}
@media (max-width: 600px) {
  .file-tree-columns {
    grid-template-columns: minmax(0, 1fr) 70px;
    gap: 6px;
  }
  .file-tree-date-column {
    display: none;
  }
}
</style>
