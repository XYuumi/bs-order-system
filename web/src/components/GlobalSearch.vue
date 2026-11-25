<template>
  <el-dialog
    v-model="visible" :width="600" :fullscreen="isMobile"
    :show-close="false" class="gs-modal" append-to-body
  >
    <div class="gs-head">
      <Icon icon="ri:search-line" class="gs-icon" />
      <input
        ref="inputEl" v-model="kw" class="gs-input"
        placeholder="搜索订单，或输入页面名称…"
        @input="onInput"
        @keydown.enter.prevent="onEnter"
        @keydown.down.prevent="move(1)"
        @keydown.up.prevent="move(-1)"
        @keydown.esc="close"
      >
      <span class="gs-esc">ESC</span>
    </div>
    <div ref="bodyEl" class="gs-body" v-loading="loading" element-loading-background="transparent">
      <div v-if="!kw.trim()" class="gs-block">
        <p class="gs-sec-title">快捷入口 <span>输入关键词可同时搜索订单</span></p>
        <button
          v-for="(c, i) in commands" :key="c.key" class="gs-item"
          :class="{ active: i === activeIdx }" :data-idx="i"
          @click="runCommand(c)" @mousemove="activeIdx = i"
        >
          <Icon :icon="c.icon" class="gs-cmd-icon" />
          <span class="gs-cmd-label">{{ c.label }}</span>
          <span class="gs-cmd-hint">跳转</span>
        </button>
        <p v-if="!commands.length" class="gs-tip">没有匹配的快捷入口</p>
      </div>

      <template v-else>
        <div class="gs-block">
          <p class="gs-sec-title">
            订单 <span v-if="searched && !loading">{{ items.length }} 条结果</span>
          </p>
          <div v-if="errorMsg" class="gs-error">
            <Icon icon="ri:error-warning-line" />
            <span>{{ errorMsg }}</span>
          </div>
          <button
            v-for="(it, i) in items" :key="it.id" class="gs-item"
            :class="{ active: i === activeIdx }" :data-idx="i"
            @click="go(it)" @mousemove="activeIdx = i"
          >
            <span class="mono gs-id">{{ it.id }}</span>
            <span class="gs-title">{{ it.title }}</span>
            <QualityBadge :name="it.quality.name" :color="it.quality.color" />
            <StatusTag :status="it.status" />
          </button>
          <div v-if="loading && !items.length" class="gs-tip">正在搜索…</div>
          <EmptyState
            v-else-if="searched && !items.length && !errorMsg"
            compact
            icon="ri:file-search-line"
            title="没有匹配的订单"
            description="换个单号或题目关键词试试"
          />
        </div>

        <div v-if="commands.length" class="gs-block">
          <p class="gs-sec-title">页面与操作 <span>回车跳转</span></p>
          <button
            v-for="(c, i) in commands" :key="c.key" class="gs-item"
            :class="{ active: commandOffset + i === activeIdx }" :data-idx="commandOffset + i"
            @click="runCommand(c)" @mousemove="activeIdx = commandOffset + i"
          >
            <Icon :icon="c.icon" class="gs-cmd-icon" />
            <span class="gs-cmd-label">{{ c.label }}</span>
            <span class="gs-cmd-hint">跳转</span>
          </button>
        </div>
      </template>
    </div>
    <div class="gs-foot">
      <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
      <span><kbd>Enter</kbd> 打开</span>
      <span><kbd>Esc</kbd> 关闭</span>
      <span v-if="items.length" class="gs-count">{{ items.length }} 条订单</span>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import http from '../api'
import { useAuthStore } from '../stores/auth'
import QualityBadge from './QualityBadge.vue'
import StatusTag from './StatusTag.vue'
import EmptyState from './ui/EmptyState.vue'

const props = defineProps({ open: Boolean })
const emit = defineEmits(['update:open'])

const visible = computed({
  get: () => props.open,
  set: (v) => { if (!v) close() },
})

const router = useRouter()
const auth = useAuthStore()
const COMMAND_LIST = [
  { key: 'dashboard', label: '工作台', icon: 'ri:dashboard-2-line', path: '/', alias: '首页 工作台' },
  { key: 'orders', label: '订单列表', icon: 'ri:clipboard-line', path: '/orders', alias: '订单 管理 列表' },
  { key: 'board', label: '生产看板', icon: 'ri:kanban-view', path: '/orders/board', alias: '看板 拖拽 生产' },
  { key: 'calendar', label: '订单日历', icon: 'ri:calendar-schedule-line', path: '/orders/calendar', alias: '日历 排期 交期 月历' },
  { key: 'create', label: '新建订单', icon: 'ri:add-circle-line', path: '/orders/create', alias: '下单 新建 创建' },
  { key: 'customers', label: '客户管理', icon: 'ri:contacts-line', path: '/customers', alias: '客户 CRM' },
  { key: 'settlement', label: '对账单', icon: 'ri:bill-line', path: '/settlement', alias: '结算 佣金 对账', roles: ['admin', 'agent'] },
  { key: 'ai', label: 'AI 参谋', icon: 'ri:sparkling-2-line', path: '/ai', alias: 'AI 风险 需求书', roles: ['admin', 'staff'] },
  { key: 'margin', label: '毛利分析', icon: 'ri:money-cny-circle-line', path: '/margin', alias: '毛利 利润 成本', roles: ['admin'] },
  { key: 'users', label: '用户管理', icon: 'ri:group-line', path: '/users', alias: '账号 用户 权限', roles: ['admin'] },
  { key: 'profile', label: '个人中心', icon: 'ri:user-3-line', path: '/profile', alias: '账号 密码 2FA' },
]

const kw = ref('')
const items = ref([])
const loading = ref(false)
const searched = ref(false)
const activeIdx = ref(-1)
const errorMsg = ref('')
const inputEl = ref(null)
const bodyEl = ref(null)
let timer = null
let reqSeq = 0
let mediaQuery = null
const isMobile = ref(typeof window !== 'undefined' && window.matchMedia('(max-width: 640px)').matches)

const commands = computed(() => {
  const q = kw.value.trim().toLowerCase()
  return COMMAND_LIST.filter((c) => {
    if (c.roles && !c.roles.includes(auth.user?.role)) return false
    if (!q) return true
    return `${c.label} ${c.alias || ''}`.toLowerCase().includes(q)
  })
})
const commandOffset = computed(() => (kw.value.trim() ? items.value.length : 0))
const entryCount = computed(() => (kw.value.trim() ? items.value.length + commands.value.length : commands.value.length))

function onMediaChange(e) {
  isMobile.value = e.matches
}

function close() {
  clearTimeout(timer)
  reqSeq += 1
  loading.value = false
  activeIdx.value = -1
  emit('update:open', false)
}

async function fetchResults() {
  const q = kw.value.trim()
  if (!q) {
    reqSeq += 1
    items.value = []
    searched.value = false
    loading.value = false
    return
  }
  const seq = ++reqSeq
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await http.get('/orders', { params: { keyword: q, page: 1, page_size: 8 } })
    if (seq !== reqSeq) return
    items.value = data.items || []
    searched.value = true
    activeIdx.value = entryCount.value ? 0 : -1
  } catch {
    if (seq !== reqSeq) return
    items.value = []
    searched.value = true
    activeIdx.value = commands.value.length ? 0 : -1
    errorMsg.value = '搜索失败，请检查网络后重试'
  } finally {
    if (seq === reqSeq) loading.value = false
  }
}

function onInput() {
  activeIdx.value = 0
  errorMsg.value = ''
  clearTimeout(timer)
  // 每次输入都让在途请求失效
  reqSeq += 1
  if (!kw.value.trim()) {
    items.value = []
    searched.value = false
    loading.value = false
    return
  }
  timer = setTimeout(fetchResults, 280)
}

function doSearch() {
  clearTimeout(timer)
  fetchResults()
}

// ↑ / ↓ / Enter 键盘导航（订单在前，快捷入口在后）
function move(step) {
  if (!entryCount.value) return
  if (activeIdx.value < 0) activeIdx.value = step > 0 ? 0 : entryCount.value - 1
  else activeIdx.value = (activeIdx.value + step + entryCount.value) % entryCount.value
  nextTick(() => {
    bodyEl.value?.querySelector(`[data-idx="${activeIdx.value}"]`)?.scrollIntoView({ block: 'nearest' })
  })
}

function onEnter() {
  if (!kw.value.trim()) {
    if (activeIdx.value >= 0 && commands.value[activeIdx.value]) runCommand(commands.value[activeIdx.value])
    return
  }
  if (activeIdx.value >= 0 && activeIdx.value < entryCount.value) {
    if (activeIdx.value < items.value.length) {
      const it = items.value[activeIdx.value]
      if (it) go(it)
      return
    }
    const c = commands.value[activeIdx.value - items.value.length]
    if (c) runCommand(c)
    return
  }
  if (!searched.value) doSearch()
  else if (items.value.length) go(items.value[0])
}

function go(it) {
  close()
  router.push(`/orders/${it.id}`)
}

function runCommand(c) {
  close()
  router.push(c.path)
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      errorMsg.value = ''
      activeIdx.value = commands.value.length ? 0 : -1
      nextTick(() => inputEl.value?.focus())
      if (kw.value.trim()) doSearch()
    } else {
      clearTimeout(timer)
      reqSeq += 1
      loading.value = false
    }
  },
)

defineExpose({
  focus: () => nextTick(() => inputEl.value?.focus()),
})

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 640px)')
  isMobile.value = mediaQuery.matches
  mediaQuery.addEventListener('change', onMediaChange)
})

onBeforeUnmount(() => {
  clearTimeout(timer)
  reqSeq += 1
  loading.value = false
  mediaQuery?.removeEventListener('change', onMediaChange)
})
</script>

<style scoped>
.gs-head { display: flex; align-items: center; gap: 10px; padding: 6px 4px 12px; border-bottom: 1px solid var(--border); }
.gs-icon { font-size: 16px; color: var(--text-3); }
.gs-input {
  flex: 1; border: none; outline: none; background: transparent;
  color: var(--text); font-size: 15px; min-width: 0;
}
.gs-esc {
  font-size: 10px; color: var(--text-3); border: 1px solid var(--border-2);
  border-radius: 4px; padding: 1px 5px;
}
.gs-body { max-height: min(52vh, 460px); overflow-y: auto; padding: 8px 0; min-height: 80px; }
.gs-block + .gs-block { margin-top: 4px; padding-top: 4px; border-top: 1px dashed var(--border); }
.gs-sec-title {
  display: flex; align-items: center; gap: 8px;
  margin: 4px 10px 4px; font-size: 10.5px; font-weight: 600;
  letter-spacing: .06em; color: var(--text-3); text-transform: uppercase;
}
.gs-sec-title span { font-weight: 400; letter-spacing: 0; text-transform: none; color: var(--text-4); }
.gs-tip { color: var(--text-3); font-size: 12.5px; padding: 18px 6px; text-align: center; }
.gs-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 9px 10px; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px;
  border: 1px solid transparent; background: none; color: inherit; text-align: left;
  font-family: inherit;
}
.gs-item.active { background: var(--hover); border-color: var(--border-2); }
.gs-cmd-icon { font-size: 15px; color: var(--brand); flex-shrink: 0; }
.gs-cmd-label { flex: 1; min-width: 0; }
.gs-cmd-hint {
  flex-shrink: 0; font-size: 10.5px; color: var(--text-4);
  border: 1px solid var(--border); border-radius: 4px; padding: 0 5px;
}
.gs-item.active .gs-cmd-hint { color: var(--text-2); border-color: var(--border-2); }
.gs-error {
  display: flex; align-items: center; gap: 7px;
  margin: 2px 10px 6px; padding: 9px 10px; border-radius: var(--radius-sm);
  font-size: 12px; color: var(--danger);
  background: color-mix(in srgb, var(--danger) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--danger) 22%, transparent);
}
.gs-id { color: var(--brand); font-weight: 600; flex-shrink: 0; }
.gs-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gs-foot {
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  padding-top: 10px; border-top: 1px solid var(--border);
  font-size: 11px; color: var(--text-3);
}
.gs-foot kbd {
  display: inline-block; min-width: 18px; text-align: center;
  padding: 0 4px; margin-right: 3px;
  border: 1px solid var(--border-2); border-radius: 4px;
  background: var(--card-2); font-family: var(--font-mono); font-size: 10px;
}
.gs-count { margin-left: auto; }
</style>
<style>
.gs-modal { border-radius: 14px !important; }
.gs-modal .el-dialog__header { display: none; }
.gs-modal .el-dialog__body { padding: 16px 20px 14px; }
.gs-modal.is-fullscreen { border-radius: 0 !important; }
.gs-modal.is-fullscreen .el-dialog__body { padding: 14px 14px 12px; height: 100vh; display: flex; flex-direction: column; }
.gs-modal.is-fullscreen .gs-body { max-height: none; flex: 1; }
</style>