<template>
  <div ref="pageRef" class="screen-page">
    <template v-if="data">
      <div class="screen-inner">
        <!-- 顶栏 -->
        <header class="sc-top">
          <div class="sc-brand">
            <div class="sc-logo">{{ brandInitial }}</div>
            <div class="sc-brand-copy">
              <div class="sc-site">{{ data.site_name }}</div>
              <div class="sc-sub">经营数据大屏 · REAL-TIME</div>
            </div>
          </div>
          <div class="sc-tools">
            <button
              class="sc-fs"
              type="button"
              :title="isFullscreen ? '退出全屏' : '进入全屏'"
              :aria-label="isFullscreen ? '退出全屏' : '进入全屏'"
              @click="toggleFullscreen"
            >
              <Icon :icon="isFullscreen ? 'ri:fullscreen-exit-line' : 'ri:fullscreen-line'" />
            </button>
            <div class="sc-clock">
              <div class="sc-time">{{ clock.time }}</div>
              <div class="sc-date">{{ clock.date }}</div>
            </div>
          </div>
        </header>

        <!-- KPI -->
        <section class="sc-kpis">
          <div
            v-for="k in kpiCards"
            :key="k.label"
            class="sc-kpi"
            :style="{ '--k-accent': k.accent }"
          >
            <div class="sk-head">
              <span class="sk-label">{{ k.label }}</span>
              <span class="sk-ic"><Icon :icon="k.icon" /></span>
            </div>
            <div class="sk-num-line">
              <CountTo
                class="sk-value"
                :target="Number(k.value)"
                :decimals="decimalsOf(k.value)"
                :duration="1200"
              />
              <small v-if="k.unit" class="sk-unit">{{ k.unit }}</small>
            </div>
          </div>
        </section>

        <!-- 图表区 -->
        <section class="sc-charts">
          <div class="sc-panel">
            <div class="sp-head">
              <div class="sp-title">月度接单趋势</div>
              <span class="sp-tag mono">LAST 12 MONTHS</span>
            </div>
            <ChartBox
              :option="trendOption"
              height="clamp(240px, 24vw, 320px)"
              empty-text="暂无接单趋势数据"
            />
          </div>
          <div class="sc-panel">
            <div class="sp-head">
              <div class="sp-title">业务类型分布</div>
              <span class="sp-tag mono">PROJECT TYPE</span>
            </div>
            <ChartBox
              v-if="catData.length"
              :option="catOption"
              height="clamp(240px, 24vw, 320px)"
            />
            <EmptyState
              v-else
              compact
              class="sp-empty"
              icon="ri:pie-chart-line"
              title="暂无业务类型数据"
              description="产生订单后将自动展示分布"
            />
          </div>
        </section>

        <!-- 最近交付 -->
        <section class="sc-panel sc-recent">
          <div class="sp-head">
            <div class="sp-title">最近交付</div>
            <span class="sp-tag mono">LIVE</span>
          </div>
          <div class="sr-list">
            <div
              v-for="(r, i) in data.recent_done"
              :key="r.id"
              class="sr-row rise-in"
              :style="{ animationDelay: `${Math.min(i, 8) * 40}ms` }"
            >
              <span class="sr-cat" :class="catClass(r.project_type)">{{ catLabel(r.project_type) }}</span>
              <span class="sr-id mono">{{ r.id }}</span>
              <span class="sr-title" :title="r.title">{{ r.title }}</span>
              <span class="sr-q">{{ r.quality }}</span>
              <span class="sr-date mono">{{ fmtDate(r.done_at) }}</span>
            </div>
            <div v-if="!data.recent_done.length" class="sr-empty">
              <Icon icon="ri:inbox-line" />
              暂无交付记录
            </div>
          </div>
        </section>

        <footer class="sc-foot">数据每 60 秒自动刷新 · {{ data.updated_at }} 更新</footer>
      </div>
    </template>

    <div v-else-if="error" class="sc-state">
      <EmptyState icon="ri:lock-2-line" :title="error" description="请向管理员索取最新大屏链接" />
    </div>

    <div v-else class="screen-inner sc-skeleton" aria-busy="true">
      <header class="sc-top">
        <div class="sk-brand">
          <div class="skeleton sk-logo" />
          <div class="sk-lines">
            <div class="skeleton sk-line w-220" />
            <div class="skeleton sk-line w-140" />
          </div>
        </div>
        <div class="skeleton sk-clock" />
      </header>
      <section class="sc-kpis">
        <div v-for="i in 6" :key="i" class="skeleton sk-kpi" />
      </section>
      <section class="sc-charts">
        <div class="skeleton sk-chart" />
        <div class="skeleton sk-chart" />
      </section>
      <div class="skeleton sk-recent" />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import ChartBox from '../components/ChartBox.vue'
import CountTo from '../components/CountTo.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import { useThemeStore } from '../stores/theme'
import {
  ART_COLORS,
  anim,
  animCallbacks,
  artGrid,
  artLegend,
  artTooltip,
  buildBar,
  catAxis,
  cssVar,
  valueAxis,
} from '../utils/artChart'

const route = useRoute()
const themeStore = useThemeStore()

const pageRef = ref(null)
const data = ref(null)
const error = ref('')
const clock = ref({ time: '', date: '' })
const isFullscreen = ref(false)
let refreshTimer = null
let clockTimer = null

const brandInitial = computed(() => (data.value?.site_name || '毕').slice(0, 1))
const catData = computed(() => data.value?.project_type_dist || [])

const kpiCards = computed(() => {
  const k = data.value?.kpis || {}
  return [
    { label: '累计订单', value: k.total ?? 0, unit: '单', icon: 'ri:file-list-3-line', accent: 'var(--brand)' },
    { label: '本月新增', value: k.month_new ?? 0, unit: '单', icon: 'ri:add-circle-line', accent: 'var(--info)' },
    { label: '已交付结单', value: k.closed ?? 0, unit: '单', icon: 'ri:checkbox-circle-line', accent: 'var(--success)' },
    { label: '结单率', value: k.close_rate ?? 0, unit: '%', icon: 'ri:percent-line', accent: 'var(--warning)' },
    { label: '按时交付率', value: k.on_time_rate ?? 0, unit: '%', icon: 'ri:time-line', accent: 'var(--purple)' },
    { label: '平均交付周期', value: k.avg_cycle_days ?? 0, unit: '天', icon: 'ri:timer-line', accent: 'var(--brand-2)' },
  ]
})

function decimalsOf(v) {
  const n = Number(v)
  return Number.isFinite(n) && !Number.isInteger(n) ? 1 : 0
}

// 两类业务沿用 v1.15 语义色令牌（回退到 art 调色板）
function catColor(name, i) {
  const map = {
    程序设计: cssVar('--cat-code', ART_COLORS[0]),
    艺术设计: cssVar('--cat-design', ART_COLORS[2]),
    纯论文: cssVar('--cat-thesis', ART_COLORS[3]),
  }
  return map[name] || ART_COLORS[i % ART_COLORS.length]
}

const trendOption = computed(() => {
  // 读取主题模式建立依赖：切换亮/暗时重新计算图表配色
  void themeStore.mode
  const t = data.value?.trend || []
  return {
    grid: artGrid({ top: 32, right: 12, bottom: 4 }),
    tooltip: artTooltip({
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
        shadowStyle: { color: cssVar('--brand-weak') },
      },
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params
        if (!p) return ''
        return `${p.axisValueLabel}<br/>${p.marker} 接单量 <b style="font-size:13px">${p.value}</b> 单`
      },
    }),
    xAxis: catAxis(t.map((x) => String(x.month).slice(2)), { boundaryGap: true }),
    yAxis: valueAxis({ minInterval: 1 }),
    series: [{
      name: '接单量',
      type: 'bar',
      barMaxWidth: 28,
      data: t.map((x) => Number(x.orders) || 0),
      itemStyle: { color: buildBar(ART_COLORS[0]), borderRadius: [6, 6, 0, 0] },
      emphasis: { itemStyle: { color: buildBar(ART_COLORS[1]) } },
      ...animCallbacks(45, 1200),
    }],
  }
})

const catOption = computed(() => {
  void themeStore.mode
  return {
    tooltip: artTooltip({
      trigger: 'item',
      formatter: (p) => `${p.marker} ${p.name}<br/><b>${p.value}</b> 单 · ${p.percent}%`,
    }),
    legend: artLegend({ bottom: 0, left: 'center' }),
    series: [{
      name: '业务类型',
      type: 'pie',
      radius: ['52%', '74%'],
      center: ['50%', '43%'],
      itemStyle: {
        borderColor: cssVar('--chart-ring'),
        borderWidth: 3,
        borderRadius: 6,
      },
      label: { show: false },
      labelLine: { show: false },
      emphasis: {
        scale: true,
        scaleSize: 6,
        itemStyle: { shadowBlur: 18, shadowColor: cssVar('--brand-weak') },
      },
      data: catData.value.map((x, i) => ({
        name: x.name,
        value: x.value,
        itemStyle: { color: catColor(x.name, i) },
      })),
      ...anim(0),
    }],
  }
})

const PT_LABEL = { program: '纯设计', thesis: '纯论文', thesis_program: '论文+设计' }
function catLabel(pt) {
  return PT_LABEL[pt] || '未设置'
}
function catClass(pt) {
  return { program: 'code', thesis: 'thesis', thesis_program: 'design' }[pt] || 'code'
}

function fmtDate(t) {
  return t ? String(t).replace('T', ' ').slice(0, 10) : ''
}

async function load() {
  try {
    const resp = await fetch(`/api/screen/${route.params.token}`)
    const body = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      error.value = typeof body.detail === 'string' ? body.detail : '大屏加载失败'
      return
    }
    data.value = body
    error.value = ''
    document.title = `${body.site_name} · 经营大屏`
  } catch {
    error.value = '大屏加载失败，请稍后重试'
  }
}

function tick() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  clock.value = {
    time: `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`,
    date: `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} 星期${'日一二三四五六'[d.getDay()]}`,
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) {
      await pageRef.value?.requestFullscreen?.()
    } else {
      await document.exitFullscreen?.()
    }
  } catch {
    // 浏览器不允许全屏时保持当前状态
  }
}

onMounted(() => {
  load()
  tick()
  clockTimer = setInterval(tick, 1000)
  refreshTimer = setInterval(load, 60 * 1000)
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

onBeforeUnmount(() => {
  clearInterval(refreshTimer)
  clearInterval(clockTimer)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})
</script>

<style scoped>
.screen-page {
  position: relative;
  min-height: 100vh;
  padding: clamp(14px, 2.4vw, 28px) clamp(14px, 2.6vw, 32px);
  overflow-x: hidden;
  color: var(--text);
  background:
    radial-gradient(1200px 580px at 74% -14%, color-mix(in srgb, var(--brand) 30%, transparent), transparent 62%),
    radial-gradient(900px 520px at 0% -6%, color-mix(in srgb, var(--purple) 15%, transparent), transparent 58%),
    var(--bg);
}
.screen-page::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(color-mix(in srgb, var(--text) 3%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--text) 3%, transparent) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at 70% 0%, #000 0%, transparent 70%);
}
.screen-page:fullscreen {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 24px 28px;
}

.screen-inner {
  position: relative;
  z-index: 1;
  max-width: var(--screen-max);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: clamp(12px, 1.4vw, 18px);
}

/* ===== 顶栏 ===== */
.sc-top { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.sc-brand { display: flex; align-items: center; gap: 14px; min-width: 0; }
.sc-logo {
  width: clamp(42px, 3.4vw, 52px);
  height: clamp(42px, 3.4vw, 52px);
  flex-shrink: 0;
  border-radius: 14px;
  background: var(--brand-grad);
  box-shadow: var(--brand-glow);
  color: #fff;
  font-size: clamp(19px, 1.8vw, 24px);
  font-weight: 750;
  display: flex; align-items: center; justify-content: center;
}
.sc-brand-copy { min-width: 0; }
.sc-site {
  font-size: clamp(20px, 2.4vw, 26px);
  font-weight: 750;
  letter-spacing: 0.06em;
  color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sc-sub {
  margin-top: 3px;
  font-size: 10.5px;
  letter-spacing: 0.3em;
  color: var(--text-3);
  white-space: nowrap;
}
.sc-tools { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
.sc-fs {
  width: 38px; height: 38px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--card) 72%, transparent);
  color: var(--text-2);
  font-size: 18px;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: color 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}
.sc-fs:hover {
  color: var(--brand);
  border-color: color-mix(in srgb, var(--brand) 40%, var(--border));
  background: var(--brand-weak);
}
.sc-clock { text-align: right; }
.sc-time {
  font-family: var(--font-mono);
  font-size: clamp(24px, 2.8vw, 34px);
  font-weight: 650;
  line-height: 1.08;
  letter-spacing: 0.04em;
  color: var(--brand);
  text-shadow: 0 0 20px color-mix(in srgb, var(--brand) 45%, transparent);
  font-variant-numeric: tabular-nums;
}
.sc-date { margin-top: 3px; font-size: 12.5px; color: var(--text-3); }

/* ===== KPI ===== */
.sc-kpis {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 14px;
}
.sc-kpi {
  position: relative;
  min-width: 0;
  overflow: hidden;
  padding: 15px 16px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--card) 84%, transparent),
    color-mix(in srgb, var(--card) 62%, transparent)
  );
  box-shadow: var(--shadow-card);
  backdrop-filter: blur(12px);
  transition: border-color 0.2s ease, transform 0.2s ease;
}
.sc-kpi:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--k-accent) 30%, var(--border));
}
.sc-kpi::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: linear-gradient(90deg, var(--k-accent), transparent 82%);
  opacity: 0.9;
}
.sc-kpi::after {
  content: '';
  position: absolute;
  right: -34px; bottom: -46px;
  width: 110px; height: 110px;
  border-radius: 50%;
  background: radial-gradient(circle, color-mix(in srgb, var(--k-accent) 16%, transparent), transparent 70%);
  pointer-events: none;
}
.sk-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.sk-label {
  font-size: 12.5px;
  color: var(--text-2);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sk-ic { flex-shrink: 0; font-size: 16px; color: var(--k-accent); }
.sk-num-line {
  display: flex; align-items: baseline; gap: 4px;
  margin-top: 9px;
  min-width: 0;
}
.sk-value {
  min-width: 0;
  max-width: 100%;
  font-size: clamp(23px, 2.35vw, 40px);
  font-weight: 750;
  line-height: 1.12;
  letter-spacing: -0.02em;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sk-unit { flex-shrink: 0; font-size: 12px; font-weight: 500; color: var(--text-3); }

/* ===== 面板 / 图表 ===== */
.sc-charts {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 14px;
  align-items: stretch;
}
.sc-panel {
  position: relative;
  min-width: 0;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--card) 86%, transparent),
    color-mix(in srgb, var(--card) 68%, transparent)
  );
  box-shadow: var(--shadow-card);
  backdrop-filter: blur(12px);
  overflow: hidden;
}
.sc-panel::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--brand) 55%, transparent), transparent);
}
.sp-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-bottom: 8px;
}
.sp-title { font-size: 14px; font-weight: 650; letter-spacing: 0.02em; color: var(--text); }
.sp-tag {
  flex-shrink: 0;
  padding: 2px 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--card-2);
  font-size: 9.5px;
  letter-spacing: 0.12em;
  color: var(--text-3);
  white-space: nowrap;
}
.sp-empty { height: clamp(240px, 24vw, 320px); min-height: 0; padding: 20px; }

/* ===== 最近交付 ===== */
.sc-recent { padding-bottom: 14px; }
.sr-list {
  display: flex; flex-direction: column; gap: 7px;
  max-height: 280px;
  overflow-y: auto;
}
.sr-row {
  display: flex; align-items: center; gap: 12px;
  min-width: 0;
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--card-2) 70%, transparent);
  font-size: 13px;
  transition: background 0.18s ease, border-color 0.18s ease;
}
.sr-row:hover {
  background: var(--card-2);
  border-color: var(--border-2);
}
.sr-cat {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 10.5px;
  font-weight: 600;
}
.sr-cat.code { background: var(--brand-weak); color: var(--brand); }
.sr-cat.design { background: var(--purple-weak); color: var(--purple); }
.sr-cat.thesis { background: var(--success-weak); color: var(--success); }
.sr-id { flex-shrink: 0; font-size: 12px; color: var(--text-2); }
.sr-title {
  flex: 1; min-width: 0;
  color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sr-q { flex-shrink: 0; color: var(--text-3); }
.sr-date { flex-shrink: 0; font-size: 12px; color: var(--text-3); }
.sr-empty {
  display: flex; align-items: center; justify-content: center; gap: 7px;
  padding: 28px 0;
  font-size: 12.5px;
  color: var(--text-3);
}
.sr-empty .iconify { font-size: 18px; }

.sc-foot {
  text-align: center;
  font-size: 11.5px;
  letter-spacing: 0.08em;
  color: var(--text-3);
  padding-bottom: 4px;
}

/* ===== 错误 / 骨架 ===== */
.sc-state {
  position: relative;
  z-index: 1;
  width: 100%;
  min-height: calc(100vh - 56px);
  display: flex; align-items: center; justify-content: center;
}
.sc-skeleton { position: relative; z-index: 1; }
.sk-brand { display: flex; align-items: center; gap: 14px; }
.sk-logo { width: 52px; height: 52px; border-radius: 14px; flex-shrink: 0; }
.sk-lines { display: flex; flex-direction: column; gap: 8px; }
.sk-line { height: 14px; border-radius: 6px; }
.w-220 { width: 220px; max-width: 55vw; }
.w-140 { width: 140px; }
.sk-clock { width: 170px; height: 54px; border-radius: var(--radius); }
.sk-kpi { height: 96px; border-radius: var(--radius-lg); }
.sk-chart { height: clamp(240px, 24vw, 320px); border-radius: var(--radius-lg); }
.sk-recent { height: 150px; border-radius: var(--radius-lg); }

/* ===== 响应式 ===== */
@media (max-width: 1100px) {
  .screen-page { padding: 18px; }
  .sc-kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .sc-charts { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .screen-page { padding: 14px 12px; }
  .sc-top { flex-wrap: wrap; align-items: flex-start; gap: 10px; }
  .sc-brand { gap: 10px; flex: 1; min-width: 0; }
  .sc-logo { width: 42px; height: 42px; border-radius: 12px; font-size: 19px; }
  .sc-site { font-size: 18px; letter-spacing: 0.03em; }
  .sc-sub { font-size: 9px; letter-spacing: 0.14em; }
  .sc-tools { margin-left: auto; gap: 9px; }
  .sc-fs { width: 32px; height: 32px; font-size: 16px; }
  .sc-time { font-size: 21px; }
  .sc-date { font-size: 10.5px; }
  .sc-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .sc-kpi { padding: 12px 13px; }
  .sk-value { font-size: 24px; }
  .sk-num-line { margin-top: 7px; }
  .sc-charts { gap: 10px; }
  .sc-panel { padding: 13px; }
  .sp-title { font-size: 13.5px; }
  .sr-row { gap: 8px; padding: 8px 10px; font-size: 12px; }
  .sr-q { display: none; }
  .sr-date { font-size: 11px; }
  .sc-foot { font-size: 10.5px; letter-spacing: 0.04em; }
}
@media (max-width: 420px) {
  .sc-site { font-size: 16.5px; }
  .sc-time { font-size: 19px; }
  .sc-date { font-size: 9.5px; }
  .sr-id { display: none; }
  .sk-value { font-size: 22px; }
}
</style>
