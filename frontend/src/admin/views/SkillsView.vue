<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { codeHtml } from '../../shared/markdown.js';
import MarkdownDocument from '../../shared/MarkdownDocument.vue';
import { api, run, ask, confirm, notify } from '../state.js';
import { encode } from '../../shared/api.js';
import HelpTip from '../../shared/HelpTip.vue';
import UiIcon from '../../shared/UiIcon.vue';
import UiModal from '../../shared/UiModal.vue';
import CodeEditor from '../../shared/CodeEditor.vue';
const packs = ref([]),
  active = ref(''),
  selected = ref(null),
  content = ref(''),
  original = ref(''),
  preview = ref(false),
  busy = ref(false),
  error = ref(''),
  testOpen = ref(false),
  testBusy = ref(false),
  testOutput = ref('');
let sequence = 0;
const pack = computed(() => packs.value.find((p) => p.name === active.value));
const dirty = computed(() => content.value !== original.value);
const language = computed(() => {
  const ext = selected.value?.name.split('.').at(-1).toLowerCase();
  return (
    { py: 'python', md: 'markdown', markdown: 'markdown', json: 'json', yaml: 'yaml', yml: 'yaml' }[
      ext
    ] || 'plaintext'
  );
});
const highlighted = computed(() => codeHtml(content.value, language.value));
const isMarkdown = computed(() => /\.(md|markdown)$/i.test(selected.value?.name || ''));
const files = (p) => [
  ...(p.md ? [{ name: p.md, kind: 'md' }] : []),
  ...p.scripts.map((f) => ({ ...f, kind: 'script' })),
  ...p.members.map((f) => ({ ...f, kind: 'member' })),
];
async function load() {
  try {
    packs.value = (await api('GET', '/admin/v1/skill-library')).packs;
    error.value = '';
  } catch (e) {
    error.value = e.message;
  }
}
function beforeUnload(e) {
  if (dirty.value) {
    e.preventDefault();
    e.returnValue = '';
  }
}
onMounted(() => {
  load();
  window.addEventListener('beforeunload', beforeUnload);
});
onBeforeUnmount(() => {
  sequence++;
  window.removeEventListener('beforeunload', beforeUnload);
});
async function discard() {
  return !dirty.value || (await confirm('未保存的修改', '放弃当前文件的修改？'));
}
async function choose(p) {
  if (!(await discard())) return;
  active.value = active.value === p.name ? '' : p.name;
  selected.value = null;
  content.value = '';
  original.value = '';
  sequence++;
}
async function open(p, kind, name) {
  if (!(await discard())) return;
  const seq = ++sequence;
  try {
    const url =
      kind === 'md'
        ? `/admin/v1/skill-source/${encode(name)}`
        : `/admin/v1/skill-scripts/${encode(p.name)}/${encode(name)}`;
    const data = await api('GET', url);
    if (seq !== sequence) return;
    active.value = p.name;
    selected.value = { pack: p.name, kind, name };
    content.value = data.content;
    original.value = data.content;
    preview.value = /\.(md|markdown)$/i.test(name);
  } catch (e) {
    notify(e.message, true);
  }
}
async function save() {
  if (!selected.value || busy.value) return;
  busy.value = true;
  await run(async () => {
    const f = selected.value,
      body = { content: content.value };
    if (f.kind === 'md') {
      await api('PUT', `/admin/v1/skill-source/${encode(f.name)}`, body);
      await api('PUT', `/admin/v1/default-skills/${encode(f.name)}`, body);
    } else {
      await api(
        'PUT',
        `/admin/v1/${f.kind === 'script' ? 'skill-scripts' : 'skill-members'}/${encode(f.pack)}/${encode(f.name)}`,
        body,
      );
    }
    original.value = content.value;
    await load();
    notify('文件已保存');
  });
  busy.value = false;
}
async function create(kind = 'md') {
  if (!(await discard())) return;
  if (kind !== 'md' && !active.value) {
    notify('请先选择一个技能', true);
    return;
  }
  const result = await ask(
    kind === 'md' ? '新建技能' : kind === 'script' ? '新建脚本' : '新建成员文件',
    [
      {
        name: 'name',
        label: '文件名',
        required: true,
        placeholder: kind === 'md' ? 'my-skill' : kind === 'script' ? 'my_script.py' : 'notes.md',
      },
    ],
  );
  if (!result) return;
  let name = result.name.trim();
  if (kind === 'md' && !name.endsWith('.md')) name += '.md';
  if (!/^[a-zA-Z0-9_-]+\.md$/.test(name) && kind === 'md') {
    notify('技能名称请使用字母、数字、下划线和连字符', true);
    return;
  }
  if (kind === 'script' && !/^[\w-]+\.py$/.test(name)) {
    notify('脚本名请使用 xxx.py，不带路径', true);
    return;
  }
  if (
    kind === 'member' &&
    (!/^[\w.-]+\.(md|markdown|json|ya?ml|txt|csv)$/i.test(name) || name.includes('..'))
  ) {
    notify('成员文件须为 .md/.json/.yaml/.txt/.csv，不带路径', true);
    return;
  }
  const pname = kind === 'md' ? name.slice(0, -3) : active.value;
  if (
    (kind === 'md' && packs.value.some((p) => p.md === name)) ||
    (kind === 'script' && pack.value?.scripts.some((f) => f.name === name)) ||
    (kind === 'member' && pack.value?.members.some((f) => f.name === name))
  ) {
    notify('文件已存在，请选择它进行编辑', true);
    return;
  }
  await run(async () => {
    const template =
      kind === 'script'
        ? (await api('GET', '/admin/v1/skill-scripts-template')).content
        : kind === 'md'
          ? `---\nname: ${pname}\ndescription: 说明技能适用的场景与用途\n---\n\n# ${pname}\n\n在这里编写执行步骤和输出要求。\n`
          : '在这里编写内容。\n';
    active.value = pname;
    selected.value = { pack: pname, kind, name };
    content.value = template;
    original.value = '';
    preview.value = false;
  });
}
async function dispatch(p) {
  await run(async () => {
    if (p.imported) await api('POST', `/admin/v1/default-skills/${encode(p.md)}/toggle`);
    else await api('POST', `/admin/v1/default-skills/import/${encode(p.md)}`);
    await load();
    notify(p.enabled ? '已停用下发' : '已启用下发');
  });
}
async function remove() {
  const f = selected.value;
  if (!f || !(await confirm('删除技能文件', `永久删除“${f.pack}/${f.name}”？`))) return;
  await run(async () => {
    if (f.kind === 'md') {
      await api('DELETE', `/admin/v1/skill-source/${encode(f.name)}`);
      await api('DELETE', `/admin/v1/default-skills/${encode(f.name)}`).catch((e) => {
        if (!e.message.includes('不存在')) throw e;
      });
    } else
      await api(
        'DELETE',
        `/admin/v1/${f.kind === 'script' ? 'skill-scripts' : 'skill-members'}/${encode(f.pack)}/${encode(f.name)}`,
      );
    selected.value = null;
    content.value = '';
    original.value = '';
    await load();
    notify('文件已删除');
  });
}
async function test() {
  if (dirty.value) {
    notify('请先保存脚本，再运行测试', true);
    return;
  }
  const result = await ask('测试脚本', [
    {
      name: 'args',
      label: '参数（JSON 对象）',
      type: 'textarea',
      rows: 4,
      value: '{}',
      required: true,
    },
    { name: 'timeout', label: '超时秒数（1–30）', type: 'number', min: 1, value: 10 },
  ]);
  if (!result) return;
  await run(async () => {
    JSON.parse(result.args);
    const timeout = Number(result.timeout);
    if (!Number.isInteger(timeout) || timeout < 1 || timeout > 30)
      throw new Error('超时请输入 1–30 之间的整数');
    testOpen.value = true;
    testBusy.value = true;
    testOutput.value = '正在执行…';
    try {
      const f = selected.value,
        r = await api('POST', `/admin/v1/skill-scripts/${encode(f.pack)}/${encode(f.name)}/test`, {
          args: result.args,
          timeout,
        });
      testOutput.value =
        typeof r.output === 'string' ? r.output : JSON.stringify(r.output, null, 2);
    } catch (e) {
      testOutput.value = e.message;
    } finally {
      testBusy.value = false;
    }
  });
}
async function upload(files, into = false) {
  if (!(await discard())) return;
  if (into && !active.value) {
    notify('请先选择一个技能', true);
    return;
  }
  for (const file of files)
    await run(async () => {
      const name = file.name,
        body = { content: await file.text() };
      if (!into || name === pack.value?.md) {
        if (!name.endsWith('.md')) throw new Error('新建技能 只接受 .md 文件');
        await api('PUT', `/admin/v1/skill-source/${encode(name)}`, body);
        await api('PUT', `/admin/v1/default-skills/${encode(name)}`, body);
      } else {
        const type = name.endsWith('.py') ? 'skill-scripts' : 'skill-members';
        await api('PUT', `/admin/v1/${type}/${encode(active.value)}/${encode(name)}`, body);
      }
      notify('已导入 ' + name);
    });
  await load();
}
</script>
<template>
  <section id="page-dskills" class="card">
    <header class="card-head">
      <div class="heading-line">
        <h2>技能库</h2>
        <span class="badge">{{ packs.length }}</span>
        <HelpTip
          text="主文件定义技能，同名目录保存脚本和成员文件。保存主文件会同步下发副本；开关控制是否下发。可拖入文件或使用导入按钮上传。"
        />
      </div>
      <div class="row">
        <label class="skill-import"
          ><UiIcon name="upload" :size="18" />导入技能
          <input
            type="file"
            accept=".md"
            multiple
            @change="
              (e) => {
                upload([...e.target.files]);
                e.target.value = '';
              }
            "
          />
        </label>
        <button class="primary" @click="create('md')">
          <UiIcon name="plus" :size="18" />新建技能
        </button>
      </div>
    </header>
    <p v-if="error" class="feedback bad card-body">{{ error }}</p>
    <div class="editor-layout">
      <aside
        class="editor-tree"
        aria-label="技能文件树"
        @dragover.prevent
        @drop.prevent="upload([...$event.dataTransfer.files])"
      >
        <div v-for="p in packs" :key="p.name" class="skill-pack">
          <button
            class="pack-button"
            :class="{ active: active === p.name }"
            :aria-expanded="active === p.name"
            :title="p.name"
            @click="choose(p)"
          >
            <span class="pack-title"
              ><UiIcon
                class="pack-chevron"
                :class="{ expanded: active === p.name }"
                name="chevron"
                :size="16"
              /><UiIcon name="folder" :size="20" /><strong class="pack-name">{{
                p.name
              }}</strong></span
            >
            <span class="pack-meta"
              ><span class="skill-status" :class="{ enabled: p.imported && p.enabled }">{{
                p.imported ? (p.enabled ? '下发中' : '已停用') : '未下发'
              }}</span
              ><span>{{ files(p).length }} 个文件</span><span v-if="p.stale">源已更新</span></span
            >
          </button>
          <div
            v-if="active === p.name"
            class="skill-pack-content"
            @dragover.prevent.stop
            @drop.prevent.stop="upload([...$event.dataTransfer.files], true)"
          >
            <div class="tree-files">
              <button
                v-for="f in files(p)"
                :key="f.name"
                class="skill-file-button"
                :class="{ active: selected?.pack === p.name && selected?.name === f.name }"
                :aria-current="
                  selected?.pack === p.name && selected?.name === f.name ? 'true' : undefined
                "
                :title="f.name"
                @click="open(p, f.kind, f.name)"
              >
                <UiIcon :name="f.kind === 'script' ? 'code' : 'file'" :size="20" /><span
                  class="skill-file-name"
                  >{{ f.name }}</span
                >
              </button>
            </div>
            <div class="skill-pack-actions">
              <button v-if="p.md" class="dispatch-button" @click="dispatch(p)">
                {{ p.enabled ? '停用下发' : '启用下发' }}
              </button>
              <button @click="create('script')"><UiIcon name="plus" :size="16" />脚本</button>
              <button @click="create('member')"><UiIcon name="plus" :size="16" />文件</button>
              <label class="skill-import"
                ><UiIcon name="upload" :size="16" />导入文件<input
                  type="file"
                  multiple
                  @change="
                    (e) => {
                      upload([...e.target.files], true);
                      e.target.value = '';
                    }
                  "
              /></label>
            </div>
          </div>
        </div>
        <div v-if="!packs.length" class="empty-state">暂无技能</div>
      </aside>
      <div v-if="selected" class="code-editor">
        <header class="editor-toolbar">
          <div class="editor-path grow" :title="selected.pack + '/' + selected.name">
            <span>{{ selected.pack }}</span
            ><strong>{{ selected.name }}</strong>
          </div>
          <span v-if="dirty" class="editor-dirty">● 未保存</span>
          <div class="editor-modes" role="group" aria-label="文件显示方式">
            <button id="skill-edit" :aria-pressed="!preview" @click="preview = false">编辑</button>
            <button id="skill-preview" :aria-pressed="preview" @click="preview = true">预览</button>
          </div>
          <button v-if="selected.kind === 'script'" @click="test">
            <UiIcon name="terminal" :size="18" />测试
          </button>
          <button
            class="danger"
            title="删除文件"
            aria-label="删除文件"
            @click="remove"
            :disabled="busy"
          >
            <UiIcon name="trash" :size="18" />
          </button>
          <button class="primary" @click="save" :disabled="busy">
            <UiIcon name="save" :size="18" />{{ busy ? '正在保存…' : '保存' }}
          </button>
        </header>
        <MarkdownDocument
          v-if="preview && isMarkdown"
          class="skill-document"
          :content="content"
          skill
        />
        <pre
          v-else-if="preview"
          class="editor-code-preview"
        ><code class="hljs" v-html="highlighted"></code></pre>
        <CodeEditor
          v-else
          id="sk-content"
          v-model="content"
          :language="language"
          :disabled="busy"
        />
      </div>
      <div v-else class="empty-state skill-empty">
        <UiIcon name="skills" :size="32" /><strong>{{
          active ? '选择文件开始查看' : '选择一个技能'
        }}</strong>
      </div>
    </div>
    <UiModal v-model="testOpen" title="脚本测试结果" wide :busy="testBusy">
      <pre class="json-view">{{ testOutput }}</pre>
      <template #footer
        ><button :disabled="testBusy" @click="testOpen = false">关闭</button></template
      ></UiModal
    >
  </section>
</template>
<style scoped>
.editor-layout {
  grid-template-columns: 280px minmax(0, 1fr);
}
.editor-tree {
  background: var(--sidebar);
  padding: 12px;
}
.skill-pack + .skill-pack {
  margin-top: 6px;
}
.pack-button {
  min-height: 70px;
  padding: 10px;
}
.pack-title {
  display: grid;
  grid-template-columns: 16px 20px minmax(0, 1fr);
  align-items: center;
  gap: 9px;
}
.pack-name {
  font-size: 14px;
  line-height: 1.5;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pack-chevron {
  color: var(--muted);
  transition: transform 0.15s;
}
.pack-chevron.expanded {
  transform: rotate(90deg);
}
.pack-title > :nth-child(2) {
  color: var(--accent);
}
.pack-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 8px 0 0 25px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--ink-secondary);
}
.skill-status {
  padding: 2px 6px;
  border-radius: 5px;
  border: 1px solid var(--line);
}
.skill-status.enabled {
  color: var(--success-ink);
  background: var(--success-bg);
  border-color: var(--success-border);
}
.tree-files {
  margin: 0 0 12px 18px;
  padding-left: 12px;
  border-left: 1px solid var(--line-strong);
}
.tree-files .skill-file-button {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  align-items: center;
  min-height: 38px;
  gap: 9px;
  padding: 8px;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  color: var(--ink-secondary);
}
.skill-file-button:hover {
  background: var(--hover);
  color: var(--ink);
}
.tree-files .skill-file-button.active {
  background: var(--accent-soft);
  color: var(--accent);
  box-shadow: inset 2px 0 var(--accent);
}
.skill-file-button svg {
  flex-shrink: 0;
}
.skill-file-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.skill-pack-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 8px 14px 30px;
}
.skill-pack-actions button,
.skill-pack-actions .skill-import {
  min-height: 36px;
  padding: 7px 9px;
  font-size: 13px;
}
.dispatch-button {
  width: 100%;
}
.skill-import {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 8px 12px;
  background: var(--raised);
  color: var(--ink);
  font-size: 14px;
  cursor: pointer;
}
.skill-import:hover {
  background: var(--hover);
  border-color: var(--line-strong);
}
.skill-import:focus-within {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
.skill-import input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  overflow: hidden;
}
.editor-toolbar {
  gap: 10px;
  padding: 14px 18px;
  background: var(--surface);
}
.editor-toolbar button {
  min-height: 36px;
  font-size: 14px;
}
.editor-path {
  min-width: 120px;
  display: grid;
  gap: 4px;
}
.editor-path span {
  color: var(--muted);
  font-size: 13px;
}
.editor-path strong {
  color: var(--ink);
  font-size: 15px;
  font-weight: 600;
}
.editor-path span,
.editor-path strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.editor-dirty {
  font-size: 13px;
  color: var(--accent);
}
.editor-modes {
  display: inline-flex;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--sidebar);
}
.editor-modes button {
  border: 0;
  background: transparent;
  padding: 5px 12px;
  color: var(--muted);
  min-height: 30px;
}
.editor-modes button[aria-pressed='true'] {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}
.skill-document {
  padding: 24px clamp(18px, 3vw, 36px);
  background: var(--surface);
  flex: 1;
  min-width: 0;
}
.editor-code-preview {
  padding: 24px;
  background: var(--field);
  font: 14px/1.8 var(--mono);
  white-space: pre;
  overflow-wrap: normal;
}
.editor-code-preview code {
  padding: 0;
  background: transparent;
  font: inherit;
}
.skill-empty {
  align-self: center;
  font-size: 14px;
}
@media (max-width: 760px) {
  .editor-layout {
    grid-template-columns: 1fr;
  }
  .editor-tree {
    max-height: 320px;
  }
  .editor-path {
    flex-basis: 100%;
  }
}
</style>
