<template>
  <div class="page-shell health-view">
    <AppPageHeader
      title="系统健康检查"
      description="数据库、缓存、存储、备份与实时通道的实时体检"
      icon="ri:heart-pulse-line"
    >
      <template #badge>
        <span v-if="data" class="overall-badge" :class="overall" aria-live="polite">
          <span class="badge-dot art-dot-breathe" />{{ overallText }}
        </span>
      </template>
      <template #actions>
        <span class="refresh-hint">
          <Icon icon="ri:time-line" />{{ refreshHint }}
        </span>
        <el-button :loading="loading" @click="load()">
          <Icon v-if="!loading" icon="ri:refresh-line" class="btn-ic" />立即刷新
        </el-button>
      </template>
    </AppPageHeader>

    <div v-if="loading && !data" class="skeleton-wrap" aria-busy="true">
      <div class="skeleton sk-summary" />
      <div class="sk-grid">
        <div v-for="i in 6" :key="i" class="skeleton sk-card" />
      </div>
    </div>

    <section v-else-if="error && !data" class="art-card">
      <EmptyState
        icon="ri:error-warning-line"
        title="健康数据加载失败"
        :description="error"
        tone="var(--danger)"
      >
        <el-button type="primary" :loading="loading" @click="load()">重新加载</el-button>
      </EmptyState>
    </section>

    <template v-else-if="data">
      <div v-if="error" class="refresh-error">
        <Icon icon="ri:alert-line" />
        最近一次刷新失败：{{ error }}，以下为上次检查结果
      </div>

      <section class="art-card summary-card" :class="overall">
        <div class="sum-left">
          <span class="sum-icon">
            <Icon :icon="overall === 'ok' ? 'ri:shield-check-line' : 'ri:error-warning-line'" />
          </span>
          <div class="sum-copy">
            <div class="sum-title">{{ overallText }}</div>
            <div class="sum-desc">{{ summaryText }}</div>
          </div>
        </div>
        <div class="sum-meta">
          <div class="meta-cell">
            <span>版本</span>
            <b class="mono">v{{ data.version || 'unknown' }}</b>
          </div>
          <div class="meta-cell">
            <span>运行时长</span>
            <b>{{ fmtUptime(data.uptime_seconds) }}</b>
          </div>
          <div class="meta-cell">
            <span>检查时间</span>
            <b class="mono">{{ fmtTime(data.checked_at) }}</b>
          </div>
        </div>
      </section>

      <div class="check-grid">
        <article
          v-for="(item, i) in checks"
          :key="item.key"
          class="art-card check-card rise-in"
          :class="item.status"
          :style="{ animationDelay: `${i * 45}ms` }"
        >
          <div class="cc-head">
            <span class="cc-icon"><Icon :icon="CHECK_ICONS[item.key] || 'ri:question-line'" /></span>
            <div class="cc-copy">
              <div class="cc-title">
                <h3>{{ item.label }}</h3>
                <span class="cc-status" :class="item.status">
                  <span class="cc-dot" />{{ statusText(item.status) }}
                </span>
              </div>
              <span class="cc-key mono">{{ item.key }}</span>
            </div>
          </div>
          <p class="cc-detail">{{ item.detail }}</p>
          <div class="cc-foot">
            <span class="cc-latency">
              <Icon icon="ri:timer-flash-line" />
              <template v-if="item.latency_ms != null">延迟 {{ fmtLatency(item.latency_ms) }}</template>
              <template v-else>未计时</template>
            </span>
            <Icon :icon="STATUS_ICONS[item.status] || 'ri:question-line'" class="cc-status-icon" />
          </div>
        </article>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import http from '../api'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const REFRESH_SECONDS = 15
const CHECK_ICONS = {
  db: 'ri:database-2-line',
  redis: 'ri:cloud-line',
  uploads: 'ri:folder-upload-line',
  backups: 'ri:file-shield-2-line',
  ws: 'ri:wifi-line',
  disk: 'ri:hard-drive-2-line',
}
const STATUS_TEXT = { ok: '正常', warn: '注意', fail: '异常' }
const STATUS_ICONS = { ok: 'ri:check-line', warn: 'ri:error-warning-line', fail: 'ri:close-circle-line' }

const data = ref(null)
const loading = ref(true)
const error = ref('')
const lastUpdated = ref(null)

let inFlight = false
let timer = null

const checks = computed(() => data.value?.checks || [])
const overall = computed(() => (data.value?.status === 'ok' ? 'ok' : 'degraded'))
const overallText = computed(() => (overall.value === 'ok' ? '运行正常' : '存在异常'))
const issues = computed(() => checks.value.filter((item) => item.status !== 'ok'))
const summaryText = computed(() => {
  if (!checks.value.length) return '暂无检查结果'
  if (!issues.value.length) return `${checks.value.length} 项检查全部通过`
  const fail = issues.value.filter((item) => item.status === 'fail').length
  const warn = issues.value.length - fail
  const parts = []
  if (fail) parts.push(`${fail} 项异常`)
  if (warn) parts.push(`${warn} 项需关注`)
  return `${checks.value.length} 项检查中 ${parts.join('、')}`
})
const refreshHint = computed(() => {
  if (loading.value) return '正在刷新…'
  if (!lastUpdated.value) return `每 ${REFRESH_SECONDS} 秒自动刷新`
  return `最后更新 ${fmtClock(lastUpdated.value)} · 每 ${REFRESH_SECONDS} 秒自动刷新`
})

onMounted(() => {
  load()
  timer = window.setInterval(() => {
    if (!document.hidden) load()
  }, REFRESH_SECONDS * 1000)
  document.addEventListener('visibilitychange', onVisibility)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibility)
})

function onVisibility() {
  if (!document.hidden) load()
}

async function load() {
  if (inFlight) return
  inFlight = true
  loading.value = true
  try {
    const resp = await http.get('/admin/health')
    data.value = resp
    error.value = ''
    lastUpdated.value = new Date()
  } catch (err) {
    // 请求拦截器已弹出提示，这里只维护页内错误态并保留上次结果
    error.value = err?.response?.data?.detail || err?.message || '健康检查请求失败'
  } finally {
    inFlight = false
    loading.value = false
  }
}

function statusText(status) {
  return STATUS_TEXT[status] || status || '未知'
}

function fmtLatency(ms) {
  const n = Number(ms)
  if (!Number.isFinite(n)) return '—'
  if (n < 1) return '<1 ms'
  if (n < 1000) return `${Math.round(n)} ms`
  return `${(n / 1000).toFixed(2)} s`
}

function fmtUptime(seconds) {
  const s = Math.max(0, Number(seconds) || 0)
  const days = Math.floor(s / 86400)
  const hours = Math.floor((s % 86400) / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  if (days) return `${days} 天 ${hours} 小时`
  if (hours) return `${hours} 小时 ${minutes} 分钟`
  if (minutes) return `${minutes} 分钟`
  return `${Math.floor(s)} 秒`
}

function fmtTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 19)
}

function fmtClock(date) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}
</script>

<style scoped>
.health-view { min-width: 0; }
.btn-ic { margin-right: 4px; }

.overall-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 10px; border-radius: var(--radius-pill);
  font-size: 12px; font-weight: 600; line-height: 20px;
  border: 1px solid transparent; white-space: nowrap;
}
.overall-badge.ok {
  color: var(--success); background: var(--success-weak);
  border-color: color-mix(in srgb, var(--success) 32%, transparent);
}
.overall-badge.degraded {
  color: var(--warning); background: var(--warning-weak);
  border-color: color-mix(in srgb, var(--warning) 32%, transparent);
}
.badge-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

.refresh-hint {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--text-3); white-space: nowrap;
}
.refresh-hint .iconify { font-size: 13px; }

.skeleton-wrap { display: flex; flex-direction: column; gap: 16px; }
.sk-summary { height: 92px; border-radius: var(--radius-lg); }
.sk-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 16px;
}
@media (min-width: 1200px) {
  .sk-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
.sk-card { height: 154px; border-radius: var(--radius-lg); }

.refresh-error {
  display: flex; align-items: center; gap: 6px;
  padding: 9px 12px; border-radius: var(--radius-sm);
  background: var(--danger-weak); color: var(--danger);
  border: 1px solid color-mix(in srgb, var(--danger) 28%, transparent);
  font-size: 12px; line-height: 1.5;
}
.refresh-error .iconify { font-size: 14px; flex-shrink: 0; }

.summary-card {
  display: flex; align-items: center; justify-content: space-between;
  gap: 18px; flex-wrap: wrap;
}
.summary-card.ok { background: linear-gradient(120deg, var(--success-weak), var(--card) 58%); }
.summary-card.degraded { background: linear-gradient(120deg, var(--warning-weak), var(--card) 58%); }
.sum-left { display: flex; align-items: center; gap: 13px; min-width: 0; }
.sum-icon {
  width: 46px; height: 46px; flex-shrink: 0; border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; border: 1px solid var(--border);
}
.summary-card.ok .sum-icon { color: var(--success); background: var(--success-weak); }
.summary-card.degraded .sum-icon { color: var(--warning); background: var(--warning-weak); }
.sum-title { font-size: 15px; font-weight: 650; color: var(--text); }
.sum-desc { margin-top: 3px; font-size: 12.5px; color: var(--text-3); }
.sum-meta { display: flex; align-items: center; gap: 28px; flex-wrap: wrap; }
.meta-cell span { display: block; font-size: 11px; color: var(--text-3); margin-bottom: 2px; }
.meta-cell b { font-size: 13px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }

.check-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 16px;
}
@media (min-width: 1200px) {
  .check-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
.check-card {
  display: flex; flex-direction: column; gap: 12px;
  padding: 16px 18px; min-width: 0;
}
.check-card.warn { border-color: color-mix(in srgb, var(--warning) 30%, var(--border)); }
.check-card.fail { border-color: color-mix(in srgb, var(--danger) 34%, var(--border)); }
.cc-head { display: flex; align-items: center; gap: 11px; min-width: 0; }
.cc-icon {
  width: 38px; height: 38px; flex-shrink: 0; border-radius: 11px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; background: var(--card-2); border: 1px solid var(--border);
  color: var(--text-2);
}
.check-card.ok .cc-icon { color: var(--success); background: var(--success-weak); }
.check-card.warn .cc-icon { color: var(--warning); background: var(--warning-weak); }
.check-card.fail .cc-icon { color: var(--danger); background: var(--danger-weak); }
.cc-copy { min-width: 0; flex: 1; }
.cc-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cc-title h3 { margin: 0; font-size: 13.5px; font-weight: 600; color: var(--text); }
.cc-key { display: inline-block; margin-top: 2px; font-size: 10.5px; color: var(--text-4); letter-spacing: 0.05em; }
.cc-status {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 0 7px; border-radius: var(--radius-pill);
  font-size: 10.5px; font-weight: 500; line-height: 18px;
}
.cc-status.ok { color: var(--success); background: var(--success-weak); }
.cc-status.warn { color: var(--warning); background: var(--warning-weak); }
.cc-status.fail { color: var(--danger); background: var(--danger-weak); }
.cc-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.cc-detail {
  flex: 1; margin: 0; min-height: 40px;
  font-size: 12.5px; color: var(--text-2); line-height: 1.65; word-break: break-word;
}
.cc-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding-top: 10px; border-top: 1px solid var(--border);
  font-size: 11.5px; color: var(--text-3);
}
.cc-latency { display: inline-flex; align-items: center; gap: 4px; font-variant-numeric: tabular-nums; }
.cc-latency .iconify { font-size: 13px; }
.cc-status-icon { font-size: 15px; color: var(--text-4); }
.check-card.ok .cc-status-icon { color: var(--success); }
.check-card.warn .cc-status-icon { color: var(--warning); }
.check-card.fail .cc-status-icon { color: var(--danger); }

@media (min-width: 2200px) {
  .sk-grid, .check-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 20px; }
}

@media (max-width: 768px) {
  .summary-card { flex-direction: column; align-items: flex-start; gap: 14px; }
  .sum-meta { gap: 20px; }
  .check-grid, .sk-grid { grid-template-columns: 1fr; }
}
@media (max-width: 520px) {
  .refresh-hint { display: none; }
  .sum-meta { gap: 14px; }
}
</style>
