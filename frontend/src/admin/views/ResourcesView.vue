<script setup>
import { useAdminI18n } from '../../shared/adminI18n.js';
const { tr, locale, date } = useAdminI18n();
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { api, run, notify } from '../state.js';
import { bytes, encode } from '../../shared/api.js';
import HelpTip from '../../shared/HelpTip.vue';
import UiIcon from '../../shared/UiIcon.vue';
const snapshot = ref(null),
  tasks = ref([]),
  error = ref(''),
  loading = ref(false),
  current = computed(() => snapshot.value?.current);
let timer,
  alive = true;
async function load() {
  if (loading.value || !alive) return;
  clearTimeout(timer);
  loading.value = true;
  try {
    const [data, list] = await Promise.all([
      api('GET', '/admin/v1/resources'),
      api('GET', '/admin/v1/tasks'),
    ]);
    if (alive) {
      snapshot.value = data;
      tasks.value = list;
      error.value = '';
    }
  } catch (e) {
    if (alive) error.value = e.message;
  } finally {
    loading.value = false;
    if (alive && !document.hidden) timer = setTimeout(load, 5000);
  }
}
function visibility() {
  clearTimeout(timer);
  if (!document.hidden) load();
}
onMounted(() => {
  load();
  document.addEventListener('visibilitychange', visibility);
});
onBeforeUnmount(() => {
  alive = false;
  clearTimeout(timer);
  document.removeEventListener('visibilitychange', visibility);
});
const metrics = computed(() => {
  const c = current.value;
  if (!c) return [];
  return [
    {
      label: tr('服务器 CPU'),
      value: c.host.cpu_percent.toFixed(1) + '%',
      detail: c.host.cpu_count + tr(' 个逻辑核心'),
      field: (s) => s.host.cpu_percent,
      percent: c.host.cpu_percent,
    },
    {
      label: tr('服务器内存'),
      value: c.host.memory_percent.toFixed(1) + '%',
      detail: bytes(c.host.memory_used) + ' / ' + bytes(c.host.memory_total),
      field: (s) => s.host.memory_percent,
      percent: c.host.memory_percent,
    },
    {
      label: tr('数据所在磁盘'),
      value: c.host.disk_percent.toFixed(1) + '%',
      detail: tr('剩余 ') + bytes(c.host.disk_free),
      field: (s) => s.host.disk_percent,
      percent: c.host.disk_percent,
    },
    {
      label: tr('UMEKO 进程内存'),
      value: bytes(c.process.memory_rss),
      detail:
        'CPU ' + c.process.cpu_percent.toFixed(1) + '% · ' + c.process.threads + tr(' 个线程'),
      field: (s) => (s.process.memory_rss / s.host.memory_total) * 100,
    },
  ];
});
function points(field) {
  const values = (snapshot.value?.history || []).map(field).filter(Number.isFinite);
  return values
    .map(
      (v, i) =>
        `${(i / Math.max(1, values.length - 1)) * 300},${43 - Math.min(100, Math.max(0, v)) * 0.4}`,
    )
    .join(' ');
}
const labels = computed(() => ({
  queued: tr('排队'),
  running: tr('执行中'),
  cancelling: tr('正在停止'),
  completed: tr('已完成'),
  failed: tr('失败'),
  cancelled: tr('已取消'),
}));
async function cancel(t) {
  await run(async () => {
    await api('POST', `/admin/v1/tasks/${encode(t.id)}/cancel`);
    notify(tr('已请求停止'));
    await load();
  });
}
</script>
<template>
  <section id="page-resources" class="stack">
    <div class="row between">
      <div class="heading-line">
        <span class="badge on">{{ tr('每 5 秒更新') }}</span
        ><HelpTip
          :text="
            tr(
              '监控本机 CPU、内存、磁盘与 UMEKO 进程。模型运行在远端时，这里不显示远端 GPU 负载。切换页面或隐藏窗口会暂停刷新。',
            )
          "
        />
      </div>
      <div class="row">
        <span class="muted">{{
          current
            ? tr('更新于 ') + new Date(current.timestamp).toLocaleTimeString(locale)
            : tr('正在读取…')
        }}</span
        ><button class="icon-button" :aria-label="tr('刷新监控')" :disabled="loading" @click="load">
          <UiIcon name="refresh" />
        </button>
      </div>
    </div>
    <p v-if="error" class="feedback bad" role="alert">{{ tr('读取失败：') }}{{ error }}</p>
    <template v-if="current"
      ><div class="metrics">
        <section
          v-for="metric in metrics"
          :key="metric.label"
          class="metric"
          :class="{ warn: metric.percent >= 85 }"
        >
          <span class="muted">{{ metric.label }}</span
          ><strong>{{ metric.value }}</strong
          ><span class="muted small">{{ metric.detail }}</span
          ><svg viewBox="0 0 300 48" preserveAspectRatio="none" aria-hidden="true">
            <path d="M0 44H300" stroke="var(--line)" />
            <polyline
              :points="points(metric.field)"
              fill="none"
              stroke="var(--accent)"
              stroke-width="2"
            />
          </svg>
        </section>
      </div>
      <section class="card">
        <header class="card-head">
          <h2>{{ tr('服务运行状态') }}</h2>
          <code>PID {{ current.process.pid }}</code>
        </header>
        <div class="card-body row" style="gap: 22px">
          <span class="muted"
            >{{ tr('运行') }} {{ Math.floor(current.uptime_seconds / 3600) }} {{ tr('小时') }}
            {{ Math.floor((current.uptime_seconds % 3600) / 60) }} {{ tr('分钟') }}</span
          ><span
            >{{ tr('网页会话') }} <b>{{ current.service.chat_sessions }}</b></span
          ><span
            >{{ tr('机器工作区') }} <b>{{ current.service.machine_sessions }}</b></span
          ><span
            >{{ tr('内存会话') }} <b>{{ current.service.loaded_sessions }}</b></span
          ><span
            >{{ tr('执行中') }} <b>{{ current.service.runs.running || 0 }}</b></span
          ><span
            >{{ tr('等待') }} <b>{{ current.service.runs.queued || 0 }}</b></span
          ><span class="muted">{{ tr('数据库') }} {{ bytes(current.service.database_bytes) }}</span>
        </div>
      </section>
      <section class="card">
        <header class="card-head">
          <div class="heading-line">
            <h2>{{ tr('模型调用队列') }}</h2>
            <HelpTip
              :text="
                tr('模型并发上限可在模型与供应商页面设置。达到上限后等待，名额释放后继续执行。')
              "
            />
          </div>
        </header>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{{ tr('供应商') }}</th>
                <th>{{ tr('模型') }}</th>
                <th>{{ tr('并发上限') }}</th>
                <th>{{ tr('调用中') }}</th>
                <th>{{ tr('等待中') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in current.models" :key="m.id">
                <td>{{ m.provider }}</td>
                <td>
                  <code>{{ m.name }}</code>
                </td>
                <td>{{ m.limit || tr('不限') }}</td>
                <td>
                  <span class="badge" :class="{ on: m.active > 0 }">{{ m.active }}</span>
                </td>
                <td>{{ m.waiting }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!current.models.length" class="empty-state">{{ tr('尚未配置模型') }}</div>
        </div>
      </section>
      <section class="card">
        <header class="card-head">
          <div class="heading-line">
            <h2>{{ tr('机器调用任务') }}</h2>
            <HelpTip
              :text="
                tr(
                  '排队上限 {p0}，执行工作线程 {p1}。每个调用者最多 {p2} 个未结束任务，完成后保留 {p3} 小时。',
                  {
                    p0: current.tasks.queue_limit,
                    p1: current.tasks.workers,
                    p2: current.tasks.caller_limit,
                    p3: Math.round(current.tasks.retention_seconds / 3600),
                  },
                )
              "
            />
          </div>
          <span class="badge"
            >{{ tr('等待') }} {{ current.tasks.counts.queued || 0 }} {{ tr('· 执行') }}
            {{ (current.tasks.counts.running || 0) + (current.tasks.counts.cancelling || 0) }}</span
          >
        </header>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{{ tr('任务 ID') }}</th>
                <th>{{ tr('智能体') }}</th>
                <th>{{ tr('调用者') }}</th>
                <th>IP</th>
                <th>{{ tr('协议') }}</th>
                <th>{{ tr('状态') }}</th>
                <th>{{ tr('创建时间') }}</th>
                <th>{{ tr('操作') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in tasks" :key="t.id">
                <td :title="t.id">
                  <code>{{ t.id.slice(-10) }}</code>
                </td>
                <td>{{ t.agent_name }}</td>
                <td>{{ t.caller }}</td>
                <td>{{ t.caller_ip || tr('未知') }}</td>
                <td>
                  <span class="badge">{{ t.source.toUpperCase() }}</span>
                </td>
                <td>
                  <span
                    class="badge"
                    :class="{
                      on: t.status === 'running' || t.status === 'completed',
                      bad: t.status === 'failed',
                    }"
                    >{{ labels[t.status] || t.status }}</span
                  >
                </td>
                <td>{{ date(t.created_at) }}</td>
                <td>
                  <button
                    v-if="['queued', 'running', 'cancelling'].includes(t.status)"
                    @click="cancel(t)"
                  >
                    {{ tr('停止') }}</button
                  ><span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="!tasks.length" class="empty-state">{{ tr('暂无机器调用任务') }}</div>
        </div>
      </section></template
    >
  </section>
</template>
