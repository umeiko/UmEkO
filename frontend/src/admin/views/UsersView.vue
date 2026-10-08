<script setup>
import { ref, onMounted } from 'vue';
import { api, ask, confirm, notify, run, sessionsFor } from '../state.js';
import UiIcon from '../../shared/UiIcon.vue';
import { date, encode } from '../../shared/api.js';
const users = ref([]),
  error = ref(''),
  loading = ref(true);
async function load() {
  try {
    users.value = await api('GET', '/admin/v1/users');
    error.value = '';
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
async function create() {
  const r = await ask('新建用户', [
    { name: 'username', label: '用户名', required: true },
    { name: 'password', label: '密码', type: 'password', required: true },
    {
      name: 'role',
      label: '角色',
      value: 'user',
      options: [
        { value: 'user', label: '用户' },
        { value: 'admin', label: '管理员' },
      ],
    },
  ]);
  if (!r) return;
  await run(async () => {
    await api('POST', '/admin/v1/users', r);
    await load();
    notify('用户已创建');
  });
}
async function password(u) {
  const r = await ask('重置 ' + u.username + ' 的密码', [
    { name: 'password', label: '新密码', type: 'password', required: true },
  ]);
  if (!r) return;
  await run(async () => {
    await api('PUT', `/admin/v1/users/${encode(u.id)}/password`, r);
    notify('密码已重置');
  });
}
async function role(u) {
  const r = await ask('修改用户角色', [
    {
      name: 'role',
      label: '角色',
      value: u.role,
      options: [
        { value: 'user', label: '用户' },
        { value: 'admin', label: '管理员' },
      ],
    },
  ]);
  if (!r) return;
  await run(async () => {
    await api('PUT', `/admin/v1/users/${encode(u.id)}/role`, r);
    await load();
    notify('角色已更新');
  });
}
async function remove(u) {
  if (!(await confirm('删除用户', `永久删除“${u.username}”及其全部会话、附件和历史记录？`))) return;
  await run(async () => {
    await api('DELETE', `/admin/v1/users/${encode(u.id)}`);
    await load();
    notify('用户已删除');
  });
}
</script>
<template>
  <section id="page-users" class="card">
    <header class="card-head">
      <h2>
        用户账号 <span class="badge">{{ users.length }}</span>
      </h2>
      <button class="primary" @click="create"><UiIcon name="plus" :size="15" />新建用户</button>
    </header>
    <p v-if="error" class="feedback bad card-body">
      {{ error }} <button @click="load">重试</button>
    </p>
    <div class="table-wrap">
      <table v-if="users.length">
        <thead>
          <tr>
            <th>用户名</th>
            <th>角色</th>
            <th>会话数</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>
              <strong>{{ u.username }}</strong>
            </td>
            <td>
              <span class="badge" :class="{ on: u.role === 'admin' }">{{
                u.role === 'admin' ? '管理员' : '用户'
              }}</span>
            </td>
            <td>{{ u.session_count }}</td>
            <td>{{ date(u.created_at) }}</td>
            <td>
              <div class="row">
                <button @click="sessionsFor(u)">查看会话</button
                ><button @click="password(u)">重置密码</button
                ><button @click="role(u)">修改角色</button
                ><button class="danger" @click="remove(u)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">{{ loading ? '正在读取…' : '暂无用户' }}</div>
    </div>
  </section>
</template>
