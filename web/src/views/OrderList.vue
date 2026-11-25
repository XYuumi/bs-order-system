<template>
  <div class="page-shell order-page">
    <AppPageHeader
      title="订单管理"
      description="全生命周期订单、交付物与状态流转"
      icon="ri:file-list-3-line"
    >
      <template #actions>
        <!-- 写手不负责建单（路由只放开给管理员与代理），这里对他们隐藏 -->
        <el-button v-if="!auth.isStaffView || auth.isAdmin" type="primary" @click="router.push('/orders/create')">
          <Icon icon="ri:add-line" />新建订单
        </el-button>
        <el-button class="bs-eye-btn" size="small" circle title="价格显示/脱敏切换" @click="togglePriceMask">
          <Icon :icon="priceMasked ? 'ri:lock-line' : 'ri:eye-line'" />
        </el-button>
        <ExcelIO
          v-if="auth.isStaffView" kind="orders" :params="exportParams"
          @imported="load(1)"
        />
      </template>
    </AppPageHeader>

    <FilterBar :loading="loading" @search="load(1)" @reset="resetFilters">
      <el-select v-model="query.status" placeholder="全部状态" clearable class="f-status" @change="load(1)">
        <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-select v-model="query.quality" placeholder="全部品质" clearable class="f-quality" @change="load(1)">
        <el-option v-for="q in qualities" :key="q.code" :label="q.name" :value="q.code" />
      </el-select>
      <el-select v-model="query.project_type" placeholder="全部项目类型" clearable class="f-ptype" @change="load(1)">
        <el-option v-for="p in ptOptions" :key="p.value" :label="p.label" :value="p.value" />
      </el-select>
      <el-select
        v-if="auth.isStaffView" v-model="query.agent_id" placeholder="全部代理"
        clearable filterable class="f-agent" @change="load(1)"
      >
        <el-option v-for="a in agents" :key="a.id" :label="a.display_name || a.username" :value="a.id" />
      </el-select>
      <el-date-picker
        v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
        start-placeholder="开始日期" end-placeholder="结束日期"
        class="f-date" @change="load(1)"
      />
      <el-input
        v-model="query.keyword" placeholder="搜索单号 / 题目" clearable
        class="f-keyword" @keyup.enter="load(1)" @clear="load(1)"
      >
        <template #prefix><Icon icon="ri:search-line" /></template>
      </el-input>
    </FilterBar>

    <section class="art-card table-card" :class="{ 'table-fullscreen': isTableFull }">
      <DataTableToolbar :count="total" :loading="loading" @refresh="load()">
        <template #left>
          <template v-if="auth.isStaffView">
            <div class="batch-actions">
              <el-dropdown trigger="click" @command="batchChangeStatus">
                <el-button :disabled="!selectedKeys.length || batchLoading" :loading="batchLoading">
                  <Icon icon="ri:arrow-left-right-line" />
                  批量改状态{{ selectedKeys.length ? `（${selectedKeys.length}）` : '' }}
                  <Icon icon="ri:arrow-down-s-line" class="dd-caret" />
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-for="s in batchStatusOptions" :key="s.value" :command="s.value"
                      :disabled="!eligibleFor(s.value)"
                    >
                      {{ s.label }}{{ eligibleFor(s.value) ? `（${countEligible(s.value)}）` : '' }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-dropdown trigger="click" @command="batchChangeDeploy">
                <el-button :disabled="!selectedKeys.length || batchLoading" :loading="batchLoading">
                  <Icon icon="ri:upload-cloud-line" />
                  批量改部署{{ selectedKeys.length ? `（${selectedKeys.length}）` : '' }}
                  <Icon icon="ri:arrow-down-s-line" class="dd-caret" />
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="undeployed">未部署</el-dropdown-item>
                    <el-dropdown-item command="deployed">已部署</el-dropdown-item>
                    <el-dropdown-item command="not_required">无需部署</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button v-if="auth.isAdmin" type="danger" :disabled="!selectedKeys.length || batchLoading" :loading="batchLoading" @click="batchDelete">
                <Icon icon="ri:delete-bin-line" />批量删除{{ selectedKeys.length ? `（${selectedKeys.length}）` : '' }}
              </el-button>
            </div>
          </template>
          <span v-else class="toolbar-hint">点击行查看详情</span>
        </template>
        <template #right>
          <el-dropdown trigger="click" @command="setTableSize">
            <button class="tool-btn" title="表格尺寸"><Icon icon="ri:line-height" /></button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="s in sizeOpts" :key="s.value" :command="s.value"
                  :class="{ 'is-size-active': tableSize === s.value }"
                >{{ s.label }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <button class="tool-btn" :title="isTableFull ? '退出全屏 (Esc)' : '全屏'" @click="toggleFull">
            <Icon :icon="isTableFull ? 'ri:fullscreen-exit-line' : 'ri:fullscreen-line'" />
          </button>
          <el-popover trigger="click" placement="bottom-end" :width="260">
            <template #reference>
              <button class="tool-btn" title="列设置"><Icon icon="ri:settings-3-line" /></button>
            </template>
            <div class="col-setting" @mouseenter="initSortable">
              <div class="cs-title">列显示（拖拽调整顺序）</div>
              <div class="cs-scroll" ref="csScrollEl">
                <div v-for="c in dragCols" :key="c.key" class="cs-item" :data-key="c.key">
                  <span class="drag-handle" :class="{ disabled: c.required }" title="拖拽排序"><Icon icon="ri:drag-move-2-line" /></span>
                  <el-checkbox
                    :model-value="!hiddenCols.includes(c.key)" :disabled="c.required"
                    @change="(v) => toggleCol(c.key, v)"
                  >{{ c.title }}</el-checkbox>
                </div>
              </div>
              <el-button link type="primary" size="small" class="cs-reset" @click="resetCols">重置列配置</el-button>
            </div>
          </el-popover>
        </template>
      </DataTableToolbar>

      <!-- 移动端卡片列表 -->
      <div class="mobile-orders">
        <div
          v-for="row in items" :key="row.id" class="mo-card" role="button" tabindex="0"
          @click="goDetail(row)" @keydown.enter="goDetail(row)"
        >
          <div class="mo-top">
            <span class="mono mo-id">{{ row.id }}</span>
            <StatusTag :status="row.status" />
          </div>
          <div class="mo-title">{{ row.title }}</div>
          <div class="mo-tags">
            <ProjectTypeTag :project-type="row.project_type" />
            <QualityBadge :name="row.quality.name" :color="row.quality.color" />
            <span class="price agent">¥{{ maskPrice(Number((auth.isAdmin || auth.isAgent) ? (row.owner_price ?? 0) : (row.agent_price || 0)).toLocaleString()) }}</span>
          </div>
          <div class="mo-foot">
            <span>期限 {{ row.deadline || '—' }}</span>
            <span :class="['src-tag', agentColorClass(row.agent)]">{{ row.agent ? (row.agent.display_name || row.agent.username) : '自接' }}</span>
          </div>
          <div class="mo-actions" @click.stop>
            <button class="ra-btn view" @click="goDetail(row)"><Icon icon="ri:eye-line" /></button>
            <button class="ra-btn edit" @click="editRow(row)"><Icon icon="ri:edit-line" /></button>
            <button v-if="auth.isAdmin" class="ra-btn del" @click="trashRow(row)"><Icon icon="ri:delete-bin-line" /></button>
          </div>
        </div>
        <EmptyState
          v-if="!items.length && !loading"
          icon="ri:file-search-line"
          title="没有找到订单"
          description="试试调整筛选条件，或创建一张新订单"
        />
        <el-pagination
          v-if="total > query.page_size"
          layout="prev, pager, next"
          :total="total"
          :page-size="query.page_size"
          :current-page="query.page"
          class="mo-pager"
          @current-change="onTableChange"
        />
      </div>

      <el-table
        class="desktop-table"
        ref="orderTable"
        v-loading="loading"
        :data="items"
        :row-key="(r) => r.id"
        :size="epSize"
        :row-style="{ cursor: 'pointer' }"
        style="width: 100%"
        @row-click="goDetail"
        @row-contextmenu="onRowContextMenu"
        @selection-change="onSelectionChange"
      >
        <template #empty>
          <EmptyState
            icon="ri:file-search-line"
            title="没有找到订单"
            description="试试调整筛选条件，或创建一张新订单"
          >
            <el-button type="primary" @click="router.push('/orders/create')">新建订单</el-button>
            <el-button @click="resetFilters">清空筛选</el-button>
          </EmptyState>
        </template>
        <el-table-column v-if="auth.isStaffView" type="selection" width="42" fixed="left" reserve-selection />
        <el-table-column
          v-for="col in columns"
          :key="col.key"
          :prop="col.dataIndex || col.key"
          :label="col.title"
          :width="col.width"
          :min-width="col.minWidth"
          :align="col.align"
          :fixed="col.fixed"
          :class-name="col.className"
          :label-class-name="col.className"
          :show-overflow-tooltip="!!col.ellipsis"
        >
          <template #default="{ row }">
            <div v-if="col.key === 'video'">
              <div v-if="row.video && row.video.has_thumb !== false" class="v-thumb" @click.stop="playVideo(row.video)">
                <img :src="`/api/files/${row.video.id}/thumb`" alt="" @error="thumbErr($event)" />
                <Icon icon="ri:play-circle-fill" class="v-play" />
              </div>
              <div
                v-else class="v-text-thumb" :class="[ptClass(row.project_type), { 'has-video': row.video }]"
                :title="row.video ? '播放演示视频' : ''"
                @click.stop="row.video && playVideo(row.video)"
              >
                <span class="vt-icon">{{ ptMeta(row.project_type).icon }}</span>
                <Icon v-if="row.video" icon="ri:play-circle-fill" class="v-play" />
              </div>
            </div>
            <span v-else-if="col.key === 'id'" class="mono order-id">{{ row.id }}</span>
            <span v-else-if="col.key === 'title'" class="order-title">{{ row.title }}</span>
            <ProjectTypeTag v-else-if="col.key === 'project_type'" :project-type="row.project_type" />
            <QualityBadge v-else-if="col.key === 'quality'" :name="row.quality.name" :color="row.quality.color" />
            <span v-else-if="col.key === 'owner_price'" class="price owner">{{ maskPrice('¥' + Number(row.owner_price || 0).toLocaleString()) }}</span>
            <span v-else-if="col.key === 'agent_price'" class="price agent">{{ maskPrice('¥' + Number(row.agent_price || 0).toLocaleString()) }}</span>
            <StatusTag v-else-if="col.key === 'status'" :status="row.status" />
            <template v-else-if="col.key === 'deploy'">
              <el-dropdown v-if="auth.isStaffView" trigger="click" @command="(cmd) => quickDeploy(row, cmd)">
                <span class="deploy-trigger" title="点击修改部署状态" @click.stop>
                  <StatusTag :status="row.deploy_status" kind="deploy" />
                  <Icon icon="ri:arrow-down-s-line" class="deploy-caret" />
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="undeployed" :disabled="row.deploy_status === 'undeployed'">未部署</el-dropdown-item>
                    <el-dropdown-item command="deployed" :disabled="row.deploy_status === 'deployed'">已部署</el-dropdown-item>
                    <el-dropdown-item command="not_required" :disabled="row.deploy_status === 'not_required'">无需部署</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <StatusTag v-else :status="row.deploy_status" kind="deploy" />
            </template>
            <template v-else-if="col.key === 'agent'">
              <span :class="['src-tag', agentColorClass(row.agent)]">{{ row.agent ? (row.agent.display_name || row.agent.username) : '自接' }}</span>
            </template>
              <span
                v-else-if="col.key === 'deadline'"
                :class="['deadline', { overdue: isOverdue(row) }]"
                :title="row.deadline || ''"
              >{{ row.deadline || '-' }}</span>
            <template v-else-if="col.key === 'created_at'"><span class="time-cell">{{ fmtTime(row.created_at) }}</span></template>
            <div v-else-if="col.key === 'op'" class="row-actions" @click.stop>
              <button class="ra-btn view" title="查看详情" @click="goDetail(row)"><Icon icon="ri:eye-line" /></button>
              <button class="ra-btn edit" title="编辑订单" @click="editRow(row)"><Icon icon="ri:pencil-line" /></button>
              <button v-if="auth.isAdmin" class="ra-btn del" title="移入回收站" @click="trashRow(row)"><Icon icon="ri:delete-bin-line" /></button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager desktop-pager">
        <span class="pager-summary">
          共 {{ total }} 条 · 本页 {{ items.length }} 单<template v-if="auth.isAdmin"> · 真实价 ¥{{ sumOwner }}</template> · 代理价 ¥{{ sumAgent }} · 选中 {{ selectedKeys.length }} 项
        </span>
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[20, 50, 100]"
          :total="total"
          @current-change="onTableChange"
          @size-change="onSizeChange"
        />
      </div>
    </section>

    <ArtContextMenu ref="ctxMenu" :items="ctxItems" @select="onCtxAction" />

    <el-dialog v-model="videoVisible" :title="playing?.name" width="880px" destroy-on-close>
      <video v-if="playing" :key="playing.id" :src="`/api/files/${playing.id}/download`" controls autoplay class="video-player" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon } from '@iconify/vue'
import Sortable from 'sortablejs'
import http from '../api'
import { sensitiveConfirm, withConfirm } from '../utils/sensitive'
import { useAuthStore } from '../stores/auth'
import QualityBadge from '../components/QualityBadge.vue'
import ProjectTypeTag from '../components/ProjectTypeTag.vue'
import StatusTag from '../components/StatusTag.vue'
import ArtContextMenu from '../components/ArtContextMenu.vue'
import { deadlineState, projectTypeMeta } from '../constants/orderMeta'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import FilterBar from '../components/ui/FilterBar.vue'
import DataTableToolbar from '../components/ui/DataTableToolbar.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import ExcelIO from '../components/ExcelIO.vue'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const items = ref([])
const total = ref(0)
const qualities = ref([])
const agents = ref([])
const dateRange = ref(null)

const statusOptions = [
  { label: '待开始', value: 'pending' }, { label: '制作中', value: 'in_progress' },
  { label: '已完成', value: 'completed' }, { label: '已结单', value: 'closed' },
  { label: '售后中', value: 'after_sale' }, { label: '已取消', value: 'cancelled' },
]

// ===== 列显隐 + 列拖拽排序（localStorage 记忆） =====
const COLS_STORE = 'order-cols-hidden'
const COLS_ORDER_STORE = 'order-cols-order'
const DEFAULT_HIDDEN = ['created_at']
const hiddenCols = ref([])
try {
  const saved = localStorage.getItem(COLS_STORE)
  hiddenCols.value = saved ? JSON.parse(saved) : [...DEFAULT_HIDDEN]
} catch { hiddenCols.value = [...DEFAULT_HIDDEN] }

function toggleCol(key, checked) {
  hiddenCols.value = checked ? hiddenCols.value.filter((k) => k !== key) : [...hiddenCols.value, key]
  try { localStorage.setItem(COLS_STORE, JSON.stringify(hiddenCols.value)) } catch { /* 忽略 */ }
}
function resetCols() {
  hiddenCols.value = []
  colOrder.value = []
  try {
    localStorage.removeItem(COLS_STORE)
    localStorage.removeItem(COLS_ORDER_STORE)
  } catch { /* 忽略 */ }
}

// 基础列定义（真实价/来源代理按角色动态加入）
function buildAllCols() {
  const cols = [
    { title: '视频', key: 'video', width: 78, required: true },
    { title: '单号', key: 'id', width: 112, fixed: 'left', className: 'nowrap-col', required: true },
    { title: '题目', key: 'title', dataIndex: 'title', ellipsis: true, minWidth: 200, required: true },
    { title: '项目类型', key: 'project_type', width: 126, className: 'hide-md' },
    { title: '品质', key: 'quality', width: 82 },
  ]
  if (auth.isAdmin) cols.push({ title: '真实价', key: 'owner_price', width: 88, align: 'right' })
  // 代理看自己的成交价，其他人看写手价
  cols.push(auth.isAgent
    ? { title: '成交价', key: 'owner_price', width: 88, align: 'right' }
    : { title: '写手价', key: 'agent_price', width: 88, align: 'right' })
  cols.push(
    { title: '状态', key: 'status', width: 90 },
    { title: '部署', key: 'deploy', width: 112, className: 'hide-sm' },
  )
  if (auth.isStaffView) cols.push({ title: '来源', key: 'agent', width: 80, ellipsis: true, className: 'hide-md' })
  cols.push(
    { title: '期限', key: 'deadline', width: 112, className: 'nowrap-col' },
    { title: '创建时间', key: 'created_at', width: 138, className: 'hide-md nowrap-col' },
  )
  cols.push({ title: '操作', key: 'op', width: 116, fixed: 'right', required: true })
  return cols
}

// 列顺序（拖拽排序后持久化）
const colOrder = ref([])
try { colOrder.value = JSON.parse(localStorage.getItem(COLS_ORDER_STORE) || '[]') } catch { colOrder.value = [] }

// 列设置面板的可拖拽数据（浅拷贝独立数组，v-model 直接改）
const dragCols = ref([])
// 同步初始顺序
function syncDragCols() {
  const all = buildAllCols().map((c) => ({ ...c }))
  if (colOrder.value.length) {
    all.sort((a, b) => {
      const ia = colOrder.value.indexOf(a.key)
      const ib = colOrder.value.indexOf(b.key)
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    })
  }
  dragCols.value = all
}
syncDragCols()

function onDragEnd() {
  colOrder.value = dragCols.value.map((c) => c.key)
  try { localStorage.setItem(COLS_ORDER_STORE, JSON.stringify(colOrder.value)) } catch { /* 忽略 */ }
}

// Sortable 实例：绑定到列设置面板（首次打开时初始化）
const csScrollEl = ref(null)
let sortable = null

function initSortable() {
  if (!csScrollEl.value) return
  // 面板 DOM 每次打开都可能重建：旧实例必须销毁再重绑，
  // 否则 Sortable 绑在已脱离文档的节点上，二次打开拖拽静默失效。
  if (sortable) {
    sortable.destroy()
    sortable = null
  }
  sortable = Sortable.create(csScrollEl.value, {
    animation: 200,
    handle: '.drag-handle:not(.disabled)',
    ghostClass: 'cs-ghost',
    onEnd() {
      // 按新 DOM 顺序重建 dragCols
      const keys = [...csScrollEl.value.children].map((el) => el.dataset.key)
      dragCols.value = keys.map((k) => dragCols.value.find((c) => c.key === k)).filter(Boolean)
      onDragEnd()
    },
  })
}

const columns = computed(() => {
  let cols = buildAllCols().filter((c) => c.required || !hiddenCols.value.includes(c.key || c.dataIndex))
  if (colOrder.value.length) {
    cols = [...cols].sort((a, b) => {
      const ia = colOrder.value.indexOf(a.key || a.dataIndex)
      const ib = colOrder.value.indexOf(b.key || b.dataIndex)
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    })
  }
  return cols
})

// ===== 表格尺寸（三档持久化：存储 small/middle/large → EP small/default/large） =====
const SIZE_STORE = 'order-table-size'
const tableSize = ref(localStorage.getItem(SIZE_STORE) || 'middle')
const sizeOpts = [
  { value: 'small', label: '紧凑' },
  { value: 'middle', label: '默认' },
  { value: 'large', label: '宽松' },
]
const epSize = computed(() => (tableSize.value === 'middle' ? 'default' : tableSize.value))
function setTableSize(v) {
  tableSize.value = v
  try { localStorage.setItem(SIZE_STORE, v) } catch { /* 忽略 */ }
}

// ===== 价格脱敏：把本页价格里的数字换成 *（截图 / 投屏时用），开关状态记在浏览器本地 =====
const PRICE_MASK_STORE = 'bs-price-mask'
const priceMasked = ref(localStorage.getItem(PRICE_MASK_STORE) === '1')

function togglePriceMask() {
  priceMasked.value = !priceMasked.value
  try { localStorage.setItem(PRICE_MASK_STORE, priceMasked.value ? '1' : '0') } catch { /* 忽略 */ }
}

function maskPrice(value) {
  return priceMasked.value ? String(value).replace(/\d/g, '*') : String(value)
}

/** 代理标签的配色：按用户名哈希取 0–7 号色；没有代理（自接）用 self */
function agentColorClass(agent) {
  if (!agent || !agent.username) return 'self'
  let hash = 0
  for (let i = 0; i < agent.username.length; i++) hash = (hash * 31 + agent.username.charCodeAt(i)) >>> 0
  return 'agc' + (hash % 8)
}

// ===== 本页合计（分页行内联摘要用：真实价 / 代理价 / 选中数） =====
const sumOwner = computed(() => maskPrice(items.value.reduce((a, r) => a + Number(r.owner_price || 0), 0).toFixed(2).replace(/\.00$/, '')))
const sumAgent = computed(() => maskPrice(items.value.reduce((a, r) => a + Number(r.agent_price || 0), 0).toFixed(2).replace(/\.00$/, '')))

// ===== 行右键菜单 =====
const ctxMenu = ref(null)
const ctxRow = ref(null)

const ctxItems = computed(() => {
  const list = [
    { key: 'view', label: '查看详情', icon: 'ri:eye-line' },
    { key: 'edit', label: '编辑订单', icon: 'ri:pencil-line' },
    { key: 'copy', label: '复制单号', icon: 'ri:file-copy-line' },
  ]
  if (auth.isAdmin) list.push({ key: 'trash', label: '移入回收站', icon: 'ri:delete-bin-line', danger: true })
  return list
})

function onRowContextMenu(row, _column, event) {
  // EP 自定义事件第三个参数才是原生 MouseEvent，preventDefault 需手动调
  event.preventDefault()
  ctxRow.value = row
  ctxMenu.value?.show(event)
}

async function onCtxAction(key) {
  const row = ctxRow.value
  if (!row) return
  if (key === 'view') goDetail(row)
  else if (key === 'edit') editRow(row)
  else if (key === 'trash') trashRow(row)
  else if (key === 'copy') {
    try {
      await navigator.clipboard.writeText(row.id)
      ElMessage.success('单号已复制')
    } catch {
      ElMessage.warning('复制失败，请手动复制')
    }
  }
}

const ptOptions = [
  { label: '⌨️ 纯程序设计', value: 'program' },
  { label: '📑 纯论文', value: 'thesis' },
  { label: '📘 论文+设计', value: 'thesis_program' },
]

const query = reactive({
  status: undefined, quality: undefined, project_type: undefined,
  agent_id: undefined, keyword: '',
  date_from: '', date_to: '', page: 1, page_size: 20,
})

function onTableChange(page) {
  query.page = page
  load()
}
function onSizeChange() {
  query.page = 1
  load()
}

function resetFilters() {
  query.status = undefined
  query.quality = undefined
  query.project_type = undefined
  query.agent_id = undefined
  query.keyword = ''
  dateRange.value = null
  load(1)
}

function isOverdue(row) {
  if (!row.deadline || ['completed', 'closed', 'cancelled'].includes(row.status)) return false
  // 用本地时区判断（deadlineState 会把今天 0 点归一化），
  // 不能取 toISOString() 的 UTC 日期：东八区 00:00-08:00 会把当天到期的单误判为逾期。
  return deadlineState(row.deadline).key === 'overdue'
}

function fmtTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : '-'
}

let loadSeq = 0
async function load(page) {
  if (page) query.page = page
  query.date_from = dateRange.value?.[0] || ''
  query.date_to = dateRange.value?.[1] || ''
  const seq = ++loadSeq
  loading.value = true
  try {
    const params = Object.fromEntries(Object.entries(query).filter(([, v]) => v !== '' && v != null))
    const data = await http.get('/orders', { params })
    if (seq !== loadSeq) return
    items.value = data.items
    total.value = data.total
  } catch {
    // 失败时清空列表与总数：不能让旧 total 配空列表，把接口失败伪装成“筛选无结果”
    if (seq === loadSeq) {
      items.value = []
      total.value = 0
    }
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

// 导出 Excel 与当前筛选一致
const exportParams = computed(() => ({
  status: query.status || '',
  quality: query.quality || '',
  project_type: query.project_type || '',
  agent_id: auth.isStaffView ? (query.agent_id || '') : '',
  keyword: query.keyword || '',
  date_from: dateRange.value?.[0] || '',
  date_to: dateRange.value?.[1] || '',
}))

// 写手靠点行来勾选批量操作：点的是单号列 / 勾选框那一格时切换选中，而不是进入详情
function goDetail(row, column) {
  if (auth.isStaffView && column && (column.property === 'id' || column.type === 'selection') && orderTable.value) {
    orderTable.value.toggleRowSelection(row)
    return
  }
  router.push(`/orders/${row.id}`)
}

// ===== 工具栏：全屏 / 刷新 / 行操作 =====
const isTableFull = ref(false)

function toggleFull() {
  isTableFull.value = !isTableFull.value
  document.body.style.overflow = isTableFull.value ? 'hidden' : ''
}
function onEsc(e) {
  if (e.key === 'Escape' && isTableFull.value) toggleFull()
}
onMounted(() => window.addEventListener('keydown', onEsc))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onEsc)
  if (isTableFull.value) document.body.style.overflow = ''
  // Sortable 会持有整棵面板 DOM，不销毁会阻止其释放
  if (sortable) {
    sortable.destroy()
    sortable = null
  }
})

function editRow(row) {
  router.push({ path: `/orders/${row.id}`, query: { edit: '1' } })
}

async function trashRow(row) {
  try {
    await ElMessageBox.confirm(
      `确定将订单 ${row.id}（${row.title.slice(0, 20)}…）移入回收站吗？`,
      '移入回收站',
      { confirmButtonText: '移入', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' },
    )
  } catch { return }
  const pwd = await sensitiveConfirm({ title: '删除订单确认', content: '移入回收站需要密码二次确认' })
  if (pwd == null) return
  await http.delete(`/orders/${row.id}`, withConfirm(pwd))
  ElMessage.success('已移入回收站')
  load()
}

// ===== 多选 + 批量操作（跨页保留已选行，批量动作使用完整选择集） =====
const selectedKeys = ref([])
const selectionMap = reactive(new Map())
const batchLoading = ref(false)
// 与后端 can_change_status 保持一致：已取消为终态；管理员可设其余任意非当前状态；写手只能推进，不能取消/结单/售后。
const ADMIN_BATCH_TARGETS = ['in_progress', 'completed', 'closed', 'after_sale', 'pending', 'cancelled']
const STAFF_TRANSITIONS = {
  pending: ['in_progress', 'completed'],
  in_progress: ['completed'],
}
const STATUS_LABEL = {
  pending: '待开始', in_progress: '制作中', completed: '已完成',
  closed: '已结单', after_sale: '售后中', cancelled: '已取消',
}
const DEPLOY_LABEL = { undeployed: '未部署', deployed: '已部署', not_required: '无需部署' }

const batchStatusOptions = computed(() => {
  const values = auth.isAdmin
    ? ADMIN_BATCH_TARGETS
    : [...new Set(Object.values(STAFF_TRANSITIONS).flat())]
  return values.map((value) => ({ value, label: STATUS_LABEL[value] }))
})

const selectedRows = computed(() => Array.from(selectionMap.values()))

function canBatchTo(from, to) {
  if (from === 'cancelled' || from === to) return false
  if (auth.isAdmin) return ADMIN_BATCH_TARGETS.includes(to)
  return (STAFF_TRANSITIONS[from] || []).includes(to)
}
function eligibleFor(status) {
  return selectedRows.value.some((r) => canBatchTo(r.status, status))
}
function countEligible(status) {
  return selectedRows.value.filter((r) => canBatchTo(r.status, status)).length
}

const orderTable = ref(null)
function onSelectionChange(rows) {
  const pageIds = new Set(items.value.map((r) => r.id))
  for (const id of pageIds) selectionMap.delete(id)
  for (const row of rows) selectionMap.set(row.id, row)
  selectedKeys.value = Array.from(selectionMap.keys())
}
function clearSelection() {
  orderTable.value?.clearSelection()
  selectionMap.clear()
  selectedKeys.value = []
}

async function batchChangeStatus(status) {
  const eligible = selectedRows.value.filter((r) => canBatchTo(r.status, status))
  if (!eligible.length) return
  const skip = selectedKeys.value.length > eligible.length ? `，其余 ${selectedKeys.value.length - eligible.length} 个状态不适用会自动跳过` : ''
  try {
    await ElMessageBox.confirm(
      `将把 ${eligible.length} 个订单改为「${STATUS_LABEL[status]}」${skip}。确定继续吗？`,
      `批量改为「${STATUS_LABEL[status]}」`,
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  batchLoading.value = true
  try {
    const data = await http.post('/orders/batch-status', { ids: eligible.map((r) => r.id), status })
    const failed = (data.results || []).filter((r) => !r.ok)
    if (data.changed) ElMessage.success(`已更新 ${data.changed} 个订单`)
    if (failed.length) ElMessage.warning(`${failed.length} 个未生效：${failed[0].id} ${failed[0].reason}`)
    clearSelection()
    await load()
  } finally {
    batchLoading.value = false
  }
}

async function batchChangeDeploy(deployStatus) {
  if (!selectedKeys.value.length) return
  try {
    await ElMessageBox.confirm(
      `将把选中的 ${selectedKeys.value.length} 个订单部署状态统一修改。确定继续吗？`,
      `批量改部署为「${DEPLOY_LABEL[deployStatus]}」`,
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  batchLoading.value = true
  let ok = 0
  let fail = 0
  try {
    for (const id of selectedKeys.value) {
      try {
        await http.post(`/orders/${id}/deploy-status`, { deploy_status: deployStatus })
        ok++
      } catch { fail++ }
    }
    if (ok) ElMessage.success(`已更新 ${ok} 个订单的部署状态`)
    if (fail) ElMessage.warning(`${fail} 个失败`)
    clearSelection()
    await load()
  } finally {
    batchLoading.value = false
  }
}

async function batchDelete() {
  if (!selectedKeys.value.length) return
  try {
    await ElMessageBox.confirm(
      `确定将选中的 ${selectedKeys.value.length} 个订单移入回收站吗？可在回收站恢复。`,
      '批量删除（移入回收站）',
      { confirmButtonText: '批量删除', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' },
    )
  } catch { return }
  const pwd = await sensitiveConfirm({ title: '批量删除确认', content: `将删除 ${selectedKeys.value.length} 个订单，需要密码二次确认` })
  if (pwd == null) return
  batchLoading.value = true
  let ok = 0
  let fail = 0
  try {
    for (const id of selectedKeys.value) {
      try {
        await http.delete(`/orders/${id}`, withConfirm(pwd))
        ok++
      } catch { fail++ }
    }
    if (ok) ElMessage.success(`已移入回收站 ${ok} 个订单`)
    if (fail) ElMessage.warning(`${fail} 个失败`)
    clearSelection()
    await load()
  } finally {
    batchLoading.value = false
  }
}

async function quickDeploy(row, deployStatus) {
  if (row.deploy_status === deployStatus) return
  try {
    await http.post(`/orders/${row.id}/deploy-status`, { deploy_status: deployStatus })
    ElMessage.success(`${row.id} 部署状态已更新`)
    row.deploy_status = deployStatus
  } catch { /* 拦截器处理 */ }
}

// ===== 视频缩略图/播放 =====
const videoVisible = ref(false)
const playing = ref(null)

function playVideo(video) {
  playing.value = video
  videoVisible.value = true
}

function thumbErr(e) {
  e.target.style.display = 'none'
}

function ptMeta(pt) {
  return projectTypeMeta(pt)
}
function ptClass(pt) {
  return { program: 'pt-program', thesis: 'pt-thesis', thesis_program: 'pt-thesis-program' }[pt] || 'pt-none'
}

onMounted(() => {
  load(1)
  // 元数据加载互不阻断：品质失败不应连带代理筛选也无法加载
  http.get('/qualities', { params: { enabled_only: true } })
    .then((q) => { qualities.value = q.qualities })
    .catch(() => { qualities.value = [] })
  if (auth.isStaffView) {
    http.get('/users')
      .then((u) => { agents.value = u.items.filter((x) => x.role === 'agent') })
      .catch(() => { agents.value = [] })
  }
})
</script>

<style scoped>
.order-page { gap: 16px; }
.f-status { width: 128px; }
.f-quality { width: 120px; }
.f-ptype { width: 146px; }
.f-agent { width: 142px; }
.f-date { width: 246px; }
.f-keyword { width: 220px; }

.table-card { padding: 16px 18px 14px; overflow: hidden; }
.toolbar-hint { font-size: 12px; color: var(--text-3); }
.batch-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mobile-orders { display: none; }
.dd-caret { margin-left: 4px; font-size: 10px; }
.tool-btn {
  width: 32px; height: 32px; border: 1px solid var(--border); cursor: pointer;
  border-radius: var(--radius-xs); background: var(--card-2); color: var(--text-2); font-size: 14px;
  display: inline-flex; align-items: center; justify-content: center;
  transition: background .15s, color .15s, border-color .15s;
}
.tool-btn:hover { background: var(--brand-weak); border-color: var(--brand); color: var(--brand); }
.is-size-active { color: var(--brand); font-weight: 600; }

/* 列设置 */
.col-setting { width: 220px; }
.cs-title { font-size: 12px; font-weight: 600; margin-bottom: 8px; color: var(--text-2); }
.cs-scroll { max-height: 300px; overflow-y: auto; }
.cs-item { display: flex; align-items: center; gap: 6px; padding: 5px 4px; border-radius: var(--radius-xs); }
.drag-handle { color: var(--text-3); cursor: grab; font-size: 12px; display: inline-flex; }
.drag-handle.disabled { cursor: default; opacity: 0.3; }
.cs-item:hover { background: var(--hover); }
.cs-ghost { opacity: 0.4; background: var(--brand-weak) !important; border-radius: var(--radius-xs); }
.cs-reset { padding: 0; margin-top: 6px; height: auto; }

/* 分页 */
.pager { margin-top: 14px; display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.pager-summary { font-size: 11.5px; color: var(--text-3); }

/* 行内操作 */
.row-actions { display: flex; align-items: center; gap: 6px; }
.ra-btn {
  width: 28px; height: 28px; border: none; cursor: pointer; border-radius: var(--radius-xs); font-size: 13px;
  display: inline-flex; align-items: center; justify-content: center;
  transition: transform .12s, filter .15s;
}
.ra-btn:active { transform: scale(0.92); }
.ra-btn.view { background: var(--brand-weak); color: var(--brand); }
.ra-btn.edit { background: var(--success-weak); color: var(--success); }
.ra-btn.del { background: var(--danger-weak); color: var(--danger); }
.ra-btn:hover { filter: brightness(1.2); }

/* 表格全屏 */
.table-fullscreen {
  position: fixed; inset: 0; z-index: 2000;
  border-radius: 0; margin: 0; padding: 16px;
  background: var(--bg); overflow: auto;
}
.video-player { width: 100%; max-height: 70vh; background: #000; border-radius: var(--radius); }

/* 视频缩略图 / 文字占位 */
.v-thumb {
  position: relative; width: 64px; height: 38px; border-radius: 6px; overflow: hidden;
  cursor: pointer; background: #000; transition: transform .15s, box-shadow .15s;
}
.v-thumb:hover { transform: scale(1.06); box-shadow: 0 4px 14px rgba(0, 0, 0, .35); }
.v-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.v-play { position: absolute; inset: 0; margin: auto; width: 18px; height: 18px; color: rgba(255,255,255,.94); filter: drop-shadow(0 1px 3px rgba(0,0,0,.6)); }
.v-text-thumb {
  position: relative;
  width: 64px; height: 38px; border-radius: 6px; display: flex; align-items: center; justify-content: center;
  font-size: 16px; user-select: none; cursor: default; border: 1px solid transparent;
}
.v-text-thumb.has-video { cursor: pointer; }
.v-text-thumb.has-video:hover { filter: brightness(1.15); }
.v-text-thumb.pt-program { background: rgba(93,135,255,.11); border-color: rgba(93,135,255,.24); }
.v-text-thumb.pt-thesis { background: rgba(19,222,185,.1); border-color: rgba(19,222,185,.22); }
.v-text-thumb.pt-thesis-program { background: rgba(180,141,243,.11); border-color: rgba(180,141,243,.24); }
.vt-icon { opacity: .82; }

.deploy-trigger { display: inline-flex; align-items: center; gap: 3px; cursor: pointer; padding: 2px 4px; border-radius: 6px; }
.deploy-trigger:hover { background: var(--hover); }
.deploy-caret { font-size: 9px; color: var(--text-3); }
.order-id { color: var(--text-2); font-weight: 600; font-size: 11.5px; }
.order-title { color: var(--text); }
.agent-cell { color: var(--text-2); font-size: 12px; }
.time-cell { color: var(--text-3); font-size: 11.5px; }
.deadline { font-variant-numeric: tabular-nums; }
.deadline.overdue { color: var(--danger); font-weight: 600; }
.price { font-weight: 600; font-variant-numeric: tabular-nums; }
.price.owner { color: var(--text); }
.price.agent { color: var(--info); }

:deep(.nowrap-col .cell) { white-space: nowrap; }
:deep(.nowrap-col.el-table__cell) { white-space: nowrap; }
@media (max-width: 1300px) { :deep(.hide-md) { display: none !important; } }
@media (max-width: 900px) { :deep(.hide-sm) { display: none !important; } }
@media (max-width: 620px) { :deep(.hide-xs) { display: none !important; } }
@media (max-width: 900px) {
  .f-status, .f-quality, .f-ptype, .f-agent, .f-date, .f-keyword { width: 100% !important; }
  .table-card { padding: 12px; }
  .pager { flex-direction: column; align-items: flex-start; }
  .pager-summary { line-height: 1.7; }
}
@media (max-width: 620px) {
  .desktop-table, .desktop-pager { display: none !important; }
  .mobile-orders { display: flex; flex-direction: column; gap: 10px; }
  .batch-actions { display: none; }
  .mo-card {
    position: relative; width: 100%; text-align: left; cursor: pointer;
    padding: 13px 14px 11px; border-radius: var(--radius);
    border: 1px solid var(--border); background: var(--card-2); color: inherit;
    display: flex; flex-direction: column; gap: 7px;
  }
  .mo-card:active { transform: scale(0.995); }
  .mo-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .mo-id { font-size: 11.5px; color: var(--text-2); font-weight: 600; }
  .mo-title { font-size: 13.5px; font-weight: 550; line-height: 1.45; padding-right: 12px; }
  .mo-tags { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .mo-tags .price { margin-left: auto; font-size: 13px; }
  .mo-foot { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; color: var(--text-3); border-top: 1px solid var(--border); padding-top: 7px; }
  .mo-actions { display: flex; gap: 5px; justify-content: flex-end; margin-top: -2px; }
  .mo-pager { justify-content: center; margin-top: 4px; }
}
</style>
