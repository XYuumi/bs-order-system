<template>
  <div class="page-shell writer-perf">
    <AppPageHeader
      title="写手绩效"
      description="按月查看写手接单、交付与收益表现"
      icon="ri:bar-chart-grouped-line"
    >
      <template #actions>
        <el-date-picker
          v-model="month" type="month" value-format="YYYY-MM"
          placeholder="全部月份" clearable style="width: 150px"
        />
        <el-button :loading="loading" @click="load">
          <Icon icon="ri:refresh-line" />刷新
        </el-button>
      </template>
    </AppPageHeader>

    <!-- 汇总卡 -->
    <div class="stat-grid">
      <StatCard
        v-for="(st, i) in statCards" :key="st.label"
        :label="st.label" :value="st.value" :icon="st.icon" :color="st.color"
        :prefix="st.prefix" :suffix="st.suffix" :decimals="st.decimals || 0"
        :sub="st.sub" :loading="loading"
        :style="{ animationDelay: `${i * 0.04}s` }"
      />
    </div>

    <!-- 绩效明细表 -->
    <section class="art-card table-card">
      <div class="card-head">
        <div class="title">
          <h4>绩效明细</h4>
          <p>按时率按「已完成」订单统计 · 平均交付为接单到完成的平均天数</p>
        </div>
        <span class="chip">{{ month ? `${month} · ` : '全部数据 · ' }}{{ rows.length }} 位写手</span>
      </div>

      <!-- 加载骨架 -->
      <div v-if="loading" class="table-skeleton" aria-busy="true">
        <div v-for="i in 6" :key="i" class="skeleton sk-row" />
      </div>

      <!-- 桌面端表格 -->
      <el-table v-else-if="!isMobile" :data="rows" row-key="id">
        <el-table-column label="写手" min-width="160">
          <template #default="{ row }">
            <div class="wp-writer">
              <span class="wp-name">{{ row.name }}</span>
              <span class="wp-username mono">{{ row.username }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="total" label="总接单" width="86" align="right" />
        <el-table-column prop="in_progress" label="制作中" width="86" align="right" />
        <el-table-column prop="done" label="已完成" width="86" align="right" />
        <el-table-column prop="closed" label="已结单" width="86" align="right" />
        <el-table-column label="按时率" width="160">
          <template #default="{ row }">
            <div v-if="row.on_time_rate != null" class="wp-rate">
              <el-progress
                :percentage="row.on_time_rate" :color="rateColor(row.on_time_rate)"
                :stroke-width="6" :show-text="false" class="wp-bar"
              />
              <span class="wp-rate-num">{{ row.on_time_rate }}%</span>
            </div>
            <span v-else class="text-3">—</span>
          </template>
        </el-table-column>
        <el-table-column label="平均交付(天)" width="110" align="right">
          <template #default="{ row }">
            <span v-if="row.avg_days != null">{{ row.avg_days }}</span>
            <span v-else class="text-3">—</span>
          </template>
        </el-table-column>
        <el-table-column label="售后率" width="90" align="right">
          <template #default="{ row }">
            <span v-if="row.after_sale_rate != null" :class="{ 'wp-warn': row.after_sale_rate > 0 }">{{ row.after_sale_rate }}%</span>
            <span v-else class="text-3">—</span>
          </template>
        </el-table-column>
        <el-table-column label="写手报酬(¥)" width="120" align="right">
          <template #default="{ row }">
            <b class="price">¥{{ Number(row.income ?? 0).toLocaleString() }}</b>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            compact
            icon="ri:bar-chart-grouped-line"
            :title="month ? '该月份暂无写手接单数据' : '暂无写手接单数据'"
            description="有写手接单并产生制作进度后，这里会自动汇总"
          />
        </template>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-else class="wp-cards">
        <EmptyState
          v-if="!rows.length"
          icon="ri:bar-chart-grouped-line"
          :title="month ? '该月份暂无写手接单数据' : '暂无写手接单数据'"
          description="有写手接单并产生制作进度后，这里会自动汇总"
        />
        <div v-for="row in rows" :key="row.id" class="wp-card">
          <div class="wc-head">
            <div class="wp-writer">
              <span class="wp-name">{{ row.name }}</span>
              <span class="wp-username mono">@{{ row.username }}</span>
            </div>
            <span class="wc-income price">¥{{ Number(row.income ?? 0).toLocaleString() }}</span>
          </div>
          <div class="wc-stats">
            <div class="wc-stat"><span class="wc-label">总接单</span><b>{{ row.total ?? 0 }}</b></div>
            <div class="wc-stat"><span class="wc-label">制作中</span><b>{{ row.in_progress ?? 0 }}</b></div>
            <div class="wc-stat"><span class="wc-label">已完成</span><b>{{ row.done ?? 0 }}</b></div>
            <div class="wc-stat"><span class="wc-label">已结单</span><b>{{ row.closed ?? 0 }}</b></div>
          </div>
          <div class="wc-rate">
            <span class="wc-label">按时率</span>
            <template v-if="row.on_time_rate != null">
              <el-progress
                :percentage="row.on_time_rate" :color="rateColor(row.on_time_rate)"
                :stroke-width="6" :show-text="false" class="wp-bar"
              />
              <span class="wp-rate-num">{{ row.on_time_rate }}%</span>
            </template>
            <span v-else class="text-3">—</span>
          </div>
          <div class="wc-foot">
            <span>平均交付 <b>{{ row.avg_days != null ? row.avg_days + ' 天' : '—' }}</b></span>
            <span>售后率 <b :class="{ 'wp-warn': row.after_sale_rate > 0 }">{{ row.after_sale_rate != null ? row.after_sale_rate + '%' : '—' }}</b></span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import http from '../api'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import StatCard from '../components/StatCard.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const loading = ref(false)
const month = ref(null) // null = 全部
const data = ref({ month: null, rows: [], totals: {} })
let mediaQuery = null
const isMobile = ref(typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches)

function onMediaChange(e) {
  isMobile.value = e.matches
}

const rows = computed(() => data.value.rows || [])
const totals = computed(() => data.value.totals || {})

// 汇总卡：总接单 / 已完成 / 平均交付 / 写手报酬合计
const statCards = computed(() => [
  {
    label: '总接单',
    value: Number(totals.value.total ?? 0),
    suffix: '单',
    icon: 'ri:stack-line',
    color: 'var(--brand)',
    sub: `共 ${totals.value.staff_count ?? 0} 位写手`,
  },
  {
    label: '已完成',
    value: Number(totals.value.done ?? 0),
    suffix: '单',
    icon: 'ri:checkbox-circle-line',
    color: 'var(--success)',
    sub: `已结单 ${rows.value.reduce((a, r) => a + (r.closed ?? 0), 0)} 单`,
  },
  {
    label: '平均交付',
    value: totals.value.avg_days ?? '—',
    suffix: totals.value.avg_days != null ? '天' : '',
    decimals: Number.isInteger(Number(totals.value.avg_days)) ? 0 : 1,
    icon: 'ri:time-line',
    color: 'var(--warning)',
    sub: '接单到完成的平均用时',
  },
  {
    label: '写手报酬合计',
    value: Number(totals.value.income ?? 0),
    prefix: '¥',
    icon: 'ri:money-cny-circle-line',
    color: 'var(--info)',
    sub: '已结单订单合计',
  },
])

// 按时率进度条配色：≥90 绿 / ≥60 黄 / 其余红（全部走语义 token）
function rateColor(v) {
  if (v >= 90) return 'var(--success)'
  if (v >= 60) return 'var(--warning)'
  return 'var(--danger)'
}

async function load() {
  loading.value = true
  try {
    data.value = await http.get('/stats/writer-perf', { params: month.value ? { month: month.value } : {} })
  } finally {
    loading.value = false
  }
}

watch(month, load)

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 768px)')
  isMobile.value = mediaQuery.matches
  mediaQuery.addEventListener('change', onMediaChange)
  load()
})

onBeforeUnmount(() => mediaQuery?.removeEventListener('change', onMediaChange))
</script>

<style scoped>
.writer-perf { min-width: 0; }

.table-card { min-width: 0; }
.card-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-bottom: 14px;
}
.card-head .title h4 { margin: 0; font-size: 15px; font-weight: 600; color: var(--text); }
.card-head .title p { margin: 3px 0 0; font-size: 12px; color: var(--text-3); }

/* 表格骨架 */
.table-skeleton { display: flex; flex-direction: column; gap: 10px; padding: 4px 0 8px; }
.sk-row { height: 38px; border-radius: var(--radius-sm); }

.wp-writer { display: flex; flex-direction: column; gap: 2px; }
.wp-name { font-weight: 600; font-size: 13.5px; color: var(--text); }
.wp-username { font-size: 11.5px; color: var(--text-3); }
.wp-rate { display: flex; align-items: center; gap: 8px; }
.wp-bar { flex: 1; min-width: 0; }
.wp-bar :deep(.el-progress-bar__outer) { border-radius: var(--radius-pill); }
.wp-bar :deep(.el-progress-bar__inner) { border-radius: var(--radius-pill); transition: width 0.4s ease; }
.wp-rate-num { font-size: 12.5px; font-weight: 600; flex-shrink: 0; color: var(--text); }
.wp-warn { color: var(--danger); font-weight: 600; }

/* 移动端卡片 */
.wp-cards { display: flex; flex-direction: column; gap: 10px; }
.wp-card {
  padding: 14px; background: var(--card-2);
  border: 1px solid var(--border); border-radius: var(--radius);
}
.wc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.wc-income { font-size: 14px; color: var(--success); white-space: nowrap; }
.wc-stats {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px; margin-top: 12px; padding-top: 10px;
  border-top: 1px solid var(--border);
}
.wc-stat { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.wc-label { font-size: 11px; color: var(--text-3); }
.wc-stat b { font-size: 14px; color: var(--text); font-variant-numeric: tabular-nums; }
.wc-rate {
  display: flex; align-items: center; gap: 8px;
  margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border);
}
.wc-rate .wc-label { flex-shrink: 0; }
.wc-foot {
  display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  margin-top: 8px; font-size: 11.5px; color: var(--text-3);
}
.wc-foot b { color: var(--text-2); margin-left: 2px; }

@media (max-width: 520px) {
  .wc-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .card-head .chip { display: none; }
}
</style>
