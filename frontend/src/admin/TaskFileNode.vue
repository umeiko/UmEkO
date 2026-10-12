<script setup>
import { ref } from 'vue';
import UiIcon from '../shared/UiIcon.vue';
import { bytes } from '../shared/api.js';
import { useAdminI18n } from '../shared/adminI18n.js';
defineOptions({ name: 'TaskFileNode' });
const props = defineProps({ node: Object, depth: { type: Number, default: 0 } });
const { tr, date } = useAdminI18n();
const expanded = ref(props.depth === 0);
</script>
<template>
  <li class="metadata-node">
    <details
      v-if="node.type === 'directory'"
      :open="expanded"
      @toggle="expanded = $event.target.open"
    >
      <summary class="metadata-row" :data-path="node.path" :title="node.path">
        <UiIcon name="chevron" :size="16" class="metadata-chevron" /><UiIcon
          name="folder"
          :size="20"
        />
        <span class="metadata-name">{{ node.name }}</span
        ><span class="metadata-size">—</span>
        <time class="metadata-date">{{ date(node.modified_at) }}</time>
      </summary>
      <template v-if="expanded">
        <ul v-if="node.children?.length" class="metadata-children">
          <TaskFileNode
            v-for="(child, index) in node.children"
            :key="child.id || child.path || index"
            :node="child"
            :depth="depth + 1"
          />
        </ul>
        <p v-else class="metadata-empty">
          {{ node.truncated ? tr('子目录未完整记录') : tr('空目录') }}
        </p>
        <p v-if="node.truncated && node.children?.length" class="metadata-empty">
          {{ tr('部分条目未记录') }}
        </p>
      </template>
    </details>
    <div
      v-else
      class="metadata-row metadata-file"
      :data-path="node.path"
      tabindex="0"
      :title="node.path + '\n' + date(node.modified_at)"
    >
      <span class="metadata-spacer"></span
      ><UiIcon :name="node.type === 'link' ? 'link' : 'file'" :size="20" />
      <span class="metadata-name"
        >{{ node.name
        }}<span v-if="node.type === 'link'" class="metadata-link">{{
          tr('链接，未跟随')
        }}</span></span
      >
      <span class="metadata-size">{{ node.size == null ? '—' : bytes(node.size) }}</span
      ><time class="metadata-date">{{ date(node.modified_at) }}</time>
    </div>
  </li>
</template>
<style scoped>
.metadata-node {
  list-style: none;
  min-width: 0;
}
.metadata-row {
  display: grid;
  grid-template-columns: 16px 20px minmax(0, 1fr) 86px 170px;
  align-items: center;
  gap: 8px;
  padding: 9px 8px;
  border-radius: 6px;
  font-size: 14px;
  min-width: 0;
}
summary {
  list-style: none;
  cursor: pointer;
}
summary::-webkit-details-marker {
  display: none;
}
.metadata-row:hover {
  background: var(--accent-soft);
}
.metadata-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
details[open] > summary .metadata-chevron {
  transform: rotate(90deg);
}
.metadata-chevron {
  transition: transform 0.15s;
}
.metadata-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.metadata-size {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.metadata-date {
  color: var(--ink-secondary);
  font-size: 13px;
  text-align: right;
  white-space: nowrap;
}
.metadata-children {
  list-style: none;
  margin: 0 0 0 22px;
  padding: 0 0 0 5px;
  border-left: 1px solid var(--line);
}
.metadata-empty {
  color: var(--muted);
  margin: 6px 0 12px 52px;
  font-size: 13px;
}
.metadata-link {
  margin-left: 8px;
  color: var(--muted);
  font-size: 12px;
}
@media (max-width: 600px) {
  .metadata-row {
    grid-template-columns: 16px 20px minmax(0, 1fr) 70px;
    gap: 6px;
  }
  .metadata-date {
    display: none;
  }
}
</style>
