<template>
  <div class="page-shell logs-view">
    <AppPageHeader
      title="操作日志"
      description="追踪登录、订单、文件与系统配置等关键操作"
      icon="ri:file-list-3-line"
    />

    <FilterBar :loading="loading" @search="load(1)" @reset="resetFilters">
      <el-input v-model="query.username" placeholder="操作人" clearable class="f-user" />
      <el-select v-model="query.action" placeholder="全部动作" clearable filterable class="f-action">
        <el-option v-for="a in actions" :key="a" :label="ACTION_TEXT[a] || a" :value="a" />
      </el-select>
      <el-input v-model="query.entity_id" placeholder="单号 / 对象ID" clearable class="f-entity" />
      <el-date-picker
        v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
        start-placeholder="开始日期" end-placeholder="结束日期" class="f-date"
      />
    </FilterBar>

    <section class="art-card">
      <DataTableToolbar :count="total" :loading="loading" @refresh="load()">
        <template #left>
          <span class="toolbar-hint">
            <Icon icon="ri:shield-keyhole-line" />
            仅展示你有权查看的操作记录；非管理员详情不含真实价
          </span>
        </template>
      </DataTableToolbar>

      <el-table v-loading="loading" :data="items" row-key="id" style="width: 100%">
        <el-table-column label="时间" width="165">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="165">
          <template #default="{ row }">
            <span class="nowrap">{{ row.username }}</span>
            <!-- 角色名称优先显示管理员自定义的角色标签（role_label） -->
            <span class="text-3 role-tag">{{ row.role_label || roleText(row.role) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="动作" width="150">
          <template #default="{ row }">
            <span class="action-tag" :class="tagClass(row.action)">
              {{ ACTION_TEXT[row.action] || row.action }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="对象" width="125">
          <template #default="{ row }">
            <router-link v-if="row.entity_type === 'order'" :to="`/orders/${row.entity_id}`" class="mono link">{{ row.entity_id }}</router-link>
            <span v-else class="text-3">{{ row.entity_type || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="detail">{{ detailText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="IP" width="130">
          <template #default="{ row }">
            <span class="mono text-3 nowrap">{{ row.ip }}</span>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            compact
            icon="ri:file-search-line"
            title="没有操作记录"
            :description="hasFilters ? '试试调整筛选条件或日期范围' : '产生操作后，这里会自动记录'"
          />
        </template>
      </el-table>

      <div class="pager-row">
        <el-pagination
          :current-page="query.page" :page-size="query.page_size" :total="total"
          layout="total, prev, pager, next"
          @current-change="onPageChange"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Icon } from '@iconify/vue'
import http from '../api'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import FilterBar from '../components/ui/FilterBar.vue'
import DataTableToolbar from '../components/ui/DataTableToolbar.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const items = ref([])
const total = ref(0)
const actions = ref([])
const dateRange = ref(null)

const query = reactive({
  username: '', action: undefined, entity_id: '',
  date_from: '', date_to: '', page: 1, page_size: 20,
})

const hasFilters = computed(() =>
  !!(query.username || query.action || query.entity_id || dateRange.value?.length)
)

const ACTION_TEXT = {
  login: '登录系统', login_failed: '登录失败', change_password: '修改密码',
  order_create: '创建订单', order_update: '修改订单信息', order_status: '变更订单状态',
  order_deploy_status: '变更部署状态',
  file_upload: '上传文件', file_delete: '删除文件', file_download: '下载文件',
  requirement_generate: '生成需求书', requirement_update: '编辑需求书', requirement_download: '下载需求书',
  requirement_ai_revise: 'AI 修改需求书',
  user_create: '创建用户', user_update: '修改用户', api_key_reset: '重置 API Key', api_key_reset_self: '重置 API Key',
  api_order_create: 'API 创建订单', api_requirement_download: 'API 下载需求书', api_file_download: 'API 下载文件',
  logout_all: '退出所有设备', order_restore: '恢复订单', customer_create: '新增客户',
  customer_update: '编辑客户', customer_delete: '删除客户',
}
const STATUS_TEXT = {
  pending: '待开始', in_progress: '制作中', completed: '已完成',
  closed: '已结单', after_sale: '售后中', cancelled: '已取消',
}
const ROLE_TEXT = { admin: '管理员', staff: '写手', agent: '代理', '-': '系统' }

function roleText(role) {
  return ROLE_TEXT[role] || role || '系统'
}

function onPageChange(p) {
  query.page = p
  load()
}

function resetFilters() {
  query.username = ''
  query.action = undefined
  query.entity_id = ''
  dateRange.value = null
  load(1)
}

function tagClass(action) {
  if (action.includes('delete') || action.includes('failed')) return 'danger'
  if (action.includes('create') || action.includes('restore')) return 'success'
  if (action.startsWith('api_')) return 'warning'
  return 'brand'
}

function fmt(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '-'
}

function detailText(row) {
  const d = row.detail || {}
  if (!d || typeof d !== 'object') return row.detail ? String(row.detail) : '-'
  if (row.action === 'order_status') {
    return `${STATUS_TEXT[d.before] || d.before || '-'} → ${STATUS_TEXT[d.after] || d.after || '-'}`
  }
  if (row.action === 'order_deploy_status') return `${d.before || '-'} → ${d.after || '-'}`
  if (row.action === 'requirement_generate') {
    const src = { ai: 'AI 生成', template: '模板生成' }[d.source] || d.source || '-'
    return `来源：${src}${d.note ? '；' + d.note : ''}`
  }
  if (row.action === 'requirement_ai_revise') {
    return `修改建议：${d.instruction || '-'}`
  }
  if (d.file) return `文件：${d.file}${d.size != null ? `（${d.size}B）` : ''}`
  if (row.action === 'order_create') {
    const parts = [`题目：${d.title || '-'}`, `品质：${d.quality || '-'}`]
    // 后端已对非管理员脱敏，前端同样不做任何兜底展示
    if (auth.isAdmin && d.owner_price != null) parts.push(`真实价 ¥${d.owner_price}`)
    if (d.agent_price != null) parts.push(`代理价 ¥${d.agent_price}`)
    return parts.join('｜')
  }
  const hidden = ['owner_price', 'multiplier']
  const keys = Object.keys(d.after || {}).filter((k) => auth.isAdmin || !hidden.includes(k))
  if (keys.length) {
    return keys.map((k) => `${k}: ${JSON.stringify(d.before?.[k]) ?? '无'} → ${JSON.stringify(d.after[k])}`).join('；')
  }
  if (d.before || d.after) {
    return '已脱敏的字段变更'
  }
  return row.detail ? JSON.stringify(d) : '-'
}

async function load(page) {
  if (page) query.page = page
  query.date_from = dateRange.value?.[0] || ''
  query.date_to = dateRange.value?.[1] || ''
  loading.value = true
  try {
    const params = Object.fromEntries(Object.entries(query).filter(([, v]) => v !== '' && v != null))
    const data = await http.get('/logs', { params })
    items.value = data.items || []
    total.value = data.total || 0
    actions.value = data.actions || []
  } finally {
    loading.value = false
  }
}

onMounted(() => load(1))
</script>

<style scoped>
.logs-view { min-width: 0; }

.f-user { width: 140px; }
.f-action { width: 180px; }
.f-entity { width: 150px; }
.f-date { width: 245px; }

.toolbar-hint {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-3); line-height: 1.5;
}
.toolbar-hint .iconify { font-size: 14px; flex-shrink: 0; }

.role-tag { font-size: 11px; margin-left: 5px; white-space: nowrap; }
.detail { font-size: 12.5px; color: var(--text-2); }
.link { color: var(--brand); text-decoration: none; }
.nowrap { white-space: nowrap; }
.pager-row { margin-top: 14px; display: flex; justify-content: flex-end; }

/* 动作标签：语义 token */
.action-tag {
  display: inline-flex; align-items: center;
  padding: 1px 9px; border-radius: var(--radius-xs);
  font-size: 11.5px; font-weight: 500; white-space: nowrap;
  border: 1px solid transparent;
}
.action-tag.brand { color: var(--brand); background: var(--brand-weak); border-color: color-mix(in srgb, var(--brand) 30%, transparent); }
.action-tag.success { color: var(--success); background: var(--success-weak); border-color: color-mix(in srgb, var(--success) 30%, transparent); }
.action-tag.warning { color: var(--warning); background: var(--warning-weak); border-color: color-mix(in srgb, var(--warning) 30%, transparent); }
.action-tag.danger { color: var(--danger); background: var(--danger-weak); border-color: color-mix(in srgb, var(--danger) 30%, transparent); }

@media (max-width: 768px) {
  .pager-row { justify-content: center; }
  .toolbar-hint { font-size: 11.5px; }
}
</style>
