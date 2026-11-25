<template>
  <div class="page-shell sug-page">
    <AppPageHeader
      title="建议反馈"
      :description="auth.isStaffView ? '代理与写手提交的建议/问题工单，回复后提交人会收到通知' : '对订单或系统有想法？提交后后台与写手会同步收到通知（代理不能直接改单）'"
      icon="ri:lightbulb-line"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">
          <Icon icon="ri:add-line" />提建议
        </el-button>
      </template>
    </AppPageHeader>

    <!-- 筛选 -->
    <div class="art-card sug-filters">
      <div class="pill-tabs">
        <button
          v-for="t in statusTabs" :key="t.value"
          class="pill-tab" :class="{ active: filter.status === t.value }"
          @click="setStatusFilter(t.value)"
        >
          {{ t.label }}
          <span v-if="t.value && counts[t.value]" class="pill-count">{{ counts[t.value] > 99 ? '99+' : counts[t.value] }}</span>
        </button>
      </div>
      <div class="sf-right">
        <el-select
          v-if="auth.isStaffView"
          v-model="filter.kind" class="sf-kind" placeholder="全部类型"
          clearable @change="load"
        >
          <el-option label="建议" value="suggestion" />
          <el-option label="问题" value="issue" />
          <el-option label="加急" value="urgent" />
        </el-select>
        <el-checkbox v-if="auth.isStaffView" v-model="filter.mine" @change="load">只看我的</el-checkbox>
      </div>
    </div>

    <!-- 列表 -->
    <div v-loading="loading" class="sug-body">
      <div v-if="items.length" class="sug-list">
        <div v-for="s in items" :key="s.id" class="art-card sug-item" :class="s.kind">
          <div class="si-head">
            <span class="si-kind" :class="s.kind">{{ s.kind_cn }}</span>
            <span class="si-id">#{{ s.id }}</span>
            <router-link v-if="s.order_id" :to="`/orders/${s.order_id}`" class="si-order">
              <Icon icon="ri:link" />{{ s.order_id }}
            </router-link>
            <span class="si-user">{{ s.username }}</span>
            <span class="si-status" :class="s.status">{{ s.status_cn }}</span>
            <span class="si-time">{{ fmtTime(s.created_at) }}</span>
          </div>
          <div class="si-content">{{ s.content }}</div>

          <!-- 已有回复 -->
          <div v-if="s.reply" class="si-reply">
            <div class="si-reply-head">
              <Icon icon="ri:message-3-line" class="si-reply-icon" />
              <b>{{ s.replied_by }}</b> 回复于 {{ fmtTime(s.replied_at) }}
            </div>
            <div class="si-reply-body">{{ s.reply }}</div>
          </div>

          <!-- 管理员/写手：回复 + 状态操作 -->
          <div v-if="canReply" class="si-actions">
            <template v-if="replyTo === s.id">
              <el-input v-model="replyForm.reply" type="textarea" :rows="2" :maxlength="2000" placeholder="回复内容（提交人会收到通知）" />
              <div class="si-reply-row">
                <el-select v-model="replyForm.status" style="width: 120px">
                  <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
                <div class="si-reply-btns">
                  <el-button size="small" :disabled="replying" @click="replyTo = null">取消</el-button>
                  <el-button size="small" type="primary" :loading="replying" @click="submitReply(s)">提交回复</el-button>
                </div>
              </div>
            </template>
            <template v-else>
              <el-button size="small" :disabled="statusLoadingId != null" @click="startReply(s)">
                <Icon icon="ri:message-3-line" /> 回复
              </el-button>
              <el-button
                v-if="s.status === 'open'" size="small"
                :loading="statusLoadingId === s.id && pendingStatus === 'processing'"
                :disabled="statusLoadingId != null && statusLoadingId !== s.id"
                @click="setStatus(s, 'processing')"
              >标记处理中</el-button>
              <el-button
                v-if="s.status !== 'closed' && s.status !== 'resolved'" size="small"
                :loading="statusLoadingId === s.id && pendingStatus === 'resolved'"
                :disabled="statusLoadingId != null && statusLoadingId !== s.id"
                @click="setStatus(s, 'resolved')"
              >标记已解决</el-button>
              <el-button
                v-if="s.status !== 'closed'" size="small" type="danger"
                :loading="statusLoadingId === s.id && pendingStatus === 'closed'"
                :disabled="statusLoadingId != null && statusLoadingId !== s.id"
                @click="setStatus(s, 'closed')"
              >关闭</el-button>
            </template>
          </div>
        </div>
      </div>
      <EmptyState
        v-else-if="!loading"
        icon="ri:lightbulb-line"
        :title="filter.status || filter.kind || filter.mine ? '没有符合条件的反馈' : '暂无建议'"
        :description="filter.status || filter.kind || filter.mine ? '试试切换状态或清空筛选条件' : '点击「提建议」发起第一条，后台与写手会同步收到通知'"
      >
        <el-button v-if="!filter.status && !filter.kind && !filter.mine" type="primary" @click="openCreate">
          <Icon icon="ri:add-line" />提建议
        </el-button>
      </EmptyState>
    </div>

    <!-- 提交弹窗 -->
    <el-dialog v-model="createOpen" title="提交建议 / 工单" width="min(520px, 94vw)">
      <div class="sc-form">
        <div class="sc-row">
          <span class="sc-label">类型</span>
          <el-radio-group v-model="form.kind">
            <el-radio-button value="suggestion">建议</el-radio-button>
            <el-radio-button value="issue">问题</el-radio-button>
            <el-radio-button value="urgent">加急</el-radio-button>
          </el-radio-group>
        </div>
        <div class="sc-row">
          <span class="sc-label">关联订单</span>
          <el-input v-model="form.order_id" placeholder="选填，如 261018-001（本人名下订单）" style="max-width: 260px" />
        </div>
        <div class="sc-row sc-row-top">
          <span class="sc-label">内容</span>
          <el-input v-model="form.content" type="textarea" :rows="4" :maxlength="2000" show-word-limit placeholder="说清楚建议/问题（至少 5 个字），后台与写手会同步收到通知" />
        </div>
      </div>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

import { Icon } from '@iconify/vue'
import { useRoute } from 'vue-router'
import http from '../api'
import { useAuthStore } from '../stores/auth'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const auth = useAuthStore()
const route = useRoute()

const items = ref([])
const counts = ref({})
const canReply = ref(false)
const loading = ref(false)
const filter = reactive({ status: '', kind: null, mine: false })
let loadSeq = 0

const statusTabs = [
  { label: '全部', value: '' },
  { label: '待处理', value: 'open' },
  { label: '处理中', value: 'processing' },
  { label: '已解决', value: 'resolved' },
  { label: '已关闭', value: 'closed' },
]
const statusOptions = [
  { label: '待处理', value: 'open' },
  { label: '处理中', value: 'processing' },
  { label: '已解决', value: 'resolved' },
  { label: '已关闭', value: 'closed' },
]

function setStatusFilter(value) {
  if (filter.status === value) return
  filter.status = value
  load()
}

async function load() {
  const seq = ++loadSeq
  loading.value = true
  try {
    const params = {}
    if (filter.status) params.status = filter.status
    if (filter.kind) params.kind = filter.kind
    if (filter.mine) params.mine = 1
    const data = await http.get('/suggestions', { params })
    if (seq !== loadSeq) return
    items.value = data.items || []
    counts.value = data.counts || {}
    canReply.value = !!data.can_reply
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function fmtTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 16)
}

// ===== 提交 =====
const createOpen = ref(false)
const creating = ref(false)
const form = reactive({ order_id: '', kind: 'suggestion', content: '' })

function openCreate() {
  form.order_id = String(route.query.order || '')
  form.kind = 'suggestion'
  form.content = ''
  createOpen.value = true
}

async function submitCreate() {
  if (form.content.trim().length < 5) return ElMessage.warning('内容至少 5 个字')
  creating.value = true
  try {
    await http.post('/suggestions', {
      order_id: form.order_id.trim() || null,
      kind: form.kind,
      content: form.content.trim(),
    })
    ElMessage.success('已提交，后台与写手会同步收到通知')
    createOpen.value = false
    await load()
  } finally {
    creating.value = false
  }
}

// ===== 回复 =====
const replyTo = ref(null)
const replying = ref(false)
const replyForm = reactive({ reply: '', status: 'resolved' })

function startReply(s) {
  replyTo.value = s.id
  replyForm.reply = s.reply || ''
  replyForm.status = s.status === 'open' ? 'processing' : (s.status === 'processing' ? 'resolved' : s.status)
}

async function submitReply(s) {
  if (!replyForm.reply.trim()) return ElMessage.warning('回复内容不能为空')
  replying.value = true
  try {
    await http.post(`/suggestions/${s.id}/reply`, {
      reply: replyForm.reply.trim(),
      status: replyForm.status,
    })
    ElMessage.success('已回复，提交人会收到通知')
    replyTo.value = null
    await load()
  } finally {
    replying.value = false
  }
}

// ===== 状态变更：已解决 / 关闭需确认 =====
const statusLoadingId = ref(null)
const pendingStatus = ref('')

async function setStatus(s, status) {
  if (status === 'resolved' || status === 'closed') {
    const isClose = status === 'closed'
    try {
      await ElMessageBox.confirm(
        isClose
          ? `确定关闭反馈 #${s.id} 吗？关闭后仍保留记录，但不再跟进。`
          : `确定将反馈 #${s.id} 标记为已解决吗？提交人会收到状态通知。`,
        isClose ? '关闭反馈' : '标记已解决',
        {
          confirmButtonText: isClose ? '关闭' : '标记已解决',
          cancelButtonText: '取消',
          type: isClose ? 'warning' : 'info',
        },
      )
    } catch {
      return
    }
  }
  statusLoadingId.value = s.id
  pendingStatus.value = status
  try {
    await http.post(`/suggestions/${s.id}/status`, null, { params: { status } })
    ElMessage.success('状态已更新')
    await load()
  } finally {
    statusLoadingId.value = null
    pendingStatus.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.sug-page { min-width: 0; }

/* 筛选 */
.sug-filters {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; flex-wrap: wrap; gap: 12px;
}
.sf-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.sf-kind { width: 120px; }

/* 可复用 pill 状态标签 */
.pill-tabs {
  display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
  padding: 4px; background: var(--card-2);
  border: 1px solid var(--border); border-radius: var(--radius-pill);
}
.pill-tab {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 14px; border: none; border-radius: var(--radius-pill);
  background: transparent; color: var(--text-2);
  font-size: 12.5px; cursor: pointer; white-space: nowrap;
  transition: background 0.16s ease, color 0.16s ease;
}
.pill-tab:hover { color: var(--text); background: var(--hover); }
.pill-tab.active { color: #fff; background: var(--brand); font-weight: 600; box-shadow: 0 6px 16px color-mix(in srgb, var(--brand) 28%, transparent); }
.pill-count {
  min-width: 17px; padding: 0 5px; border-radius: var(--radius-pill);
  font-size: 10.5px; font-weight: 600; text-align: center;
  background: color-mix(in srgb, var(--warning) 18%, transparent);
  color: var(--warning);
}
.pill-tab.active .pill-count { background: rgba(255, 255, 255, 0.22); color: #fff; }

/* 列表 */
.sug-body { min-height: 140px; }
.sug-list { display: flex; flex-direction: column; gap: 10px; }
.sug-item { padding: 15px 17px; border-left: 3px solid transparent; min-width: 0; }
.sug-item.urgent { border-left-color: var(--danger); }
.sug-item.issue { border-left-color: var(--warning); }
.sug-item.suggestion { border-left-color: var(--brand); }

.si-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.si-kind { font-size: 11.5px; font-weight: 600; padding: 1px 9px; border-radius: var(--radius-xs); }
.si-kind.suggestion { background: var(--brand-weak); color: var(--brand); }
.si-kind.issue { background: var(--warning-weak); color: var(--warning); }
.si-kind.urgent { background: var(--danger-weak); color: var(--danger); }
.si-id { font-weight: 600; font-size: 13px; color: var(--text); }
.si-order {
  color: var(--brand); text-decoration: none; font-size: 12.5px;
  display: inline-flex; align-items: center; gap: 4px;
  background: var(--brand-weak); padding: 1px 8px; border-radius: var(--radius-xs);
}
.si-order:hover { text-decoration: underline; }
.si-user { font-size: 12.5px; color: var(--text-2); }
.si-status { font-size: 12px; padding: 1px 9px; border-radius: var(--radius-xs); margin-left: auto; white-space: nowrap; }
.si-status.open { background: var(--warning-weak); color: var(--warning); }
.si-status.processing { background: var(--brand-weak); color: var(--brand); }
.si-status.resolved { background: var(--success-weak); color: var(--success); }
.si-status.closed { background: var(--hover); color: var(--text-3); }
.si-time { font-size: 12px; color: var(--text-3); }

.si-content { font-size: 13.5px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; color: var(--text); }

.si-reply {
  margin-top: 10px; padding: 10px 12px;
  background: var(--card-2); border: 1px solid var(--border); border-radius: var(--radius-sm);
}
.si-reply-head { font-size: 12.5px; color: var(--text-2); display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.si-reply-icon { color: var(--brand); }
.si-reply-head b { color: var(--brand); }
.si-reply-body { font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }

.si-actions {
  margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border);
  display: flex; gap: 8px; flex-wrap: wrap;
}
.si-actions :deep(.el-button + .el-button) { margin-left: 0; }
.si-actions .el-textarea { margin-bottom: 8px; }
.si-reply-row { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; align-items: center; }
.si-reply-btns { display: flex; gap: 8px; }

.sc-form { display: flex; flex-direction: column; gap: 14px; margin-top: 8px; }
.sc-row { display: flex; align-items: center; gap: 14px; }
.sc-row-top { align-items: flex-start; }
.sc-label { width: 64px; flex-shrink: 0; color: var(--text-2); font-size: 13px; }

@media (max-width: 768px) {
  .sug-filters { align-items: flex-start; flex-direction: column; }
  .sf-right { width: 100%; }
  .sf-kind { width: 100%; }
  .pill-tabs { width: 100%; border-radius: var(--radius); }
  .pill-tab { flex: 1 0 auto; justify-content: center; }
  .si-status { margin-left: 0; }
  .si-actions { gap: 6px; }
}
@media (max-width: 520px) {
  .sc-row { flex-direction: column; align-items: stretch; gap: 6px; }
  .sc-label { width: auto; }
  .si-reply-row { flex-direction: column; align-items: stretch; }
  .si-reply-row :deep(.el-select) { width: 100% !important; }
  .si-reply-btns { justify-content: flex-end; }
}
</style>
