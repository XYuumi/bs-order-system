<template>
  <SettingsShell
    title="安全设置"
    description="登录失败锁定策略、会话管理与当前安全能力总览"
    icon="ri:shield-check-line"
    :loading="loading"
  >
    <div class="settings-stack">
      <section class="settings-section">
        <div class="settings-section-head">
          <div>
            <div class="settings-section-title">登录与会话</div>
            <p class="settings-section-desc">配置失败锁定策略，或在需要时让所有设备立即退出登录</p>
          </div>
        </div>

        <div class="security-grid">
          <div class="lock-block">
            <div class="block-title">登录失败锁定</div>
            <el-form label-position="top" @submit.prevent>
              <div class="lock-row">
                <el-form-item label="失败次数阈值（次）">
                  <el-input-number
                    v-model="form.login_lock_threshold"
                    :min="3"
                    :max="20"
                    :precision="0"
                    :step="1"
                    controls-position="right"
                    style="width: 180px"
                  />
                  <div class="settings-hint">连续输错密码达到该次数后锁定账号。</div>
                </el-form-item>
                <el-form-item label="锁定时长（分钟）">
                  <el-input-number
                    v-model="form.login_lock_minutes"
                    :min="1"
                    :max="1440"
                    :precision="0"
                    :step="5"
                    controls-position="right"
                    style="width: 180px"
                  />
                  <div class="settings-hint">锁定期间该账号无法登录，到期自动解锁。</div>
                </el-form-item>
              </div>
              <el-button type="primary" :loading="saving" @click="saveSettings">保存策略</el-button>
            </el-form>
          </div>

          <div class="session-block">
            <div class="block-title">会话与设备</div>
            <div class="session-user">
              <Icon icon="ri:account-circle-line" />
              当前账号：<span class="mono">{{ auth.user?.username || '—' }}</span>
            </div>
            <p class="settings-hint session-desc">
              退出所有设备后，所有设备上的登录状态立即失效（包括当前设备），需要重新登录。
            </p>
            <div class="settings-actions">
              <el-button type="danger" plain :loading="loggingOutAll" @click="logoutAll">
                <Icon icon="ri:logout-box-r-line" class="btn-ic" />退出所有设备
              </el-button>
            </div>
          </div>
        </div>
      </section>

      <section class="settings-section">
        <div class="settings-section-head">
          <div>
            <div class="settings-section-title">当前安全能力</div>
            <p class="settings-section-desc">以下状态按当前账号的真实配置展示</p>
          </div>
        </div>

        <div class="sec-list">
          <div class="sec-item">
            <div class="sec-item-ic"><Icon icon="ri:lock-2-line" /></div>
            <div class="sec-item-body">
              <div class="sec-item-name">
                登录失败锁定
                <span class="sec-state on"><Icon icon="ri:checkbox-circle-fill" />已启用</span>
              </div>
              <div class="sec-item-desc text-2">
                同一账号连续输错密码达到 {{ form.login_lock_threshold }} 次后锁定 {{ form.login_lock_minutes }} 分钟，到期自动解锁。
              </div>
            </div>
          </div>

          <div class="sec-item">
            <div class="sec-item-ic" :class="{ warn: !totpEnabled }"><Icon icon="ri:smartphone-line" /></div>
            <div class="sec-item-body">
              <div class="sec-item-name">
                TOTP 两步验证
                <span class="sec-state" :class="totpEnabled ? 'on' : 'off'">
                  <Icon :icon="totpEnabled ? 'ri:checkbox-circle-fill' : 'ri:checkbox-blank-circle-line'" />
                  {{ totpEnabled ? '已开启' : '未开启' }}
                </span>
              </div>
              <div class="sec-item-desc text-2">
                登录时需输入验证器 App 的一次性验证码。
                <router-link to="/profile" class="sec-link">
                  去个人中心{{ totpEnabled ? '管理' : '开启' }}<Icon icon="ri:arrow-right-up-line" class="sec-link-ic" />
                </router-link>
              </div>
            </div>
          </div>

          <div class="sec-item">
            <div class="sec-item-ic"><Icon icon="ri:key-2-line" /></div>
            <div class="sec-item-body">
              <div class="sec-item-name">
                API Key 隔离
                <span class="sec-state on"><Icon icon="ri:checkbox-circle-fill" />已启用</span>
              </div>
              <div class="sec-item-desc text-2">写手与代理各自持有独立 API Key，外部系统只能访问自己权限内的数据。</div>
            </div>
          </div>

          <div class="sec-item">
            <div class="sec-item-ic"><Icon icon="ri:fingerprint-line" /></div>
            <div class="sec-item-body">
              <div class="sec-item-name">
                敏感操作密码确认
                <span class="sec-state on"><Icon icon="ri:checkbox-circle-fill" />已启用</span>
              </div>
              <div class="sec-item-desc text-2">改价、重置密码 / API Key、下载或删除备份等敏感操作需要再次输入登录密码确认。</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </SettingsShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../../api'
import SettingsShell from '../../components/ui/SettingsShell.vue'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const loggingOutAll = ref(false)

const form = reactive({
  login_lock_threshold: 5,
  login_lock_minutes: 10,
})

// 真实字段来自 /auth/me 的 user.totp_enabled，不再固定显示“已支持”
const totpEnabled = computed(() => !!auth.user?.totp_enabled)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const s = await http.get('/settings')
    const st = s.settings
    form.login_lock_threshold = Number(st.login_lock_threshold || 5)
    form.login_lock_minutes = Number(st.login_lock_minutes || 10)
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  const threshold = Number(form.login_lock_threshold)
  const minutes = Number(form.login_lock_minutes)
  if (!Number.isFinite(threshold) || threshold < 1) {
    ElMessage.warning('失败次数阈值必须是有效数字')
    return
  }
  if (!Number.isFinite(minutes) || minutes < 1) {
    ElMessage.warning('锁定时长必须是有效数字')
    return
  }
  saving.value = true
  try {
    await http.put('/settings', {
      login_lock_threshold: String(threshold),
      login_lock_minutes: String(minutes),
    })
    ElMessage.success('已保存')
  } finally {
    saving.value = false
  }
}

async function logoutAll() {
  try {
    await ElMessageBox.confirm(
      '退出后所有设备都需要重新登录（当前设备也会退出），确定继续吗？',
      '退出所有设备',
      {
        confirmButtonText: '退出所有设备',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      }
    )
  } catch {
    return
  }

  loggingOutAll.value = true
  try {
    await http.post('/auth/logout-all')
    ElMessage.success('已退出所有设备，请重新登录')
    await auth.logout()
  } finally {
    loggingOutAll.value = false
  }
}
</script>

<style scoped>
.security-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr);
  gap: 18px;
}
.lock-block,
.session-block { min-width: 0; }
.block-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 12px; }
.lock-row { display: flex; gap: 24px; flex-wrap: wrap; }
.session-block {
  display: flex;
  flex-direction: column;
  padding: 14px 15px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.session-user {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-2);
}
.session-user .iconify { color: var(--text-3); font-size: 15px; }
.session-desc { margin-top: 8px; }
.session-block .settings-actions { margin-top: auto; padding-top: 14px; }
.btn-ic { margin-right: 4px; }

/* ===== 安全能力列表 ===== */
.sec-list { display: flex; flex-direction: column; gap: 10px; }
.sec-item {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 13px 15px; border-radius: var(--radius-sm);
  background: var(--card); border: 1px solid var(--border);
}
.sec-item-ic {
  width: 34px; height: 34px; border-radius: 9px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--success-weak); color: var(--success); font-size: 17px;
}
.sec-item-ic.warn { background: var(--warning-weak); color: var(--warning); }
.sec-item-body { min-width: 0; flex: 1; }
.sec-item-name {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  font-size: 13.5px; font-weight: 600;
}
.sec-state {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; font-weight: 500;
}
.sec-state.on { color: var(--success); }
.sec-state.off { color: var(--warning); }
.sec-state .iconify { font-size: 13px; }
.sec-item-desc { font-size: 12px; line-height: 1.6; margin-top: 3px; }
.sec-link {
  display: inline-flex; align-items: center; gap: 3px;
  color: var(--brand); font-size: 12px;
}
.sec-link:hover { color: var(--brand-2); }
.sec-link-ic { font-size: 12px; }

@media (max-width: 900px) {
  .security-grid { grid-template-columns: 1fr; gap: 16px; }
  .lock-row { gap: 14px; }
  .session-block .settings-actions { margin-top: 14px; }
}
</style>
