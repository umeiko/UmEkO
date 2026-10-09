<script setup>
import { useAdminI18n } from '../../shared/adminI18n.js';
const { tr, date } = useAdminI18n();
import { ref, onMounted } from 'vue';
import { api, ask, confirm, notify, run, sessionsFor } from '../state.js';
import UiIcon from '../../shared/UiIcon.vue';
import { encode } from '../../shared/api.js';
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
  const r = await ask(tr('新建用户'), [
    { name: 'username', label: tr('用户名'), required: true },
    { name: 'password', label: tr('密码'), type: 'password', required: true },
    {
      name: 'role',
      label: tr('角色'),
      value: 'user',
      options: [
        { value: 'user', label: tr('用户') },
        { value: 'admin', label: tr('管理员') },
      ],
    },
  ]);
  if (!r) return;
  await run(async () => {
    await api('POST', '/admin/v1/users', r);
    await load();
    notify(tr('用户已创建'));
  });
}
async function password(u) {
  const r = await ask(tr('重置 ') + u.username + tr(' 的密码'), [
    { name: 'password', label: tr('新密码'), type: 'password', required: true },
  ]);
  if (!r) return;
  await run(async () => {
    await api('PUT', `/admin/v1/users/${encode(u.id)}/password`, r);
    notify(tr('密码已重置'));
  });
}
async function role(u) {
  const r = await ask(tr('修改用户角色'), [
    {
      name: 'role',
      label: tr('角色'),
      value: u.role,
      options: [
        { value: 'user', label: tr('用户') },
        { value: 'admin', label: tr('管理员') },
      ],
    },
  ]);
  if (!r) return;
  await run(async () => {
    await api('PUT', `/admin/v1/users/${encode(u.id)}/role`, r);
    await load();
    notify(tr('角色已更新'));
  });
}
async function remove(u) {
  if (
    !(await confirm(
      tr('删除用户'),
      tr('永久删除“{p0}”及其全部会话、附件和历史记录？', { p0: u.username }),
    ))
  )
    return;
  await run(async () => {
    await api('DELETE', `/admin/v1/users/${encode(u.id)}`);
    await load();
    notify(tr('用户已删除'));
  });
}
</script>
<template>
  <section id="page-users" class="card">
    <header class="card-head">
      <h2>
        {{ tr('用户账号') }} <span class="badge">{{ users.length }}</span>
      </h2>
      <button class="primary" @click="create">
        <UiIcon name="plus" :size="15" />{{ tr('新建用户') }}
      </button>
    </header>
    <p v-if="error" class="feedback bad card-body">
      {{ error }} <button @click="load">{{ tr('重试') }}</button>
    </p>
    <div class="table-wrap">
      <table v-if="users.length">
        <thead>
          <tr>
            <th>{{ tr('用户名') }}</th>
            <th>{{ tr('角色') }}</th>
            <th>{{ tr('会话数') }}</th>
            <th>{{ tr('创建时间') }}</th>
            <th>{{ tr('操作') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>
              <strong>{{ u.username }}</strong>
            </td>
            <td>
              <span class="badge" :class="{ on: u.role === 'admin' }">{{
                u.role === 'admin' ? tr('管理员') : tr('用户')
              }}</span>
            </td>
            <td>{{ u.session_count }}</td>
            <td>{{ date(u.created_at) }}</td>
            <td>
              <div class="row">
                <button @click="sessionsFor(u)">{{ tr('查看会话') }}</button
                ><button @click="password(u)">{{ tr('重置密码') }}</button
                ><button @click="role(u)">{{ tr('修改角色') }}</button
                ><button class="danger" @click="remove(u)">{{ tr('删除') }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">{{ loading ? tr('正在读取…') : tr('暂无用户') }}</div>
    </div>
  </section>
</template>
