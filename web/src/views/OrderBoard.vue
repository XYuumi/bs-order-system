<template>
  <div class="page-shell board-page">
    <!-- 生产脉搏 -->
    <section class="board-hero">
      <div class="bh-grid" aria-hidden="true" />
      <div class="bh-copy">
        <div class="bh-eyebrow"><span class="bh-dot" /> PRODUCTION BOARD · 生产看板</div>
        <h1>让每一单，<em>按节奏流动。</em></h1>
        <p>按状态分列查看生产进度，拖拽卡片即可推进；非法流转会被状态机拒绝。</p>
        <div class="bh-chips">
          <span><Icon icon="ri:drag-move-2-line" />拖拽流转</span>
          <span><Icon icon="ri:alarm-warning-line" />逾期预警</span>
          <span><Icon icon="ri:shield-check-line" />角色只读</span>
        </div>
        <div class="bh-actions">
          <el-button type="primary" @click="router.push('/orders/create')"><Icon icon="ri:add-line" />新建订单</el-button>
          <el-button :loading="loading" @click="loadBoard"><Icon icon="ri:refresh-line" />刷新看板</el-button>
        </div>
      </div>
      <div class="bh-pulse">
        <button
          v-for="p in pulse" :key="p.key"
          class="bh-kpi" :class="p.tone"
          type="button" @click="focusColumn(p.column)"
        >
          <span class="bh-kpi-icon"><Icon :icon="p.icon" /></span>
          <span class="bh-kpi-copy">
            <small>{{ p.label }}</small>
            <b>{{ p.value }}</b>
            <em>{{ p.hint }}</em>
          </span>
        </button>
      </div>
    </section>

    <!-- 看板工具栏 -->
    <div class="kb-toolbar">
      <div class="kb-tools-left">
        <el-input
          v-model="keyword"
          class="kb-search"
          placeholder="搜索单号 / 题目"
          clearable
          @clear="loadBoard"
        >
          <template #prefix><Icon icon="ri:search-line" /></template>
        </el-input>
        <el-select v-model="projectType" class="kb-select" placeholder="全部项目类型" clearable @change="loadBoard">
          <el-option v-for="(m, k) in PROJECT_TYPE_META" :key="k" :label="m.label" :value="k" />
        </el-select>
        <span class="kb-total"><b>{{ totalOpen }}</b> 个在制订单</span>
      </div>
      <div class="kb-tools-right">
        <div v-if="showMoney && auth.isAdmin" class="kb-finance">
          <span class="kb-fin-hint">金额口径</span>
          <el-switch
            v-model="showOwner"
            inline-prompt
            active-text="真实价"
            inactive-text="代理价"
          />
        </div>
        <span v-if="!canDrag" class="kb-readonly">
          <Icon icon="ri:lock-2-line" /> 当前角色只读
        </span>
        <span class="kb-scroll-hint"><Icon icon="ri:arrow-left-right-line" />左右滑动看全部列</span>
      </div>
    </div>

    <div v-if="error" class="kb-error">
      <Icon icon="ri:error-warning-line" />
      <span>{{ error }}</span>
      <el-button link type="primary" @click="loadBoard">重试</el-button>
    </div>

    <div v-if="loading && !loaded" class="kb-board">
      <div v-for="c in columns" :key="c.key" class="kb-col">
        <div class="kb-col-head"><span class="skeleton skeleton-line" style="width: 90px" /></div>
        <div class="kb-col-body">
          <div v-for="i in 3" :key="i" class="kb-card skeleton-card">
            <span class="skeleton skeleton-line" style="width: 60%" />
            <span class="skeleton skeleton-line" style="width: 90%" />
            <span class="skeleton skeleton-line" style="width: 40%" />
          </div>
        </div>
      </div>
    </div>

    <div v-else class="kb-board">
      <section
        v-for="c in columns"
        :id="'kb-col-' + c.key"
        :key="c.key"
        class="kb-col"
        :class="{ 'is-drop': dropTarget === c.key, 'is-blocked': dropTarget === c.key && !dropAllowed }"
        @dragover.prevent="onDragOver(c)"
        @dragleave="onDragLeave(c)"
        @drop.prevent="onDrop(c)"
      >
        <header class="kb-col-head" :style="{ '--tone': c.hex }">
          <span class="kb-col-icon"><Icon :icon="c.icon" /></span>
          <span class="kb-col-title">{{ c.label }}</span>
          <span class="kb-col-count" :title="colTitle(c)">{{ totals[c.key] ?? (lists[c.key] || []).length }}</span>
          <span v-if="truncated(c)" class="kb-col-more">前 {{ (lists[c.key] || []).length }}</span>
          <span class="kb-col-amount">{{ amountText(c) }}</span>
          <span class="kb-col-line"><i :style="{ width: colPct(c) + '%', background: c.hex }" /></span>
        </header>

        <div v-if="dropTarget === c.key" class="kb-drop-hint" :class="{ blocked: !dropAllowed }">
          <Icon :icon="dropAllowed ? 'ri:arrow-down-circle-line' : 'ri:forbid-2-line'" />
          {{ dropAllowed ? `松开以流转到「${c.label}」` : '当前状态不允许流转到此列' }}
        </div>

        <div class="kb-col-body">
          <article
            v-for="o in lists[c.key] || []"
            :key="o.id"
            class="kb-card"
            :class="{ dragging: draggingId === o.id, overdue: urgency(o).key === 'overdue' }"
            :draggable="canDrag && movable(o)"
            :style="{ '--card-tone': c.hex }"
            @dragstart="onDragStart(o, $event)"
            @dragend="onDragEnd"
            @click="openOrder(o)"
          >
            <span class="kb-card-accent" />
            <div class="kb-card-top">
              <span class="kb-id mono">{{ o.id }}</span>
              <span class="kb-quality-mini">
                <i :style="{ background: o.quality?.color || '#8f8fa3' }" />
                {{ o.quality?.name || '未定级' }}
              </span>
              <span v-if="urgency(o).key !== 'normal' && urgency(o).key !== 'none'" class="kb-badge" :class="urgency(o).key">
                {{ urgency(o).label }}
              </span>
            </div>
            <h4 class="kb-title" :title="o.title">{{ o.title }}</h4>
            <div class="kb-meta">
              <span class="kb-cat-chip" :style="{ color: projectTypeMeta(o.project_type).hex, borderColor: projectTypeMeta(o.project_type).hex + '33', background: projectTypeMeta(o.project_type).hex + '12' }">
                {{ projectTypeMeta(o.project_type).icon }} {{ projectTypeMeta(o.project_type).short }}
              </span>
              <span v-if="o.deploy_status && o.deploy_status !== 'not_required'" class="kb-deploy">
                <Icon icon="ri:upload-cloud-2-line" />{{ deployMeta(o.deploy_status).label }}
              </span>
              <span v-if="o.deadline && urgency(o).key === 'normal'" class="kb-due">
                <Icon icon="ri:calendar-line" />{{ o.deadline.slice(5) }}
              </span>
            </div>
            <div class="kb-foot">
              <span class="kb-agent">
                <span class="kb-avatar">{{ agentInitial(o) }}</span>
                <span class="kb-agent-name">{{ o.agent?.display_name || o.agent?.username || '自接' }}</span>
              </span>
              <span class="kb-price mono">{{ priceText(o) }}</span>
            </div>
          </article>

          <EmptyState
            v-if="!(lists[c.key] || []).length"
            compact
            :icon="error ? 'ri:error-warning-line' : c.icon"
            :title="emptyText(c)"
          />
        </div>
      </section>
    </div>

    <p class="kb-tip">
      <Icon icon="ri:information-line" />
      只显示未删除的订单；「已取消」不进入看板。拖拽仅在合法状态流转时生效，非法流转会被拒绝并提示。
    </p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { ElMessage } from 'element-plus'

import http from '../api'
import { useAuthStore } from '../stores/auth'
import EmptyState from '../components/ui/EmptyState.vue'
import {
  BOARD_COLUMNS,
  PROJECT_TYPE_META,
  STATUS_META,
  deadlineState,
  deployMeta,
  projectTypeMeta,
} from '../constants/orderMeta'

const router = useRouter()
const auth = useAuthStore()

const ICONS = {
  pending: 'ri:inbox-archive-line',
  in_progress: 'ri:loader-4-line',
  completed: 'ri:checkbox-circle-line',
  closed: 'ri:archive-line',
  after_sale: 'ri:customer-service-2-line',
}

const EMPTY = {
  pending: '暂无待开始订单',
  in_progress: '暂无制作中订单',
  completed: '暂无已完成订单',
  closed: '暂无已结单',
  after_sale: '暂无售后订单',
}

const columns = computed(() =>
  BOARD_COLUMNS.map((key) => ({
    key,
    label: STATUS_META[key].label,
    hex: STATUS_META[key].hex,
    icon: ICONS[key],
    emptyText: EMPTY[key],
  }))
)

const lists = ref({})
const totals = ref({})
const loading = ref(false)
const loaded = ref(false)
const keyword = ref('')
const projectType = ref('')
const showOwner = ref(false)
// 后端下发的真实价可见性开关（fail-closed：字段缺失即不可见）
const showMoney = ref(false)
const error = ref('')
// 请求序号：快速切筛选/连点刷新时，旧响应必须丢弃，否则会覆盖新结果
let loadSeq = 0
const draggingId = ref('')
const dragFrom = ref('')
const dropTarget = ref('')
const dropAllowed = ref(false)

const canDrag = computed(() => auth.isStaffView)
const totalOpen = computed(() => Number(totals.value.pending || 0) + Number(totals.value.in_progress || 0) + Number(totals.value.after_sale || 0))

const overdueCount = computed(() => {
  const all = Object.values(lists.value).flat()
  return all.filter((o) => urgency(o).key === 'overdue').length
})
const soonCount = computed(() => {
  const all = Object.values(lists.value).flat()
  return all.filter((o) => urgency(o).key === 'soon').length
})
const maxColCount = computed(() => Math.max(1, ...columns.value.map((c) => Number(totals.value[c.key] || 0))))

function firstColumnByUrgency(kind) {
  for (const c of columns.value) {
    if ((lists.value[c.key] || []).some((o) => urgency(o).key === kind)) return c.key
  }
  return 'in_progress'
}

const pulse = computed(() => [
  {
    key: 'wip', column: 'in_progress', tone: 'brand', icon: 'ri:loader-4-line',
    label: '在制订单', value: totalOpen.value, hint: '待开始 + 制作中 + 售后',
  },
  {
    key: 'overdue', column: firstColumnByUrgency('overdue'), tone: 'danger', icon: 'ri:alarm-warning-line',
    label: '已逾期', value: overdueCount.value, hint: '本列仅统计已加载卡片',
  },
  {
    key: 'soon', column: firstColumnByUrgency('soon'), tone: 'warning', icon: 'ri:time-line',
    label: '3 天内到期', value: soonCount.value, hint: '含今天到期',
  },
  {
    key: 'closed', column: 'closed', tone: 'success', icon: 'ri:checkbox-circle-line',
    label: '已结单', value: Number(totals.value.closed || 0), hint: '全部已结单',
  },
])

function focusColumn(key) {
  const el = document.getElementById('kb-col-' + key)
  el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
  if (el) {
    el.classList.add('is-focus')
    setTimeout(() => el.classList.remove('is-focus'), 900)
  }
}

function colPct(c) {
  const count = Number(totals.value[c.key] || 0)
  if (!count) return 0
  return Math.max(6, Math.round((count / maxColCount.value) * 100))
}

function agentInitial(o) {
  const name = o.agent?.display_name || o.agent?.username || '自'
  return String(name).trim().slice(0, 1).toUpperCase()
}

function urgency(o) {
  if (!o.deadline) return { key: 'none', label: '', days: null }
  if (['completed', 'closed', 'cancelled'].includes(o.status)) {
    return { key: 'none', label: '', days: null }
  }
  return deadlineState(o.deadline)
}

// 与后端 can_change_status 对齐：管理员可在看板各列间任意修正；写手只能推进到开始/完成。
const STAFF_FLOW = {
  pending: ['in_progress', 'completed'],
  in_progress: ['completed'],
}
function canMove(from, to) {
  if (!from || !to || from === to) return false
  if (auth.isAdmin) return BOARD_COLUMNS.includes(to)
  return (STAFF_FLOW[from] || []).includes(to)
}
// 只有当前角色还存在可拖入的列时才允许抓起卡片
function movable(o) {
  return BOARD_COLUMNS.some((to) => canMove(o.status, to))
}

const ownerVisible = computed(() => showMoney.value && auth.isAdmin && showOwner.value)

function priceText(o) {
  if (ownerVisible.value && o.owner_price != null) return '¥' + Number(o.owner_price).toLocaleString()
  return '¥' + Number(o.agent_price || 0).toLocaleString()
}

function amountText(c) {
  const rows = lists.value[c.key] || []
  if (!rows.length) return ''
  const sum = rows.reduce(
    (acc, o) => acc + Number(ownerVisible.value && o.owner_price != null ? o.owner_price : o.agent_price || 0),
    0
  )
  return '¥' + sum.toLocaleString()
}

// 列头计数用后端 total，与摘要条保持同一口径；本列只加载前 100 单
function truncated(c) {
  const total = totals.value[c.key] ?? 0
  return total > (lists.value[c.key] || []).length
}

function colTitle(c) {
  const total = totals.value[c.key] ?? (lists.value[c.key] || []).length
  const shown = (lists.value[c.key] || []).length
  return total > shown ? `共 ${total} 单，本列仅显示最近 ${shown} 单` : `共 ${total} 单`
}

function emptyText(c) {
  return error.value ? '加载失败，请重试' : c.emptyText
}

function openOrder(o) {
  router.push('/orders/' + o.id)
}

async function loadBoard() {
  const my = ++loadSeq
  loading.value = true
  error.value = ''
  const params = { page_size: 100 }
  if (keyword.value.trim()) params.keyword = keyword.value.trim()
  if (projectType.value) params.project_type = projectType.value
  try {
    const results = await Promise.all(
      columns.value.map((c) => http.get('/orders', { params: { ...params, status: c.key } }))
    )
    if (my !== loadSeq) return
    const next = {}
    const tot = {}
    columns.value.forEach((c, i) => {
      next[c.key] = results[i]?.items || []
      tot[c.key] = results[i]?.total ?? next[c.key].length
    })
    lists.value = next
    totals.value = tot
    showMoney.value = results[0]?.show_money === true
  } catch {
    if (my !== loadSeq) return
    // 拦截器只弹一次提示；这里保留页面级错误态，避免接口失败被误认成「没有订单」
    error.value = '看板数据加载失败，请检查网络后重试'
  } finally {
    if (my === loadSeq) {
      loading.value = false
      loaded.value = true
    }
  }
}

// 关键字输入 300ms 防抖，避免每敲一个字就打 5 个请求
let kwTimer = null
watch(keyword, () => {
  clearTimeout(kwTimer)
  kwTimer = setTimeout(loadBoard, 300)
})
onBeforeUnmount(() => clearTimeout(kwTimer))

function onDragStart(o, e) {
  if (!canDrag.value) return
  draggingId.value = o.id
  dragFrom.value = o.status
  try {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', o.id)
  } catch {
    /* Safari 兼容 */
  }
}

function onDragEnd() {
  draggingId.value = ''
  dragFrom.value = ''
  dropTarget.value = ''
  dropAllowed.value = false
}

function onDragOver(c) {
  if (!draggingId.value) return
  dropTarget.value = c.key
  dropAllowed.value = c.key === dragFrom.value || canMove(dragFrom.value, c.key)
}

function onDragLeave(c) {
  if (dropTarget.value === c.key) {
    dropTarget.value = ''
    dropAllowed.value = false
  }
}

async function onDrop(c) {
  const from = dragFrom.value
  const id = draggingId.value
  dropTarget.value = ''
  dropAllowed.value = false
  draggingId.value = ''
  dragFrom.value = ''
  if (!id || !canDrag.value) return
  if (c.key === from) return
  if (!canMove(from, c.key)) {
    ElMessage.warning(
      `「${STATUS_META[from]?.label || from}」不能直接变更为「${c.label}」`
    )
    return
  }
  // 乐观更新：先移动卡片，失败再回滚
  const fromList = lists.value[from] || []
  const idx = fromList.findIndex((o) => o.id === id)
  if (idx < 0) return
  const [card] = fromList.splice(idx, 1)
  const backup = { ...card }
  card.status = c.key
  lists.value[c.key] = [card, ...(lists.value[c.key] || [])]
  totals.value[from] = Math.max(0, (totals.value[from] || 1) - 1)
  totals.value[c.key] = (totals.value[c.key] || 0) + 1
  try {
    await http.post(`/orders/${encodeURIComponent(id)}/status`, { status: c.key })
    ElMessage.success(`已变更为「${c.label}」`)
  } catch {
    // 回滚
    lists.value[c.key] = (lists.value[c.key] || []).filter((o) => o.id !== id)
    const restored = { ...backup }
    fromList.splice(idx, 0, restored)
    lists.value[from] = [...fromList]
    totals.value[from] = (totals.value[from] || 0) + 1
    totals.value[c.key] = Math.max(0, (totals.value[c.key] || 1) - 1)
  }
}

onMounted(loadBoard)
</script>

<style scoped>
.board-page { gap: 14px; }
.kb-search { width: 210px; }
.kb-select { width: 130px; }

/* 摘要条 */
.kb-summary {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 10px 14px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius);
}
.kb-sum-item {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 8px;
  background: var(--card-2); border: 1px solid var(--border);
  font-size: 12px; color: var(--text-2);
}
.kb-sum-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--tone); }
.kb-sum-icon { color: var(--tone); font-size: 14px; }
.kb-sum-value { font-weight: 650; color: var(--text); font-variant-numeric: tabular-nums; }
.kb-sum-item.danger { border-color: color-mix(in srgb, var(--danger) 35%, transparent); }
.kb-sum-spacer { flex: 1; }
.kb-finance { display: inline-flex; align-items: center; gap: 8px; }
.kb-fin-hint { font-size: 12px; color: var(--text-3); }
.kb-readonly {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--text-3);
  padding: 3px 9px; border-radius: 7px; background: var(--card-2);
}

/* 看板 */
.kb-board {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(208px, 1fr);
  gap: 10px;
  align-items: start;
  overflow-x: auto;
  padding-bottom: 4px;
  min-height: 320px;
  scrollbar-width: thin;
  scrollbar-color: var(--border-2) transparent;
}
.kb-board::-webkit-scrollbar { height: 7px; }
.kb-board::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 999px; }
.kb-board::-webkit-scrollbar-track { background: transparent; }
.kb-col {
  display: flex; flex-direction: column;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  min-height: 300px;
  max-height: calc(100vh - 300px);
  transition: border-color 0.18s, box-shadow 0.18s, background 0.18s;
}
.kb-col.is-drop.is-blocked { border-color: var(--border-2); }
.kb-col.is-drop { border-color: var(--brand); box-shadow: 0 0 0 2px var(--brand-weak); }
.kb-col-head {
  display: flex; align-items: center; gap: 7px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 1;
  background: var(--card);
  border-radius: var(--radius) var(--radius) 0 0;
}
.kb-col-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--tone); flex-shrink: 0; }
.kb-col-title { font-size: 13px; font-weight: 600; color: var(--text); }
.kb-col-count {
  min-width: 20px; height: 18px; padding: 0 5px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 9px; background: var(--card-3); color: var(--text-2);
  font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums;
}
.kb-col-more { font-size: 10px; color: var(--text-4); }
.kb-col-amount { margin-left: auto; font-size: 11px; color: var(--text-4); font-variant-numeric: tabular-nums; }
.kb-error {
  display: flex; align-items: center; gap: 8px;
  padding: 9px 14px; border-radius: var(--radius);
  border: 1px solid color-mix(in srgb, var(--danger) 35%, transparent);
  background: var(--danger-weak); color: var(--danger); font-size: 13px;
}
.kb-col-body {
  flex: 1; overflow-y: auto;
  padding: 10px; display: flex; flex-direction: column; gap: 8px;
}

/* 卡片 */
.kb-card {
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 11px;
  cursor: pointer;
  transition: transform 0.16s cubic-bezier(0.22, 0.61, 0.36, 1), border-color 0.18s, box-shadow 0.18s;
  animation: rise-in 0.28s ease both;
}
.kb-card:hover {
  border-color: var(--border-3);
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.28);
}
.kb-card.dragging { opacity: 0.45; transform: scale(0.98); }
.kb-card.overdue { border-left: 2px solid var(--danger); }
.kb-card-top { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.kb-id { font-size: 11px; color: var(--text-3); letter-spacing: 0.02em; }
.kb-badge {
  margin-left: auto; font-size: 10px; font-weight: 600;
  padding: 0 6px; border-radius: 5px; line-height: 17px;
}
.kb-badge.overdue { color: var(--danger); background: var(--danger-weak); }
.kb-badge.soon { color: var(--warning); background: var(--warning-weak); }
.kb-badge.today { color: var(--warning); background: var(--warning-weak); font-weight: 700; }
.kb-title {
  margin: 0 0 7px; font-size: 13px; font-weight: 600; color: var(--text);
  line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.kb-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11px; color: var(--text-3); }
.kb-quality { display: inline-flex; align-items: center; gap: 4px; }
.kb-q-dot { width: 6px; height: 6px; border-radius: 50%; }
.kb-cat { color: var(--text-4); }
.kb-deploy { color: var(--text-4); }
.kb-foot {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 9px; padding-top: 8px; border-top: 1px dashed var(--border);
  font-size: 11.5px; color: var(--text-3);
}
.kb-agent { display: inline-flex; align-items: center; gap: 4px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-price { color: var(--text); font-weight: 600; font-size: 12px; }

.kb-tip {
  display: flex; align-items: center; gap: 6px;
  margin: 0; font-size: 12px; color: var(--text-4);
}
.skeleton-card { display: flex; flex-direction: column; gap: 7px; cursor: default; }

@media (max-width: 900px) {
  .kb-board { grid-auto-columns: minmax(230px, 78vw); }
  .kb-col { max-height: none; }
  .kb-search { width: 100%; }
}

/* ============================================================
   v1.15.1 生产看板重设计
   ============================================================ */
.board-page { gap: 16px; }

/* ---- 生产脉搏 Hero ---- */
.board-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 26px;
  align-items: center;
  padding: 26px 28px;
  overflow: hidden;
  border: 1px solid rgba(120, 150, 255, 0.2);
  border-radius: var(--radius-lg);
  background:
    radial-gradient(720px 220px at 0% -30%, rgba(93, 135, 255, 0.28), transparent 62%),
    radial-gradient(520px 220px at 100% 130%, rgba(255, 174, 31, 0.1), transparent 65%),
    linear-gradient(135deg, #151b30 0%, #101116 58%, #0d1017 100%);
  box-shadow: 0 20px 54px rgba(0, 0, 0, 0.24);
}
html.light .board-hero {
  border-color: rgba(93, 135, 255, 0.16);
  background:
    radial-gradient(720px 220px at 0% -30%, rgba(93, 135, 255, 0.18), transparent 62%),
    radial-gradient(520px 220px at 100% 130%, rgba(255, 174, 31, 0.08), transparent 65%),
    linear-gradient(135deg, #eef3ff 0%, #ffffff 58%, #fffaf1 100%);
  box-shadow: 0 16px 40px rgba(16, 24, 40, 0.07);
}
.bh-grid {
  position: absolute; inset: 0; opacity: 0.32; pointer-events: none;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
  background-size: 30px 30px;
  mask-image: linear-gradient(90deg, #000, transparent 76%);
}
html.light .bh-grid {
  background-image:
    linear-gradient(rgba(16, 24, 40, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(16, 24, 40, 0.05) 1px, transparent 1px);
}
.bh-copy { position: relative; z-index: 1; min-width: 0; }
.bh-eyebrow {
  display: flex; align-items: center; gap: 8px;
  font-size: 10.5px; font-weight: 650; letter-spacing: 0.16em;
  color: rgba(255, 255, 255, 0.52);
}
html.light .bh-eyebrow { color: var(--text-3); }
.bh-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--success); box-shadow: 0 0 12px var(--success); }
.bh-copy h1 {
  text-wrap: balance;
  margin: 10px 0 0; font-size: 30px; line-height: 1.3; font-weight: 700;
  letter-spacing: -0.5px; color: #fff;
}
.bh-copy h1 em {
  font-style: normal;
  background: linear-gradient(100deg, #7fa2ff, #ffd27a);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
html.light .bh-copy h1 { color: var(--text); }
html.light .bh-copy h1 em { background: var(--brand-grad); -webkit-background-clip: text; background-clip: text; }
.bh-copy > p { max-width: 560px; margin: 9px 0 0; font-size: 12.5px; line-height: 1.7; color: rgba(255, 255, 255, 0.55); }
html.light .bh-copy > p { color: var(--text-2); }
.bh-chips { display: flex; gap: 7px; flex-wrap: wrap; margin-top: 12px; }
.bh-chips span {
  display: inline-flex; align-items: center; gap: 5px;
  height: 24px; padding: 0 9px;
  border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  font-size: 10.5px; color: rgba(255, 255, 255, 0.6);
}
.bh-chips .iconify { color: #8fa9ff; font-size: 12px; }
html.light .bh-chips span { border-color: var(--border-2); background: rgba(255, 255, 255, 0.7); color: var(--text-2); }
.bh-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
.bh-actions .el-button--default { border-color: rgba(255, 255, 255, 0.18); background: rgba(255, 255, 255, 0.06); color: #fff; }
.bh-actions .el-button--default:hover { border-color: #fff; background: rgba(255, 255, 255, 0.12); color: #fff; }
html.light .bh-actions .el-button--default { border-color: var(--border-2); background: var(--card); color: var(--text-2); }

.bh-pulse { position: relative; z-index: 1; display: grid; grid-template-columns: repeat(2, 148px); gap: 9px; }
.bh-kpi {
  display: flex; align-items: flex-start; gap: 9px;
  min-width: 0; padding: 11px 12px; text-align: left; cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px;
  background: rgba(255, 255, 255, 0.04); color: #fff;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}
.bh-kpi:hover { transform: translateY(-2px); background: rgba(255, 255, 255, 0.08); border-color: rgba(255, 255, 255, 0.22); }
html.light .bh-kpi { border-color: var(--border); background: rgba(255, 255, 255, 0.72); color: var(--text); }
.bh-kpi-icon {
  width: 28px; height: 28px; flex-shrink: 0; border-radius: 8px;
  display: inline-flex; align-items: center; justify-content: center;
  background: rgba(255, 255, 255, 0.08); font-size: 15px;
}
.bh-kpi.brand .bh-kpi-icon { color: #8fa9ff; background: rgba(93, 135, 255, 0.16); }
.bh-kpi.danger .bh-kpi-icon { color: #ff8a8c; background: rgba(255, 77, 79, 0.14); }
.bh-kpi.warning .bh-kpi-icon { color: #ffd27a; background: rgba(255, 174, 31, 0.14); }
.bh-kpi.success .bh-kpi-icon { color: #5be7cf; background: rgba(19, 222, 185, 0.13); }
.bh-kpi.danger { border-color: rgba(255, 77, 79, 0.28); }
.bh-kpi-copy { min-width: 0; display: flex; flex-direction: column; }
.bh-kpi-copy small { font-size: 10px; color: rgba(255, 255, 255, 0.5); white-space: nowrap; }
.bh-kpi-copy b { margin-top: 1px; font-size: 21px; font-weight: 700; line-height: 1.15; font-variant-numeric: tabular-nums; }
.bh-kpi-copy em { margin-top: 1px; font-style: normal; font-size: 9px; color: rgba(255, 255, 255, 0.34); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
html.light .bh-kpi-copy small,
html.light .bh-kpi-copy em { color: var(--text-3); }

/* ---- 工具栏 ---- */
.kb-toolbar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  padding: 9px 12px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--card);
}
.kb-tools-left, .kb-tools-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.kb-total { font-size: 11.5px; color: var(--text-3); padding: 0 4px; }
.kb-total b { color: var(--text); font-size: 13px; font-variant-numeric: tabular-nums; }
.kb-finance { display: inline-flex; align-items: center; gap: 7px; }
.kb-fin-hint { font-size: 11px; color: var(--text-3); }
.kb-readonly {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11.5px; color: var(--text-3);
  padding: 3px 9px; border-radius: 7px; background: var(--card-2);
}
.kb-scroll-hint { display: none; align-items: center; gap: 4px; font-size: 10.5px; color: var(--text-4); }
.kb-scroll-hint .iconify { font-size: 12px; }
@media (max-width: 1300px) { .kb-scroll-hint { display: inline-flex; } }

/* ---- 看板网格 ---- */
.kb-board {
  grid-auto-columns: minmax(252px, 1fr);
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}
.kb-board::-webkit-scrollbar { display: none; }
.kb-col {
  position: relative;
  min-height: 360px;
  max-height: calc(100vh - 390px);
  background: linear-gradient(180deg, var(--card), color-mix(in srgb, var(--card) 84%, var(--bg)));
  border: 1px solid var(--border);
  border-radius: 16px;
  transition: border-color 0.18s, box-shadow 0.18s, background 0.18s;
}
.kb-col.is-drop { border-color: var(--brand); box-shadow: 0 0 0 2px var(--brand-weak), 0 18px 40px rgba(0, 0, 0, 0.18); }
.kb-col.is-drop.is-blocked { border-color: var(--danger); box-shadow: 0 0 0 2px var(--danger-weak); }
.kb-col.is-focus { animation: col-focus 0.9s ease; }
@keyframes col-focus { 0%, 100% { box-shadow: none; } 35% { box-shadow: 0 0 0 2px var(--brand), 0 0 34px var(--brand-weak); } }
.kb-col-head {
  position: sticky; top: 0; z-index: 2;
  display: flex; align-items: center; gap: 7px;
  padding: 12px 13px 11px;
  border-bottom: 1px solid var(--border);
  border-radius: 16px 16px 0 0;
  background: color-mix(in srgb, var(--card) 92%, transparent);
  backdrop-filter: blur(12px);
}
.kb-col-icon {
  width: 24px; height: 24px; flex-shrink: 0; border-radius: 7px;
  display: inline-flex; align-items: center; justify-content: center;
  color: var(--tone); background: color-mix(in srgb, var(--tone) 13%, transparent);
  font-size: 14px;
}
.kb-col-title { font-size: 13px; font-weight: 650; color: var(--text); }
.kb-col-count {
  min-width: 20px; height: 18px; padding: 0 5px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 9px; background: var(--card-3); color: var(--text-2);
  font-size: 10.5px; font-weight: 650; font-variant-numeric: tabular-nums;
}
.kb-col-more { font-size: 9px; color: var(--text-4); }
.kb-col-amount { margin-left: auto; font-size: 10.5px; color: var(--text-3); font-variant-numeric: tabular-nums; }
.kb-col-line { position: absolute; left: 0; right: 0; bottom: -1px; height: 2px; background: var(--card-3); overflow: hidden; }
.kb-col-line i { display: block; height: 100%; border-radius: 2px; transition: width 0.45s ease; }

.kb-drop-hint {
  display: flex; align-items: center; gap: 6px;
  margin: 8px 9px 0; padding: 8px 10px;
  border: 1px dashed color-mix(in srgb, var(--brand) 40%, transparent);
  border-radius: 9px; background: var(--brand-weak);
  color: var(--brand); font-size: 11px; font-weight: 500;
}
.kb-drop-hint.blocked { border-color: color-mix(in srgb, var(--danger) 40%, transparent); background: var(--danger-weak); color: var(--danger); }
.kb-drop-hint .iconify { font-size: 14px; }

.kb-col-body { padding: 9px; display: flex; flex-direction: column; gap: 9px; }

/* ---- 卡片 ---- */
.kb-card {
  position: relative;
  padding: 11px 12px 10px 14px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  cursor: pointer;
  overflow: hidden;
  transition: transform 0.16s cubic-bezier(0.22, 0.61, 0.36, 1), border-color 0.18s, box-shadow 0.18s;
  animation: rise-in 0.3s ease both;
}
.kb-card:hover {
  transform: translateY(-2px);
  border-color: var(--border-3);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.24);
}
html.light .kb-card:hover { box-shadow: 0 10px 24px rgba(16, 24, 40, 0.09); }
.kb-card.dragging { opacity: 0.42; transform: scale(0.98); }
.kb-card-accent {
  position: absolute; left: 0; top: 11px; bottom: 11px; width: 3px;
  border-radius: 0 3px 3px 0; background: var(--card-tone); opacity: 0.85;
}
.kb-card.overdue .kb-card-accent { background: var(--danger); }
.kb-card.overdue { border-left: 1px solid var(--border); }
.kb-card-top { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; min-width: 0; }
.kb-id { font-size: 10.5px; color: var(--text-3); letter-spacing: 0.02em; flex-shrink: 0; }
.kb-quality-mini { display: inline-flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text-3); min-width: 0; }
.kb-quality-mini i { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.kb-badge { margin-left: auto; font-size: 9.5px; font-weight: 600; padding: 0 6px; border-radius: 5px; line-height: 16px; white-space: nowrap; }
.kb-badge.overdue { color: var(--danger); background: var(--danger-weak); }
.kb-badge.soon { color: var(--warning); background: var(--warning-weak); }
.kb-badge.today { color: var(--warning); background: var(--warning-weak); font-weight: 700; }
.kb-title {
  margin: 0 0 8px; font-size: 12.5px; font-weight: 600; color: var(--text); line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.kb-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 10px; color: var(--text-3); }
.kb-cat-chip { display: inline-flex; align-items: center; gap: 3px; padding: 1px 6px; border: 1px solid; border-radius: 5px; font-size: 9.5px; }
.kb-deploy, .kb-due { display: inline-flex; align-items: center; gap: 3px; color: var(--text-4); font-size: 9.5px; }
.kb-deploy .iconify, .kb-due .iconify { font-size: 11px; }
.kb-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin-top: 9px; padding-top: 8px; border-top: 1px dashed var(--border);
}
.kb-agent { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
.kb-avatar {
  width: 20px; height: 20px; flex-shrink: 0; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--brand-weak); color: var(--brand); font-size: 9px; font-weight: 700;
}
.kb-agent-name { font-size: 10.5px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-price { color: var(--text); font-weight: 650; font-size: 12px; }

.kb-tip { margin: 0; font-size: 11px; color: var(--text-4); }

@media (max-width: 1300px) {
  .bh-pulse { grid-template-columns: repeat(2, 136px); }
}
@media (max-width: 1100px) {
  .board-hero { grid-template-columns: 1fr; align-items: start; gap: 18px; }
  .bh-pulse { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .kb-board { grid-auto-columns: minmax(258px, 82vw); }
  .kb-col { max-height: none; }
  .kb-search { width: 100%; }
  .kb-tools-left { flex: 1; min-width: 0; }
}
@media (max-width: 700px) {
  .board-hero { padding: 21px 18px; border-radius: var(--radius); }
  .bh-copy h1 { font-size: 24px; }
  .bh-chips { display: none; }
  .bh-pulse { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .bh-kpi { padding: 10px; }
  .bh-kpi-copy b { font-size: 18px; }
  .kb-toolbar { padding: 8px 10px; }
  .kb-total { display: none; }
  .kb-col { min-height: 300px; }
}
</style>
