<template>
  <SettingsShell
    title="集成通知"
    description="机器人推送、备份自动同步与备份完成通知"
    icon="ri:webhook-line"
    :loading="loading"
  >
    <el-form label-position="top" @submit.prevent>
      <div class="settings-stack">
        <section class="settings-section">
          <div class="settings-section-head">
            <div>
              <div class="settings-section-title">机器人推送</div>
              <p class="settings-section-desc">新订单与状态变更时自动推送；留空停用</p>
            </div>
          </div>
          <el-form-item label="机器人 Webhook 地址" :error="webhookError">
            <el-input
              v-model="form.webhook_url"
              clearable
              placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
            />
            <div v-if="form.webhook_url.trim() && !webhookError" class="url-valid">
              <Icon icon="ri:checkbox-circle-line" />
              地址格式正确
            </div>
            <div v-else class="settings-hint">
              支持企业微信 / 钉钉群机器人（text 消息）。仅做前端格式提示，保存后由后端校验并生效。
            </div>
          </el-form-item>
        </section>

        <section class="settings-section">
          <div class="settings-section-head">
            <div>
              <div class="settings-section-title">备份集成</div>
              <p class="settings-section-desc">备份完成后复制到网盘同步目录，并可通过上方 Webhook 推送通知</p>
            </div>
          </div>
          <el-form-item label="备份同步目录">
            <el-input v-model="form.backup_sync_dir" placeholder="D:\Nutstore\backups（网盘同步目录）" />
            <div class="settings-hint">每次备份完成后自动把备份文件复制到该目录（如网盘同步盘），留空停用；需填写绝对路径。</div>
          </el-form-item>
          <el-form-item label="备份完成通知">
            <el-switch v-model="form.backup_notify_webhook" />
            <div class="settings-hint">备份完成后通过上方 Webhook 推送一条通知（需已配置 Webhook 地址）。</div>
          </el-form-item>
        </section>

        <div class="settings-actions">
          <el-button type="primary" :loading="saving" @click="saveSettings">保存</el-button>
          <span class="save-hint text-2">保存后立即生效</span>
        </div>
      </div>
    </el-form>
  </SettingsShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../../api'
import SettingsShell from '../../components/ui/SettingsShell.vue'

const loading = ref(false)
const saving = ref(false)

const TRUTHY = ['1', 'true', 'yes', 'on']

const form = reactive({
  webhook_url: '',
  backup_sync_dir: '',
  backup_notify_webhook: false,
})

// 后端没有测试 Webhook 的接口：这里只做前端 URL 合法性提示，不伪造测试请求
const webhookError = computed(() => {
  const raw = form.webhook_url.trim()
  if (!raw) return ''
  let url
  try {
    url = new URL(raw)
  } catch {
    return '请输入完整的 URL（包含 https:// 等协议头）'
  }
  if (!['http:', 'https:'].includes(url.protocol)) return '仅支持 http / https 协议的地址'
  return ''
})

onMounted(load)

async function load() {
  loading.value = true
  try {
    const s = await http.get('/settings')
    const st = s.settings
    form.webhook_url = st.webhook_url || ''
    form.backup_sync_dir = st.backup_sync_dir || ''
    form.backup_notify_webhook = TRUTHY.includes(String(st.backup_notify_webhook || '').trim().toLowerCase())
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  if (webhookError.value) {
    ElMessage.warning('请先修正 Webhook 地址')
    return
  }
  saving.value = true
  try {
    await http.put('/settings', {
      webhook_url: form.webhook_url.trim(),
      backup_sync_dir: form.backup_sync_dir.trim(),
      // 后端按 "1"/"true"/"yes"/"on" 识别开启，统一存 "1"/"0"
      backup_notify_webhook: form.backup_notify_webhook ? '1' : '0',
    })
    ElMessage.success('已保存')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.url-valid {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--success);
}
.url-valid .iconify { font-size: 14px; }
.save-hint { font-size: 12px; }
</style>
