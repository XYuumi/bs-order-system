<template>
  <SettingsShell
    title="数据备份"
    :description="headerDesc"
    icon="ri:database-2-line"
  >
    <template #actions>
      <el-button type="primary" :loading="backingUp" @click="runBackup">
        <Icon icon="ri:database-2-line" class="btn-ic" />立即备份
      </el-button>
    </template>

    <div class="settings-stack">
      <div class="backup-note">
        <Icon icon="ri:shield-check-line" class="note-ic" />
        <span>
          JSON 逻辑备份加密存储到 server/backups/，自动保留最近 14 份；恢复用 scripts/restore_backup.py。
          定时备份可在 Windows 任务计划中每日执行 backup.py。
        </span>
      </div>

      <div class="backup-list-wrap">
        <div v-if="loading" class="backup-list">
          <div v-for="i in 3" :key="i" class="backup-item">
            <div class="skeleton sk-line" />
            <div class="skeleton sk-btn" />
          </div>
        </div>

        <div v-else-if="backups.length" class="backup-list">
          <div v-for="(b, i) in backups" :key="b.name" class="backup-item">
            <div class="bi-main">
              <div class="bi-name-line">
                <span class="bi-ic"><Icon icon="ri:file-shield-2-line" /></span>
                <span class="bi-name mono">{{ b.name }}</span>
                <span v-if="i === 0" class="bi-tag latest">最新</span>
                <span class="bi-tag" :class="b.encrypted ? 'enc' : 'plain'">
                  <Icon :icon="b.encrypted ? 'ri:lock-2-line' : 'ri:lock-unlock-line'" />
                  {{ b.encrypted ? '已加密' : '未加密' }}
                </span>
              </div>
              <div class="bi-meta">{{ fmtSize(b.size) }} · {{ b.created_at }}</div>
            </div>
            <div class="bi-ops">
              <el-button size="small" text :loading="downloading === b.name" @click="downloadBackup(b)">
                <span class="bi-op"><Icon icon="ri:download-2-line" />下载</span>
              </el-button>
              <el-button size="small" text type="danger" :loading="deleting === b.name" @click="removeBackup(b)">
                <span class="bi-op"><Icon icon="ri:delete-bin-line" />删除</span>
              </el-button>
            </div>
          </div>
        </div>

        <EmptyState
          v-else
          icon="ri:database-2-line"
          title="暂无备份"
          description="点击右上角「立即备份」创建第一份加密备份"
        >
          <el-button type="primary" :loading="backingUp" @click="runBackup">立即备份</el-button>
        </EmptyState>
      </div>
    </div>
  </SettingsShell>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../../api'
import SettingsShell from '../../components/ui/SettingsShell.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import { sensitiveConfirm, withConfirm } from '../../utils/sensitive'

const loading = ref(false)
const backingUp = ref(false)
const downloading = ref('')
const deleting = ref('')
const backups = ref([])

const headerDesc = computed(() => {
  const latest = backups.value[0]?.created_at
  return latest
    ? `最新备份：${latest} · 共 ${backups.value.length} 份`
    : 'JSON 逻辑备份，加密存储，自动保留最近 14 份'
})

onMounted(loadBackups)

async function loadBackups() {
  loading.value = true
  try {
    const data = await http.get('/admin/backups')
    backups.value = data.items || []
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function runBackup() {
  backingUp.value = true
  try {
    // 数据量大时备份要跑几十秒，单独放宽超时
    const info = await http.post('/admin/backup', null, { timeout: 0 })
    ElMessage.success(`备份完成：${info.name}（${info.rows} 行数据${info.encrypted ? '，已加密' : ''}）`)
    await loadBackups()
  } finally {
    backingUp.value = false
  }
}

function fmtSize(size) {
  const n = Number(size || 0)
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

async function downloadBackup(b) {
  const password = await sensitiveConfirm({
    title: '下载备份确认',
    content: `下载 ${b.name} 需要输入登录密码确认`,
  })
  if (password == null) return

  downloading.value = b.name
  try {
    // 下载是 GET 文件流，使用 withConfirm 生成请求头并交给 fetch，便于读取 403 的错误详情
    const { headers } = withConfirm(password)
    const res = await fetch(`/api/admin/backups/${encodeURIComponent(b.name)}/download`, {
      headers,
      credentials: 'include',
    })
    if (!res.ok) {
      let detail = `下载失败（HTTP ${res.status}）`
      try {
        const data = await res.json()
        if (data?.detail) detail = data.detail
      } catch {
        /* 非 JSON 错误响应 */
      }
      if (res.status === 401) window.location.href = '/login'
      throw new Error(detail)
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = b.name
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1500)
    ElMessage.success('已开始下载')
  } catch (err) {
    ElMessage.error(err?.message || '下载失败')
  } finally {
    downloading.value = ''
  }
}

async function removeBackup(b) {
  const password = await sensitiveConfirm({
    title: '删除备份确认',
    content: `删除 ${b.name} 后不可恢复，请输入登录密码确认`,
  })
  if (password == null) return

  deleting.value = b.name
  try {
    await http.delete(`/admin/backups/${encodeURIComponent(b.name)}`, withConfirm(password))
    ElMessage.success('已删除')
    await loadBackups()
  } finally {
    deleting.value = ''
  }
}
</script>

<style scoped>
.btn-ic { margin-right: 4px; }

.backup-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 11px 13px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.65;
}
.note-ic { color: var(--info); font-size: 15px; flex-shrink: 0; margin-top: 2px; }

.backup-list-wrap { min-height: 160px; }
.backup-list { display: flex; flex-direction: column; gap: 10px; }
.backup-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 13px 15px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.bi-main { min-width: 0; flex: 1; }
.bi-name-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
.bi-ic { color: var(--brand); font-size: 16px; display: inline-flex; }
.bi-name { font-size: 13px; font-weight: 500; word-break: break-all; }
.bi-meta { margin: 4px 0 0 24px; font-size: 12px; color: var(--text-3); }
.bi-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  font-size: 10.5px;
  font-weight: 500;
}
.bi-tag .iconify { font-size: 11px; }
.bi-tag.latest { background: var(--brand-weak); color: var(--brand); }
.bi-tag.enc { background: var(--success-weak); color: var(--success); }
.bi-tag.plain { background: var(--warning-weak); color: var(--warning); }

.bi-ops { display: flex; align-items: center; flex-shrink: 0; }
.bi-ops :deep(.el-button + .el-button) { margin-left: 2px; }
.bi-op { display: inline-flex; align-items: center; gap: 4px; }
.bi-op .iconify { font-size: 14px; }

.sk-line { width: 58%; height: 16px; }
.sk-btn { width: 90px; height: 28px; flex-shrink: 0; }

@media (max-width: 640px) {
  .backup-item { flex-direction: column; align-items: stretch; gap: 8px; }
  .bi-ops { justify-content: flex-end; }
  .bi-meta { margin-left: 0; }
  .sk-line { width: 78%; }
}
</style>
