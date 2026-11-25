<template>
  <div class="dashboard">
    <PageSkeleton v-if="loading && !loaded" />

    <template v-else>
      <!-- 欢迎横幅：暗色流星 + 品牌渐变 -->
      <section class="welcome art-card">
        <div class="welcome-glow" />
        <div class="meteors" aria-hidden="true">
          <span v-for="m in meteors" :key="m.id" class="meteor" :style="m.style" />
        </div>
        <div class="welcome-main">
          <div class="welcome-eyebrow">
            <span class="live-dot art-dot-breathe" />
            {{ greeting }}，{{ displayName }}
          </div>
          <h2 class="welcome-title">把每一单，交付得漂亮。</h2>
          <p class="welcome-sub">{{ todayLabel }} · {{ currentMonth }} · 数据更新于 {{ updatedText }}</p>
          <div class="welcome-actions">
            <!-- 写手不负责建单（路由只放开给管理员与代理），这里对他们隐藏 -->
            <button v-if="!auth.isStaffView || auth.isAdmin" class="w-btn primary" @click="router.push('/orders/create')">
              <Icon icon="ri:add-line" /> 新建订单
            </button>
            <button v-if="auth.isAdmin" class="w-btn" @click="openReport">
              <Icon icon="ri:sparkling-2-line" /> AI 经营报告
            </button>
            <button class="w-btn ghost" @click="load">
              <Icon icon="ri:refresh-line" :class="{ spin: loading }" /> 刷新数据
            </button>
            <button v-if="gridActive" class="w-btn ghost" @click="resetLayout">
              <Icon icon="ri:layout-line" /> 重置布局
            </button>
            <button v-if="auth.isAdmin || auth.isAgent" class="w-btn ghost" @click="saveAsDefault">
              <Icon icon="ri:save-3-line" /> 存为默认布局
            </button>
          </div>
        </div>
        <div class="welcome-side">
          <div class="ws-cell">
            <span>进行中</span>
            <b><CountTo :target="Number(kpis.active_orders || 0)" /></b>
          </div>
          <div class="ws-cell">
            <span>本周完成</span>
            <b><CountTo :target="Number(kpis.week_completed || 0)" /></b>
          </div>
          <div class="ws-cell">
            <span>按时交付</span>
            <b>{{ cards.on_time_rate != null ? cards.on_time_rate + '%' : '—' }}</b>
          </div>
        </div>
      </section>

      <!-- 统计卡 -->
      <div class="stat-grid">
        <StatCard
          v-for="(st, i) in statCards" :key="st.label"
          :label="st.label" :value="st.value" :prefix="st.prefix" :suffix="st.suffix"
          :icon="st.icon" :color="st.color" :delta="st.delta" :sub="st.sub"
          :delta-label="st.deltaLabel || '较上周'"
          :style="{ animationDelay: `${i * 60}ms` }"
          clickable @click="st.to && router.push(st.to)"
        />
      </div>

      <!-- 交期风险 -->
      <section class="risk-card art-card">
        <div class="rc-head">
          <div class="rc-title">
            <span class="rc-ico"><Icon icon="ri:alarm-warning-line" /></span>
            <div><h4>交期风险</h4><p>逾期与 {{ risk.days || 3 }} 天内到期的进行中订单</p></div>
          </div>
          <router-link to="/orders" class="link">查看全部 <Icon icon="ri:arrow-right-s-line" /></router-link>
        </div>
        <div class="rc-body">
          <div class="rc-counts">
            <div class="rc-count danger"><b>{{ risk.summary?.overdue ?? 0 }}</b><span>已逾期</span></div>
            <div class="rc-count warn"><b>{{ risk.summary?.soon ?? 0 }}</b><span>即将到期</span></div>
          </div>
          <ul v-if="riskItems.length" class="rc-list">
            <li v-for="it in riskItems" :key="it.id" @click="router.push('/orders/' + it.id)">
              <StatusTag :status="it.status" />
              <b class="rc-order">{{ it.id }}</b>
              <span class="rc-name" :title="it.title">{{ it.title }}</span>
              <span class="rc-days" :class="it.days_left < 0 ? 'danger' : 'warn'">{{ it.days_left < 0 ? '逾期 ' + (-it.days_left) + ' 天' : it.days_left === 0 ? '今天到期' : '剩 ' + it.days_left + ' 天' }}</span>
            </li>
          </ul>
          <EmptyState v-else compact icon="ri:shield-check-line" title="暂无交期风险" description="所有进行中订单都在安全期内" />
        </div>
      </section>

      <div v-if="error" class="error-card art-card">
        <EmptyState icon="ri:error-warning-line" title="数据加载失败" :description="error" tone="var(--danger)">
          <el-button type="primary" @click="load">重新加载</el-button>
        </EmptyState>
      </div>

      <!-- 可拖拽网格 -->
      <div
        v-else ref="gridEl" :key="gridActive ? 'grid' : 'static'"
        class="dash-grid" :class="gridActive ? 'grid-stack' : 'dash-grid-static'"
      >
        <!-- 订单趋势 -->
        <div class="grid-stack-item" gs-id="trend" gs-w="8" gs-h="13" gs-min-w="4" gs-min-h="9">
          <div class="grid-stack-item-content">
            <div class="dash-card">
              <div class="dc-head gs-head">
                <div>
                  <h4>订单趋势</h4>
                  <p>近 12 个月 · 单量 / {{ showMoney ? '收入' : '完成' }}</p>
                </div>
                <router-link to="/orders" class="link">订单列表 <Icon icon="ri:arrow-right-s-line" /></router-link>
              </div>
              <div class="dc-body"><ChartBox :option="trendOption" fill :loading="loading" /></div>
            </div>
          </div>
        </div>

        <!-- 本月概览 -->
        <div class="grid-stack-item" gs-id="overview" gs-w="4" gs-h="13" gs-min-w="3" gs-min-h="9">
          <div class="grid-stack-item-content">
            <div class="dash-card">
              <div class="dc-head gs-head">
                <div><h4>本月概览</h4><p>{{ currentMonth }}</p></div>
                <span class="mini-badge">实时</span>
              </div>
              <div class="ov-body">
                <div class="ov-hero">
                  <span class="ov-label">{{ showMoney ? '本月收入（已结单）' : '本月新增订单' }}</span>
                  <div class="ov-number">
                    <CountTo
                      v-if="showMoney" :target="Number(kpis.month_income_cal ?? kpis.month_income ?? 0)"
                      prefix="¥"
                    />
                    <CountTo v-else :target="Number(kpis.month_new || 0)" />
                    <span v-if="monthDelta != null" class="delta" :class="monthDelta >= 0 ? 'up' : 'down'">
                      <Icon :icon="monthDelta >= 0 ? 'ri:arrow-up-s-fill' : 'ri:arrow-down-s-fill'" />
                      {{ Math.abs(monthDelta) }}%
                    </span>
                  </div>
                  <div v-if="showMoney && kpis.month_gross != null" class="ov-gross">
                    毛利 <b>¥{{ Number(kpis.month_gross).toLocaleString() }}</b>
                  </div>
                </div>
                <div class="ov-mini-grid">
                  <div class="ov-mini"><b>{{ kpis.month_new ?? 0 }}</b><span>本月新增</span></div>
                  <div class="ov-mini"><b>{{ kpis.active_orders ?? 0 }}</b><span>进行中</span></div>
                  <div class="ov-mini"><b>{{ showMoney ? '¥' + Number(cards.avg_price ?? 0).toLocaleString() : (kpis.week_completed ?? 0) }}</b><span>{{ showMoney ? '平均客单价' : '本周完成' }}</span></div>
                  <div class="ov-mini"><b>{{ cards.on_time_rate != null ? cards.on_time_rate + '%' : '—' }}</b><span>按时交付</span></div>
                </div>
                <div class="status-bar">
                  <span
                    v-for="seg in statusSegs" :key="seg.key"
                    :style="{ width: seg.pct + '%', background: seg.hex }" :title="`${seg.label} ${seg.count}`"
                  />
                </div>
                <div class="status-legend">
                  <div v-for="seg in statusSegs" :key="seg.key" class="sl-item">
                    <span class="sl-dot" :style="{ background: seg.hex }" />
                    <span>{{ seg.label }}</span>
                    <b>{{ seg.count }}</b>
                  </div>
                </div>
                <div v-if="qualityChips.length" class="quality-row">
                  <span class="qr-label">品质</span>
                  <span
                    v-for="qc in qualityChips" :key="qc.name" class="q-chip"
                    :style="{ color: qc.color, borderColor: qc.color + '55', background: qc.color + '12' }"
                  >{{ qc.name }} × {{ qc.count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 最近订单 -->
        <div class="grid-stack-item" gs-id="recent" gs-w="5" gs-h="12" gs-min-w="3" gs-min-h="8">
          <div class="grid-stack-item-content">
            <div class="dash-card">
              <div class="dc-head gs-head">
                <div><h4>最近订单</h4><p>最新 {{ recent.length }} 条</p></div>
                <router-link to="/orders" class="link">查看全部 <Icon icon="ri:arrow-right-s-line" /></router-link>
              </div>
              <div class="row-list">
                <button v-for="r in recent" :key="r.id" class="data-row recent-row" @click="router.push(`/orders/${r.id}`)">
                  <span class="row-main">
                    <span class="mono row-id">{{ r.id }}</span>
                    <span class="row-title">{{ r.title }}</span>
                  </span>
                  <span class="row-meta">
                    <ProjectTypeTag :project-type="r.project_type" />
                    <StatusTag :status="r.status" />
                    <span v-if="showMoney" class="price">¥{{ Number(r.owner_price ?? r.agent_price ?? 0).toLocaleString() }}</span>
                  </span>
                </button>
                <EmptyState v-if="!recent.length" compact icon="ri:file-list-3-line" title="还没有订单" description="从上方「新建订单」开始第一单" />
              </div>
            </div>
          </div>
        </div>

        <!-- 交付提醒 -->
        <div class="grid-stack-item" gs-id="due" gs-w="3" gs-h="12" gs-min-w="3" gs-min-h="8">
          <div class="grid-stack-item-content">
            <div class="dash-card">
              <div class="dc-head gs-head">
                <div><h4>交付提醒</h4><p>7 天内到期 · 含逾期</p></div>
                <span v-if="overdueCount" class="danger-badge">{{ overdueCount }} 逾期</span>
              </div>
              <div v-if="dueList.length" class="row-list due-list">
                <button v-for="d in dueList" :key="d.id" class="data-row due-row" @click="router.push(`/orders/${d.id}`)">
                  <span class="due-chip" :class="dueClass(d.days_left)">{{ dueText(d.days_left) }}</span>
                  <span class="row-main">
                    <span class="row-title">{{ d.title }}</span>
                    <span class="row-sub mono">{{ d.id }} · {{ d.deadline }}</span>
                  </span>
                </button>
                <div class="due-foot">共 {{ dueList.length }} 条临期<router-link to="/orders">处理订单 →</router-link></div>
              </div>
              <EmptyState v-else compact icon="ri:checkbox-circle-line" title="近期没有临期交付" description="7 天内到期的进行中订单会显示在这里" tone="var(--success)" />
            </div>
          </div>
        </div>

        <!-- 项目类型分布 -->
        <div class="grid-stack-item" gs-id="cat" gs-w="4" gs-h="12" gs-min-w="3" gs-min-h="9">
          <div class="grid-stack-item-content">
            <div class="dash-card">
              <div class="dc-head gs-head">
                <div><h4>项目类型分布</h4><p>全部订单类型占比</p></div>
              </div>
              <div class="cat-body">
                <div class="donut-wrap">
                  <ChartBox :option="categoryOption" fill :loading="loading" />
                  <div class="donut-center">
                    <b>{{ catTotal }}</b><span>总单量</span>
                  </div>
                </div>
                <div class="cat-stats">
                  <div v-for="c in catStats" :key="c.label" class="cat-cell">
                    <span class="cat-dot" :style="{ background: c.hex }" />
                    <span>{{ c.label }}</span>
                    <b>{{ c.value }}</b>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 运营健康度 -->
        <div class="grid-stack-item" gs-id="radar" gs-w="4" gs-h="11" gs-min-w="3" gs-min-h="9">
          <div class="grid-stack-item-content">
            <div class="dash-card">
              <div class="dc-head gs-head">
                <div><h4>运营健康度</h4><p>六维评估 · 0-100</p></div>
                <span class="mini-badge">{{ healthScore }}</span>
              </div>
              <div v-if="radarList.length" class="dc-body radar-body">
                <ChartBox :option="radarOption" fill />
              </div>
              <EmptyState v-else compact icon="ri:radar-line" title="暂无评估数据" />
              <div class="radar-legend">
                <div v-for="r in radarList" :key="r.name" class="rl-item">
                  <span>{{ r.name }}</span><b>{{ r.value }}</b>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 代理排行 -->
        <div v-if="auth.isAdmin" class="grid-stack-item" gs-id="rank" gs-w="4" gs-h="11" gs-min-w="3" gs-min-h="8">
          <div class="grid-stack-item-content">
            <div class="dash-card">
              <div class="dc-head gs-head">
                <div><h4>代理排行</h4><p>按单量排序 · 前 4 名</p></div>
              </div>
              <div v-if="agentRank.length" class="rank-list">
                <div v-for="(a, i) in agentRank" :key="a.id || a.name" class="rank-row">
                  <span class="rank-no" :class="{ top: i < 3 }">{{ i + 1 }}</span>
                  <span class="rank-info">
                    <b>{{ a.name }}</b>
                    <small>结单 {{ a.closed }} / 总 {{ a.count }}</small>
                  </span>
                  <span class="rank-right">
                    <b>{{ a.count }}</b>
                    <i :style="{ width: Math.max(12, (a.count / maxRankCount) * 54) + 'px', background: rankColors[i % rankColors.length] }" />
                  </span>
                </div>
              </div>
              <EmptyState v-else compact icon="ri:user-star-line" title="暂无代理订单" />
            </div>
          </div>
        </div>

        <!-- 热力图 -->
        <div class="grid-stack-item" gs-id="heat" gs-w="4" gs-h="11" gs-min-w="3" gs-min-h="8">
          <div class="grid-stack-item-content">
            <div class="dash-card">
              <div class="dc-head gs-head">
                <div><h4>接单活跃</h4><p>周一至周日 · 按时段</p></div>
              </div>
              <div class="heat-wrap">
                <div class="heat-main">
                  <div class="heat-cols">
                    <div v-for="(row, di) in heatmap" :key="di" class="heat-row">
                      <span class="heat-day">{{ heatDays[di] }}</span>
                      <div class="heat-cells">
                        <span
                          v-for="(v, hi) in row" :key="hi" class="heat-cell"
                          :style="{ background: heatColor(v) }" :title="`周${heatDays[di]} ${heatHours[hi]}时：${v} 单`"
                        />
                      </div>
                    </div>
                  </div>
                  <div class="heat-hours"><span v-for="h in heatHours" :key="h">{{ h }}</span></div>
                </div>
              </div>
              <div class="heat-legend">
                <span>少</span><i v-for="i in 5" :key="i" :style="{ background: heatLegend[i - 1] }" /><span>多</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

  <div v-if="reportOpen" class="rp-mask" @click.self="reportOpen = false">
    <aside class="rp-panel" role="dialog" aria-modal="true" aria-label="AI 经营报告">
        <header class="rp-head">
          <div class="rp-head-main">
            <span class="rp-head-icon"><Icon icon="ri:sparkling-2-line" /></span>
            <div>
              <h3>AI 经营报告</h3>
              <p>基于真实经营数据生成，可复制到文档或直接发给客户</p>
            </div>
          </div>
          <button type="button" class="rp-close" aria-label="关闭报告" @click="reportOpen = false">
            <Icon icon="ri:close-line" />
          </button>
        </header>
        <div class="rp-toolbar">
          <el-radio-group v-model="reportPeriod" size="small">
            <el-radio-button value="week">近 7 天</el-radio-button>
            <el-radio-button value="month">近 30 天</el-radio-button>
          </el-radio-group>
          <el-button type="primary" size="small" :loading="reportLoading" @click="genReport">
            <Icon icon="ri:sparkling-2-line" /> {{ reportData ? '重新生成' : '生成报告' }}
          </el-button>
          <el-button v-if="reportData" size="small" @click="copyReport">复制全文</el-button>
        </div>
        <div v-loading="reportLoading" class="rp-wrap">
          <div v-if="reportData" class="rp-body">
            <div class="rp-meta">{{ reportData.generated_at }} 生成 · {{ reportData.model }} · 数据库真实统计</div>
            <div class="rp-content" v-html="reportHtml" />
          </div>
          <EmptyState v-else icon="ri:bar-chart-box-line" title="还没有生成报告" description="基于真实经营数据，由 DeepSeek 输出分析与建议" />
        </div>
    </aside>
  </div>
  </div>
</template>

<script>
// 管理员在设置里存的默认布局（管理员 / 普通用户各一套）。
// 放在模块级：路由切换会重建组件实例，这份缓存要跨实例保留。
const defaultLayoutCache = { admin: null, user: null }
</script>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'

import { GridStack } from 'gridstack'
import 'gridstack/dist/gridstack.css'
import http from '../api'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import ChartBox from '../components/ChartBox.vue'
import CountTo from '../components/CountTo.vue'
import StatCard from '../components/StatCard.vue'
import PageSkeleton from '../components/ui/PageSkeleton.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatusTag from '../components/StatusTag.vue'
import ProjectTypeTag from '../components/ProjectTypeTag.vue'
import {
  animCallbacks, artLegend, artTooltip, buildArea, buildBar, catAxis,
  moneyLabel, valueAxis,
} from '../utils/artChart'
import { STATUS_META, STATUS_ORDER } from '../constants/orderMeta'

const auth = useAuthStore()
const themeStore = useThemeStore()
const router = useRouter()

const loading = ref(true)
const loaded = ref(false)
const error = ref('')
const updatedAt = ref(null)
const data = ref({
  cards: {}, status_counts: {}, trend: [], quality_dist: [], project_type_counts: {},
  agent_rank: [], recent: [], due_soon: [], kpis: {}, radar: [], activity_heatmap: [],
})
const risk = ref({ days: 3, summary: {}, overdue: [], soon: [] })
const riskItems = computed(() => [...(risk.value.overdue || []), ...(risk.value.soon || [])].slice(0, 5))
async function loadRisk() {
  try { risk.value = await http.get('/stats/deadline-risk', { params: { days: 3 } }) } catch { /* 非关键数据，忽略 */ }
}

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const displayName = computed(() => auth.user?.display_name || auth.user?.username || '')
const currentMonth = computed(() => `${new Date().getFullYear()} 年 ${new Date().getMonth() + 1} 月`)
const todayLabel = computed(() => new Date().toLocaleDateString('zh-CN', { weekday: 'long', month: 'long', day: 'numeric' }))
const updatedText = computed(() => updatedAt.value ? updatedAt.value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '—')

const cards = computed(() => data.value.cards || {})
const kpis = computed(() => data.value.kpis || {})
// fail-closed：字段缺失（旧后端 / 响应裁剪 / 局部报错）时按「不可见」处理，
// 避免契约漂移时默认泄露真实价。
const showMoney = computed(() => data.value.show_money === true)
const monthDelta = computed(() =>
  kpis.value.month_income_cal_delta != null ? kpis.value.month_income_cal_delta : kpis.value.month_income_delta
)

const statCards = computed(() => {
  const n = (v) => Number(v ?? 0)
  const income = showMoney.value
    ? { label: auth.isAgent ? '总收入' : '总收入（已结单）', value: n(cards.value.income), prefix: '¥', icon: 'ri:money-cny-circle-line', color: '#38c0fc', delta: kpis.value.month_income_delta, to: '/orders' }
    : { label: '按时交付率', value: cards.value.on_time_rate != null ? cards.value.on_time_rate + '%' : '—', icon: 'ri:time-line', color: '#38c0fc', sub: '按完成时间对比交付期限' }
  return [
    income,
    { label: '总单量', value: n(cards.value.total), icon: 'ri:stack-line', color: '#5d87ff', delta: kpis.value.week_new_delta, to: '/orders' },
    { label: '已结单', value: n(cards.value.closed), icon: 'ri:checkbox-circle-line', color: '#13deb9', sub: `完成 ${cards.value.completed ?? 0} 单`, to: '/orders' },
    { label: '制作中', value: n(cards.value.in_progress), icon: 'ri:loader-4-line', color: '#ffae1f', sub: `本周完成 ${kpis.value.week_completed ?? 0} 单`, to: '/orders' },
  ]
})

/* ===== 图表 ===== */
const trendOption = computed(() => {
  void themeStore.mode
  const t = data.value.trend || []
  const withMoney = showMoney.value
  return {
    tooltip: artTooltip({
      trigger: 'axis',
      valueFormatter: (v) => (typeof v === 'number' ? v.toLocaleString('zh-CN') : v),
    }),
    legend: artLegend({ data: withMoney ? ['单量', '收入'] : ['单量'], top: 0, right: 0 }),
    grid: { left: 4, right: 10, top: 34, bottom: 2, containLabel: true },
    xAxis: catAxis(t.map((x) => x.month.slice(2)), { boundaryGap: true }),
    yAxis: [
      valueAxis({ minInterval: 1, splitNumber: 4, alignTicks: true }),
      ...(withMoney ? [valueAxis({ splitNumber: 4, alignTicks: true, splitLine: { show: false }, axisLabel: { formatter: (v) => moneyLabel(v) } })] : []),
    ],
    series: [
      {
        name: '单量', type: 'bar', barMaxWidth: 18,
        itemStyle: { color: buildBar('#5d87ff'), borderRadius: [4, 4, 0, 0] },
        data: t.map((x) => x.orders),
        ...animCallbacks(),
      },
      ...(withMoney ? [{
        name: '收入', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'circle', symbolSize: 5, showSymbol: false,
        lineStyle: { width: 2.4, color: '#13deb9' },
        itemStyle: { color: '#13deb9', borderColor: chartCardColor.value, borderWidth: 2 },
        areaStyle: { color: buildArea('#13deb9') },
        emphasis: { focus: 'series', lineStyle: { width: 3.2 } },
        data: t.map((x) => x.income),
        ...animCallbacks(),
      }] : []),
    ],
  }
})

const catStats = computed(() => {
  const cc = data.value.project_type_counts || {}
  return [
    { label: '纯设计', icon: '⌨️', value: Number(cc.program || 0), hex: '#5d87ff' },
    { label: '纯论文', icon: '📑', value: Number(cc.thesis || 0), hex: '#13deb9' },
    { label: '论文+设计', icon: '📘', value: Number(cc.thesis_program || 0), hex: '#b48df3' },
  ]
})
const catTotal = computed(() => catStats.value.reduce((a, b) => a + b.value, 0))

// Canvas 不解析 CSS 变量：图表里的底色必须取实际色值，否则 ECharts 会把描边画成黑色。
const chartCardColor = computed(() => (themeStore.isDark ? '#161618' : '#ffffff'))
const activeCatStats = computed(() => catStats.value.filter((c) => c.value > 0))

const categoryOption = computed(() => {
  void themeStore.mode
  const cats = activeCatStats.value
  const hasGap = cats.length > 1
  return {
    tooltip: artTooltip({ trigger: 'item', formatter: '{b}<br/>{c} 单 · {d}%' }),
    series: [{
      name: '项目类型分布', type: 'pie', radius: ['56%', '80%'], center: ['50%', '50%'],
      avoidLabelOverlap: false,
      // 单一种类时不描边，避免圆环接缝；多类别用卡片底色留出干净间隙。
      itemStyle: {
        borderRadius: 10,
        borderColor: chartCardColor.value,
        borderWidth: hasGap ? 2 : 0,
      },
      padAngle: hasGap ? 1.5 : 0,
      label: { show: false }, labelLine: { show: false },
      emphasis: { scale: true, scaleSize: 6 },
      color: cats.map((c) => c.hex),
      data: cats.map((c) => ({ name: c.label, value: c.value })),
      ...animCallbacks(80, 900),
      animationType: 'expansion',
    }],
  }
})

const radarList = computed(() => data.value.radar || [])
const healthScore = computed(() => {
  if (!radarList.value.length) return '—'
  return Math.round(radarList.value.reduce((a, b) => a + Number(b.value || 0), 0) / radarList.value.length)
})
const radarOption = computed(() => {
  void themeStore.mode
  const dark = themeStore.isDark
  return {
    tooltip: artTooltip({ trigger: 'item' }),
    radar: {
      indicator: radarList.value.map((x) => ({ name: x.name, max: 100 })),
      radius: '68%', center: ['50%', '50%'],
      axisName: { show: false },
      splitLine: { lineStyle: { color: dark ? 'rgba(255,255,255,.1)' : '#e6eaf0' } },
      axisLine: { lineStyle: { color: dark ? 'rgba(255,255,255,.1)' : '#e6eaf0' } },
      splitArea: {
        show: true,
        areaStyle: { color: dark ? ['rgba(255,255,255,.015)', 'rgba(255,255,255,.04)'] : ['rgba(16,24,40,.015)', 'rgba(16,24,40,.04)'] },
      },
    },
    series: [{
      type: 'radar', symbolSize: 4,
      data: [{
        value: radarList.value.map((x) => x.value), name: '健康度',
        lineStyle: { width: 2, color: '#5d87ff' },
        itemStyle: { color: '#5d87ff' },
        areaStyle: { color: 'rgba(93,135,255,.14)' },
        emphasis: { areaStyle: { color: 'rgba(93,135,255,.26)' }, lineStyle: { width: 3 } },
      }],
      ...animCallbacks(120, 900),
    }],
  }
})

const recent = computed(() => (data.value.recent || []).slice(0, 8))
const dueList = computed(() => (data.value.due_soon || []).slice(0, 6))
const overdueCount = computed(() => dueList.value.filter((d) => d.days_left < 0).length)

function dueClass(days) {
  if (days < 0) return 'over'
  if (days === 0) return 'today'
  if (days <= 3) return 'soon'
  return 'far'
}
function dueText(days) {
  if (days < 0) return `逾期 ${-days} 天`
  if (days === 0) return '今天到期'
  return `${days} 天后`
}

const rankColors = ['#5d87ff', '#38c0fc', '#ffae1f', '#13deb9', '#b48df3', '#ff4d4f']
const agentRank = computed(() => (data.value.agent_rank || []).slice(0, 4))
const maxRankCount = computed(() => Math.max(1, ...agentRank.value.map((a) => Number(a.count || 0))))

const statusSegs = computed(() => {
  const counts = data.value.status_counts || {}
  const total = Object.values(counts).reduce((a, b) => a + Number(b || 0), 0) || 1
  return STATUS_ORDER.filter((k) => Number(counts[k] || 0) > 0).map((k) => ({
    key: k, label: STATUS_META[k].label, hex: STATUS_META[k].hex,
    count: Number(counts[k] || 0), pct: Math.max(2, Math.round((Number(counts[k] || 0) / total) * 100)),
  }))
})
const qualityChips = computed(() => (data.value.quality_dist || []).filter((q) => q.count > 0))

const heatDays = ['一', '二', '三', '四', '五', '六', '日']
const heatHours = ['0-4', '4-8', '8-12', '12-16', '16-20', '20-24']
const heatLegend = ['#252530', '#0d5c4c', '#0f8a70', '#11b493', '#13deb9']
const heatmap = computed(() => data.value.activity_heatmap || Array.from({ length: 7 }, () => [0, 0, 0, 0, 0, 0]))
function heatColor(v) {
  if (!v) return themeStore.isDark ? 'var(--card-3)' : '#e8edf4'
  if (v === 1) return heatLegend[1]
  if (v === 2) return heatLegend[2]
  if (v <= 4) return heatLegend[3]
  return heatLegend[4]
}

const meteors = Array.from({ length: 8 }, (_, i) => ({
  id: i,
  style: {
    left: `${8 + i * 12}%`,
    animationDuration: `${3 + (i % 4)}s`,
    animationDelay: `${(i % 5) * 0.8}s`,
    opacity: 0.25 + (i % 3) * 0.12,
  },
}))

/* ===== GridStack ===== */
const GRID_KEY = 'dash-grid-layout:v3:' + (auth.isAdmin ? 'admin' : 'user')
const GRID_COLS = 12
const GRID_BREAKPOINT = 1200
function gridCellHeight() {
  if (window.innerWidth >= 3000) return 38
  if (window.innerWidth >= 2200) return 30
  return 22
}
const GRID_OPTIONS = {
  column: GRID_COLS, cellHeight: gridCellHeight(), margin: 8,
  handle: '.gs-head', resizable: { handles: 'se' }, animate: true,
  float: true, // 拖动 / 缩放后自动上移补位，不留空洞
}
// 管理员默认布局（含「代理业绩榜」卡片）
const DEFAULT_LAYOUT = [
  { id: 'trend', x: 0, y: 0, w: 8, h: 17 },
  { id: 'overview', x: 8, y: 0, w: 4, h: 17 },
  { id: 'recent', x: 0, y: 17, w: 5, h: 13 },
  { id: 'due', x: 5, y: 17, w: 3, h: 13 },
  { id: 'cat', x: 8, y: 17, w: 4, h: 13 },
  { id: 'rank', x: 0, y: 30, w: 4, h: 11 },
  { id: 'heat', x: 4, y: 30, w: 4, h: 11 },
  { id: 'radar', x: 8, y: 30, w: 4, h: 11 },
]
// 普通用户默认布局：没有业绩榜卡片，热力图与雷达图各占一半
const DEFAULT_LAYOUT_USER = [
  { id: 'trend', x: 0, y: 0, w: 8, h: 17 },
  { id: 'overview', x: 8, y: 0, w: 4, h: 17 },
  { id: 'recent', x: 0, y: 17, w: 5, h: 13 },
  { id: 'due', x: 5, y: 17, w: 3, h: 13 },
  { id: 'cat', x: 8, y: 17, w: 4, h: 13 },
  { id: 'heat', x: 0, y: 30, w: 6, h: 10 },
  { id: 'radar', x: 6, y: 30, w: 6, h: 10 },
]

const gridEl = ref(null)
const gridActive = ref(false)
let grid = null
let gridResizeTimer = null

function currentDomIds() {
  if (!gridEl.value) return new Set()
  return new Set([...gridEl.value.children].map((el) => el.getAttribute('gs-id')).filter(Boolean))
}
/** 丢弃页面上已不存在的卡片，并把各项收窄到当前网格范围内 */
function normalizeLayout(items) {
  const domIds = currentDomIds()
  return items
    .filter((n) => n && domIds.has(n.id) && [n.x, n.y, n.w, n.h].every(Number.isFinite))
    .map((n) => {
      const w = Math.min(Math.max(1, n.w | 0), GRID_COLS)
      return { id: n.id, x: Math.min(Math.max(0, n.x | 0), GRID_COLS - w), y: Math.max(0, n.y | 0), w, h: Math.max(1, n.h | 0) }
    })
}
function readSavedLayout() {
  try {
    const raw = JSON.parse(localStorage.getItem(GRID_KEY) || 'null')
    const items = raw != null && Array.isArray(raw.items) ? raw.items : []
    const clean = normalizeLayout(items)
    if (clean.length) return clean
  } catch { /* 数据损坏时按「没有保存过」处理 */ }
  return null
}
/** 取管理员在设置里存的默认布局；取不到就保持为空，退回内置默认布局 */
async function fetchDefaultLayouts() {
  try {
    const data = await http.get('/settings/dash-layout')
    if (data) {
      if (data.admin != null) defaultLayoutCache.admin = data.admin
      if (data.user != null) defaultLayoutCache.user = data.user
    }
  } catch { /* 忽略：使用内置默认布局 */ }
}
// 生效的初始布局：本地保存的 > 管理员存的默认布局
function resolveInitialLayout() {
  const saved = readSavedLayout()
  if (saved) return saved
  try {
    const stored = auth.isAdmin ? defaultLayoutCache.admin : defaultLayoutCache.user
    if (Array.isArray(stored) && stored.length) {
      const clean = normalizeLayout(stored)
      if (clean.length) return clean
    }
  } catch { /* 同上 */ }
  return null
}
function persistLayout() {
  if (!grid) return
  const items = grid.save(false).map((n) => ({ id: n.id, x: n.x, y: n.y, w: n.w, h: n.h }))
  localStorage.setItem(GRID_KEY, JSON.stringify({ v: 12, items }))
}
function initGrid() {
  if (grid || !gridEl.value) return
  const saved = readSavedLayout()
  if (saved) {
    grid = GridStack.init({ ...GRID_OPTIONS }, gridEl.value)
    grid.load(saved, false)
    grid.on('dragstop resizestop', persistLayout)
    return
  }
  // 本地没有保存过：先取管理员存的默认布局，再初始化网格（期间组件可能已切走）
  ;(async () => {
    await fetchDefaultLayouts()
    if (grid || !gridEl.value) return
    grid = GridStack.init({ ...GRID_OPTIONS }, gridEl.value)
    const layout = resolveInitialLayout() || (auth.isAdmin ? DEFAULT_LAYOUT : DEFAULT_LAYOUT_USER)
      .filter((n) => currentDomIds().has(n.id)).map((n) => ({ ...n }))
    grid.load(layout, false)
    grid.on('dragstop resizestop', persistLayout)
  })()
}
function destroyGrid() {
  if (!grid) return
  try { grid.destroy(false) } catch { /* DOM 即将重建 */ }
  grid = null
}
async function syncGrid() {
  // 刷新数据时保留 GridStack 实例：销毁/重建会改动 Vue 托管的卡片 DOM，
  // 在 patch 期间触发 insertBefore 空指针，也会让图表容器瞬间丢失尺寸。
  if (gridActive.value && !error.value) {
    if (grid) return
    await nextTick()
    if (gridActive.value && !error.value && !grid) initGrid()
    return
  }
  if (!grid) return
  destroyGrid()
  await nextTick()
}
watch([gridActive, loading, error], syncGrid)
function onGridResize() {
  clearTimeout(gridResizeTimer)
  gridResizeTimer = setTimeout(() => {
    const active = window.innerWidth > GRID_BREAKPOINT
    if (active !== gridActive.value) gridActive.value = active
    else if (grid) grid.cellHeight(gridCellHeight())
  }, 160)
}
async function resetLayout() {
  try {
    await ElMessageBox.confirm('将清除已保存的自定义布局，恢复默认卡片排列。', '重置布局', {
      type: 'warning', confirmButtonText: '重置', cancelButtonText: '取消',
    })
  } catch { return }
  localStorage.removeItem(GRID_KEY)
  // 「默认」= 管理员存过的布局；没存过才是内置的那套
  await fetchDefaultLayouts()
  const stored = auth.isAdmin ? defaultLayoutCache.admin : defaultLayoutCache.user
  const source = Array.isArray(stored) && stored.length ? stored : (auth.isAdmin ? DEFAULT_LAYOUT : DEFAULT_LAYOUT_USER)
  if (grid) grid.load(source.filter((n) => currentDomIds().has(n.id)).map((n) => ({ ...n })), false)
  ElMessage.success('已恢复默认布局')
}
/** 把当前排列存为默认布局（管理员 / 代理可用），之后「重置布局」会回到它 */
async function saveAsDefault() {
  if (!grid) return
  try {
    const items = [...gridEl.value.children].map((el) => ({
      id: el.getAttribute('gs-id'),
      x: +el.getAttribute('gs-x'), y: +el.getAttribute('gs-y'),
      w: +el.getAttribute('gs-w'), h: +el.getAttribute('gs-h'),
    }))
    await http.post('/settings/dash-layout', { scope: auth.isAdmin ? 'admin' : 'user', items })
    ElMessage.success('当前布局已存为默认（重置布局后将恢复到它）')
  } catch {
    ElMessage.error('保存失败，请重试')
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    // 顺带刷新默认布局缓存，失败不影响下面的数据加载
    await fetchDefaultLayouts()
    data.value = await http.get('/stats/overview')
    loaded.value = true
    updatedAt.value = new Date()
  } catch (e) {
    error.value = e?.response?.data?.detail || '无法连接服务，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  gridActive.value = window.innerWidth > GRID_BREAKPOINT
  window.addEventListener('resize', onGridResize)
  load()
  loadRisk()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onGridResize)
  clearTimeout(gridResizeTimer)
  destroyGrid()
  document.body.style.overflow = ''
})

/* ===== AI 报告 ===== */
const reportOpen = ref(false)
const reportPeriod = ref('week')
const reportLoading = ref(false)
const reportData = ref(null)
function openReport() {
  reportOpen.value = true
  if (!reportData.value && !reportLoading.value) genReport()
}
watch(reportOpen, (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
})
async function genReport() {
  reportLoading.value = true
  try {
    reportData.value = await http.get('/stats/ai-report', { params: { period: reportPeriod.value }, timeout: 180000 })
  } catch { /* 拦截器处理 */ } finally { reportLoading.value = false }
}
async function copyReport() {
  try {
    await navigator.clipboard.writeText(reportData.value.report)
    ElMessage.success('报告已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本复制')
  }
}
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
const reportHtml = computed(() => {
  const md = reportData.value?.report || ''
  const lines = md.split(/\r?\n/)
  const out = []
  let inList = false
  for (const raw of lines) {
    const line = esc(raw.trimEnd())
    const listItem = line.match(/^[-*]\s+(.*)/)
    if (listItem) {
      if (!inList) { out.push('<ul>'); inList = true }
      out.push(`<li>${listItem[1]}</li>`)
      continue
    }
    if (inList) { out.push('</ul>'); inList = false }
    if (/^###\s+/.test(line)) out.push(`<h4>${line.replace(/^###\s+/, '')}</h4>`)
    else if (/^##\s+/.test(line)) out.push(`<h3>${line.replace(/^##\s+/, '')}</h3>`)
    else if (/^#\s+/.test(line)) out.push(`<h3>${line.replace(/^#\s+/, '')}</h3>`)
    else if (line === '') out.push('')
    else out.push(`<p>${line}</p>`)
  }
  if (inList) out.push('</ul>')
  return out.join('\n').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
})
</script>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 18px; }

/* ===== 欢迎横幅 ===== */
.welcome {
  position: relative; overflow: hidden;
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
  padding: 26px 28px;
  background:
    radial-gradient(900px 220px at 8% -30%, rgba(93, 135, 255, 0.32), transparent 60%),
    radial-gradient(700px 260px at 92% 120%, rgba(19, 222, 185, 0.16), transparent 60%),
    linear-gradient(135deg, #151a2c 0%, #101116 55%, #0e1118 100%);
  border-color: rgba(120, 150, 255, 0.18);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
}
html.light .welcome {
  background:
    radial-gradient(900px 220px at 8% -30%, rgba(93, 135, 255, 0.2), transparent 60%),
    radial-gradient(700px 260px at 92% 120%, rgba(19, 222, 185, 0.12), transparent 60%),
    linear-gradient(135deg, #eef3ff 0%, #ffffff 60%, #f5fbfa 100%);
  border-color: rgba(93, 135, 255, 0.16);
  box-shadow: 0 18px 40px rgba(16, 24, 40, 0.08);
}
.welcome-glow {
  position: absolute; width: 420px; height: 420px; right: -120px; top: -220px;
  border-radius: 50%; background: radial-gradient(circle, rgba(93, 135, 255, 0.28), transparent 62%);
  pointer-events: none;
}
.meteors { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
.meteor {
  position: absolute; top: -80px; width: 2px; height: 64px;
  background: linear-gradient(to top, rgba(255,255,255,.5), rgba(255,255,255,.1), transparent);
  border-radius: 2px;
  animation: meteor-fall 4s linear infinite;
}
.meteor::after {
  content: ''; position: absolute; left: -1px; bottom: -2px; width: 4px; height: 4px;
  border-radius: 50%; background: #fff; box-shadow: 0 0 10px rgba(255,255,255,.8);
}
html.light .meteor { display: none; }
.welcome-main { position: relative; z-index: 1; min-width: 0; }
.welcome-eyebrow { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: rgba(255,255,255,.72); font-weight: 500; }
html.light .welcome-eyebrow { color: var(--text-2); }
.live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--success); box-shadow: 0 0 10px var(--success); }
.welcome-title { margin: 10px 0 0; font-size: 26px; line-height: 1.25; font-weight: 700; letter-spacing: -0.5px; color: #fff; }
html.light .welcome-title { color: var(--text); }
.welcome-sub { margin: 7px 0 0; font-size: 12.5px; color: rgba(255,255,255,.55); }
html.light .welcome-sub { color: var(--text-3); }
.welcome-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 18px; }
.w-btn {
  height: 34px; padding: 0 13px; display: inline-flex; align-items: center; gap: 6px;
  border-radius: var(--radius-sm); border: 1px solid rgba(255,255,255,.16);
  background: rgba(255,255,255,.07); color: rgba(255,255,255,.86);
  font-size: 12.5px; font-weight: 500; cursor: pointer; transition: all .18s;
  backdrop-filter: blur(8px);
}
.w-btn:hover { background: rgba(255,255,255,.14); border-color: rgba(255,255,255,.3); transform: translateY(-1px); }
.w-btn.primary { background: #fff; border-color: #fff; color: #315bd9; font-weight: 650; }
.w-btn.primary:hover { background: #eef3ff; }
.w-btn.ghost { background: transparent; }
html.light .w-btn { border-color: var(--border-2); background: var(--card); color: var(--text-2); }
html.light .w-btn.primary { background: var(--brand); border-color: var(--brand); color: #fff; }
.welcome-side { position: relative; z-index: 1; display: flex; gap: 10px; flex: none; }
.ws-cell {
  min-width: 84px; padding: 12px 14px; border-radius: var(--radius);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);
  display: flex; flex-direction: column; gap: 4px;
  backdrop-filter: blur(8px);
}
.ws-cell span { font-size: 10.5px; color: rgba(255,255,255,.55); }
.ws-cell b { font-size: 19px; color: #fff; font-variant-numeric: tabular-nums; }
html.light .ws-cell { background: rgba(255,255,255,.7); border-color: var(--border); }
html.light .ws-cell span { color: var(--text-3); }
html.light .ws-cell b { color: var(--text); }
.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.error-card { padding: 0; }

/* ===== 交期风险 ===== */
.risk-card { padding: 15px 18px; }
.rc-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.rc-title { display: flex; align-items: center; gap: 10px; min-width: 0; }
.rc-ico {
  width: 32px; height: 32px; border-radius: 10px; flex: none;
  display: flex; align-items: center; justify-content: center;
  font-size: 17px; color: var(--warning); background: var(--warning-weak);
}
.rc-title h4 { margin: 0; font-size: 14px; font-weight: 600; }
.rc-title p { margin: 2px 0 0; font-size: 11px; color: var(--text-3); }
.rc-body { display: flex; align-items: center; gap: 18px; }
.rc-counts { display: flex; gap: 10px; flex: none; }
.rc-count {
  min-width: 96px; padding: 10px 14px; border-radius: var(--radius-sm);
  display: flex; flex-direction: column; gap: 2px; border: 1px solid transparent;
}
.rc-count b { font-size: 22px; line-height: 1.1; font-variant-numeric: tabular-nums; }
.rc-count span { font-size: 11px; }
.rc-count.danger { background: var(--danger-weak); border-color: rgba(255,77,79,.16); }
.rc-count.danger b { color: var(--danger); }
.rc-count.danger span { color: var(--danger); opacity: .8; }
.rc-count.warn { background: var(--warning-weak); border-color: rgba(255,174,31,.16); }
.rc-count.warn b { color: var(--warning); }
.rc-count.warn span { color: var(--warning); opacity: .85; }
.rc-list { list-style: none; margin: 0; padding: 0; flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.rc-list li {
  display: flex; align-items: center; gap: 8px; min-width: 0;
  padding: 6px 9px; border-radius: var(--radius-sm); cursor: pointer;
  background: var(--card-2); transition: background .15s;
}
.rc-list li:hover { background: var(--hover); }
.rc-order { font-size: 11.5px; font-weight: 600; color: var(--text-2); font-variant-numeric: tabular-nums; flex: none; }
.rc-name { flex: 1; min-width: 0; font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rc-days { flex: none; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px; }
.rc-days.danger { background: var(--danger-weak); color: var(--danger); }
.rc-days.warn { background: var(--warning-weak); color: var(--warning); }
@media (max-width: 900px) {
  .rc-body { flex-direction: column; align-items: stretch; }
  .rc-count { flex: 1; min-width: 0; }
}

/* ===== 网格 ===== */
.dash-grid-static { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.dash-grid-static > * { min-width: 0; }
.dash-grid-static [gs-id="trend"],
.dash-grid-static [gs-id="recent"],
.dash-grid-static [gs-id="overview"] { grid-column: span 2; }
/* 静态布局由内容撑高：固定 item 高度会让 chart 的百分比高度退化为 0，且长列表会压到下一行 */
.dash-grid-static [gs-id="trend"] .dc-body,
.dash-grid-static [gs-id="radar"] .radar-body { flex: 0 0 240px; height: 240px; }
.dash-grid-static [gs-id="cat"] .cat-body { height: 220px; flex: 0 0 220px; }
.dash-grid-static [gs-id="cat"] .donut-wrap { flex: 1 1 0; height: 100%; }
.dash-grid.grid-stack .grid-stack-item-content { display: flex; flex-direction: column; overflow: hidden; }
.dash-grid.grid-stack .dash-card { flex: 1; min-height: 0; }
.dash-grid.grid-stack .gs-head { cursor: grab; }
.dash-grid.grid-stack .gs-head:active { cursor: grabbing; }
.dash-grid :deep(.grid-stack-placeholder > .placeholder-content) {
  background-color: rgba(93, 135, 255, 0.07);
  border: 1px dashed rgba(93, 135, 255, 0.45);
  border-radius: var(--radius-lg);
}
.dash-grid :deep(.grid-stack-item > .ui-resizable-se) {
  background-image: none; transform: none; width: 12px; height: 12px;
  right: 10px; bottom: 10px; border-radius: 4px;
  background-color: rgba(93, 135, 255, 0.35); transition: background-color .15s;
}
.dash-grid :deep(.grid-stack-item:hover > .ui-resizable-se) { background-color: var(--brand); }

/* ===== 卡片 ===== */
.dash-card {
  display: flex; flex-direction: column; min-width: 0; min-height: 0;
  height: 100%; padding: 15px 17px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius-lg); transition: border-color .2s, box-shadow .2s;
}
.dash-card:hover { border-color: var(--border-2); }
.dc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 10px; flex: none; }
.dc-head h4 { margin: 0; font-size: 14.5px; font-weight: 600; color: var(--text); }
.dc-head p { margin: 2px 0 0; font-size: 11.5px; color: var(--text-3); }
.link { font-size: 12px; color: var(--text-3); display: inline-flex; align-items: center; gap: 2px; text-decoration: none; padding: 4px 6px; border-radius: 6px; }
.link:hover { color: var(--brand); background: var(--brand-weak); }
.mini-badge { font-size: 10.5px; color: var(--text-3); border: 1px solid var(--border); background: var(--card-2); border-radius: 999px; padding: 1px 8px; }
.dc-body { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }

/* 概览 */
.ov-body { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.ov-hero {
  padding: 13px 14px; border-radius: var(--radius);
  background: linear-gradient(135deg, rgba(93,135,255,.12), rgba(19,222,185,.05));
  border: 1px solid rgba(93,135,255,.2);
}
.ov-label { font-size: 11.5px; color: var(--text-2); }
.ov-number { display: flex; align-items: baseline; gap: 9px; margin-top: 5px; font-size: 27px; font-weight: 650; letter-spacing: -0.7px; color: var(--text); }
.delta { font-size: 11.5px; font-weight: 600; display: inline-flex; align-items: center; }
.delta.up { color: var(--success); }
.delta.down { color: var(--danger); }
.ov-gross { margin-top: 5px; font-size: 11.5px; color: var(--text-3); }
.ov-gross b { color: var(--success); }
.ov-mini-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.ov-mini {
  padding: 9px 11px; background: var(--card-2); border: 1px solid var(--border);
  border-radius: var(--radius-sm); display: flex; flex-direction: column; gap: 2px;
}
.ov-mini b { font-size: 16px; color: var(--text); font-variant-numeric: tabular-nums; }
.ov-mini span { font-size: 10.5px; color: var(--text-3); }
.status-bar { display: flex; gap: 2px; height: 6px; border-radius: 3px; overflow: hidden; background: var(--card-2); }
.status-bar span { transition: width .4s ease; }
.status-legend { display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px 12px; }
.sl-item { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-2); }
.sl-item b { margin-left: auto; color: var(--text); font-size: 11px; }
.sl-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.quality-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.qr-label { font-size: 10.5px; color: var(--text-3); }
.q-chip { font-size: 10.5px; padding: 1px 7px; border: 1px solid; border-radius: 999px; }

/* 列表行 */
.row-list { display: flex; flex-direction: column; min-height: 0; overflow: auto; }
.data-row {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  width: 100%; padding: 8px 6px; border: none; background: transparent; cursor: pointer;
  border-radius: var(--radius-xs); text-align: left; color: inherit;
  transition: background .15s, padding-left .15s;
}
.data-row + .data-row { border-top: 1px solid var(--border); }
.data-row:hover { background: var(--hover); padding-left: 10px; }
.row-main { display: flex; align-items: center; gap: 9px; min-width: 0; flex: 1; }
.row-id { font-size: 11px; color: var(--brand); flex-shrink: 0; }
.row-title { font-size: 12.5px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-sub { font-size: 10.5px; color: var(--text-3); margin-top: 2px; }
.row-meta { display: flex; align-items: center; gap: 7px; flex-shrink: 0; }
.row-meta .price { font-size: 12px; color: var(--text); }
.due-row { align-items: flex-start; }
.due-row .row-main { flex-direction: column; align-items: flex-start; gap: 2px; }
.due-chip { flex-shrink: 0; min-width: 58px; text-align: center; font-size: 10.5px; font-weight: 600; padding: 2px 7px; border-radius: 999px; }
.due-chip.over { background: var(--danger-weak); color: var(--danger); }
.due-chip.today { background: var(--warning-weak); color: var(--warning); }
.due-chip.soon { background: rgba(255,174,31,.1); color: #e0a13a; }
.due-chip.far { background: var(--card-2); color: var(--text-3); }
.due-foot { margin-top: auto; border-top: 1px solid var(--border); padding-top: 9px; font-size: 11px; color: var(--text-3); display: flex; justify-content: space-between; }
.due-foot a { font-size: 11px; }
.danger-badge { font-size: 10px; color: var(--danger); background: var(--danger-weak); border: 1px solid rgba(255,77,79,.2); padding: 1px 7px; border-radius: 999px; }

/* 环形 */
.cat-body { display: flex; flex: 1 1 0; min-height: 0; align-items: center; justify-content: center; gap: 14px; }
.donut-wrap { position: relative; flex: 1.15 1 0; max-width: 220px; height: 100%; min-height: 0; }
.donut-wrap::before {
  content: ''; position: absolute; left: 50%; top: 50%; height: 74%; aspect-ratio: 1;
  transform: translate(-50%, -50%); border-radius: 50%; pointer-events: none;
  background: radial-gradient(circle, rgba(93, 135, 255, 0.2), rgba(93, 135, 255, 0.06) 56%, transparent 72%);
  filter: blur(7px);
}
.donut-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
.donut-center b { font-size: 25px; color: var(--text); font-variant-numeric: tabular-nums; line-height: 1; letter-spacing: -0.02em; }
.donut-center span { font-size: 11px; color: var(--text-3); margin-top: 5px; letter-spacing: 0.04em; }
.cat-stats {
  flex: 0 0 132px; min-width: 0; display: flex; flex-direction: column;
  border-left: 1px solid var(--border); padding: 2px 0 2px 14px;
}
.cat-cell { flex: 1; display: flex; align-items: center; gap: 7px; min-width: 0; padding: 5px 0; font-size: 11.5px; color: var(--text-2); }
.cat-cell + .cat-cell { border-top: 1px solid var(--border); }
.cat-cell b { margin-left: auto; color: var(--text); font-size: 13px; font-variant-numeric: tabular-nums; }
.cat-dot { width: 6px; height: 6px; border-radius: 50%; }

/* 雷达 */
.radar-body { min-height: 0; }
.radar-legend { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3px 10px; margin-top: 6px; flex: none; }
.rl-item { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--text-3); }
.rl-item b { color: var(--text); font-variant-numeric: tabular-nums; }

/* 排行 */
.rank-list { display: flex; flex-direction: column; gap: 10px; }
.rank-row { display: flex; align-items: center; gap: 10px; }
.rank-no { width: 22px; height: 22px; border-radius: 7px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; color: var(--text-3); background: var(--card-2); }
.rank-no.top { background: var(--brand-grad); color: #fff; }
.rank-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.rank-info b { font-size: 12.5px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-info small { font-size: 10.5px; color: var(--text-3); margin-top: 1px; }
.rank-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
.rank-right b { font-size: 14px; font-variant-numeric: tabular-nums; }
.rank-right i { display: block; height: 3px; border-radius: 2px; transition: width .5s ease; }

/* 热力图 */
.heat-wrap { display: flex; flex: 1; min-height: 0; align-items: stretch; }
.heat-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.heat-cols { display: flex; flex-direction: column; gap: 3px; flex: 1; }
.heat-row { flex: 1; display: flex; align-items: stretch; gap: 4px; min-height: 12px; }
.heat-day { width: 12px; flex: none; display: flex; align-items: center; font-size: 9.5px; color: var(--text-3); }
.heat-cells { flex: 1; display: flex; gap: 3px; min-width: 0; }
.heat-cell { flex: 1; min-height: 12px; border-radius: 4px; transition: transform .15s, filter .15s; }
.heat-cell:hover { transform: scale(1.08); filter: brightness(1.25); }
.heat-hours { display: flex; gap: 3px; margin-top: 4px; padding-left: 16px; }
.heat-hours span { flex: 1; text-align: center; font-size: 8px; color: var(--text-4); }
.heat-legend { display: flex; align-items: center; gap: 4px; justify-content: flex-end; margin-top: 8px; font-size: 9.5px; color: var(--text-3); flex: none; }
.heat-legend i { width: 12px; height: 8px; border-radius: 2px; }

/* AI 报告：原生滑出面板，避免 ElDrawer 的 Teleport 与多根 Transition 警告 */
.rp-mask { position: fixed; inset: 0; z-index: 3000; display: flex; justify-content: flex-end; background: rgba(4, 6, 12, .58); backdrop-filter: blur(3px); -webkit-backdrop-filter: blur(3px); animation: rp-fade-in .2s ease; }
.rp-panel { width: min(560px, 100vw); height: 100vh; height: 100dvh; display: flex; flex-direction: column; padding: 22px 24px 0; background: var(--card); border-left: 1px solid var(--border-2); box-shadow: -28px 0 70px rgba(0, 0, 0, .42); animation: rp-slide-in .26s cubic-bezier(.22, 1, .36, 1); }
@keyframes rp-fade-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes rp-slide-in { from { transform: translateX(32px); opacity: .5; } to { transform: translateX(0); opacity: 1; } }
.rp-head { flex: 0 0 auto; display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
.rp-head-main { display: flex; align-items: flex-start; gap: 12px; min-width: 0; }
.rp-head-icon { width: 36px; height: 36px; border-radius: 10px; flex: 0 0 auto; display: grid; place-items: center; font-size: 18px; color: #9db8ff; background: linear-gradient(145deg, rgba(98, 133, 255, .24), rgba(98, 133, 255, .06)); border: 1px solid rgba(120, 150, 255, .26); }
.rp-head h3 { margin: 0; font-size: 17px; font-weight: 650; color: var(--text); }
.rp-head p { margin: 5px 0 0; font-size: 12px; line-height: 1.5; color: var(--text-3); }
.rp-close { width: 32px; height: 32px; flex: 0 0 auto; border-radius: 9px; display: grid; place-items: center; border: 1px solid var(--border); background: var(--card-2); color: var(--text-2); font-size: 16px; cursor: pointer; transition: color .16s, border-color .16s, background .16s; }
.rp-close:hover { color: var(--text); border-color: var(--border-2); background: rgba(255, 255, 255, .06); }
.rp-toolbar { flex: 0 0 auto; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 16px 0 14px; }
.rp-wrap { flex: 1 1 auto; min-height: 0; min-width: 0; overflow-y: auto; overscroll-behavior: contain; padding-bottom: 24px; }
.rp-body { display: flex; flex-direction: column; gap: 12px; }
.rp-meta { font-size: 11.5px; color: var(--text-3); padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.rp-content { font-size: 13px; line-height: 1.8; color: var(--text-2); }
.rp-content :deep(h3) { font-size: 15px; margin: 18px 0 8px; color: var(--text); }
.rp-content :deep(h4) { font-size: 13.5px; margin: 14px 0 6px; color: var(--text); }
.rp-content :deep(p) { margin: 6px 0; }
.rp-content :deep(ul) { margin: 6px 0; padding-left: 20px; }
.rp-content :deep(li) { margin: 3px 0; }
.rp-content :deep(strong) { color: var(--text); }

@media (max-width: 600px) {
  .rp-panel { padding: 18px 16px 0; border-left: 0; }
  .rp-head p { display: none; }
}

@media (max-width: 1200px) {
  .dash-grid-static { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dash-grid-static [gs-id="heat"] { grid-column: span 2; }
}
@media (max-width: 900px) {
  .welcome { flex-direction: column; align-items: flex-start; padding: 22px; }
  .welcome-side { width: 100%; }
  .ws-cell { flex: 1; min-width: 0; }
  .welcome-title { font-size: 22px; }
  .dash-grid-static { grid-template-columns: 1fr; }
  .dash-grid-static > * { grid-column: auto !important; height: auto !important; min-height: 300px; }
  .dash-grid-static [gs-id="recent"], .dash-grid-static [gs-id="rank"], .dash-grid-static [gs-id="heat"] { min-height: 280px; }
  /* 图表绘图高度见上方 .dash-grid-static 规则（901–1200 与移动端共用） */
}
@media (max-width: 600px) {
  .welcome-actions { width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .w-btn { width: 100%; justify-content: center; white-space: nowrap; }
  .welcome-actions .w-btn:last-child:nth-child(odd) { grid-column: 1 / -1; }
  .recent-row { flex-wrap: wrap; row-gap: 5px; padding: 9px 6px; }
  .recent-row .row-main { flex: 1 0 100%; }
  .recent-row .row-meta { width: 100%; justify-content: flex-end; }
  .welcome-side { flex-direction: column; }
  .ws-cell { flex-direction: row; align-items: center; justify-content: space-between; }
  .welcome-title { font-size: 20px; }
}
</style>
