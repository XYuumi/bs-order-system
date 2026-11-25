<template>
  <div class="page-shell tpl-page">
    <AppPageHeader
      title="模板库"
      description="沉淀常用需求、技术栈、备注与报价话术，一键复制复用"
      icon="ri:file-copy-2-line"
    >
      <template #actions>
        <el-button v-if="auth.isStaffView" type="primary" @click="openCreate">
          <Icon icon="ri:add-line" />新建模板
        </el-button>
      </template>
    </AppPageHeader>

    <!-- 筛选行 -->
    <div class="art-card tpl-filters">
      <el-radio-group v-model="filter.kind" @change="load">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button v-for="k in kinds" :key="k.value" :value="k.value">{{ k.label }}</el-radio-button>
      </el-radio-group>
      <div class="spacer" />
      <el-input
        v-model="filter.keyword"
        class="tpl-search"
        placeholder="搜索标题、内容或创建人"
        clearable
        @keyup.enter="load"
        @clear="load"
      >
        <template #prefix><Icon icon="ri:search-line" /></template>
      </el-input>
      <el-button @click="load"><Icon icon="ri:search-line" />搜索</el-button>
      <el-button v-if="hasFilter" link type="primary" @click="clearFilter">清空筛选</el-button>
      <span class="filter-hint">共 {{ total }} 个模板</span>
    </div>

    <!-- 模板卡片网格 -->
    <div v-loading="loading" class="tpl-body">
      <div v-if="items.length" class="tpl-grid">
        <div v-for="t in items" :key="t.id" class="art-card tpl-card" :class="`k-${t.kind}`">
          <div class="tc-head">
            <span class="tc-kind" :class="`k-${t.kind}`">
              <Icon :icon="kindIcon(t.kind)" />{{ t.kind_cn || kindLabel(t.kind) }}
            </span>
            <span class="tc-share" :class="t.is_shared ? 'on' : 'off'">
              <Icon :icon="t.is_shared ? 'ri:team-line' : 'ri:lock-2-line'" />{{ t.is_shared ? '共享' : '私有' }}
            </span>
          </div>

          <div class="tc-title" :title="t.title">{{ t.title }}</div>
          <div class="tc-content">{{ t.content }}</div>

          <div class="tc-meta">
            <span class="tc-user"><Icon icon="ri:user-3-line" />{{ t.username || '未知' }}</span>
            <span><Icon icon="ri:file-copy-2-line" />使用 {{ t.usage_count || 0 }} 次</span>
            <span class="tc-time">{{ fmtTime(t.updated_at) }}</span>
          </div>

          <div class="tc-actions">
            <el-button
              size="small" type="primary"
              :loading="usingId === t.id" :disabled="usingId != null && usingId !== t.id"
              @click="useTemplate(t)"
            >
              <Icon v-if="usingId !== t.id" icon="ri:file-copy-line" />使用
            </el-button>
            <el-button v-if="t.can_edit" size="small" @click="openEdit(t)">
              <Icon icon="ri:edit-line" />编辑
            </el-button>
            <el-button v-if="t.can_delete" size="small" type="danger" plain @click="remove(t)">
              <Icon icon="ri:delete-bin-line" />删除
            </el-button>
          </div>
        </div>
      </div>

      <EmptyState
        v-else-if="!loading"
        icon="ri:file-copy-2-line"
        :title="hasFilter ? '没有符合条件的模板' : '暂无模板'"
        :description="emptyDesc"
      />
    </div>

    <!-- 新建 / 编辑弹窗 -->
    <el-dialog v-model="dlg.visible" :title="dlg.id ? '编辑模板' : '新建模板'" width="min(600px, 92vw)">
      <el-form
        ref="formRef"
        :model="dlg.form"
        :rules="rules"
        label-position="top"
        style="margin-top: 4px"
        @submit.prevent
      >
        <el-form-item label="标题" prop="title">
          <el-input v-model="dlg.form.title" :maxlength="120" show-word-limit placeholder="例如：Java 课设需求书标准开头" />
        </el-form-item>
        <el-form-item label="类型" prop="kind">
          <el-radio-group v-model="dlg.form.kind">
            <el-radio-button v-for="k in kinds" :key="k.value" :value="k.value">{{ k.label }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input
            v-model="dlg.form.content"
            type="textarea"
            :rows="9"
            placeholder="整段粘贴常用需求描述、技术栈、备注或报价话术，使用时会一键复制"
          />
        </el-form-item>
        <el-form-item label="共享给全员">
          <el-switch v-model="dlg.form.is_shared" />
          <div class="form-extra">开启后所有同事都能看到并使用；关闭则仅自己可见</div>
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
import { computed, nextTick, onMounted, reactive, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../api'
import { useAuthStore } from '../stores/auth'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const auth = useAuthStore()

const kinds = [
  { value: 'requirement', label: '需求模板', icon: 'ri:file-text-line' },
  { value: 'tech', label: '技术栈', icon: 'ri:code-s-slash-line' },
  { value: 'remark', label: '常用备注', icon: 'ri:sticky-note-line' },
  { value: 'quote', label: '报价话术', icon: 'ri:money-cny-circle-line' },
]

const loading = ref(false)
const items = ref([])
const total = ref(0)
const usingId = ref(null)
const filter = reactive({ kind: '', keyword: '' })

const hasFilter = computed(() => !!filter.kind || !!filter.keyword.trim())
const emptyDesc = computed(() => {
  if (hasFilter.value) return '换个类型或关键词再试试'
  if (auth.isStaffView) return '点击右上角「新建模板」，把常用内容沉淀下来，下次一键复用'
  return '暂时没有可用的共享模板，写手创建后会出现在这里'
})

function kindMeta(kind) {
  return kinds.find((k) => k.value === kind)
}
function kindLabel(kind) {
  return kindMeta(kind)?.label || kind || '模板'
}
function kindIcon(kind) {
  return kindMeta(kind)?.icon || 'ri:file-text-line'
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filter.kind) params.kind = filter.kind
    const kw = filter.keyword.trim()
    if (kw) params.keyword = kw
    const data = await http.get('/templates', { params })
    items.value = data.items || []
    total.value = data.total ?? items.value.length
  } finally {
    loading.value = false
  }
}

function clearFilter() {
  filter.kind = ''
  filter.keyword = ''
  load()
}

function fmtTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 16)
}

// ===== 使用：次数 +1 并复制正文 =====
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text)
    return
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(ta)
  if (!ok) throw new Error('copy failed')
}

async function useTemplate(t) {
  if (usingId.value != null) return
  usingId.value = t.id
  try {
    const data = await http.post(`/templates/${t.id}/use`)
    if (typeof data.usage_count === 'number') t.usage_count = data.usage_count
    try {
      await copyText(data.content || t.content || '')
      ElMessage.success(`已使用「${t.title}」，内容已复制到剪贴板`)
    } catch {
      ElMessage.warning('模板已使用，但自动复制失败，请手动复制内容')
    }
  } catch {
    /* 拦截器已提示 */
  } finally {
    usingId.value = null
  }
}

// ===== 新建 / 编辑 =====
const formRef = ref(null)
const dlg = reactive({
  visible: false, id: null, saving: false,
  form: { kind: 'requirement', title: '', content: '', is_shared: true },
})

const rules = {
  title: [
    { required: true, whitespace: true, message: '请输入模板标题', trigger: 'blur' },
    { max: 120, message: '标题最多 120 个字', trigger: 'blur' },
  ],
  kind: [{ required: true, message: '请选择模板类型', trigger: 'change' }],
  content: [{ required: true, whitespace: true, message: '请输入模板内容', trigger: 'blur' }],
}

function resetForm() {
  Object.assign(dlg.form, { kind: 'requirement', title: '', content: '', is_shared: true })
}

function openCreate() {
  dlg.id = null
  dlg.saving = false
  resetForm()
  dlg.visible = true
  nextTick(() => formRef.value?.clearValidate())
}

function openEdit(t) {
  dlg.id = t.id
  dlg.saving = false
  Object.assign(dlg.form, {
    kind: t.kind || 'requirement',
    title: t.title || '',
    content: t.content || '',
    is_shared: !!t.is_shared,
  })
  dlg.visible = true
  nextTick(() => formRef.value?.clearValidate())
}

async function save() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  dlg.saving = true
  try {
    const payload = {
      kind: dlg.form.kind,
      title: dlg.form.title.trim(),
      content: dlg.form.content.trim(),
      is_shared: dlg.form.is_shared,
    }
    if (dlg.id) await http.patch(`/templates/${dlg.id}`, payload)
    else await http.post('/templates', payload)
    ElMessage.success(dlg.id ? '模板已更新' : '模板已创建')
    dlg.visible = false
    await load()
  } catch {
    /* 拦截器已提示 */
  } finally {
    dlg.saving = false
  }
}

// ===== 删除 =====
function remove(t) {
  ElMessageBox.confirm(`确定删除模板「${t.title}」吗？删除后不可恢复。`, '删除模板', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
    confirmButtonClass: 'el-button--danger',
  }).then(async () => {
    try {
      await http.delete(`/templates/${t.id}`)
      ElMessage.success('模板已删除')
      await load()
    } catch {
      /* 拦截器已提示 */
    }
  }).catch(() => {})
}

onMounted(load)
</script>

<style scoped>
.tpl-page { min-width: 0; }

/* 筛选行 */
.tpl-filters {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; flex-wrap: wrap;
}
.tpl-filters :deep(.el-radio-group) { flex-wrap: wrap; }
.spacer { flex: 1; }
.tpl-search { width: 250px; }
.filter-hint { font-size: 12.5px; color: var(--text-3); white-space: nowrap; }

/* 卡片网格 */
.tpl-body { min-height: 180px; }
.tpl-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(340px, 100%), 1fr));
  gap: 12px;
  animation: rise-in 0.46s cubic-bezier(0.4, 0, 0.2, 1) both;
}
.tpl-card {
  padding: 15px 17px;
  display: flex; flex-direction: column;
  border-left: 3px solid transparent;
}
.tpl-card.k-requirement { border-left-color: var(--brand); }
.tpl-card.k-tech { border-left-color: var(--info); }
.tpl-card.k-remark { border-left-color: var(--warning); }
.tpl-card.k-quote { border-left-color: var(--success); }
.tpl-card:hover { transform: translateY(-1px); }

.tc-head { display: flex; align-items: center; gap: 8px; }
.tc-kind {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px; font-weight: 600;
  padding: 2px 9px; border-radius: var(--radius-xs);
}
.tc-kind.k-requirement { background: var(--brand-weak); color: var(--brand); }
.tc-kind.k-tech { background: var(--info-weak); color: var(--info); }
.tc-kind.k-remark { background: var(--warning-weak); color: var(--warning); }
.tc-kind.k-quote { background: var(--success-weak); color: var(--success); }

.tc-share {
  margin-left: auto; display: inline-flex; align-items: center; gap: 4px;
  font-size: 11.5px; color: var(--text-3); white-space: nowrap;
}
.tc-share.on { color: var(--success); }

.tc-title {
  margin-top: 10px;
  font-size: 14.5px; font-weight: 600; line-height: 1.45; color: var(--text);
  word-break: break-word;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.tc-content {
  margin-top: 8px;
  font-size: 13px; line-height: 1.7; color: var(--text-2);
  white-space: pre-line; word-break: break-word;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;
}
.tc-meta {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-top: 10px; font-size: 11.5px; color: var(--text-3);
}
.tc-meta span { display: inline-flex; align-items: center; gap: 4px; }
.tc-time { margin-left: auto; }

.tc-actions {
  margin-top: auto; padding-top: 10px;
  border-top: 1px solid var(--border);
  display: flex; gap: 4px; flex-wrap: wrap;
}
.tc-actions :deep(.el-button + .el-button) { margin-left: 0; }

.form-extra { font-size: 12px; color: var(--text-3); line-height: 1.5; margin-top: 4px; }

@media (max-width: 768px) {
  .tpl-grid { grid-template-columns: 1fr; }
  .tpl-filters { align-items: stretch; flex-direction: column; gap: 10px; }
  .spacer { display: none; }
  .tpl-search { width: 100%; }
  .filter-hint { order: 6; }
}
</style>
