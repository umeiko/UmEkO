<script setup>
import { computed, ref } from 'vue';
import UiIcon from './UiIcon.vue';
import { skillTree } from './skillTree.js';
const props = defineProps({ files: { type: Array, default: () => [] }, selected: String });
const emit = defineEmits(['select']);
const expanded = ref(new Set(['scripts', 'references', 'assets']));
const rows = computed(() => {
  const result = [];
  function walk(nodes, depth = 0) {
    for (const node of nodes) {
      result.push({ ...node, depth });
      if (expanded.value.has(node.path)) walk(node.children, depth + 1);
    }
  }
  walk(skillTree(props.files));
  return result;
});
function choose(node) {
  if (!node.directory) return emit('select', node.file);
  const next = new Set(expanded.value);
  if (next.has(node.path)) next.delete(node.path);
  else next.add(node.path);
  expanded.value = next;
}
</script>
<template>
  <div class="skill-file-tree" role="tree">
    <button
      v-for="node in rows"
      :key="node.path"
      type="button"
      role="treeitem"
      :aria-level="node.depth + 1"
      :aria-expanded="node.directory ? expanded.has(node.path) : undefined"
      :aria-selected="!node.directory && selected === (node.file?.name || node.path)"
      :class="{
        active: !node.directory && selected === node.file?.name,
        'skill-file-button': !node.directory,
      }"
      :style="{ '--skill-depth': node.depth }"
      :title="node.path"
      :data-skill-path="node.path"
      @click="choose(node)"
    >
      <UiIcon
        v-if="node.directory"
        name="chevron"
        :size="14"
        :class="{ expanded: expanded.has(node.path) }"
      />
      <span v-else class="skill-tree-spacer" />
      <UiIcon
        :name="node.directory ? 'folder' : node.name.endsWith('.py') ? 'code' : 'file'"
        :size="19"
      />
      <span class="skill-tree-name" :class="{ 'skill-file-name': !node.directory }">{{
        node.name
      }}</span>
    </button>
  </div>
</template>
<style scoped>
.skill-file-tree {
  display: grid;
  gap: 2px;
}
.skill-file-tree button {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 7px;
  min-height: 34px;
  width: 100%;
  padding: 5px 8px 5px calc(6px + var(--skill-depth) * 18px);
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--text);
  font-size: 14px;
}
.skill-file-tree button:hover,
.skill-file-tree button.active {
  background: var(--hover, var(--bg));
}
.skill-file-tree svg,
.skill-tree-spacer {
  flex: none;
}
.skill-tree-spacer {
  width: 14px;
}
.skill-tree-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.expanded {
  transform: rotate(90deg);
}
</style>
