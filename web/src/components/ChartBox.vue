<template>
  <div ref="el" class="chart-box" :class="{ 'chart-fill': fill }" :style="fill ? undefined : { height }">
    <div ref="chartEl" class="chart-canvas" />
    <div v-if="loading" class="chart-overlay">
      <span class="overlay-dot art-dot-breathe" />
      <span>加载中</span>
    </div>
    <div v-else-if="showEmpty" class="chart-overlay empty">
      <Icon icon="ri:bar-chart-box-line" />
      <span>{{ emptyText }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, RadarChart } from 'echarts/charts'
import {
  GridComponent, LegendComponent, RadarComponent, TitleComponent, TooltipComponent, MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useThemeStore } from '../stores/theme'

echarts.use([
  BarChart, LineChart, PieChart, RadarChart,
  GridComponent, LegendComponent, RadarComponent, TitleComponent, TooltipComponent,
  MarkLineComponent, CanvasRenderer,
])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '300px' },
  /** 填充模式：高度 100% 跟随弹性容器（gridstack 卡片内随缩放自适应） */
  fill: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
})

const themeStore = useThemeStore()
const el = ref(null)
const chartEl = ref(null)
let chart = null
let resizeObserver = null
let intersectionObserver = null
let initialized = false
let visible = false
let lastWidth = 0
let lastHeight = 0
// 最近一次渲染的时间戳：入场动画还在播放时（1.6 秒内）容器尺寸一变，resize 会打断动画，
// 这时在 resize 之后补一次「重播」。
let lastRenderAt = 0

function seriesData(series) {
  if (!series || !Array.isArray(series.data)) return []
  return series.data
}

const hasData = computed(() => {
  const series = props.option?.series
  if (!series || !series.length) return false
  return series.some((s) => seriesData(s).some((item) => {
    if (item == null) return false
    if (typeof item === 'number') return item !== 0
    if (typeof item === 'object') {
      if (Array.isArray(item.value)) return item.value.some((v) => Number(v) !== 0)
      return Number(item.value) !== 0
    }
    return true
  }))
})

const showEmpty = computed(() => !props.loading && !hasData.value)

/**
 * 给没写动画参数的柱状/饼图补 art 风格入场动画。
 * 已显式配置的 series 以业务配置为准（Dashboard / ScreenView / AiCenter 已自带）。
 */
function artSeries(series) {
  if (!Array.isArray(series)) return series
  return series.map((s) => {
    if (!s || typeof s !== 'object') return s
    if (s.type === 'bar' && s.animationDelay == null) {
      return {
        ...s,
        animationDelay: (idx) => 70 + idx * 45,
        animationDuration: 1100,
      }
    }
    if (s.type === 'pie' && s.animationType == null) {
      return { ...s, animationType: 'expansion' }
    }
    return s
  })
}

function buildOption() {
  return {
    animation: true,
    animationDuration: 1400,
    animationEasing: 'quarticOut',
    animationDurationUpdate: 700,
    animationEasingUpdate: 'quarticOut',
    textStyle: { fontFamily: getComputedStyle(document.documentElement).getPropertyValue('--font-sans').trim() },
    ...props.option,
    series: artSeries(props.option?.series),
  }
}

function resizeChart(force = false) {
  if (!chart || !el.value) return
  const width = el.value.clientWidth || 0
  const height = el.value.clientHeight || 0
  if (!force && width === lastWidth && height === lastHeight) return
  lastWidth = width
  lastHeight = height
  chart.resize()
  if (Date.now() - lastRenderAt < 1600) render({ replay: true })
}

function render({ replay = false } = {}) {
  if (!el.value || !chartEl.value || !visible || props.loading) return
  if (showEmpty.value) {
    if (chart) chart.clear()
    return
  }
  try {
    if (!chart) {
      // ⚠️ ECharts 初始化会执行 root.innerHTML = ''。
      // 必须挂到独立的 chart-canvas 上，绝不能直接用含 v-if 遮罩的 .chart-box，
      // 否则会删掉 Vue 托管的遮罩/注释锚点，刷新时触发 insertBefore 空指针。
      chart = echarts.init(chartEl.value, null, { renderer: 'canvas' })
      initialized = false
      lastWidth = 0
      lastHeight = 0
    }
    const option = buildOption()
    // 刷新时先清空再 setOption，让柱状图/饼图重新走一遍“从 0 生长”的入场动画。
    // 普通 merge 更新时 ECharts 只会做数值过渡，数据没变时看起来完全静止。
    if (replay && initialized) chart.clear()
    chart.setOption(option, { notMerge: replay || !initialized, lazyUpdate: false })
    initialized = true
    lastRenderAt = Date.now()
    // 记录尺寸，避免 ResizeObserver 在入场动画刚开始时做无意义 resize 打断动画。
    lastWidth = el.value.clientWidth || 0
    lastHeight = el.value.clientHeight || 0
  } catch (err) {
    // 空数据/异常配置不应击穿整个组件树（如 radar 空 indicator 会抛错）
    console.warn('[ChartBox] render skipped:', err?.message || err)
    if (chart) { chart.dispose(); chart = null }
    initialized = false
    lastWidth = 0
    lastHeight = 0
  }
}

function initObserver() {
  if (!el.value || typeof IntersectionObserver === 'undefined') {
    visible = true
    render()
    return
  }
  intersectionObserver = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) {
      visible = true
      intersectionObserver?.disconnect()
      intersectionObserver = null
      render()
    }
  }, { threshold: 0.05 })
  intersectionObserver.observe(el.value)
}

onMounted(() => {
  initObserver()
  resizeObserver = new ResizeObserver(() => resizeChart())
  resizeObserver.observe(el.value)
})

watch(() => props.option, () => {
  if (visible && !props.loading) render({ replay: true })
}, { deep: true })

watch(() => props.loading, (value) => {
  // 加载阶段保留旧图；loading 结束后只重绘一次，动画在遮罩消失后完整可见。
  if (!value && visible) render({ replay: true })
})

watch(() => themeStore.mode, () => {
  // 主题切换：轴/提示/图例颜色都来自 CSS 变量，需重建 option。
  if (chart) { chart.dispose(); chart = null; initialized = false; lastWidth = 0; lastHeight = 0 }
  if (visible && !props.loading) render()
})

onBeforeUnmount(() => {
  intersectionObserver?.disconnect()
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

defineExpose({ resize: () => chart?.resize(), chart: () => chart })
</script>

<style scoped>
.chart-box { position: relative; min-width: 0; width: 100%; }
.chart-fill { height: 100%; min-height: 0; }
.chart-canvas { position: absolute; inset: 0; min-width: 0; }
.chart-overlay {
  position: absolute; inset: 0; z-index: 2;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
  color: var(--text-3); font-size: 12.5px; background: transparent;
}
.chart-overlay.empty .iconify { font-size: 30px; opacity: 0.5; }
.overlay-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--brand); }
</style>
