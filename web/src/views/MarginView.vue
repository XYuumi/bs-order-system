<template>
  <div class="page-shell margin-page">
    <AppPageHeader
      title="毛利分析"
      description="成交价 - 写手报酬的订单级利润，仅管理员可见"
      icon="ri:money-cny-circle-line"
    >
      <template #actions>
        <el-date-picker
          v-model="month" type="month" value-format="YYYY-MM"
          placeholder="全部月份" clearable style="width: 150px"
          @change="load"
        />
        <el-button :loading="loading" @click="load">
          <Icon icon="ri:refresh-line" />刷新
        </el-button>
      </template>
    </AppPageHeader>

    <div class="stat-grid">
      <StatCard label="结单数" :value="summary.count" icon="ri:file-check-line" color="#6366f1" :loading="loading" />
      <StatCard label="成交额" :value="summary.revenue" prefix="¥" :decimals="2" icon="ri:money-dollar-circle-line" color="#0ea5e9" :loading="loading" />
      <StatCard label="写手成本" :value="summary.cost" prefix="¥" :decimals="2" icon="ri:user-star-line" color="#f59e0b" :loading="loading" />
      <StatCard label="毛利" :value="summary.profit" prefix="¥" :decimals="2" icon="ri:line-chart-line" color="#10b981" :loading="loading" />
      <StatCard
        label="毛利率" :value="summary.margin_rate ?? 0" suffix="%"
        :decimals="1" icon="ri:percent-line" color="#8b5cf6"
        :sub="summary.avg_profit != null ? `均单毛利 ¥${summary.avg_profit}` : ''"
        :loading="loading"
      />
    </div>

    <div class="chart-grid">
      <ChartCard
        title="近 6 个月利润趋势"
        subtitle="按订单完成/结单月份归集"
        :option="trendOption" :loading="loading" :empty="!data.trend?.length"
        empty-text="还没有已结单订单" height="300px"
      />
      <ChartCard
        title="品质利润分布"
        subtitle="按订单品质汇总毛利"
        :option="qualityOption" :loading="loading" :empty="!data.by_quality?.length"
        empty-text="暂无品质数据" height="300px"
      />
    </div>

    <section class="art-card table-card">
      <div class="card-head">
        <div class="title">
          <h4>品质明细</h4>
          <p>成交额、写手成本与毛利率，按毛利从高到低排序</p>
        </div>
        <span class="chip">{{ month || '全部' }} · {{ data.by_quality?.length || 0 }} 项</span>
      </div>
      <el-table :data="data.by_quality || []" row-key="code">
        <el-table-column prop="name" label="品质" min-width="120" />
        <el-table-column prop="count" label="订单数" width="90" align="right" />
        <el-table-column label="成交额" width="130" align="right">
          <template #default="{ row }">¥{{ yuan(row.revenue) }}</template>
        </el-table-column>
        <el-table-column label="成本" width="130" align="right">
          <template #default="{ row }">¥{{ yuan(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="毛利" width="130" align="right">
          <template #default="{ row }"><b class="profit">¥{{ yuan(row.profit) }}</b></template>
        </el-table-column>
        <el-table-column label="毛利率" width="170">
          <template #default="{ row }">
            <div class="rate-cell">
              <el-progress :percentage="clamp(row.margin_rate)" :stroke-width="6" :show-text="false" :color="rateColor(row.margin_rate)" />
              <span>{{ row.margin_rate == null ? '—' : row.margin_rate + '%' }}</span>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState compact icon="ri:money-cny-circle-line" title="暂无毛利数据" description="订单结单后会自动归集成交价与写手成本" />
        </template>
      </el-table>
    </section>

    <section class="art-card table-card">
      <div class="card-head">
        <div class="title">
          <h4>低毛利订单 Top 10</h4>
          <p>优先复核报价：毛利率偏低或为负的已结单订单</p>
        </div>
      </div>
      <el-table :data="data.low_margin_orders || []" row-key="id">
        <el-table-column prop="id" label="单号" width="120" />
        <el-table-column prop="title" label="题目" min-width="220" show-overflow-tooltip />
        <el-table-column prop="quality" label="品质" width="100" />
        <el-table-column label="成交额" width="120" align="right">
          <template #default="{ row }">¥{{ yuan(row.revenue) }}</template>
        </el-table-column>
        <el-table-column label="成本" width="120" align="right">
          <template #default="{ row }">¥{{ yuan(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="毛利" width="120" align="right">
          <template #default="{ row }">
            <b :class="row.profit < 0 ? 'loss' : 'profit'">¥{{ yuan(row.profit) }}</b>
          </template>
        </el-table-column>
        <el-table-column label="毛利率" width="100" align="right">
          <template #default="{ row }">{{ row.margin_rate == null ? '—' : row.margin_rate + '%' }}</template>
        </el-table-column>
        <template #empty>
          <EmptyState compact icon="ri:shield-check-line" title="没有低毛利订单" description="当前所有已结单订单毛利都处于合理区间" />
        </template>
      </el-table>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import http from '../api'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import ChartCard from '../components/ui/ChartCard.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatCard from '../components/StatCard.vue'

const loading = ref(false)
const month = ref('')
const data = ref({ summary: {}, by_quality: [], trend: [], top_orders: [], low_margin_orders: [] })

const summary = computed(() => data.value.summary || {})

function yuan(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function clamp(v) { return Math.min(100, Math.max(0, Number(v || 0))) }
function rateColor(v) {
  const n = Number(v || 0)
  if (n < 20) return '#ef4444'
  if (n < 40) return '#f59e0b'
  return '#10b981'
}

const trendOption = computed(() => {
  const rows = data.value.trend || []
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { color: '#9ca3af', fontSize: 11 } },
    grid: { left: 8, right: 12, top: 38, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => r.month), axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: [
      { type: 'value', name: '金额(¥)', nameTextStyle: { color: '#9ca3af', fontSize: 10 }, axisLabel: { color: '#9ca3af', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.15)' } } },
      { type: 'value', name: '毛利率(%)', min: 0, max: 100, nameTextStyle: { color: '#9ca3af', fontSize: 10 }, axisLabel: { color: '#9ca3af', fontSize: 11 }, splitLine: { show: false } },
    ],
    series: [
      { name: '成交额', type: 'bar', data: rows.map((r) => r.revenue), barMaxWidth: 18, itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] } },
      { name: '写手成本', type: 'bar', data: rows.map((r) => r.cost), barMaxWidth: 18, itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] } },
      { name: '毛利率', type: 'line', yAxisIndex: 1, smooth: true, data: rows.map((r) => r.margin_rate), itemStyle: { color: '#10b981' }, symbolSize: 6 },
    ],
  }
})

const qualityOption = computed(() => {
  const rows = data.value.by_quality || []
  return {
    tooltip: { trigger: 'item', formatter: '{b}<br/>毛利 ¥{c}（{d}%）' },
    legend: { bottom: 0, textStyle: { color: '#9ca3af', fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['48%', '72%'], center: ['50%', '44%'],
      itemStyle: { borderColor: 'transparent', borderWidth: 2 },
      label: { color: '#9ca3af', fontSize: 11, formatter: '{b}\n{d}%' },
      data: rows.map((r) => ({ name: r.name, value: Math.max(0, Number(r.profit || 0)) })),
    }],
  }
})

async function load() {
  loading.value = true
  try {
    // axios 拦截器已把响应体解包为 data，不能再解构一层
    data.value = await http.get('/stats/margin', { params: month.value ? { month: month.value } : {} })
  } catch {
    // 失败必须清空：不能让上一月的数据贴着新月份标签展示（金额口径错位）
    data.value = {}
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.margin-page { gap: 16px; }
/* 5 个经营指标在宽屏上排成一整行，避免第 5 张卡片单独换行造成视觉错位 */
.margin-page .stat-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.margin-page :deep(.stat-value) { font-size: 23px; }
.chart-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 16px; }
.table-card { padding: 16px 18px; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.card-head h4 { margin: 0; font-size: 15px; font-weight: 600; color: var(--text); }
.card-head p { margin: 3px 0 0; font-size: 11.5px; color: var(--text-3); }
.chip { flex: none; font-size: 11.5px; color: var(--text-3); background: var(--hover); padding: 3px 9px; border-radius: 999px; }
.profit { color: #10b981; }
.loss { color: #ef4444; }
.rate-cell { display: flex; align-items: center; gap: 8px; }
.rate-cell :deep(.el-progress) { flex: 1; }
.rate-cell span { width: 46px; text-align: right; font-variant-numeric: tabular-nums; color: var(--text-2); }
@media (max-width: 1280px) {
  .margin-page .stat-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .margin-page .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  /* 小屏 2 列时让毛利率卡片通栏，避免最后一张单独悬空 */
  .margin-page .stat-grid > :last-child { grid-column: 1 / -1; }
}
@media (max-width: 520px) {
  .margin-page .stat-grid { grid-template-columns: 1fr; }
  .margin-page .stat-grid > :last-child { grid-column: auto; }
}
@media (max-width: 1100px) { .chart-grid { grid-template-columns: 1fr; } }
</style>
