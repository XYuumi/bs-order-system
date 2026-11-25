<template>
  <div class="page-shell ann-page">
    <AppPageHeader
      title="公告管理"
      description="发布系统公告，全员铃铛实时可见"
      icon="ri:megaphone-line"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">
          <Icon icon="ri:add-line" />新建公告
        </el-button>
      </template>
    </AppPageHeader>

    <!-- 筛选行 -->
    <div class="art-card ann-filters">
      <el-select v-model="filter.level" style="width: 120px">
        <el-option label="全部级别" value="" />
        <el-option v-for="o in levelOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-switch v-model="filter.publishedOnly" active-text="仅看已发布" />
      <div class="spacer" />
      <span class="filter-hint">
        <Icon icon="ri:megaphone-line" class="fh-ic" />
        共 {{ filtered.length }} 条{{ filter.publishedOnly ? '' : '（含草稿）' }}
      </span>
    </div>

    <!-- 列表：响应式卡片流 -->
    <div v-loading="loading" class="ann-body">
      <div v-if="filtered.length" class="ann-list">
        <div v-for="a in filtered" :key="a.id" class="art-card ann-item" :class="`lv-${a.level}`">
          <div class="ai-head">
            <span class="ai-title">{{ a.title }}</span>
            <span class="ai-level" :class="`lv-${a.level}`">{{ levelCn(a) }}</span>
            <span class="ai-status" :class="a.is_published ? 'on' : 'off'">
              <i class="ai-dot" />{{ a.is_published ? '已发布' : '草稿' }}
            </span>
          </div>
          <div class="ai-meta">
            <span class="ai-user"><Icon icon="ri:user-voice-line" /> {{ a.username || '系统' }}</span>
            <span>{{ fmtTime(a.created_at) }}</span>
            <span v-if="a.updated_at && a.updated_at !== a.created_at">· 更新于 {{ fmtTime(a.updated_at) }}</span>
          </div>
          <div class="ai-content">{{ a.content }}</div>
          <div class="ai-actions">
            <el-button size="small" type="primary" link :disabled="togglingId === a.id" @click="openEdit(a)">
              <Icon icon="ri:edit-line" /> 编辑
            </el-button>
            <el-button
              size="small" type="primary" link
              :loading="togglingId === a.id" :disabled="togglingId != null && togglingId !== a.id"
              @click="togglePublish(a)"
            >
              <Icon v-if="!a.is_published" icon="ri:send-plane-line" /> {{ a.is_published ? '取消发布' : '发布' }}
            </el-button>
            <el-button size="small" type="danger" link :disabled="togglingId === a.id" @click="remove(a)">
              <Icon icon="ri:delete-bin-line" /> 删除
            </el-button>
          </div>
        </div>
      </div>
      <EmptyState
        v-else-if="!loading"
        icon="ri:megaphone-line"
        :title="filter.level || filter.publishedOnly ? '没有符合条件的公告' : '暂无公告'"
        :description="filter.level || filter.publishedOnly ? '试试调整筛选条件' : '点击「新建公告」发布第一条，全员铃铛实时可见'"
      >
        <el-button v-if="!filter.level && !filter.publishedOnly" type="primary" @click="openCreate">
          <Icon icon="ri:add-line" />新建公告
        </el-button>
      </EmptyState>
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dlg.visible" :title="dlg.id ? '编辑公告' : '新建公告'" width="min(560px, 92vw)">
      <el-form label-position="top" style="margin-top: 4px">
        <el-form-item label="标题" required>
          <el-input v-model="dlg.form.title" :maxlength="100" show-word-limit placeholder="一句话说明公告主题" />
        </el-form-item>
        <el-form-item label="级别" required>
          <el-radio-group v-model="dlg.form.level">
            <el-radio-button value="info">通知</el-radio-button>
            <el-radio-button value="warning">警告</el-radio-button>
            <el-radio-button value="important">重要</el-radio-button>
          </el-radio-group>
          <div class="form-extra">重要（红）> 警告（橙）> 通知（蓝），级别越高在铃铛里越醒目</div>
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input v-model="dlg.form.content" type="textarea" :rows="6" :maxlength="2000" show-word-limit placeholder="公告正文，支持换行；发布后实时推送到全员铃铛" />
        </el-form-item>
        <el-form-item label="立即发布">
          <el-switch v-model="dlg.form.is_published" />
          <div class="form-extra">开启后保存立即对全员可见；关闭则存为草稿，稍后可在列表中发布</div>
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
import { computed, onMounted, reactive, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../api'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const loading = ref(false)
const items = ref([])
const filter = reactive({ level: '', publishedOnly: false })
const togglingId = ref(null)

const levelOptions = [
  { label: '通知', value: 'info' },
  { label: '警告', value: 'warning' },
  { label: '重要', value: 'important' },
]

function levelCn(a) {
  const hit = levelOptions.find((o) => o.value === a.level)
  return hit ? hit.label : (a.level_cn || a.level)
}

const filtered = computed(() => items.value.filter((a) =>
  (!filter.level || a.level === filter.level) && (!filter.publishedOnly || a.is_published)
))

async function load() {
  loading.value = true
  try {
    const data = await http.get('/announcements', { params: { limit: 50, include_unpublished: 1 } })
    items.value = data.items || []
  } finally {
    loading.value = false
  }
}

function fmtTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 16)
}

// ===== 新建 / 编辑 =====
const dlg = reactive({
  visible: false, id: null, saving: false,
  form: { title: '', level: 'info', content: '', is_published: true },
})

function openCreate() {
  Object.assign(dlg, {
    visible: true, id: null, saving: false,
    form: { title: '', level: 'info', content: '', is_published: true },
  })
}

function openEdit(a) {
  Object.assign(dlg, {
    visible: true, id: a.id, saving: false,
    form: { title: a.title, level: a.level || 'info', content: a.content || '', is_published: !!a.is_published },
  })
}

async function save() {
  const f = dlg.form
  if (!f.title.trim()) return ElMessage.warning('请填写公告标题')
  if (!f.content.trim()) return ElMessage.warning('请填写公告内容')
  dlg.saving = true
  try {
    const payload = { title: f.title.trim(), content: f.content.trim(), level: f.level, is_published: f.is_published }
    if (dlg.id) await http.put(`/announcements/${dlg.id}`, payload)
    else await http.post('/announcements', payload)
    ElMessage.success(dlg.id ? '公告已更新' : f.is_published ? '公告已发布，全员铃铛实时可见' : '已存为草稿')
    dlg.visible = false
    await load()
  } finally {
    dlg.saving = false
  }
}

// ===== 发布切换 / 删除 =====
async function togglePublish(a) {
  const next = !a.is_published
  try {
    await ElMessageBox.confirm(
      next
        ? `确定发布公告「${a.title}」吗？发布后全员铃铛将实时收到通知。`
        : `确定取消发布公告「${a.title}」吗？取消后将转为草稿。`,
      next ? '发布公告' : '取消发布',
      {
        confirmButtonText: next ? '发布' : '取消发布',
        cancelButtonText: '取消',
        type: next ? 'info' : 'warning',
      },
    )
  } catch {
    return
  }
  togglingId.value = a.id
  try {
    await http.put(`/announcements/${a.id}`, {
      title: a.title, content: a.content, level: a.level, is_published: next,
    })
    ElMessage.success(next ? '已发布，全员铃铛实时可见' : '已转为草稿')
    await load()
  } finally {
    togglingId.value = null
  }
}

function remove(a) {
  ElMessageBox.confirm(`确定删除公告「${a.title}」吗？删除后不可恢复。`, '删除公告', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
    confirmButtonClass: 'el-button--danger',
  }).then(async () => {
    await http.delete(`/announcements/${a.id}`)
    ElMessage.success('公告已删除')
    load()
  }).catch(() => {})
}

onMounted(load)
</script>

<style scoped>
.ann-page { min-width: 0; }

/* 筛选行 */
.ann-filters {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 16px; flex-wrap: wrap;
}
.spacer { flex: 1; }
.filter-hint {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12.5px; color: var(--text-3);
}
.fh-ic { font-size: 14px; }

/* 列表卡片 */
.ann-body { min-height: 160px; }
.ann-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(360px, 100%), 1fr));
  gap: 12px;
  animation: rise-in 0.46s cubic-bezier(0.4, 0, 0.2, 1) both;
}
.ann-item { padding: 15px 17px; border-left: 3px solid transparent; min-width: 0; }
.ann-item.lv-info { border-left-color: var(--brand); }
.ann-item.lv-warning { border-left-color: var(--warning); }
.ann-item.lv-important { border-left-color: var(--danger); }

.ai-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ai-title { font-weight: 600; font-size: 14.5px; color: var(--text); word-break: break-word; }
.ai-level { font-size: 11.5px; font-weight: 600; padding: 1px 9px; border-radius: var(--radius-xs); flex-shrink: 0; }
.ai-level.lv-info { background: var(--brand-weak); color: var(--brand); }
.ai-level.lv-warning { background: var(--warning-weak); color: var(--warning); }
.ai-level.lv-important { background: var(--danger-weak); color: var(--danger); }

.ai-status {
  margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; flex-shrink: 0;
}
.ai-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.ai-status.on { color: var(--success); }
.ai-status.on .ai-dot { background: var(--success); box-shadow: 0 0 6px color-mix(in srgb, var(--success) 55%, transparent); }
.ai-status.off { color: var(--text-3); }
.ai-status.off .ai-dot { background: var(--text-3); }

.ai-meta {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 12px; color: var(--text-3); margin: 7px 0 8px;
}
.ai-user { display: inline-flex; align-items: center; gap: 5px; }

.ai-content {
  font-size: 13px; line-height: 1.7; color: var(--text-2);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden; white-space: pre-line; word-break: break-word;
}

.ai-actions {
  margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border);
  display: flex; gap: 4px; flex-wrap: wrap;
}
.ai-actions :deep(.el-button + .el-button) { margin-left: 0; }

.form-extra { font-size: 12px; color: var(--text-3); line-height: 1.5; margin-top: 4px; }

@media (max-width: 768px) {
  .ann-list { grid-template-columns: 1fr; }
  .ann-filters { align-items: flex-start; flex-direction: column; gap: 10px; }
  .ann-filters :deep(.el-select) { width: 100% !important; }
  .filter-hint { order: 3; }
  .ai-status { margin-left: 0; }
}
</style>
