<script setup>
import { ref, computed, onMounted } from 'vue';
import { api, notify } from '../state.js';
import { encode } from '../../shared/api.js';
import { useAdminI18n } from '../../shared/adminI18n.js';
const { tr } = useAdminI18n();
const tools = ref([]),
  loading = ref(true),
  busy = ref(false),
  error = ref(''),
  query = ref('');
const visible = computed(() =>
  tools.value.filter((t) =>
    `${t.name} ${t.title} ${t.title_en}`.toLowerCase().includes(query.value.toLowerCase()),
  ),
);
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
      </h2>
      <button @click="load" :disabled="loading || busy">{{ tr('刷新') }}</button>
    </header>
    <div class="card-body stack">
      <p class="muted">
        {{
          tr(
            '控制平台主 Agent 和子 Agent 的工具下发。用户默认跟随全局设置，也可在用户管理中单独授权。模型能力和服务配置仍须满足工具要求。',
          )
        }}
      </p>
      <input v-model="query" :aria-label="tr('搜索工具')" :placeholder="tr('搜索工具')" />
      <p class="muted">
        {{
          tr(
            '保存后下一轮调用重新加载；已撤销的工具会在执行时拒绝。机器任务答案提交是协议必需能力，仅在机器任务中提供。',
          )
        }}
      </p>
      <p v-if="error" class="feedback bad" role="alert">{{ error }}</p>
    </div>
    <div class="table-wrap">
      <table v-if="tools.length">
        <thead>
          <tr>
            <th>{{ tr('工具') }}</th>
            <th>{{ tr('工具名称') }}</th>
            <th>{{ tr('说明') }}</th>
            <th>{{ tr('下发') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="tool in visible" :key="tool.name">
            <td>{{ tr(tool.title) }}</td>
            <td>
              <code>{{ tool.name }}</code>
            </td>
            <td>
              <span v-if="tool.required" class="badge">{{ tr('协议必需') }}</span
              ><span v-else-if="tool.max_bytes">{{ tr('公网 HTTP/HTTPS，最大 20 MB') }}</span
              ><span v-else-if="['read_image', 'image_reasoning'].includes(tool.name)">{{
                tr('需要相应模型的视觉能力')
              }}</span
              ><span v-else-if="tool.name === 'run_command'">{{
                tr('需要服务已配置命令执行器')
              }}</span>
            </td>
            <td>
              <label class="check"
                ><input
                  :id="'tool-dispatch-' + tool.name"
                  type="checkbox"
                  :checked="tool.enabled"
                  :disabled="tool.required || busy || loading"
                  :aria-label="tr('下发') + ' ' + tool.name"
                  @change="toggle(tool, $event.target.checked)"
                />{{ tool.enabled ? tr('已下发') : tr('未下发') }}</label
              >
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="card-body muted">{{ loading ? tr('正在读取…') : tr('暂无工具') }}</p>
    </div>
  </section>
</template>
