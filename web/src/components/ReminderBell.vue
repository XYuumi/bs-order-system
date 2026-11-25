<template>
  <el-popover v-model:visible="popOpen" trigger="click" placement="bottom-end" :width="360" popper-class="bell-pop">
    <template #reference>
      <button class="icon-btn tb-bell art-hover-shake" title="消息提醒">
        <el-badge :value="count" :hidden="!count" :max="99" :offset="[2, 2]">
          <Icon icon="ri:notification-2-line" style="font-size: 19px" />
        </el-badge>
      </button>
    </template>
      <div class="bell-panel">
        <div class="bell-tabs">
          <button class="bt-item" :class="{ active: tab === 'notify' }" @click="tab = 'notify'">
            通知 <span v-if="notifyUnread" class="bt-dot">{{ notifyUnread > 99 ? '99+' : notifyUnread }}</span>
          </button>
          <button class="bt-item" :class="{ active: tab === 'due' }" @click="tab = 'due'">
            到期提醒 <span v-if="dueCount" class="bt-dot warn-dot">{{ dueCount }}</span>
          </button>
          <button class="bt-item" :class="{ active: tab === 'ann' }" @click="tab = 'ann'; loadAnn()">
            公告 <span v-if="annItems.length" class="bt-dot ann-dot">{{ annItems.length }}</span>
          </button>
          <button v-if="tab === 'notify' && notifyUnread" class="bt-read" @click="readAll">全部已读</button>
        </div>

        <!-- 站内通知 -->
        <template v-if="tab === 'notify'">
          <div v-if="!notifyItems.length" class="bell-empty">暂无通知</div>
          <div v-for="n in notifyItems" :key="n.id" class="notify-item" :class="{ unread: !n.is_read }" @click="goOrder(n)">
            <div class="ni-dot" />
            <div class="ni-main">
              <div class="ni-title">{{ n.title }}</div>
              <div v-if="n.body" class="ni-body">{{ n.body }}</div>
              <div class="ni-time">{{ fmtTime(n.created_at) }}</div>
            </div>
          </div>
        </template>

        <!-- 到期提醒 -->
        <template v-else-if="tab === 'due'">
          <div v-if="dueCount === 0" class="bell-empty">暂无临期/逾期订单 🎉</div>
          <template v-else>
            <div v-if="dueData.overdue.length" class="bell-group">
              <div class="group-label danger">已逾期 {{ dueData.overdue.length }}</div>
              <div v-for="o in dueData.overdue" :key="o.id" class="bell-item" @click="go(o)">
                <span class="mono item-id">{{ o.id }}</span>
                <span class="item-title">{{ o.title }}</span>
                <span class="item-date danger">{{ o.deadline }}</span>
              </div>
            </div>
            <div v-if="dueData.due_soon.length" class="bell-group">
              <div class="group-label warn">3 天内到期 {{ dueData.due_soon.length }}</div>
              <div v-for="o in dueData.due_soon" :key="o.id" class="bell-item" @click="go(o)">
                <span class="mono item-id">{{ o.id }}</span>
                <span class="item-title">{{ o.title }}</span>
                <span class="item-date warn">{{ o.deadline }}</span>
              </div>
            </div>
          </template>
        </template>

        <!-- 系统公告 -->
        <template v-else-if="tab === 'ann'">
          <div v-if="!annItems.length" class="bell-empty">暂无公告</div>
          <div v-for="a in annItems" :key="a.id" class="notify-item ann-item" @click="annOpen = a">
            <span class="ann-ic" :class="a.level"><Icon :icon="annIcon(a.level)" /></span>
            <div class="ni-main">
              <div class="ni-title">
                <span v-if="a.level !== 'info'" class="ann-tag" :class="a.level">{{ a.level_cn }}</span>{{ a.title }}
              </div>
              <div class="ni-body">{{ a.content.slice(0, 60) }}{{ a.content.length > 60 ? '…' : '' }}</div>
              <div class="ni-time">{{ fmtTime(a.created_at) }} · {{ a.username }}</div>
            </div>
          </div>
        </template>
      </div>

      <!-- 公告详情弹窗 -->
      <el-dialog v-model="annVisible" :title="annOpen?.title" width="480px" append-to-body>
        <div v-if="annOpen">
          <div class="ann-meta">
            <span class="ann-tag" :class="annOpen.level">{{ annOpen.level_cn }}</span>
            <span class="text-2">{{ fmtTime(annOpen.created_at) }} · {{ annOpen.username }}</span>
          </div>
          <div class="ann-content">{{ annOpen.content }}</div>
        </div>
      </el-dialog>
  </el-popover>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import http from '../api'

const router = useRouter()
const popOpen = ref(false)
const tab = ref('notify')
const dueData = ref({ overdue: [], due_soon: [] })
const annItems = ref([])
const annOpen = ref(null)
const annVisible = computed({
  get: () => !!annOpen.value,
  set: (v) => { if (!v) annOpen.value = null },
})
async function loadAnn() {
  if (annItems.value.length) return
  try {
    const data = await http.get('/announcements', { params: { limit: 10 } })
    annItems.value = data.items || []
  } catch { /* 拦截器处理 */ }
}
function annIcon(level) {
  return { info: 'ri:information-line', warning: 'ri:alert-line', important: 'ri:megaphone-line' }[level] || 'ri:information-line'
}
const notifyItems = ref([])
const notifyUnread = ref(0)
let timer = null

const dueCount = computed(() => dueData.value.overdue.length + dueData.value.due_soon.length)
const count = computed(() => notifyUnread.value + (dueCount.value ? 1 : 0))

async function load() {
  try {
    const [due, notify] = await Promise.allSettled([
      http.get('/orders/reminders'),
      http.get('/notifications', { params: { limit: 20 } }),
    ])
    if (due.status === 'fulfilled') dueData.value = due.value
    if (notify.status === 'fulfilled') {
      notifyItems.value = notify.value.items || []
      notifyUnread.value = notify.value.unread || 0
    }
  } catch { /* 忽略 */ }
}

async function readAll() {
  try {
    await http.post('/notifications/read-all')
    notifyUnread.value = 0
    notifyItems.value = notifyItems.value.map((n) => ({ ...n, is_read: true }))
  } catch { /* 拦截器处理 */ }
}

function go(o) {
  popOpen.value = false
  router.push(`/orders/${o.id}`)
}

function goOrder(n) {
  if (n.order_id) {
    popOpen.value = false
    router.push(`/orders/${n.order_id}`)
  }
}

function fmtTime(t) {
  return t ? String(t).replace('T', ' ').slice(5, 16) : ''
}

onMounted(() => {
  load()
  timer = setInterval(load, 60 * 1000)
  // WebSocket 实时刷新（秒级，替代等下一轮轮询）
  window.addEventListener('ws', onWs)
})
onBeforeUnmount(() => { clearInterval(timer); window.removeEventListener('ws', onWs) })

function onWs(e) {
  const msg = e.detail || {}
  if (msg.type === 'notify') load()
}
</script>

<style scoped>
/* 与顶栏 .tb-icon-btn 统一 34px */
.icon-btn.tb-bell {
  width: 34px; height: 34px; border-radius: 6px; font-size: 18px;
  line-height: 0;
}
/* el-badge 默认 inline-block 会带出行高，图标因此比右侧 .tb-icon-btn 高 1-2px；
   改为 flex 居中并清掉 line-height，让铃铛与其它顶栏图标严格同一基线。 */
.icon-btn.tb-bell :deep(.el-badge) {
  display: inline-flex; align-items: center; justify-content: center;
  line-height: 0;
}
.icon-btn.tb-bell :deep(.el-badge__content) {
  line-height: 1;
}
/* 光学微调：徽标数字不参与布局时，铃铛视觉重心仍会略高 1px */
.icon-btn.tb-bell :deep(svg) { transform: translateY(1px); }

.bell-panel { width: 340px; max-width: calc(100vw - 40px); }
.ann-dot { background: var(--brand); }
.ann-item { align-items: flex-start; }
.ann-ic {
  width: 30px; height: 30px; border-radius: 8px; flex-shrink: 0; margin-top: 2px;
  display: flex; align-items: center; justify-content: center; font-size: 15px;
  background: var(--brand-weak); color: var(--brand);
}
.ann-ic.warning { background: rgba(245, 158, 11, 0.12); color: #f59e0b; }
.ann-ic.important { background: rgba(255, 77, 79, 0.12); color: #ff7875; }
.ann-tag {
  font-size: 10.5px; font-weight: 600; padding: 0 6px; border-radius: 4px; margin-right: 6px;
  background: var(--brand-weak); color: var(--brand);
}
.ann-tag.warning { background: rgba(245, 158, 11, 0.12); color: #f59e0b; }
.ann-tag.important { background: rgba(255, 77, 79, 0.12); color: #ff7875; }
.ann-meta { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; font-size: 12px; }
.ann-content { font-size: 13.5px; line-height: 1.8; white-space: pre-wrap; }
.bell-tabs {
  display: flex; align-items: center; gap: 4px;
  border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 8px;
}
.bt-item {
  position: relative; border: none; background: transparent; cursor: pointer;
  font-size: 13px; font-weight: 600; color: var(--text-2);
  padding: 4px 10px; border-radius: 7px;
}
.bt-item.active { color: var(--brand); background: var(--brand-weak); }
.bt-dot {
  margin-left: 4px; font-size: 10.5px; background: #FF4D4F; color: #fff;
  border-radius: 999px; padding: 0 6px;
}
.bt-dot.warn-dot { background: #FFAE1F; }
.bt-read {
  margin-left: auto; border: none; background: transparent; cursor: pointer;
  color: var(--brand); font-size: 12px;
}
.notify-item {
  display: flex; gap: 8px; padding: 8px; border-radius: 8px; cursor: pointer;
}
.notify-item:hover { background: var(--hover); }
.notify-item.unread .ni-title { font-weight: 600; }
.ni-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--brand); flex-shrink: 0; margin-top: 7px; }
.notify-item:not(.unread) .ni-dot { background: transparent; }
.ni-main { min-width: 0; flex: 1; }
.ni-title { font-size: 12.5px; line-height: 1.5; }
.ni-body { font-size: 12px; color: var(--text-2); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ni-time { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.bell-empty { color: var(--text-3); font-size: 12.5px; padding: 14px 0; text-align: center; }
.bell-group { margin-bottom: 10px; }
.group-label { font-size: 12px; margin-bottom: 4px; }
.group-label.danger { color: #f87171; }
.group-label.warn { color: #fbbf24; }
.bell-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 8px; border-radius: 8px; cursor: pointer; font-size: 12.5px;
}
.bell-item:hover { background: var(--hover); }
.item-id { color: var(--brand); flex-shrink: 0; }
.item-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-date { flex-shrink: 0; font-weight: 600; }
.item-date.danger { color: #f87171; }
.item-date.warn { color: #fbbf24; }

@media (min-width: 2200px) {
  .icon-btn.tb-bell { width: 38px; height: 38px; }
  .icon-btn.tb-bell :deep(svg) { width: 21px; height: 21px; transform: translateY(1px); }
}
@media (min-width: 3000px) {
  .icon-btn.tb-bell { width: 44px; height: 44px; }
  .icon-btn.tb-bell :deep(svg) { width: 24px; height: 24px; transform: translateY(1px); }
}
</style>
