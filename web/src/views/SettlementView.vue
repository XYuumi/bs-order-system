<template>
  <div class="page-shell settlement-view">
    <AppPageHeader
      title="对账结算"
      description="按月汇总已结单订单的成交价与上下级抽成，导出 CSV 便于对账"
      icon="ri:wallet-3-line"
    />

    <FilterBar :show-search="false" :show-reset="false">
      <el-date-picker
        v-model="month" type="month" value-format="YYYY-MM"
        :clearable="false" class="f-month"
      />
      <el-select
        v-if="auth.isStaffView"
        v-model="agentId" placeholder="全部代理（总览）" clearable filterable
        class="f-agent"
      >
        <el-option
          v-for="a in agents" :key="a.id"
          :label="a.display_name || a.username" :value="a.id"
        />
      </el-select>
      <template #actions>
        <el-button @click="exportCsv">
          <Icon icon="ri:download-2-line" class="btn-ic" />导出 CSV
        </el-button>
      </template>
    </FilterBar>

    <!-- 汇总卡 -->
    <div class="stat-grid">
      <StatCard
        label="已结单成交价合计"
        :value="Number(cardsSource.own_total ?? 0)"
        prefix="¥"
        :decimals="2"
        icon="ri:money-cny-circle-line"
        color="var(--brand)"
        :sub="`${scopeText}已结单订单`"
        :loading="loading"
      />
      <StatCard
        label="收到下级抽成"
        :value="Number(cardsSource.received ?? 0)"
        prefix="¥"
        :decimals="2"
        icon="ri:arrow-right-up-line"
        color="var(--success)"
        sub="下级代理贡献的分成"
        :loading="loading"
      />
      <StatCard
        label="付给上级抽成"
        :value="Number(cardsSource.paid ?? 0)"
        prefix="¥"
        :decimals="2"
        icon="ri:arrow-right-down-line"
        color="var(--danger)"
        sub="按抽成比例上缴"
        :loading="loading"
      />
      <StatCard
        label="净得"
        :value="Number(cardsSource.net ?? 0)"
        prefix="¥"
        :decimals="2"
        icon="ri:wallet-3-line"
        color="var(--purple)"
        sub="成交价 + 收到抽成 - 付出抽成"
        :loading="loading"
      />
    </div>

    <!-- 加载骨架 -->
    <section v-if="loading" class="art-card">
      <div class="table-skeleton" aria-busy="true">
        <div v-for="i in 6" :key="i" class="skeleton sk-row" />
      </div>
    </section>

    <!-- 单代理明细模式 -->
    <section v-else-if="isDetailMode" class="art-card">
      <div class="card-head">
        <div class="title">
          <h4>
            {{ agentInfo?.display_name || agentInfo?.username || '代理明细' }}
            <span v-if="agentInfo?.commission_rate > 0" class="text-3 sub-note">
              （上级抽成 {{ agentInfo.commission_rate }}%{{ agentInfo.parent_name ? '，上级：' + agentInfo.parent_name : '' }}）
            </span>
          </h4>
          <p>{{ month }} 已结单明细 · 共 {{ items.length }} 单</p>
        </div>
      </div>

      <!-- 桌面端表格 -->
      <el-table v-if="!isMobile" :data="pagedItems" row-key="id">
        <el-table-column prop="id" label="单号" width="120">
          <template #default="{ row }"><span class="mono">{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column prop="title" label="题目" min-width="200" show-overflow-tooltip />
        <el-table-column label="品质" width="92">
          <template #default="{ row }">
            <QualityBadge v-if="row.quality" :name="row.quality.name" :color="row.quality.color" />
          </template>
        </el-table-column>
        <el-table-column label="成交价" width="100" align="right">
          <template #default="{ row }"><span class="money">¥{{ row.agent_price }}</span></template>
        </el-table-column>
        <el-table-column label="结单时间" width="160">
          <template #default="{ row }">{{ fmt(row.closed_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" text @click="router.push(`/orders/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            compact
            icon="ri:wallet-3-line"
            :title="month + ' 暂无已结单订单'"
            description="订单结单后会自动进入当月对账明细"
          />
        </template>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-else class="mini-cards">
        <EmptyState
          v-if="!items.length"
          icon="ri:wallet-3-line"
          :title="month + ' 暂无已结单订单'"
          description="订单结单后会自动进入当月对账明细"
        />
        <div
          v-for="row in pagedItems" :key="row.id" class="mini-card"
          @click="router.push(`/orders/${row.id}`)"
        >
          <div class="mc-head">
            <span class="mono mc-id">{{ row.id }}</span>
            <span class="money">¥{{ row.agent_price }}</span>
          </div>
          <div class="mc-title">{{ row.title }}</div>
          <div class="mc-foot">
            <QualityBadge v-if="row.quality" :name="row.quality.name" :color="row.quality.color" />
            <span class="text-3">{{ fmt(row.closed_at) }}</span>
          </div>
        </div>
      </div>

      <div v-if="items.length" class="pager">
        <el-pagination
          layout="total, prev, pager, next" :total="items.length"
          :page-size="15" v-model:current-page="itemPage"
        />
      </div>
    </section>

    <!-- 总览模式（管理员/协助者） -->
    <section v-else class="art-card">
      <div class="card-head">
        <div class="title">
          <h4>按代理汇总</h4>
          <p>点击代理查看明细 · 共 {{ agentsData.length }} 位代理</p>
        </div>
      </div>

      <!-- 桌面端表格 -->
      <el-table
        v-if="!isMobile"
        :data="agentsData" row-key="id" class="ag-table"
        show-summary :summary-method="summaryRow"
        @row-click="(r) => { agentId = r.id }"
      >
        <el-table-column label="代理">
          <template #default="{ row }">
            <a class="ag-link">{{ row.display_name }}</a>
          </template>
        </el-table-column>
        <el-table-column label="上级抽成" width="96">
          <template #default="{ row }">
            <span v-if="row.commission_rate > 0" class="text-2">{{ row.commission_rate }}%</span>
            <span v-else class="text-3">—</span>
          </template>
        </el-table-column>
        <el-table-column label="已结单代理价" width="130" align="right">
          <template #default="{ row }"><b class="price">¥{{ row.own_total }}</b></template>
        </el-table-column>
        <el-table-column label="收到下级抽成" width="124" align="right">
          <template #default="{ row }"><span class="money-in">¥{{ row.received }}</span></template>
        </el-table-column>
        <el-table-column label="付给上级抽成" width="124" align="right">
          <template #default="{ row }"><span class="money-out">¥{{ row.paid }}</span></template>
        </el-table-column>
        <el-table-column label="净得" width="110" align="right">
          <template #default="{ row }"><b class="price">¥{{ row.net }}</b></template>
        </el-table-column>
        <template #empty>
          <EmptyState
            compact
            icon="ri:group-line"
            title="本月暂无代理结算数据"
            description="代理产生已结单订单后，这里会自动汇总"
          />
        </template>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-else class="mini-cards">
        <EmptyState
          v-if="!agentsData.length"
          icon="ri:group-line"
          title="本月暂无代理结算数据"
          description="代理产生已结单订单后，这里会自动汇总"
        />
        <div
          v-for="row in agentsData" :key="row.id" class="mini-card"
          @click="agentId = row.id"
        >
          <div class="mc-head">
            <span class="mc-name">{{ row.display_name }}</span>
            <b class="price">净得 ¥{{ row.net }}</b>
          </div>
          <div class="mc-grid">
            <div class="mc-field"><span class="mc-label">已结单成交价</span><span>¥{{ row.own_total }}</span></div>
            <div class="mc-field"><span class="mc-label">收到下级</span><span class="money-in">¥{{ row.received }}</span></div>
            <div class="mc-field"><span class="mc-label">付给上级</span><span class="money-out">¥{{ row.paid }}</span></div>
            <div class="mc-field"><span class="mc-label">上级抽成</span><span>{{ row.commission_rate > 0 ? row.commission_rate + '%' : '—' }}</span></div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import dayjs from 'dayjs'
import http from '../api'
import { useAuthStore } from '../stores/auth'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import StatCard from '../components/StatCard.vue'
import FilterBar from '../components/ui/FilterBar.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import QualityBadge from '../components/QualityBadge.vue'

const auth = useAuthStore()
const router = useRouter()
const month = ref(dayjs().format('YYYY-MM'))
const agentId = ref(undefined)
const agents = ref([])
const data = ref({})
const itemPage = ref(1)
const loading = ref(false)
let seq = 0
let mediaQuery = null
const isMobile = ref(typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches)

function onMediaChange(e) {
  isMobile.value = e.matches
}

const agentsData = computed(() => data.value.agents || [])
const totals = computed(() => data.value.totals || {})
const items = computed(() => data.value.items || [])
const summary = computed(() => data.value.summary || {})
const agentInfo = computed(() => data.value.agent)
const isDetailMode = computed(() => !!(agentId.value || auth.isAgent))
// 明细模式取 summary；总览模式取 totals
const cardsSource = computed(() => (isDetailMode.value ? summary.value : totals.value))
const scopeText = computed(() => {
  if (isDetailMode.value) return agentInfo.value?.display_name ? `${agentInfo.value.display_name} ` : '当前代理'
  return '全部代理'
})
// 明细表客户端分页（每页 15 条，与原表格一致）
const pagedItems = computed(() => {
  const list = items.value
  const start = (itemPage.value - 1) * 15
  return list.slice(start, start + 15)
})

function fmt(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : '-'
}

// 合计行：与原表格 summary 一致（金额列加粗）
function summaryRow({ columns }) {
  return columns.map((col, i) => {
    if (i === 0) return `合计（${totals.value.count ?? 0} 单）`
    if (i === 2) return h('b', null, `¥${totals.value.own_total ?? 0}`)
    if (i === 3) return `¥${totals.value.received ?? 0}`
    if (i === 4) return `¥${totals.value.paid ?? 0}`
    if (i === 5) return h('b', null, `¥${totals.value.net ?? 0}`)
    return ''
  })
}

async function load() {
  const current = ++seq
  loading.value = true
  const params = { month: month.value }
  if (agentId.value) params.agent_id = agentId.value
  try {
    const res = await http.get('/stats/settlement', { params })
    if (current !== seq) return
    data.value = res
  } catch {
    // 失败必须清空：不能让上一月的数据贴着新月份标签展示（金额口径错位）
    if (current === seq) data.value = {}
  } finally {
    if (current === seq) loading.value = false
  }
}

function exportCsv() {
  const params = new URLSearchParams({ month: month.value })
  if (agentId.value) params.set('agent_id', agentId.value)
  window.open('/api/stats/settlement/export?' + params.toString(), '_blank')
}

watch([month, agentId], () => {
  itemPage.value = 1
  load()
})

watch(() => items.value.length, () => {
  const maxPage = Math.max(1, Math.ceil(items.value.length / 15))
  if (itemPage.value > maxPage) itemPage.value = maxPage
})

onMounted(async () => {
  mediaQuery = window.matchMedia('(max-width: 768px)')
  isMobile.value = mediaQuery.matches
  mediaQuery.addEventListener('change', onMediaChange)
  load()
  if (auth.isStaffView) {
    try {
      const u = await http.get('/users')
      agents.value = (u.items || []).filter((x) => x.role === 'agent' && x.is_active)
    } catch { /* 拦截器已提示 */ }
  }
})

onBeforeUnmount(() => mediaQuery?.removeEventListener('change', onMediaChange))
</script>

<style scoped>
.settlement-view { min-width: 0; }

.f-month { width: 140px; }
.f-agent { width: 200px; }
.btn-ic { margin-right: 4px; }

.card-head { margin-bottom: 14px; }
.card-head .title h4 { margin: 0; font-size: 15px; font-weight: 600; color: var(--text); }
.card-head .title p { margin: 3px 0 0; font-size: 12px; color: var(--text-3); }
.sub-note { font-size: 12px; font-weight: 400; margin-left: 6px; }

.money { font-weight: 600; }
.money-in { color: var(--success); font-weight: 600; }
.money-out { color: var(--danger); font-weight: 600; }
.pager { display: flex; justify-content: flex-end; margin-top: 14px; }
.ag-table :deep(.el-table__row) { cursor: pointer; }
.ag-link { color: var(--brand); font-weight: 600; }

/* 骨架 */
.table-skeleton { display: flex; flex-direction: column; gap: 10px; padding: 4px 0 8px; }
.sk-row { height: 38px; border-radius: var(--radius-sm); }

/* 移动端卡片 */
.mini-cards { display: flex; flex-direction: column; gap: 10px; }
.mini-card {
  padding: 14px; background: var(--card-2);
  border: 1px solid var(--border); border-radius: var(--radius);
  cursor: pointer; transition: border-color 0.15s;
}
.mini-card:hover { border-color: var(--border-3); }
.mc-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.mc-id { font-size: 12.5px; color: var(--brand); font-weight: 600; }
.mc-name { font-size: 14px; font-weight: 600; color: var(--text); }
.mc-title {
  margin-top: 6px; font-size: 13.5px; line-height: 1.55; color: var(--text);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.mc-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  flex-wrap: wrap; margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border);
  font-size: 12px;
}
.mc-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px; margin-top: 10px; padding-top: 10px;
  border-top: 1px solid var(--border);
}
.mc-field { display: flex; flex-direction: column; gap: 3px; font-size: 12.5px; color: var(--text-2); }
.mc-label { font-size: 11px; color: var(--text-3); }

@media (max-width: 768px) {
  .pager { justify-content: center; }
  .f-month, .f-agent { width: 100% !important; }
}
@media (max-width: 480px) {
  .mc-grid { grid-template-columns: 1fr; }
}
</style>
