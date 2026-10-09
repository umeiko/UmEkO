<script setup>
import { useAdminI18n } from '../../shared/adminI18n.js';
const { tr, date } = useAdminI18n();
import { ref, onMounted } from 'vue';
import { admin, api, run, confirm, notify } from '../state.js';
import { encode } from '../../shared/api.js';
import HelpTip from '../../shared/HelpTip.vue';
const users = ref([]),
  selected = ref(admin.sessionUser?.id || ''),
  sessions = ref([]),
  loading = ref(false),
  error = ref('');
let sequence = 0;
async function load() {
  const id = selected.value,
    seq = ++sequence;
  if (!id) {
    sessions.value = [];
    return;
  }
  loading.value = true;
  try {
    const value = await api('GET', `/admin/v1/users/${encode(id)}/sessions`);
    if (seq === sequence) {
      sessions.value = value;
      error.value = '';
    }
  } catch (e) {
    if (seq === sequence) error.value = e.message;
  } finally {
    if (seq === sequence) loading.value = false;
  }
}
onMounted(async () => {
  await run(async () => {
    users.value = await api('GET', '/admin/v1/users');
    if (!selected.value) selected.value = users.value[0]?.id || '';
    await load();
  });
});
async function evict(s) {
  if (!(await confirm(tr('卸载内存会话'), tr('卸载后会保留历史记录，正在进行的运行会停止。'))))
    return;
  await run(async () => {
    await api('POST', `/admin/v1/sessions/${encode(s.id)}/evict`);
    await load();
    notify(tr('会话已从内存卸载'));
  });
}
async function remove(s) {
  if (!(await confirm(tr('删除会话'), tr('永久删除该会话及附件、生成文件和聊天记录？')))) return;
  await run(async () => {
    await api('DELETE', `/admin/v1/sessions/${encode(s.id)}`);
    await load();
    notify(tr('会话已删除'));
  });
}
</script>
<template>
  <section id="page-sessions" class="card">
    <header class="card-head">
      <div class="heading-line">
        <h2>{{ tr('用户会话') }}</h2>
        <HelpTip :text="tr('卸载内存会话会停止当前运行，但保留历史；删除会永久清理历史和文件。')" />
      </div>
      <select v-model="selected" :aria-label="tr('选择用户')" style="width: 220px" @change="load">
        <option v-for="u in users" :key="u.id" :value="u.id">{{ u.username }}</option>
      </select>
    </header>
    <p v-if="error" class="feedback bad card-body">
      {{ error }} <button @click="load">{{ tr('重试') }}</button>
    </p>
    <div class="table-wrap">
      <table v-if="sessions.length">
        <thead>
          <tr>
            <th>{{ tr('会话') }}</th>
            <th>{{ tr('内存状态') }}</th>
            <th>{{ tr('上下文') }}</th>
            <th>{{ tr('更新时间') }}</th>
            <th>{{ tr('操作') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in sessions" :key="s.id">
            <td>
              <strong>{{ s.title || s.id.slice(-12) }}</strong>
              <p>
                <code>{{ s.id }}</code>
              </p>
            </td>
            <td>
              <span class="badge" :class="{ on: s.loaded }">{{
                s.loaded ? tr('已加载') : tr('未加载')
              }}</span>
            </td>
            <td>{{ s.context_percent == null ? '—' : s.context_percent + '%' }}</td>
            <td>{{ date(s.updated_at) }}</td>
            <td>
              <div class="row">
                <button v-if="s.loaded" @click="evict(s)">{{ tr('卸载内存') }}</button
                ><button class="danger" @click="remove(s)">{{ tr('删除') }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">{{ loading ? tr('正在读取…') : tr('当前用户没有会话') }}</div>
    </div>
  </section>
</template>
