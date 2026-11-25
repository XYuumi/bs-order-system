<template>
  <div class="page-shell trash-view">
    <AppPageHeader
      title="回收站"
      description="软删除的订单在此保留，可恢复或保持归档；统计与列表均不计入"
      icon="ri:delete-bin-6-line"
    >
      <template #actions>
        <el-button :loading="loading" @click="load">
          <Icon icon="ri:refresh-line" />刷新
        </el-button>
      </template>
    </AppPageHeader>

    <section class="art-card">
      <DataTableToolbar :count="total" :loading="loading" @refresh="load">
        <template #left>
          <span class="toolbar-hint">
            <Icon icon="ri:archive-line" />
            恢复后订单将重新出现在订单列表与统计中
          </span>
        </template>
      </DataTableToolbar>

      <!-- 桌面端表格 -->
      <el-table v-if="!isMobile" :data="items" v-loading="loading" row-key="id" style="width: 100%">
        <el-table-column label="单号" width="120">
          <template #default="{ row }"><span class="mono">{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column prop="title" label="题目" min-width="200" show-overflow-tooltip />
        <el-table-column label="品质" width="92">
          <template #default="{ row }">
            <QualityBadge v-if="row.quality" :name="row.quality.name" :color="row.quality.color" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="删除时间" width="150">
          <template #default="{ row }">{{ fmt(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="110">
          <template #default="{ row }">
            <span class="text-2">{{ row.created_by || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="删除前创建时间" width="150">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="96">
          <template #default="{ row }">
            <el-button
              size="small" type="primary" plain
              :loading="restoringId === row.id" :disabled="restoringId != null"
              @click="restore(row)"
            >恢复</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            compact
            icon="ri:archive-line"
            title="回收站是空的"
            description="被删除的订单会暂存在这里，可随时恢复"
          />
        </template>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-else v-loading="loading" class="trash-cards">
        <EmptyState
          v-if="!loading && !items.length"
          icon="ri:archive-line"
          title="回收站是空的"
          description="被删除的订单会暂存在这里，可随时恢复"
        />
        <div v-for="row in items" :key="row.id" class="trash-card">
          <div class="tc-head">
            <span class="mono tc-id">{{ row.id }}</span>
            <StatusTag :status="row.status" />
          </div>
          <div class="tc-title">{{ row.title }}</div>
          <div class="tc-meta">
            <div class="tc-field">
              <span class="tc-label">品质</span>
              <span class="tc-value">
                <QualityBadge v-if="row.quality" :name="row.quality.name" :color="row.quality.color" />
                <span v-else>—</span>
              </span>
            </div>
            <div class="tc-field">
              <span class="tc-label">删除时间</span>
              <span class="tc-value">{{ fmt(row.updated_at) }}</span>
            </div>
            <div class="tc-field">
              <span class="tc-label">操作人</span>
              <span class="tc-value">{{ row.created_by || '—' }}</span>
            </div>
            <div class="tc-field">
              <span class="tc-label">删除前创建</span>
              <span class="tc-value">{{ fmt(row.created_at) }}</span>
            </div>
          </div>
          <div class="tc-actions">
            <el-button
              size="small" type="primary" plain
              :loading="restoringId === row.id" :disabled="restoringId != null"
              @click="restore(row)"
            >
              <Icon icon="ri:arrow-go-back-line" />恢复订单
            </el-button>
          </div>
        </div>
      </div>

      <div class="pager-row">
        <el-pagination
          :current-page="page" :page-size="pageSize" :total="total"
          layout="total, prev, pager, next"
          @current-change="onPageChange"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../api'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import DataTableToolbar from '../components/ui/DataTableToolbar.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import QualityBadge from '../components/QualityBadge.vue'
import StatusTag from '../components/StatusTag.vue'

const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const restoringId = ref(null)
let mediaQuery = null
const isMobile = ref(typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches)

function onMediaChange(e) {
  isMobile.value = e.matches
}

function onPageChange(p) {
  page.value = p
  load()
}

function fmt(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : '-'
}

async function load() {
  loading.value = true
  try {
    const data = await http.get('/orders/trash/list', { params: { page: page.value, page_size: pageSize } })
    items.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

async function restore(row) {
  try {
    await ElMessageBox.confirm(
      `确定恢复订单「${row.title || row.id}」吗？恢复后将重新计入订单列表与统计。`,
      '恢复订单',
      { confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  restoringId.value = row.id
  try {
    await http.post(`/orders/${row.id}/restore`)
    ElMessage.success(`订单 ${row.id} 已恢复`)
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } finally {
    restoringId.value = null
  }
}

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 768px)')
  isMobile.value = mediaQuery.matches
  mediaQuery.addEventListener('change', onMediaChange)
  load()
})

onBeforeUnmount(() => mediaQuery?.removeEventListener('change', onMediaChange))
</script>

<style scoped>
.trash-view { min-width: 0; }

.toolbar-hint {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-3); line-height: 1.5;
}
.toolbar-hint .iconify { font-size: 14px; flex-shrink: 0; }

.pager-row { margin-top: 14px; display: flex; justify-content: flex-end; }

/* 移动端卡片 */
.trash-cards { display: flex; flex-direction: column; gap: 10px; min-height: 140px; }
.trash-card {
  padding: 14px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.tc-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.tc-id { font-size: 12.5px; color: var(--brand); font-weight: 600; }
.tc-title { margin-top: 8px; font-size: 14px; font-weight: 600; color: var(--text); line-height: 1.5; word-break: break-word; }
.tc-meta {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px; margin-top: 12px; padding-top: 10px;
  border-top: 1px solid var(--border);
}
.tc-field { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.tc-label { font-size: 11px; color: var(--text-3); }
.tc-value { font-size: 12.5px; color: var(--text-2); }
.tc-actions {
  display: flex; justify-content: flex-end; margin-top: 10px; padding-top: 8px;
  border-top: 1px solid var(--border);
}

@media (max-width: 768px) {
  .pager-row { justify-content: center; }
  .toolbar-hint { font-size: 11.5px; }
}
@media (max-width: 480px) {
  .tc-meta { grid-template-columns: 1fr; }
}
</style>
