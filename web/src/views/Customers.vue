<template>
  <div class="page-shell cust-page">
    <AppPageHeader
      title="客户管理"
      description="沉淀客户信息，建单时可快速引用；统计基于全部客户档案"
      icon="ri:contacts-line"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">
          <Icon icon="ri:add-line" />新增客户
        </el-button>
        <ExcelIO v-if="auth.isStaffView" kind="customers" @imported="refreshAll" />
      </template>
    </AppPageHeader>

    <!-- 统计卡：始终基于全量客户，不受搜索条件影响 -->
    <div class="stat-grid">
      <StatCard
        v-for="(st, i) in statCards" :key="st.label"
        :label="st.label" :value="st.value" :icon="st.icon" :color="st.color"
        :sub="st.sub" :suffix="st.suffix" :loading="statsLoading"
        :style="{ animationDelay: `${i * 0.04}s` }"
      />
    </div>

    <section class="art-card table-card">
      <DataTableToolbar :count="items.length" :loading="loading" @refresh="refreshAll">
        <template #left>
          <el-input
            v-model="keyword" class="cust-search" clearable
            placeholder="搜索客户名 / 联系方式 / 学校"
          >
            <template #prefix><Icon icon="ri:search-line" /></template>
          </el-input>
          <span class="toolbar-hint">
            <Icon icon="ri:contacts-line" />
            {{ keyword ? `“${keyword}” 匹配 ${items.length} 位` : `共 ${allCustomers.length} 位客户` }}
          </span>
        </template>
      </DataTableToolbar>

      <!-- 桌面端表格 -->
      <el-table v-if="!isMobile" v-loading="loading" :data="pagedItems" row-key="id">
        <el-table-column label="客户名" min-width="120">
          <template #default="{ row }"><span class="cust-name">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column label="联系方式" width="130">
          <template #default="{ row }">
            <span v-if="row.contact" class="mono">{{ row.contact }}</span>
            <span v-else class="text-3">—</span>
          </template>
        </el-table-column>
        <el-table-column label="学校" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.school || '—' }}</template>
        </el-table-column>
        <el-table-column label="来源" width="96">
          <template #default="{ row }">
            <span v-if="row.source" class="src-tag">{{ row.source }}</span>
            <span v-else class="text-3">—</span>
          </template>
        </el-table-column>
        <el-table-column label="关联订单" width="84" align="center">
          <template #default="{ row }">
            <span class="oc-badge" :class="(row.order_count ?? 0) > 0 ? 'has' : 'zero'">{{ row.order_count ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="130" show-overflow-tooltip>
          <template #default="{ row }"><span :class="{ 'text-3': !row.note }">{{ row.note || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="106">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" link @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            compact
            icon="ri:contacts-line"
            :title="keyword ? '没有匹配的客户' : '暂无客户'"
            :description="keyword ? '试试更换关键词，或清空搜索查看全部客户' : '点击右上角「新增客户」建立第一份客户档案'"
          />
        </template>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-else v-loading="loading" class="cust-cards">
        <EmptyState
          v-if="!loading && !items.length"
          icon="ri:contacts-line"
          :title="keyword ? '没有匹配的客户' : '暂无客户'"
          :description="keyword ? '试试更换关键词，或清空搜索查看全部客户' : '点击右上角「新增客户」建立第一份客户档案'"
        />
        <div v-for="row in pagedItems" :key="row.id" class="cust-card">
          <div class="cc-head">
            <span class="cc-name">{{ row.name }}</span>
            <span class="oc-badge" :class="(row.order_count ?? 0) > 0 ? 'has' : 'zero'">
              {{ row.order_count ?? 0 }} 单
            </span>
          </div>
          <div class="cc-meta">
            <div class="cc-field">
              <span class="cc-label">联系方式</span>
              <span class="cc-value" :class="{ mono: row.contact }">{{ row.contact || '—' }}</span>
            </div>
            <div class="cc-field">
              <span class="cc-label">学校</span>
              <span class="cc-value">{{ row.school || '—' }}</span>
            </div>
            <div class="cc-field">
              <span class="cc-label">来源</span>
              <span class="cc-value">{{ row.source || '—' }}</span>
            </div>
            <div class="cc-field">
              <span class="cc-label">创建时间</span>
              <span class="cc-value">{{ fmtTime(row.created_at) }}</span>
            </div>
            <div v-if="row.note" class="cc-field cc-field-full">
              <span class="cc-label">备注</span>
              <span class="cc-value">{{ row.note }}</span>
            </div>
          </div>
          <div class="cc-actions">
            <el-button size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" link @click="remove(row)">删除</el-button>
          </div>
        </div>
      </div>

      <div v-if="items.length" class="pager-row">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="items.length"
          layout="total, prev, pager, next"
          background
        />
      </div>
    </section>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dlg.visible" :title="dlg.id ? `编辑客户：${dlg.form.name}` : '新增客户'" width="480">
      <el-form label-position="top" style="margin-top: 4px">
        <el-form-item label="客户名称" required>
          <el-input v-model="dlg.form.name" :maxlength="50" show-word-limit placeholder="客户称呼 / 昵称" />
        </el-form-item>
        <el-form-item label="联系方式">
          <el-input v-model="dlg.form.contact" :maxlength="100" placeholder="微信 / 手机号 / QQ，选填" />
        </el-form-item>
        <el-form-item label="学校">
          <el-input v-model="dlg.form.school" :maxlength="100" placeholder="选填，建单时可快速引用" />
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="dlg.form.source" :maxlength="50" placeholder="如：朋友介绍 / 抖音 / 淘宝" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dlg.form.note" type="textarea" :rows="3" :maxlength="200" show-word-limit placeholder="选填，如价格敏感度 / 沟通偏好等" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="dlg.saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../api'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import StatCard from '../components/StatCard.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import DataTableToolbar from '../components/ui/DataTableToolbar.vue'
import ExcelIO from '../components/ExcelIO.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const statsLoading = ref(true)
const allCustomers = ref([]) // 全量客户，仅用于统计，不受搜索影响
const items = ref([])        // 当前搜索结果
const keyword = ref('')
const page = ref(1)
const pageSize = 10

// 搜索防抖 + 请求序号，避免旧响应覆盖新结果
let kwTimer = null
let listSeq = 0
let allSeq = 0
let mediaQuery = null
const isMobile = ref(typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches)

function onMediaChange(e) {
  isMobile.value = e.matches
}

watch(keyword, () => {
  clearTimeout(kwTimer)
  // 输入即让在途请求失效，避免旧关键词的结果短暂覆盖新搜索
  listSeq += 1
  loading.value = false
  kwTimer = setTimeout(() => {
    page.value = 1
    loadList()
  }, 280)
})

watch(() => items.value.length, () => {
  const maxPage = Math.max(1, Math.ceil(items.value.length / pageSize))
  if (page.value > maxPage) page.value = maxPage
})

// ===== 统计（全量） =====
const statCards = computed(() => {
  const list = allCustomers.value
  const total = list.length
  const now = new Date()
  const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const monthNew = list.filter((c) => String(c.created_at || '').slice(0, 7) === month).length
  const withContact = list.filter((c) => c.contact && String(c.contact).trim()).length
  const orders = list.reduce((a, c) => a + (Number(c.order_count) || 0), 0)
  const contactRate = total ? Math.round((withContact / total) * 100) : 0
  return [
    { label: '全部客户', value: total, suffix: '位', icon: 'ri:group-line', color: 'var(--brand)', sub: `其中 ${withContact} 位留有联系方式` },
    { label: '本月新增', value: monthNew, suffix: '位', icon: 'ri:user-add-line', color: 'var(--success)', sub: `${month} 月新增客户档案` },
    { label: '有联系方式', value: withContact, suffix: '位', icon: 'ri:phone-line', color: 'var(--warning)', sub: `联系方式覆盖率 ${contactRate}%` },
    { label: '关联订单', value: orders, suffix: '单', icon: 'ri:file-list-3-line', color: 'var(--info)', sub: '全部客户累计关联订单' },
  ]
})

const pagedItems = computed(() => {
  const start = (page.value - 1) * pageSize
  return items.value.slice(start, start + pageSize)
})

// ===== 数据加载 =====
async function loadAll() {
  const seq = ++allSeq
  statsLoading.value = true
  try {
    const data = await http.get('/customers')
    if (seq !== allSeq) return
    allCustomers.value = data.items || []
  } finally {
    if (seq === allSeq) statsLoading.value = false
  }
}

async function loadList() {
  const seq = ++listSeq
  loading.value = true
  try {
    const params = {}
    const kw = keyword.value.trim()
    if (kw) params.keyword = kw
    const data = await http.get('/customers', { params })
    if (seq !== listSeq) return
    items.value = data.items || []
  } finally {
    if (seq === listSeq) loading.value = false
  }
}

function refreshAll() {
  loadAll()
  loadList()
}

function fmtTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 16)
}

// ===== 新增 / 编辑 =====
const dlg = reactive({
  visible: false, id: null, saving: false,
  form: { name: '', contact: '', school: '', source: '', note: '' },
})

function openCreate() {
  Object.assign(dlg, {
    visible: true, id: null, saving: false,
    form: { name: '', contact: '', school: '', source: '', note: '' },
  })
}

function openEdit(row) {
  Object.assign(dlg, {
    visible: true, id: row.id, saving: false,
    form: {
      name: row.name || '', contact: row.contact || '', school: row.school || '',
      source: row.source || '', note: row.note || '',
    },
  })
}

async function save() {
  const f = dlg.form
  if (!f.name.trim()) return ElMessage.warning('请填写客户名称')
  dlg.saving = true
  try {
    const payload = {
      name: f.name.trim(),
      contact: f.contact.trim(),
      school: f.school.trim(),
      source: f.source.trim(),
      note: f.note.trim(),
    }
    if (dlg.id) await http.put(`/customers/${dlg.id}`, payload)
    else await http.post('/customers', payload)
    ElMessage.success(dlg.id ? '客户信息已更新' : '客户已新增')
    dlg.visible = false
    page.value = 1
    refreshAll()
  } finally {
    dlg.saving = false
  }
}

function remove(row) {
  ElMessageBox.confirm(`确定删除客户「${row.name}」吗？删除后档案不可恢复。`, '删除客户', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
    confirmButtonClass: 'el-button--danger',
  }).then(async () => {
    await http.delete(`/customers/${row.id}`)
    ElMessage.success('客户已删除')
    refreshAll()
  }).catch(() => {})
}

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 768px)')
  isMobile.value = mediaQuery.matches
  mediaQuery.addEventListener('change', onMediaChange)
  refreshAll()
})

onBeforeUnmount(() => {
  clearTimeout(kwTimer)
  mediaQuery?.removeEventListener('change', onMediaChange)
})
</script>

<style scoped>
.cust-page { min-width: 0; }

.table-card { min-width: 0; }

/* 工具栏 */
.toolbar-hint {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-3); line-height: 1.5;
}
.toolbar-hint .iconify { font-size: 14px; flex-shrink: 0; }
.cust-search { width: 260px; max-width: 100%; }

.cust-name { font-weight: 600; font-size: 13.5px; }
.src-tag {
  display: inline-block; font-size: 11.5px; padding: 1px 9px; border-radius: var(--radius-xs);
  background: var(--brand-weak); color: var(--brand); max-width: 100%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: middle;
}
.oc-badge {
  display: inline-block; min-width: 26px; text-align: center;
  font-size: 12px; font-weight: 600; border-radius: var(--radius-pill); padding: 1px 8px;
}
.oc-badge.zero { background: var(--hover); color: var(--text-3); }
.oc-badge.has { background: var(--brand-weak); color: var(--brand); }

.pager-row { margin-top: 14px; display: flex; justify-content: flex-end; }

/* ===== 移动端客户卡片 ===== */
.cust-cards { display: flex; flex-direction: column; gap: 10px; min-height: 140px; }
.cust-card {
  padding: 14px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.cc-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.cc-name { font-size: 14px; font-weight: 600; color: var(--text); word-break: break-all; }
.cc-meta {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px; margin-top: 12px; padding-top: 10px;
  border-top: 1px solid var(--border);
}
.cc-field { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.cc-field-full { grid-column: 1 / -1; }
.cc-label { font-size: 11px; color: var(--text-3); }
.cc-value { font-size: 12.5px; color: var(--text-2); word-break: break-all; }
.cc-actions {
  display: flex; justify-content: flex-end; gap: 2px; flex-wrap: wrap;
  margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border);
}
.cc-actions :deep(.el-button + .el-button) { margin-left: 0; }

@media (max-width: 768px) {
  .cust-search { width: 100%; }
  .toolbar-hint { font-size: 11.5px; }
  .pager-row { justify-content: center; }
}
@media (max-width: 480px) {
  .cc-meta { grid-template-columns: 1fr; }
}
</style>
