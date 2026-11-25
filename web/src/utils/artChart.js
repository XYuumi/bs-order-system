/** art-design-pro 图表规范（useChart.ts 同源）：
 * 颜色/轴/渐变/动画统一出口，所有图表跟随 html.dark / html.light。
 */

export const ART_COLORS = ['#5D87FF', '#4ABEFF', '#B48DF3', '#13DEBA', '#FFAF20', '#FA8A6C', '#38C0FC']

export function cssVar(name, fallback = '') {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

export function isDarkTheme() {
  return document.documentElement.classList.contains('dark')
}

export function labelColor() {
  return cssVar('--chart-label', '#8f8fa3')
}

export function axisLineColor() {
  return cssVar('--chart-axis', '#444')
}

export function splitLineColor() {
  return cssVar('--chart-split', '#333')
}

/** art 交错动画：每根柱/每个点 delay = idx*50+200，时长 1500-idx*50，quarticOut */
export function anim(idx = 0) {
  return {
    animationDelay: idx * 50 + 200,
    animationDuration: Math.max(1500 - idx * 50, 600),
    animationEasing: 'quarticOut',
  }
}

export function animCallbacks(step = 50, base = 1200) {
  return {
    animationDelay: (idx) => idx * step + 150,
    animationDuration: (idx) => Math.max(base - idx * step, 500),
    animationEasing: 'quarticOut',
  }
}

/** 折线渐变面积（art art-line-chart：0.2 → 0.02） */
export function buildArea(color) {
  return {
    type: 'linear',
    x: 0, y: 0, x2: 0, y2: 1,
    colorStops: [
      { offset: 0, color: hexA(color, 0.22) },
      { offset: 1, color: hexA(color, 0.015) },
    ],
  }
}

/** 柱状渐变（art art-bar-chart：上浅下深） */
export function buildBar(color) {
  return {
    type: 'linear',
    x: 0, y: 0, x2: 0, y2: 1,
    colorStops: [
      { offset: 0, color: hexA(color, 0.62) },
      { offset: 1, color },
    ],
  }
}

/** hex / rgb(a) → rgba */
export function hexA(color, alpha) {
  const hex = String(color).trim()
  if (hex.startsWith('rgb')) {
    const nums = hex.replace(/[^\d.,]/g, '').split(',').map((n) => parseFloat(n))
    return `rgba(${nums[0] || 0}, ${nums[1] || 0}, ${nums[2] || 0}, ${alpha})`
  }
  const raw = hex.replace('#', '')
  const full = raw.length === 3 ? raw.split('').map((c) => c + c).join('') : raw
  const r = parseInt(full.slice(0, 2), 16) || 0
  const g = parseInt(full.slice(2, 4), 16) || 0
  const b = parseInt(full.slice(4, 6), 16) || 0
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/** 通用 value 轴（art 风格：虚线分割、#999 标签、无刻度） */
export function valueAxis(extra = {}) {
  return {
    type: 'value',
    axisLabel: { color: labelColor(), fontSize: 11.5 },
    splitLine: { lineStyle: { color: splitLineColor(), type: 'dashed' } },
    axisLine: { show: false },
    axisTick: { show: false },
    nameTextStyle: { color: labelColor(), fontSize: 11 },
    ...extra,
  }
}

/** 通用 category 轴 */
export function catAxis(data, extra = {}) {
  return {
    type: 'category',
    data,
    axisLabel: { color: labelColor(), fontSize: 11.5, margin: 10 },
    axisLine: { lineStyle: { color: axisLineColor() } },
    axisTick: { show: false },
    ...extra,
  }
}

/** art tooltip（暗底半透明 / 亮色白底） */
export function artTooltip(extra = {}) {
  const dark = isDarkTheme()
  return {
    backgroundColor: cssVar('--chart-tooltip', dark ? 'rgba(10,10,12,0.92)' : 'rgba(255,255,255,0.96)'),
    borderColor: cssVar('--chart-tooltip-border', dark ? '#333' : '#ddd'),
    borderWidth: 1,
    padding: [9, 12],
    textStyle: { color: dark ? '#e9e9ef' : '#1f2740', fontSize: 12 },
    extraCssText: 'border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,.32);backdrop-filter:blur(10px);',
    ...extra,
  }
}

/** art legend（roundRect 12px） */
export function artLegend(extra = {}) {
  return {
    icon: 'roundRect',
    itemWidth: 10,
    itemHeight: 10,
    itemGap: 18,
    textStyle: { color: labelColor(), fontSize: 11.5 },
    ...extra,
  }
}

/** 通用 grid（art 紧凑布局） */
export function artGrid(extra = {}) {
  return { left: 4, right: 10, top: 34, bottom: 2, containLabel: true, ...extra }
}

export function compactNumber(value, digits = 1) {
  const n = Number(value || 0)
  const abs = Math.abs(n)
  if (abs >= 100000000) return `${(n / 100000000).toFixed(digits)}亿`
  if (abs >= 10000) return `${(n / 10000).toFixed(digits)}万`
  if (abs >= 1000) return `${(n / 1000).toFixed(digits)}k`
  return String(Math.round(n))
}

export function moneyLabel(value) {
  const n = Number(value || 0)
  return n >= 10000 ? `¥${(n / 10000).toFixed(1)}万` : `¥${n.toLocaleString('zh-CN')}`
}
