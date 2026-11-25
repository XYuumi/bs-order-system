<template>
  <div class="users-view">
    <AppPageHeader
      title="用户管理"
      description="管理员可管理写手与代理账号；代理的 API Key 用于外部系统对接"
      icon="ri:group-line"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">
          <Icon icon="ri:add-line" class="btn-ic" />新建用户
        </el-button>
      </template>
    </AppPageHeader>

    <div class="page-card">
      <DataTableToolbar :count="items.length" :loading="loading" @refresh="load">
        <template #left>
          <span class="toolbar-hint">
            <Icon icon="ri:shield-user-line" />
            用户列表 · 管理员可调整角色、状态与敏感凭证
          </span>
        </template>
      </DataTableToolbar>

      <el-alert
        v-if="loadError"
        class="load-alert"
        type="error"
        show-icon
        :closable="false"
        title="用户列表加载失败"
        :description="loadError"
      />

      <!-- 桌面端表格 -->
      <el-table v-if="!isMobile" :data="items" v-loading="loading" row-key="id" style="width: 100%">
        <el-table-column label="用户名" width="140">
          <template #default="{ row }"><span class="mono">{{ row.username }}</span></template>
        </el-table-column>
        <el-table-column prop="display_name" label="名称" min-width="220" show-overflow-tooltip />
        <el-table-column label="角色" width="88">
          <template #default="{ row }">
            <!-- 角色名称优先显示管理员自定义的角色标签（role_label） -->
            <span class="role-badge" :class="row.role">{{ row.role_label || roleLabel(row.role) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上级/抽成" width="120">
          <template #default="{ row }">
            <template v-if="row.role === 'agent'">
              <div v-if="row.parent_id" class="text-2 parent-cell">
                {{ agentName(row.parent_id) }}
                <span v-if="row.commission_rate > 0" class="commission">{{ row.commission_rate }}%</span>
              </div>
              <span v-else class="text-2">—</span>
            </template>
            <span v-else class="text-2">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="72">
          <template #default="{ row }">
            <el-switch :model-value="row.is_active" size="small" @change="(v) => toggleActive(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="API Key" width="128">
          <template #default="{ row }">
            <template v-if="row.role === 'agent' || row.role === 'staff'">
              <el-button size="small" type="primary" link @click="showKey(row)">查看</el-button>
              <el-button size="small" type="danger" link @click="resetKey(row)">重置</el-button>
            </template>
            <span v-else class="text-2">—</span>
          </template>
        </el-table-column>
        <el-table-column label="最后登录" width="142">
          <template #default="{ row }">{{ fmtLogin(row.last_login_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="118">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="primary" link @click="resetPwd(row)">改密</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            compact
            icon="ri:user-add-line"
            title="暂无用户"
            description="点击右上角「新建用户」创建写手或代理账号"
          />
        </template>
      </el-table>

      <!-- 移动端卡片：保留全部操作 -->
      <div v-else class="user-cards" v-loading="loading">
        <EmptyState
          v-if="!loading && !items.length"
          icon="ri:user-add-line"
          title="暂无用户"
          description="点击右上角「新建用户」创建写手或代理账号"
        />
        <div v-for="row in items" :key="row.id" class="user-card">
          <div class="uc-head">
            <div class="uc-id">
              <span class="uc-display">{{ row.display_name || row.username }}</span>
              <span class="uc-username mono">@{{ row.username }}</span>
            </div>
            <span class="role-badge" :class="row.role">{{ row.role_label || roleLabel(row.role) }}</span>
          </div>

          <div class="uc-meta">
            <div class="uc-field">
              <span class="uc-label">状态</span>
              <span class="uc-value">
                <el-switch :model-value="row.is_active" size="small" @change="(v) => toggleActive(row, v)" />
              </span>
            </div>
            <div class="uc-field">
              <span class="uc-label">最后登录</span>
              <span class="uc-value">{{ fmtLogin(row.last_login_at) }}</span>
            </div>
            <div v-if="row.role === 'agent'" class="uc-field">
              <span class="uc-label">上级 / 抽成</span>
              <span class="uc-value">
                <template v-if="row.parent_id">
                  {{ agentName(row.parent_id) }}
                  <span v-if="row.commission_rate > 0" class="commission">{{ row.commission_rate }}%</span>
                </template>
                <template v-else>—</template>
              </span>
            </div>
          </div>

          <div class="uc-actions">
            <el-button size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="primary" link @click="resetPwd(row)">改密</el-button>
            <template v-if="row.role === 'agent' || row.role === 'staff'">
              <el-button size="small" type="primary" link @click="showKey(row)">查看 Key</el-button>
              <el-button size="small" type="danger" link @click="resetKey(row)">重置 Key</el-button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 新建/编辑 -->
    <el-dialog v-model="dlg.visible" :title="dlg.isCreate ? '新建用户' : `编辑：${dlg.form.username}`" width="470">
      <el-form label-position="top" style="margin-top: 8px">
        <el-form-item label="用户名" required>
          <el-input v-model="dlg.form.username" :disabled="!dlg.isCreate" placeholder="字母数字下划线" />
        </el-form-item>
        <el-form-item v-if="dlg.isCreate" label="初始密码" required>
          <el-input v-model="dlg.form.password" type="password" show-password placeholder="至少 6 位" />
          <div class="form-extra">至少 6 位</div>
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="dlg.form.display_name" :maxlength="50" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="dlg.form.role" style="width: 100%" :disabled="dlg.form.id === auth.user?.id">
            <el-option v-for="o in roleOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <template v-if="dlg.form.role === 'agent'">
          <el-form-item label="上级代理（可选）">
            <el-select v-model="dlg.form.parent_id" placeholder="无上级" style="width: 100%" clearable filterable>
              <el-option v-for="o in agentOptions.filter(a => a.value !== dlg.form.id)" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <div class="form-extra">形成多级代理体系；下级订单结单时按抽成比例给上级分成</div>
          </el-form-item>
          <el-form-item label="抽成比例（% 给上级）">
            <el-input-number v-model="dlg.form.commission_rate" :min="0" :max="100" :precision="1" style="width: 100%" placeholder="0" />
          </el-form-item>
          <el-form-item label="API 可拉取项目类型">
            <el-checkbox-group v-model="dlg.form.api_categories" style="width: 100%">
              <el-checkbox v-for="o in catCheckOptions" :key="o.value" :value="o.value">{{ o.label }}</el-checkbox>
            </el-checkbox-group>
            <div class="form-extra">勾选后该用户通过 API 只能拉取/创建勾选类型的订单；全不勾 = 全部</div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dlg.visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 查看 API Key -->
    <el-dialog v-model="keyVisible" title="API Key">
      <p class="text-2" style="margin-top: 4px">{{ keyOwner }} 的 API Key（请勿泄露）：</p>
      <div class="key-value mono">{{ keyValue }}</div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../api'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import DataTableToolbar from '../components/ui/DataTableToolbar.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import { sensitiveConfirm, withConfirm } from '../utils/sensitive'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const items = ref([])
const allUsers = ref([])

const ROLE_LABELS = { admin: '管理员', staff: '写手', agent: '代理' }
function roleLabel(role) {
  return ROLE_LABELS[role] || role
}

const roleOptions = [
  { label: '管理员（全部权限，见真实价）', value: 'admin' },
  { label: '写手（做单/上传/回传状态）', value: 'staff' },
  { label: '代理/销售（只见代理价 + API）', value: 'agent' },
]

const dlg = reactive({
  visible: false,
  isCreate: true,
  form: { id: null, username: '', password: '', display_name: '', role: 'agent', parent_id: undefined, commission_rate: 0, api_categories: [] },
})

const catCheckOptions = [
  { label: '纯程序设计', value: 'program' },
  { label: '纯论文', value: 'thesis' },
  { label: '论文+设计', value: 'thesis_program' },
]

const agentOptions = computed(() =>
  allUsers.value
    .filter((u) => u.role === 'agent' && u.is_active)
    .map((u) => ({ label: u.display_name || u.username, value: u.id }))
)

function agentName(id) {
  const u = allUsers.value.find((x) => x.id === id)
  return u ? (u.display_name || u.username) : `#${id}`
}

function fmtLogin(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : '从未'
}

const keyVisible = ref(false)
const keyValue = ref('')
const keyOwner = ref('')

// 移动端使用卡片，避免宽表格横向挤压
const isMobile = ref(
  typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches
)
let mediaQuery = null
function onMediaChange(e) {
  isMobile.value = e.matches
}

const loadError = ref('')
async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const data = await http.get('/users')
    items.value = data.items
    allUsers.value = data.items
  } catch (e) {
    // 接口失败时给出明确错误态，而不是让人误以为「系统里没有用户」
    loadError.value = e?.response?.data?.detail || '请检查网络或稍后重试'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(dlg, {
    visible: true,
    isCreate: true,
    form: { id: null, username: '', password: '', display_name: '', role: 'agent', parent_id: undefined, commission_rate: 0, api_categories: [] },
  })
}

function openEdit(row) {
  Object.assign(dlg, {
    visible: true,
    isCreate: false,
    form: {
      id: row.id,
      username: row.username,
      password: '',
      display_name: row.display_name,
      role: row.role,
      parent_id: row.parent_id || undefined,
      commission_rate: row.commission_rate || 0,
      api_categories: [...(row.api_categories || [])],
    },
  })
}

async function save() {
  const f = dlg.form
  if (dlg.isCreate && (!f.username || !f.password)) return ElMessage.warning('请填写用户名和初始密码')
  try {
    if (dlg.isCreate) {
      await http.post('/users', {
        username: f.username,
        password: f.password,
        display_name: f.display_name,
        role: f.role,
        ...(f.role === 'agent'
          ? { parent_id: f.parent_id || null, commission_rate: f.commission_rate || 0, api_categories: f.api_categories || [] }
          : {}),
      })
      ElMessage.success('用户已创建' + (f.role === 'agent' ? '（API Key 已自动生成）' : ''))
    } else {
      const payload = { display_name: f.display_name, role: f.role }
      if (f.password) payload.password = f.password
      if (f.role === 'agent') {
        payload.parent_id = f.parent_id || null
        payload.commission_rate = f.commission_rate || 0
        payload.api_categories = f.api_categories || []
      }
      await http.patch(`/users/${f.id}`, payload)
      ElMessage.success('已保存')
    }
  } catch {
    // 失败保持弹窗打开，便于修正后重试；具体错误由 axios 拦截器提示
    return
  }
  dlg.visible = false
  load()
}

async function resetPwd(row) {
  let value = ''
  try {
    ;({ value } = await ElMessageBox.prompt('输入新密码（至少 6 位）', '重置密码', {
      confirmButtonText: '重置',
      cancelButtonText: '取消',
      inputType: 'password',
      inputPlaceholder: '输入新密码（至少 6 位）',
      inputValidator: (v) => (v && v.length >= 6) || '密码至少 6 位',
    }))
  } catch {
    return
  }
  await http.patch(`/users/${row.id}`, { password: value })
  ElMessage.success('密码已重置')
}

async function toggleActive(row, v) {
  try {
    await http.patch(`/users/${row.id}`, { is_active: v })
    row.is_active = v
    ElMessage.success(v ? '已启用' : '已禁用')
  } catch {
    /* 保持原状 */
  }
}

async function showKey(row) {
  // 查看他人 Key 与重置同级敏感，服务端要求密码二次确认
  const pwd = await sensitiveConfirm({
    title: '查看 API Key 确认',
    content: `查看 ${row.username} 的 API Key 需要密码二次确认`,
  })
  if (pwd == null) return
  try {
    const data = await http.get(`/users/${row.id}/api-key`, withConfirm(pwd))
    keyOwner.value = row.display_name || row.username
    keyValue.value = data.api_key
    keyVisible.value = true
  } catch {
    /* 错误提示交给拦截器 */
  }
}

function resetKey(row) {
  ElMessageBox.confirm(`确定重置「${row.username}」的 API Key 吗？旧 Key 立即失效。`, '重置 API Key', {
    confirmButtonText: '重置',
    cancelButtonText: '取消',
    type: 'warning',
    confirmButtonClass: 'el-button--danger',
  })
    .then(async () => {
      const pwd = await sensitiveConfirm({
        title: '重置 API Key 确认',
        content: `重置 ${row.username} 的 Key 需要密码二次确认`,
      })
      if (pwd == null) return
      const data = await http.post(`/users/${row.id}/reset-api-key`, {}, withConfirm(pwd))
      keyOwner.value = row.display_name || row.username
      keyValue.value = data.api_key
      keyVisible.value = true
      ElMessage.success('已重置，请通知对方更新')
    })
    .catch(() => {})
}

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 768px)')
  isMobile.value = mediaQuery.matches
  mediaQuery.addEventListener('change', onMediaChange)
  load()
})

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener('change', onMediaChange)
})
</script>

<style scoped>
.users-view {
  display: flex;
  flex-direction: column;
  gap: var(--content-gap);
  min-width: 0;
}
.btn-ic { margin-right: 4px; }

.toolbar-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.5;
}
.toolbar-hint .iconify { font-size: 14px; flex-shrink: 0; }

.parent-cell { font-size: 12px; line-height: 1.4; }
.commission { color: var(--success); margin-left: 4px; }
.role-badge { display: inline-block; font-size: 11.5px; font-weight: 600; padding: 1px 9px; border-radius: 5px; }
.role-badge.admin { background: var(--purple-weak); color: var(--purple); }
.role-badge.staff { background: var(--warning-weak); color: var(--warning); }
.role-badge.agent { background: var(--success-weak); color: var(--success); }

.form-extra { font-size: 12px; color: var(--text-3); line-height: 1.5; margin-top: 4px; }
.key-value {
  padding: 12px 14px;
  font-size: 13px;
  background: var(--code-bg);
  border: 1px solid var(--code-border);
  color: var(--brand);
  border-radius: 10px;
  word-break: break-all;
}

/* ===== 移动端用户卡片 ===== */
.user-cards { display: flex; flex-direction: column; gap: 10px; min-height: 160px; }
.user-card {
  padding: 14px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.uc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.uc-id { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.uc-display { font-size: 14px; font-weight: 600; color: var(--text); word-break: break-all; }
.uc-username { font-size: 11.5px; color: var(--text-3); }
.uc-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.uc-field { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.uc-label { font-size: 11px; color: var(--text-3); }
.uc-value { font-size: 12.5px; color: var(--text-2); }
.uc-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
.uc-actions :deep(.el-button + .el-button) { margin-left: 0; }

.load-alert { margin: 0 0 12px; }

@media (max-width: 768px) {
  .toolbar-hint { font-size: 11.5px; }
  .uc-meta { grid-template-columns: 1fr; }
}
</style>
