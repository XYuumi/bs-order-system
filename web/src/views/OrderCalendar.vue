<template>
  <div class="page-shell cal-page">
    <AppPageHeader
      title="订单日历"
      description="按交付期限查看整月排期，提前发现扎堆与逾期"
      icon="ri:calendar-schedule-line"
    >
      <template #actions>
        <el-button :loading="exporting" title="导出当前月份全部订单" @click="exportIcs">
          <Icon icon="ri:download-2-line" /> 导出 ICS
        </el-button>
        <el-button @click="goToday">
          <Icon icon="ri:calendar-check-line" /> 回到本月
        </el-button>
        <el-button type="primary" @click="router.push('/orders/create')">
          <Icon icon="ri:add-line" /> 新建订单
        </el-button>
      </template>
    </AppPageHeader>

    <div class="art-card cal-toolbar">
      <div class="cal-monthnav">
        <el-button circle text aria-label="上个月" @click="shiftMonth(-1)">
          <Icon icon="ri:arrow-left-s-line" />
        </el-button>
        <div class="cal-monthlabel">
          <h2>{{ monthLabel }}</h2>
          <p>{{ monthRangeText }}</p>
        </div>
        <el-button circle text aria-label="下个月" @click="shiftMonth(1)">
          <Icon icon="ri:arrow-right-s-line" />
        </el-button>
      </div>

      <div class="cal-stats">
        <span class="cal-stat"><i class="cs-dot all" />本月订单 <b>{{ summaryTotal }}</b></span>
        <span class="cal-stat"><i class="cs-dot open" />进行中 <b>{{ summary.open || 0 }}</b></span>
        <span class="cal-stat" :class="{ danger: (summary.overdue || 0) > 0 }">
          <i class="cs-dot overdue" />已逾期 <b>{{ summary.overdue || 0 }}</b>
        </span>
        <span class="cal-stat"><i class="cs-dot done" />已结单 <b>{{ summary.done || 0 }}</b></span>
      </div>

      <el-switch v-model="onlyOpen" class="cal-filter" active-text="只看进行中" />
    </div>

    <div v-if="error" class="cal-error">
      <Icon icon="ri:error-warning-line" />
      <span>{{ error }}</span>
      <el-button link type="primary" @click="load">重试</el-button>
    </div>

    <div v-loading="loading" class="cal-body" element-loading-background="transparent">
    <div class="art-card cal-sheet">
      <div class="cal-weekdays">
        <span v-for="w in weekdays" :key="w" :class="{ weekend: w === '六' || w === '日' }">{{ w }}</span>
      </div>
      <div class="cal-grid">
        <section
          v-for="cell in gridDays" :key="cell.key"
          class="cal-day"
          :data-date="cell.key"
          :class="{
            outside: !cell.inMonth,
            today: cell.isToday,
            weekend: cell.weekend,
            'has-events': dayOrders(cell).length,
            'drag-ready': dragId && cell.inMonth,
            'drop-target': dragOverKey === cell.key,
          }"
          @dragover="onDragOver(cell, $event)"
          @dragleave="onDragLeave(cell, $event)"
          @drop="onDrop(cell, $event)"
        >
          <header class="cal-dayhead">
            <span class="cal-daynum">{{ cell.day }}</span>
            <span v-if="cell.inMonth && dayOrders(cell).length" class="cal-count">{{ dayOrders(cell).length }}</span>
          </header>
          <div v-if="cell.inMonth" class="cal-events">
            <button
              v-for="o in dayOrders(cell).slice(0, 3)" :key="o.id"
              class="cal-event"
              :class="['st-' + o.status, { 'can-drag': canReschedule && o.status !== 'cancelled', 'is-dragging': dragId === o.id }]"
              :style="{ '--tone': statusMeta(o.status).hex }"
              :title="o.id + ' · ' + o.title + (canReschedule && o.status !== 'cancelled' ? ' · 拖拽可改期' : '')"
              :draggable="canReschedule && o.status !== 'cancelled' && !rescheduling"
              @click="openOrder(o)"
              @dragstart="onDragStart(o, $event)"
              @dragend="onDragEnd"
            >
              <span class="ce-dot" />
              <span class="ce-title">{{ o.title }}</span>
              <span class="ce-id">{{ o.id.slice(-3) }}</span>
            </button>
            <button
              v-if="dayOrders(cell).length > 3"
              class="cal-more" @click="openDay(cell)"
            >
              还有 {{ dayOrders(cell).length - 3 }} 单
            </button>
          </div>
        </section>
      </div>
      <div class="cal-foot">
        <span><Icon icon="ri:information-line" /> 日历按交付期限排序；已取消订单以灰色显示。</span>
        <span v-if="canReschedule" class="cal-drag-tip"><Icon icon="ri:drag-move-2-line" /> 拖拽订单到其他日期可改期</span>
        <span v-if="loading" class="cal-loading-tip">正在加载…</span>
      </div>
    </div>

    <!-- 手机端：月历格子太窄，切换为按日议程列表 -->
    <div class="cal-agenda">
      <div v-if="!agenda.length && !loading" class="cal-agenda-empty">
        <EmptyState compact icon="ri:calendar-line" title="本月暂无订单" description="切换月份或新建订单后再来看看" />
      </div>
      <section v-for="group in agenda" :key="group.key" class="art-card agenda-group" :class="{ today: group.isToday }">
        <header class="agenda-head">
          <div>
            <b>{{ group.label }}</b>
            <span>{{ group.weekday }}</span>
          </div>
          <span class="agenda-count">{{ group.orders.length }} 单</span>
        </header>
        <button
          v-for="o in group.orders" :key="o.id" class="agenda-row"
          :style="{ '--tone': statusMeta(o.status).hex }" @click="openOrder(o)"
        >
          <i class="agenda-dot" />
          <div class="agenda-main">
            <span class="agenda-title">{{ o.title }}</span>
            <span class="agenda-meta">{{ o.id }} · {{ statusMeta(o.status).label }} · {{ o.quality?.name || '未定级' }}</span>
          </div>
          <Icon icon="ri:arrow-right-s-line" class="agenda-arrow" />
        </button>
      </section>
    </div>
    </div>

    <el-dialog v-model="dayDialog.open" :title="dayDialog.title" width="min(520px, 94vw)">
      <div class="cal-dlg-list">
        <button v-for="o in dayDialog.items" :key="o.id" class="cal-dlg-row" @click="openOrder(o)">
          <div class="cal-dlg-main">
            <span class="cal-dlg-id">{{ o.id }}</span>
            <span class="cal-dlg-title">{{ o.title }}</span>
          </div>
          <div class="cal-dlg-meta">
            <QualityBadge :name="o.quality?.name || '未定级'" :color="o.quality?.color" />
            <StatusTag :status="o.status" />
          </div>
        </button>
      </div>
      <EmptyState v-if="!dayDialog.items.length" compact icon="ri:calendar-line" title="这一天没有订单" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'

import { useAuthStore } from '../stores/auth'

import http from '../api'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import QualityBadge from '../components/QualityBadge.vue'
import StatusTag from '../components/StatusTag.vue'
import { statusMeta } from '../constants/orderMeta'

const router = useRouter()
const auth = useAuthStore()
const weekdays = ['一', '二', '三', '四', '五', '六', '日']

// 改期只对管理员开放：写手/代理不能修改对客户承诺的交付日期。
const canReschedule = computed(() => auth.isAdmin)
const exporting = ref(false)
const dragId = ref('')
const dragOverKey = ref('')
const rescheduling = ref(false)
let suppressClickUntil = 0

const today = new Date()
today.setHours(0, 0, 0, 0)
const cursor = ref(new Date(today.getFullYear(), today.getMonth(), 1))
const items = ref([])
const summary = ref({ open: 0, done: 0, overdue: 0, cancelled: 0 })
const loading = ref(false)
const error = ref('')
const onlyOpen = ref(false)
let loadSeq = 0

function pad(n) { return String(n).padStart(2, '0') }
function ymd(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }
function addDays(d, n) {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  x.setDate(x.getDate() + n)
  return x
}
function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1) }
function endOfMonth(d) { return new Date(d.getFullYear(), d.getMonth() + 1, 0) }
function sameDay(a, b) { return ymd(a) === ymd(b) }
function fmtDate(iso) {
  if (!iso) return '未设置'
  const [, m, d] = String(iso).slice(0, 10).split('-')
  return `${Number(m)} 月 ${Number(d)} 日`
}

const monthStart = computed(() => startOfMonth(cursor.value))
const monthEnd = computed(() => endOfMonth(cursor.value))
const monthLabel = computed(() => `${monthStart.value.getFullYear()} 年 ${monthStart.value.getMonth() + 1} 月`)
const monthRangeText = computed(() => `${ymd(monthStart.value)} 至 ${ymd(monthEnd.value)}`)
const summaryTotal = computed(() => items.value.length)

const weekStart = computed(() => {
  const first = monthStart.value
  const offset = (first.getDay() + 6) % 7
  return addDays(first, -offset)
})

const gridDays = computed(() => {
  const out = []
  for (let i = 0; i < 42; i += 1) {
    const d = addDays(weekStart.value, i)
    out.push({
      key: ymd(d),
      date: d,
      day: d.getDate(),
      inMonth: d.getMonth() === monthStart.value.getMonth(),
      isToday: sameDay(d, today),
      weekend: d.getDay() === 0 || d.getDay() === 6,
    })
  }
  return out
})

const visibleItems = computed(() => (
  onlyOpen.value ? items.value.filter((o) => o.status === 'pending' || o.status === 'in_progress') : items.value
))

const ordersByDay = computed(() => {
  const map = {}
  for (const o of visibleItems.value) {
    if (!o.deadline) continue
    if (!map[o.deadline]) map[o.deadline] = []
    map[o.deadline].push(o)
  }
  return map
})

function dayOrders(cell) {
  return ordersByDay.value[ymd(cell.date)] || []
}

const agenda = computed(() => {
  const groups = []
  for (let d = new Date(monthStart.value); d <= monthEnd.value; d = addDays(d, 1)) {
    const orders = ordersByDay.value[ymd(d)] || []
    if (!orders.length) continue
    groups.push({
      key: ymd(d),
      label: `${d.getMonth() + 1} 月 ${d.getDate()} 日`,
      weekday: ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()],
      isToday: sameDay(d, today),
      orders,
    })
  }
  return groups
})

async function load() {
  const seq = ++loadSeq
  loading.value = true
  error.value = ''
  try {
    const data = await http.get('/orders/calendar', {
      params: { start: ymd(monthStart.value), end: ymd(monthEnd.value) },
    })
    if (seq !== loadSeq) return
    items.value = data.items || []
    summary.value = data.summary || { open: 0, done: 0, overdue: 0, cancelled: 0 }
  } catch {
    if (seq !== loadSeq) return
    items.value = []
    summary.value = { open: 0, done: 0, overdue: 0, cancelled: 0 }
    error.value = '日历数据加载失败，请稍后重试'
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function shiftMonth(step) {
  cursor.value = new Date(cursor.value.getFullYear(), cursor.value.getMonth() + step, 1)
  load()
}

function goToday() {
  cursor.value = new Date(today.getFullYear(), today.getMonth(), 1)
  load()
}

function openOrder(o) {
  // 刚结束拖拽时浏览器还会补发一次 click，避免误跳详情。
  if (Date.now() < suppressClickUntil) return
  dayDialog.open = false
  router.push(`/orders/${o.id}`)
}

function onDragStart(o, event) {
  if (!canReschedule.value || rescheduling.value || o.status === 'cancelled') {
    event.preventDefault()
    return
  }
  dragId.value = o.id
  dragOverKey.value = ''
  suppressClickUntil = Date.now() + 600
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    // Firefox 需要 setData 才会真正开始拖拽。
    event.dataTransfer.setData('text/plain', o.id)
  }
}

function onDragEnd() {
  dragId.value = ''
  dragOverKey.value = ''
  suppressClickUntil = Date.now() + 600
}

function onDragOver(cell, event) {
  if (!canReschedule.value || !dragId.value || rescheduling.value || !cell.inMonth) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  dragOverKey.value = cell.key
}

function onDragLeave(cell, event) {
  // 只有真正离开这一格时才清高亮，子元素之间移动不清。
  if (event.currentTarget.contains(event.relatedTarget)) return
  if (dragOverKey.value === cell.key) dragOverKey.value = ''
}

async function onDrop(cell, event) {
  const id = dragId.value
  dragId.value = ''
  dragOverKey.value = ''
  suppressClickUntil = Date.now() + 600
  if (!canReschedule.value || !id || rescheduling.value) return
  event.preventDefault()

  if (!cell.inMonth) {
    ElMessage.warning('请先切换到目标月份再拖拽改期')
    return
  }

  const order = items.value.find((o) => o.id === id)
  if (!order) return
  const target = ymd(cell.date)
  if (order.deadline === target) return
  if (order.status === 'cancelled') {
    ElMessage.warning('已取消订单不可改期')
    return
  }

  const oldDeadline = order.deadline
  try {
    await ElMessageBox.confirm(
      `将「${order.title}」的交付期限从 ${fmtDate(oldDeadline)} 调整为 ${fmtDate(target)}？`,
      '拖拽改期',
      {
        confirmButtonText: '确认改期',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return
  }

  rescheduling.value = true
  order.deadline = target
  try {
    await http.patch(`/orders/${encodeURIComponent(id)}/deadline`, { deadline: target })
    ElMessage.success(`已将 ${id} 改期至 ${fmtDate(target)}`)
    await load()
  } catch {
    order.deadline = oldDeadline
  } finally {
    rescheduling.value = false
  }
}

async function exportIcs() {
  if (exporting.value) return
  exporting.value = true
  try {
    const start = ymd(monthStart.value)
    const end = ymd(monthEnd.value)
    const blob = await http.get('/orders/calendar.ics', {
      params: { start, end },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `订单日历_${start}_${end}.ics`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1500)
    ElMessage.success('本月日历已导出，可导入系统日历')
  } catch {
    // 错误提示已由 axios 拦截器统一处理。
  } finally {
    exporting.value = false
  }
}

const dayDialog = reactive({ open: false, title: '', items: [] })
function openDay(cell) {
  const list = dayOrders(cell)
  dayDialog.title = `${cell.date.getMonth() + 1} 月 ${cell.day} 日 · ${list.length} 单`
  dayDialog.items = list
  dayDialog.open = true
}

onMounted(load)
</script>

<style scoped>
.cal-page { gap: 14px; }

/* ===== 工具栏 ===== */
.cal-toolbar {
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  padding: 12px 16px;
}
.cal-monthnav { display: flex; align-items: center; gap: 6px; }
.cal-monthlabel h2 { margin: 0; font-size: 16px; font-weight: 650; letter-spacing: 0.01em; }
.cal-monthlabel p { margin: 2px 0 0; font-size: 11.5px; color: var(--text-3); font-family: var(--font-mono); }
.cal-stats { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-left: auto; }
.cal-stat { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-3); white-space: nowrap; }
.cal-stat b { color: var(--text); font-size: 13px; font-family: var(--font-mono); }
.cal-stat.danger b { color: var(--danger); }
.cs-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.cs-dot.all { background: var(--brand); }
.cs-dot.open { background: var(--status-in_progress); }
.cs-dot.overdue { background: var(--danger); }
.cs-dot.done { background: var(--status-completed); }
.cal-filter { flex-shrink: 0; }

.cal-error {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-radius: var(--radius-sm);
  color: var(--danger); background: var(--danger-weak); border: 1px solid color-mix(in srgb, var(--danger) 24%, transparent);
  font-size: 12.5px;
}

/* ===== 月历 ===== */
.cal-body { position: relative; display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.cal-sheet { padding: 0; overflow: hidden; }
.cal-weekdays {
  display: grid; grid-template-columns: repeat(7, minmax(0, 1fr));
  border-bottom: 1px solid var(--border);
  background: var(--card-2);
}
.cal-weekdays span {
  padding: 9px 8px; text-align: right; font-size: 11.5px; font-weight: 600;
  color: var(--text-3); border-right: 1px solid var(--border);
}
.cal-weekdays span:last-child { border-right: none; }
.cal-weekdays .weekend { color: var(--warning); }

.cal-grid {
  display: grid; grid-template-columns: repeat(7, minmax(0, 1fr));
  background: var(--border);
  gap: 1px;
}
.cal-day {
  min-width: 0; min-height: 122px;
  background: var(--card); padding: 7px 7px 8px;
  display: flex; flex-direction: column; gap: 4px;
  transition: background .16s ease;
}
.cal-day:hover { background: color-mix(in srgb, var(--brand) 4%, var(--card)); }
.cal-day.outside { background: color-mix(in srgb, var(--card) 86%, var(--bg)); }
.cal-day.outside .cal-daynum { color: var(--text-4); }
.cal-day.today { box-shadow: inset 0 0 0 1.5px var(--brand); background: color-mix(in srgb, var(--brand) 7%, var(--card)); }
.cal-day.drag-ready { outline: 1px dashed color-mix(in srgb, var(--brand) 46%, transparent); outline-offset: -4px; }
.cal-day.drop-target {
  background: color-mix(in srgb, var(--brand) 12%, var(--card));
  outline: 2px solid var(--brand);
  outline-offset: -2px;
}
.cal-dayhead { display: flex; align-items: center; justify-content: space-between; min-height: 20px; }
.cal-daynum { font-size: 12px; color: var(--text-2); font-family: var(--font-mono); }
.cal-day.today .cal-daynum { color: var(--brand); font-weight: 700; }
.cal-count {
  min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 600; color: var(--text-2);
  background: var(--card-3, var(--card-2));
}
.cal-events { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.cal-event {
  display: flex; align-items: center; gap: 5px; width: 100%; min-width: 0;
  border: none; border-left: 2px solid var(--tone, var(--brand));
  background: color-mix(in srgb, var(--tone, var(--brand)) 12%, transparent);
  color: var(--text); border-radius: 4px; padding: 4px 5px;
  font-size: 11px; line-height: 1.35; text-align: left; cursor: pointer;
  transition: background .14s ease, transform .14s ease;
}
.cal-event:hover { background: color-mix(in srgb, var(--tone, var(--brand)) 22%, transparent); transform: translateY(-1px); }
.cal-event.can-drag { cursor: grab; }
.cal-event.can-drag:active { cursor: grabbing; }
.cal-event.is-dragging { opacity: .32; transform: none; }
.cal-event.st-closed, .cal-event.st-after_sale, .cal-event.st-cancelled { opacity: .68; }
.cal-event.st-cancelled { text-decoration: line-through; }
.ce-dot { width: 4px; height: 4px; border-radius: 50%; background: var(--tone, var(--brand)); flex-shrink: 0; }
.ce-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ce-id { color: var(--text-3); font-family: var(--font-mono); font-size: 9.5px; flex-shrink: 0; }
.cal-more {
  border: none; background: none; color: var(--text-3);
  font-size: 10.5px; text-align: left; padding: 1px 4px; cursor: pointer;
}
.cal-more:hover { color: var(--brand); }
.cal-foot {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 9px 14px; border-top: 1px solid var(--border);
  font-size: 11px; color: var(--text-3);
}
.cal-foot span { display: inline-flex; align-items: center; gap: 5px; }
.cal-loading-tip { margin-left: auto; color: var(--brand); }
.cal-drag-tip { color: var(--brand); }

/* ===== 手机议程 ===== */
.cal-agenda { display: none; flex-direction: column; gap: 10px; }
.cal-agenda-empty { padding: 26px 0; }
.agenda-group { padding: 0; overflow: hidden; }
.agenda-group.today { border-color: color-mix(in srgb, var(--brand) 52%, var(--border)); }
.agenda-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; background: var(--card-2); border-bottom: 1px solid var(--border);
}
.agenda-head b { font-size: 13px; }
.agenda-head span { margin-left: 7px; font-size: 11px; color: var(--text-3); }
.agenda-head .agenda-count { color: var(--text-2); font-family: var(--font-mono); }
.agenda-group.today .agenda-head b { color: var(--brand); }
.agenda-row {
  display: flex; align-items: center; gap: 9px; width: 100%;
  padding: 10px 14px; border: none; border-bottom: 1px solid var(--border);
  background: none; text-align: left; cursor: pointer;
}
.agenda-row:last-child { border-bottom: none; }
.agenda-row:active { background: var(--hover); }
.agenda-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--tone); flex-shrink: 0; }
.agenda-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.agenda-title { font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.agenda-meta { font-size: 10.5px; color: var(--text-3); font-family: var(--font-mono); }
.agenda-arrow { color: var(--text-3); flex-shrink: 0; }

/* ===== 当天弹窗 ===== */
.cal-dlg-list { display: flex; flex-direction: column; gap: 6px; max-height: 60vh; overflow-y: auto; }
.cal-dlg-row {
  display: flex; align-items: center; gap: 12px; width: 100%;
  padding: 10px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--border); background: var(--card-2);
  cursor: pointer; text-align: left;
}
.cal-dlg-row:hover { border-color: var(--brand); background: var(--hover); }
.cal-dlg-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.cal-dlg-id { font-size: 10.5px; color: var(--brand); font-family: var(--font-mono); }
.cal-dlg-title { font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cal-dlg-meta { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

@media (max-width: 1100px) {
  .cal-stats { order: 3; width: 100%; margin-left: 0; padding-top: 8px; border-top: 1px dashed var(--border); }
  .cal-filter { margin-left: auto; }
  .ce-id { display: none; }
}
@media (max-width: 900px) {
  .cal-toolbar { gap: 10px; }
  .cal-sheet { display: none; }
  .cal-agenda { display: flex; }
  .cal-filter { margin-left: auto; }
  .cal-foot .cal-drag-tip { display: none; }
}
@media (max-width: 560px) {
  .cal-toolbar { padding: 10px 12px; }
  .cal-monthlabel h2 { font-size: 15px; }
  .cal-monthlabel p { display: none; }
  .cal-stats { gap: 10px 14px; }
  .cal-stat { font-size: 11.5px; }
}
</style>