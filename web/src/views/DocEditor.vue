<template>
  <div class="page-shell doc-editor">
    <!-- 首屏骨架 -->
    <template v-if="loading">
      <div class="page-card editor-head sk-head" aria-busy="true">
        <div class="sk-left">
          <div class="skeleton sk-btn" />
          <div class="skeleton sk-title" />
        </div>
        <div class="sk-right">
          <div class="skeleton sk-btn" />
          <div class="skeleton sk-btn wide" />
        </div>
      </div>
      <div class="editor-body">
        <div class="page-card chapter-nav sk-nav">
          <div v-for="i in 6" :key="i" class="skeleton sk-nav-line" />
        </div>
        <div class="chapter-area">
          <div v-for="i in 3" :key="i" class="page-card skeleton sk-chapter" />
        </div>
      </div>
    </template>

    <!-- 编辑器 -->
    <template v-else-if="doc">
      <div class="page-card editor-head">
        <div class="eh-left">
          <el-button text @click="router.push(`/orders/${orderId}`)">
            <Icon icon="ri:arrow-left-line" /> 返回订单
          </el-button>
          <div class="doc-title">{{ doc.title }}</div>
          <span v-if="isDirty" class="dirty-tag">未保存</span>
        </div>
        <div class="eh-actions">
          <el-button @click="download"><Icon icon="ri:download-2-line" /> 下载 Word</el-button>
          <el-button v-if="!isRaw" plain type="primary" :loading="aiRevising" :disabled="saving" @click="aiDialogVisible = true">
            <Icon icon="ri:magic-line" /> AI 修改
          </el-button>
          <el-button type="primary" :loading="saving" :disabled="aiRevising" @click="save">
            <Icon icon="ri:check-line" /> 保存修改
          </el-button>
        </div>
      </div>

      <!-- 原文直用：仅提供纯文本修正，不做结构化改写 -->
      <div v-if="isRaw" class="editor-body editor-body-raw">
        <div class="page-card raw-card">
          <div class="raw-head">
            <h3>需求书原文</h3>
            <el-tag size="small" type="success">原文直用 · 未做修改</el-tag>
          </div>
          <p class="hint">该需求书由上传文档直接采用。这里只做纯文本层面的修正（如错字），保存与导出均保持原文，不会被系统重组。</p>
          <el-input v-model="doc.title" maxlength="100" style="margin-bottom: 12px" placeholder="文档标题" />
          <el-input
            v-model="doc.raw_text"
            type="textarea"
            :rows="24"
            class="raw-textarea"
            spellcheck="false"
          />
        </div>
      </div>

      <div v-else class="editor-body">
        <div class="page-card chapter-nav">
          <div
            v-for="(c, i) in chapterList" :key="c.key"
            class="chapter-link" :class="{ active: activeKey === c.key }"
            @click="jump(c.key)"
          >{{ i + 1 }}. {{ c.title }}</div>
        </div>

        <div class="chapter-area">
          <section :id="ch.goal.heading" data-key="goal" class="page-card chapter-card">
            <h3>{{ ch.goal.heading }}</h3>
            <p class="hint">3~4 段项目目标文字，每段导出为独立段落。</p>
            <ItemsEditor v-model="ch.goal.paragraphs" type="textarea" add-text="添加段落" />
          </section>

          <section :id="ch.scope.heading" data-key="scope" class="page-card chapter-card">
            <h3>{{ ch.scope.heading }}</h3>
            <ItemsEditor v-model="ch.scope.items" add-text="添加范围条目" />
          </section>

          <section :id="ch.roles.heading" data-key="roles" class="page-card chapter-card">
            <h3>{{ ch.roles.heading }}</h3>
            <div v-for="(role, ri) in ch.roles.roles" :key="ri" class="block-card">
              <div class="block-head">
                <el-input v-model="role.name" class="name-input" placeholder="角色名（如：普通用户）" />
                <span class="block-no text-3">3.{{ ri + 1 }}</span>
                <el-button text type="danger" @click="ch.roles.roles.splice(ri, 1)">
                  <Icon icon="ri:delete-bin-line" />
                </el-button>
              </div>
              <ItemsEditor v-model="role.points" add-text="添加职责要点" />
            </div>
            <el-button plain class="block-btn" @click="ch.roles.roles.push({ name: '', points: [''] })">
              <Icon icon="ri:add-line" /> 添加角色
            </el-button>
          </section>

          <section :id="ch.scenarios.heading" data-key="scenarios" class="page-card chapter-card">
            <h3>{{ ch.scenarios.heading }}</h3>
            <p class="hint">导出时自动编号 1~N，建议 10 条端到端场景。</p>
            <ItemsEditor v-model="ch.scenarios.items" type="textarea" add-text="添加场景" />
          </section>

          <section :id="ch.functions.heading" data-key="functions" class="page-card chapter-card">
            <h3>{{ ch.functions.heading }}</h3>
            <div v-for="(g, gi) in ch.functions.groups" :key="gi" class="block-card">
              <div class="block-head">
                <el-input v-model="g.name" class="name-input" placeholder="分组名（如：前台用户端功能）" />
                <span class="block-no text-3">5.{{ gi + 1 }}</span>
                <el-button text type="danger" @click="ch.functions.groups.splice(gi, 1)">
                  <Icon icon="ri:delete-bin-line" />
                </el-button>
              </div>
              <div v-for="(m, mi) in g.modules" :key="mi" class="module-card">
                <div class="block-head">
                  <el-input v-model="m.name" class="name-input" placeholder="模块名（如：账户管理）" />
                  <span class="block-no text-3">5.{{ gi + 1 }}.{{ mi + 1 }}</span>
                  <el-button text type="danger" @click="g.modules.splice(mi, 1)">
                    <Icon icon="ri:delete-bin-line" />
                  </el-button>
                </div>
                <ItemsEditor v-model="m.points" add-text="添加功能点（支持/查看/提供 开头）" />
                <el-input v-model="m.note" placeholder="可选：范围划界说明（导出为灰色'说明：xxx'）" style="margin-top: 8px" />
              </div>
              <el-button size="small" plain @click="g.modules.push({ name: '', points: [''], note: '' })">
                <Icon icon="ri:add-line" /> 添加功能模块
              </el-button>
            </div>
            <el-button plain class="block-btn" @click="ch.functions.groups.push({ name: '', modules: [{ name: '', points: [''], note: '' }] })">
              <Icon icon="ri:add-line" /> 添加分组
            </el-button>
          </section>

          <section :id="ch.rules.heading" data-key="rules" class="page-card chapter-card">
            <h3>{{ ch.rules.heading }}</h3>
            <ItemsEditor v-model="ch.rules.items" type="textarea" add-text="添加业务规则" />
          </section>

          <section :id="ch.data_scope.heading" data-key="data_scope" class="page-card chapter-card">
            <h3>{{ ch.data_scope.heading }}</h3>
            <p class="hint">每行一个数据实体，格式：实体名：字段1、字段2…</p>
            <ItemsEditor v-model="ch.data_scope.items" add-text="添加数据实体" />
          </section>

          <section :id="ch.tech.heading" data-key="tech" class="page-card chapter-card">
            <h3>{{ ch.tech.heading }}</h3>
            <el-input v-model="ch.tech.intro" type="textarea" :rows="2" placeholder="技术架构总述" style="margin-bottom: 12px" />
            <div class="sub-title">8.1 技术选型（三列表格）</div>
            <TableEditor v-model="ch.tech.stack_table" :headers="['层级', '技术选型', '版本说明']" add-text="添加技术项" />
            <div class="sub-title">8.2 项目结构</div>
            <div v-for="(s, si) in ch.tech.structure" :key="si" class="struct-row">
              <el-input v-model="s.dir" placeholder="目录（如 backend/）" style="width: 220px" />
              <el-input v-model="s.desc" class="desc-input" placeholder="该目录职责说明" />
              <el-button text type="danger" @click="ch.tech.structure.splice(si, 1)">
                <Icon icon="ri:delete-bin-line" />
              </el-button>
            </div>
            <el-button size="small" plain style="margin-top: 8px" @click="ch.tech.structure.push({ dir: '', desc: '' })">
              <Icon icon="ri:add-line" /> 添加目录
            </el-button>
          </section>

          <section :id="ch.database.heading" data-key="database" class="page-card chapter-card">
            <h3>{{ ch.database.heading }}</h3>
            <el-input v-model="ch.database.intro" type="textarea" :rows="2" placeholder="数据库总体约定" style="margin-bottom: 12px" />
            <div v-for="(t, ti) in ch.database.tables" :key="ti" class="block-card">
              <div class="block-head">
                <el-input v-model="t.name" class="name-input" placeholder="表名（如：用户表（sys_user））" />
                <span class="block-no text-3">9.{{ ti + 1 }}</span>
                <el-button text type="danger" @click="ch.database.tables.splice(ti, 1)">
                  <Icon icon="ri:delete-bin-line" />
                </el-button>
              </div>
              <TableEditor v-model="t.columns" :headers="['字段名', '类型', '说明']" add-text="添加字段" />
            </div>
            <el-button plain class="block-btn" @click="ch.database.tables.push({ name: '', columns: [['', '', '']] })">
              <Icon icon="ri:add-line" /> 添加数据表
            </el-button>
          </section>
        </div>
      </div>
    </template>

    <EmptyState
      v-else
      icon="ri:file-text-line"
      title="需求书未加载"
      description="请返回订单详情页生成需求书后重试"
    >
      <el-button @click="router.push(`/orders/${orderId}`)">返回订单</el-button>
    </EmptyState>

    <!-- AI 修改：提出修改建议，由 AI 在当前内容上做最小化修订，改完仍需人工检查保存 -->
    <el-dialog
      v-model="aiDialogVisible"
      title="AI 修改需求书"
      width="560px"
      :close-on-click-modal="!aiRevising"
      :close-on-press-escape="!aiRevising"
      @closed="aiInstruction = ''"
    >
      <div class="ar-body">
        <p class="ar-hint">
          <Icon icon="ri:information-line" />
          描述你想要的修改，AI 会按建议修订当前文档（含未保存的修改）；完成后请逐章检查，再点「保存修改」生效。
        </p>
        <el-input
          v-model="aiInstruction"
          type="textarea"
          :rows="4"
          :maxlength="1000"
          show-word-limit
          placeholder="例如：把普通用户改为会员用户，并在前台新增一个积分商城模块，配套数据库表"
          :disabled="aiRevising"
          @keydown.ctrl.enter="applyAiRevise"
        />
        <div class="ar-quick">
          <span class="ar-quick-label">试试：</span>
          <el-tag
            v-for="s in QUICK_SUGGESTIONS"
            :key="s"
            class="ar-chip"
            effect="plain"
            :disable-transitions="true"
            @click="!aiRevising && (aiInstruction = s)"
          >{{ s }}</el-tag>
        </div>
      </div>
      <template #footer>
        <el-button :disabled="aiRevising" @click="aiDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="aiRevising" @click="applyAiRevise">
          {{ aiRevising ? 'AI 修改中…' : '让 AI 修改' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import { Icon } from '@iconify/vue'
import http from '../api'
import { useAuthStore } from '../stores/auth'
import EmptyState from '../components/ui/EmptyState.vue'
import ItemsEditor from '../components/ItemsEditor.vue'
import TableEditor from '../components/TableEditor.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const orderId = computed(() => route.params.id)
const doc = ref(null)
const loading = ref(true)
const saving = ref(false)
const activeKey = ref('goal')
const savedSnapshot = ref('')

// AI 修改：对话框 + 指令输入 + 请求状态
const aiDialogVisible = ref(false)
const aiInstruction = ref('')
const aiRevising = ref(false)
const QUICK_SUGGESTIONS = [
  '把「普通用户」角色改名为「会员用户」并补充其职责',
  '前台新增一个积分商城模块，并配套数据库表',
  '把核心业务场景精简为 8 条，保留完整故事线',
  '技术栈改为 Django + MySQL，同步更新技术架构章节',
]

const ch = computed(() => doc.value.chapters)
// 原文直用文档（mode=raw）：没有九章结构，走纯文本编辑分支
const isRaw = computed(() => doc.value?.mode === 'raw')

const chapterList = computed(() => [
  { key: 'goal', title: '项目目标' },
  { key: 'scope', title: '建设范围' },
  { key: 'roles', title: '角色定义' },
  { key: 'scenarios', title: '核心业务场景' },
  { key: 'functions', title: '功能需求' },
  { key: 'rules', title: '业务规则' },
  { key: 'data_scope', title: '数据范围' },
  { key: 'tech', title: '技术架构' },
  { key: 'database', title: '数据库设计' },
])

const isDirty = computed(() => !!doc.value && JSON.stringify(doc.value) !== savedSnapshot.value)

function markSaved() {
  savedSnapshot.value = doc.value ? JSON.stringify(doc.value) : ''
}

// ===== 章节导航：点击定位 + 滚动高亮（scroll spy） =====
function sectionEls() {
  return Array.from(document.querySelectorAll('.doc-editor .chapter-card[data-key]'))
}

function jump(key) {
  const target = sectionEls().find((el) => el.dataset.key === key)
  activeKey.value = key
  if (!target) return
  const offset = window.innerWidth <= 900 ? 122 : 84
  const top = target.getBoundingClientRect().top + window.scrollY - offset
  window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
}

function updateActiveFromScroll() {
  if (!doc.value) return
  const sections = sectionEls()
  if (!sections.length) return
  const offset = 110
  let current = sections[0].dataset.key
  for (const el of sections) {
    if (el.getBoundingClientRect().top <= offset) current = el.dataset.key
    else break
  }
  activeKey.value = current
}

// ===== 数据加载 =====
async function loadDoc(id) {
  loading.value = true
  doc.value = null
  savedSnapshot.value = ''
  activeKey.value = 'goal'
  try {
    const data = await http.get(`/orders/${id}/requirement`)
    doc.value = data.document
    await nextTick()
    markSaved()
    updateActiveFromScroll()
  } catch {
    ElMessage.warning('尚未生成需求书，请先在订单详情页生成')
    router.replace(`/orders/${id}`)
  } finally {
    loading.value = false
  }
}

// 切换订单（route.params.id 变化）时重新加载，而不是复用旧文档
watch(
  () => route.params.id,
  (id, oldId) => {
    if (!id || id === oldId || !auth.isStaffView) return
    loadDoc(id)
  },
)

// ===== 保存 / 下载 =====
async function save() {
  if (saving.value) return
  saving.value = true
  try {
    const data = await http.put(`/orders/${orderId.value}/requirement`, { document: doc.value }, { timeout: 60000 })
    doc.value = data.document
    await nextTick()
    markSaved()
    ElMessage.success('已保存，可随时下载最新 Word')
  } finally {
    saving.value = false
  }
}

function download() {
  window.open(`/api/orders/${orderId.value}/requirement/docx`, '_blank')
}

// ===== AI 按建议修订 =====
async function applyAiRevise() {
  if (aiRevising.value) return
  const text = aiInstruction.value.trim()
  if (text.length < 2) {
    ElMessage.warning('请先描述想要的修改')
    return
  }
  aiRevising.value = true
  try {
    // 带上当前文档（含未保存修改），AI 在此基础上做最小改动
    const data = await http.post(
      `/orders/${orderId.value}/requirement/ai-revise`,
      { instruction: text, document: doc.value },
      { timeout: 300000 },
    )
    doc.value = data.document
    await nextTick()
    aiDialogVisible.value = false
    aiInstruction.value = ''
    jump('goal')
    ElMessage.success('AI 已按建议修改，请逐章检查后点击「保存修改」')
  } catch {
    /* 错误由 axios 拦截器统一提示，文档保持原样 */
  } finally {
    aiRevising.value = false
  }
}

// ===== 未保存离开提示 =====
function handleBeforeUnload(e) {
  if (!isDirty.value) return
  e.preventDefault()
  e.returnValue = ''
}

onBeforeRouteLeave(async () => {
  if (!isDirty.value) return true
  try {
    await ElMessageBox.confirm('当前修改尚未保存，确定离开吗？', '未保存的修改', {
      confirmButtonText: '离开',
      cancelButtonText: '继续编辑',
      type: 'warning',
    })
    return true
  } catch {
    return false
  }
})

onMounted(() => {
  window.addEventListener('scroll', updateActiveFromScroll, { passive: true })
  window.addEventListener('beforeunload', handleBeforeUnload)
  // 管理员、写手与代理都可以进入需求书编辑页（路由 roles 同步放开了代理）
  if (!auth.isStaffView && !auth.isAgent) {
    ElMessage.warning('无权编辑需求书')
    router.replace(`/orders/${orderId.value}`)
    return
  }
  loadDoc(orderId.value)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', updateActiveFromScroll)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<style scoped>
.doc-editor { min-width: 0; }

.editor-head {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  flex-wrap: wrap;
}
.eh-left { display: flex; align-items: center; gap: 8px; min-width: 0; flex-wrap: wrap; }
.doc-title { font-weight: 600; font-size: 15.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: min(60vw, 640px); }
.eh-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.dirty-tag {
  font-size: 11px; font-weight: 600; color: var(--warning);
  background: var(--warning-weak); border: 1px solid color-mix(in srgb, var(--warning) 30%, transparent);
  border-radius: var(--radius-pill); padding: 1px 9px; white-space: nowrap;
}

.editor-body { display: flex; gap: 14px; align-items: flex-start; }
.editor-body-raw { display: block; }
.raw-card { width: 100%; max-width: 980px; margin: 0 auto; }
.raw-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.raw-head h3 { margin: 0; font-size: 15px; }
.raw-card .hint { font-size: 12px; color: var(--text-3); margin: 0 0 12px; }
.raw-textarea :deep(.el-textarea__inner) {
  font-family: inherit; line-height: 1.8; font-size: 13.5px;
}
.chapter-nav { width: 168px; flex-shrink: 0; position: sticky; top: 84px; padding: 10px; }
.chapter-link {
  padding: 8px 10px; border-radius: var(--radius-sm); font-size: 13px; color: var(--text-2);
  cursor: pointer; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background 0.15s ease, color 0.15s ease;
}
.chapter-link:hover { background: var(--hover); color: var(--text); }
.chapter-link.active { background: var(--brand-weak); color: var(--brand); font-weight: 600; }
.chapter-area { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.chapter-card { scroll-margin-top: 96px; }
.chapter-card h3 { margin: 0 0 6px; font-size: 15px; color: var(--text); }
.hint { font-size: 12px; color: var(--text-3); margin: 0 0 12px; }
.sub-title { font-weight: 600; font-size: 13.5px; margin: 14px 0 8px; color: var(--text); }

.block-card { border: 1px solid var(--border); border-radius: var(--radius-md); padding: 12px; margin-bottom: 12px; }
.block-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.name-input { max-width: 320px; font-weight: 600; }
.block-no { font-size: 12px; }
.module-card {
  border-left: 3px solid color-mix(in srgb, var(--brand) 28%, transparent);
  padding-left: 12px; margin-bottom: 12px;
}
.struct-row { display: flex; gap: 8px; margin-bottom: 8px; }
.desc-input { flex: 1; }
.block-btn { width: 100%; }

/* ===== AI 修改对话框 ===== */
.ar-body { display: flex; flex-direction: column; gap: 12px; }
.ar-hint {
  display: flex; align-items: flex-start; gap: 6px;
  margin: 0; font-size: 12.5px; line-height: 1.55; color: var(--text-2);
}
.ar-hint .iconify { color: var(--brand); flex-shrink: 0; margin-top: 2px; }
.ar-quick { display: flex; align-items: flex-start; gap: 6px; flex-wrap: wrap; }
.ar-quick-label { font-size: 12px; color: var(--text-3); line-height: 24px; flex-shrink: 0; }
.ar-chip { cursor: pointer; }
.ar-chip:hover { color: var(--brand); border-color: var(--brand); }

/* ===== 首屏骨架 ===== */
.sk-head { min-height: 66px; }
.sk-left, .sk-right { display: flex; align-items: center; gap: 10px; }
.sk-btn { width: 90px; height: 34px; border-radius: var(--radius-sm); }
.sk-btn.wide { width: 120px; }
.sk-title { width: 220px; height: 18px; border-radius: 6px; }
.sk-nav { display: flex; flex-direction: column; gap: 10px; min-height: 280px; }
.sk-nav-line { height: 30px; border-radius: var(--radius-sm); }
.sk-chapter { height: 170px; border-radius: var(--radius-lg); }

@media (max-width: 900px) {
  .editor-body { flex-direction: column; }
  .chapter-nav {
    width: 100%; position: sticky;
    top: calc(var(--topbar-h) + var(--tabs-h) + 6px);
    z-index: 20;
    display: flex; flex-wrap: nowrap; gap: 4px;
    overflow-x: auto; padding: 8px;
    background: color-mix(in srgb, var(--card) 92%, transparent);
    backdrop-filter: blur(10px);
  }
  .chapter-link { flex: 0 0 auto; margin-bottom: 0; }
  .name-input { max-width: none; flex: 1; }
  .struct-row { flex-wrap: wrap; }
  .sk-nav { flex-direction: row; width: 100%; min-height: 48px; }
  .sk-nav-line { width: 96px; height: 30px; flex-shrink: 0; }
  .doc-title { max-width: 100%; white-space: normal; }
}
</style>
