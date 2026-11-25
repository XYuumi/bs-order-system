<template>
  <div class="page-shell profile-view">
    <!-- ===== 顶部横向个人横幅（封面 + 头像 + 信息内联，替代原左侧短卡） ===== -->
    <div class="pv-banner">
      <div class="pv-cover">
        <div class="pv-avatar">{{ (auth.user?.display_name || auth.user?.username || '?').slice(0, 1) }}</div>
        <span class="pv-sec-pill" :class="totpEnabled ? 'on' : 'off'" :title="totpEnabled ? '账号已开启两步验证' : '账号尚未开启两步验证'">
          <Icon :icon="totpEnabled ? 'ri:shield-check-fill' : 'ri:shield-keyhole-line'" class="pv-sec-pill-ic" />
          {{ totpEnabled ? '两步验证已开启' : '两步验证未开启' }}
        </span>
        <div class="pv-name-row">
          <h2 class="pv-name">{{ auth.user?.display_name || auth.user?.username }}</h2>
          <span class="pv-role-tag">{{ auth.roleName }}</span>
        </div>
      </div>
      <div class="pv-banner-body">
        <div class="pv-info-row">
          <span class="pi-item"><Icon icon="ri:user-3-line" class="pi-icon" />{{ auth.user?.username }}</span>
          <span class="pi-item"><Icon icon="ri:shield-user-line" class="pi-icon" />{{ permText }}</span>
          <span class="pi-item"><Icon icon="ri:time-line" class="pi-icon" />上次登录 {{ lastLogin }}</span>
        </div>
      </div>
    </div>

    <!-- ===== 双列：左 安全+密码 / 右 分享页 ===== -->
    <div class="pv-grid">
      <div class="pv-col">
        <div class="pv-card">
          <div class="pc-head">账号安全</div>
          <div class="pc-body sec-body">
            <div class="sec-main">
              <span class="sec-icon" :class="{ on: totpEnabled }">
                <Icon :icon="totpEnabled ? 'ri:shield-check-fill' : 'ri:shield-keyhole-line'" />
              </span>
              <div class="sec-meta">
                <div class="sec-name">两步验证（TOTP）</div>
                <div class="text-2 sec-desc">开启后登录需输入认证器动态码，即使密码泄露也能保护账号</div>
              </div>
            </div>
            <div class="sec-actions">
              <el-button v-if="!totpEnabled" type="primary" :loading="totpLoading" @click="openTotp">
                <Icon icon="ri:shield-keyhole-line" class="sec-btn-ic" />开启两步验证
              </el-button>
              <el-button v-else :loading="totpLoading" @click="disableTotp">关闭</el-button>
            </div>
          </div>
        </div>

        <div class="pv-card">
          <div class="pc-head">修改密码</div>
          <el-form label-position="top" class="pc-body pc-form" @submit.prevent>
            <el-form-item label="原密码">
              <el-input v-model="form.old_password" type="password" show-password />
            </el-form-item>
            <div class="pf-grid">
              <el-form-item label="新密码">
                <el-input v-model="form.new_password" type="password" show-password />
                <div class="text-2 pf-extra">至少 6 位；修改后所有设备将强制重新登录</div>
              </el-form-item>
              <el-form-item label="确认新密码">
                <el-input v-model="form.confirm" type="password" show-password />
              </el-form-item>
            </div>
            <div class="pf-actions"><el-button type="primary" :loading="saving" @click="submit">修改密码</el-button></div>
          </el-form>
        </div>

        <div class="pv-card">
          <div class="pc-head">登录设备</div>
          <div class="pc-body device-body">
            <div class="device-copy">
              <span class="sec-icon"><Icon icon="ri:logout-box-r-line" /></span>
              <div class="sec-meta">
                <div class="sec-name">退出所有设备</div>
                <div class="text-2 sec-desc">吊销全部登录会话（含当前设备），适合账号异常或设备丢失时使用</div>
              </div>
            </div>
            <div class="sec-actions">
              <el-button type="danger" plain :loading="logoutAllLoading" @click="logoutAll">
                <Icon icon="ri:logout-box-r-line" class="sec-btn-ic" />退出所有设备
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <div class="pv-col">
        <div class="pv-card">
          <div class="pc-head">分享页</div>
          <div class="pc-body share-grid">
            <div v-if="auth.isAdmin" class="sg-card">
              <div class="sg-head">
                <span class="sg-icon"><Icon icon="ri:slideshow-3-line" /></span>
                <div class="sg-meta">
                  <div class="sg-name">经营数据大屏</div>
                  <div class="text-2 sg-desc">投屏 / 给合作方展示，不含金额</div>
                </div>
              </div>
              <div v-if="screenUrl" class="sg-link mono">{{ screenUrl }}</div>
              <div v-else class="sg-link text-2">加载中…</div>
              <div class="sg-actions">
                <el-button size="small" :disabled="!screenUrl" @click="openLink(screenUrl)">打开</el-button>
                <el-button size="small" type="primary" :disabled="!screenUrl" @click="copyLink(screenUrl, '大屏链接', 'screen')">
                  <Icon :icon="copiedKey === 'screen' ? 'ri:check-line' : 'ri:file-copy-line'" />
                  {{ copiedKey === 'screen' ? '已复制' : '复制链接' }}
                </el-button>
              </div>
            </div>

            <div class="sg-card">
              <div class="sg-head">
                <span class="sg-icon"><Icon icon="ri:trophy-line" /></span>
                <div class="sg-meta">
                  <div class="sg-name">代理业绩榜</div>
                  <div class="text-2 sg-desc">月度排行 + 按时交付星级，不含金额</div>
                </div>
              </div>
              <div v-if="rankUrl" class="sg-link mono">{{ rankUrl }}</div>
              <div v-else class="sg-link text-2">加载中…</div>
              <div class="sg-actions">
                <el-button size="small" :disabled="!rankUrl" @click="openLink(rankUrl)">打开</el-button>
                <el-button size="small" type="primary" :disabled="!rankUrl" @click="copyLink(rankUrl, '榜单链接', 'rank')">
                  <Icon :icon="copiedKey === 'rank' ? 'ri:check-line' : 'ri:file-copy-line'" />
                  {{ copiedKey === 'rank' ? '已复制' : '复制链接' }}
                </el-button>
              </div>
            </div>

            <div class="sg-card">
              <div class="sg-head">
                <span class="sg-icon"><Icon icon="ri:file-text-line" /></span>
                <div class="sg-meta">
                  <div class="sg-name">客户报价单</div>
                  <div class="text-2 sg-desc">各品质统一报价，仅代理价</div>
                </div>
              </div>
              <div v-if="quoteUrl" class="sg-link mono">{{ quoteUrl }}</div>
              <div v-else class="sg-link text-2">加载中…</div>
              <div class="sg-actions">
                <el-button size="small" :disabled="!quoteUrl" @click="openQuote">打开</el-button>
                <el-button size="small" type="primary" :disabled="!quoteUrl" @click="copyLink(quoteUrl, '报价单链接', 'quote')">
                  <Icon :icon="copiedKey === 'quote' ? 'ri:check-line' : 'ri:file-copy-line'" />
                  {{ copiedKey === 'quote' ? '已复制' : '复制链接' }}
                </el-button>
              </div>
            </div>

            <div class="sg-card">
              <div class="sg-head">
                <span class="sg-icon"><Icon icon="ri:code-s-slash-line" /></span>
                <div class="sg-meta">
                  <div class="sg-name">API 对接</div>
                  <div class="text-2 sg-desc">持 API Key 对接外部系统拉单与交付</div>
                </div>
              </div>
              <div class="sg-link text-2">Key 的查看与重置在「API 对接」页</div>
              <div class="sg-actions">
                <el-button size="small" @click="router.push('/api-docs')">前往 API 对接</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 开启两步验证：扫码 → 输入动态码确认 -->
  <el-dialog v-model="totpOpen" title="开启两步验证" width="min(430px, 92vw)" :close-on-click-modal="false" @closed="totpSetup = null">
    <div v-loading="totpLoading" class="tp-body">
      <template v-if="totpSetup">
        <div class="tp-qr-wrap">
          <img v-if="totpSetup.qr" :src="totpSetup.qr" alt="TOTP 二维码" />
        </div>
        <p class="text-2 tp-tip">使用 Google / Microsoft Authenticator 等认证器扫描二维码，或手动输入下方密钥</p>
        <div class="tp-secret">
          <span class="mono">{{ totpSetup.secret }}</span>
          <el-button size="small" text type="primary" @click="copySecret(totpSetup.secret)">复制</el-button>
        </div>
        <el-input
          v-model="totpCode" size="large" placeholder="输入 6 位动态码"
          maxlength="6" inputmode="numeric"
          @input="totpCode = String($event).replace(/\D/g, '')" @keyup.enter="confirmTotp"
        >
          <template #prefix><Icon icon="ri:shield-keyhole-line" class="tp-code-ic" /></template>
        </el-input>
        <div class="tp-actions">
          <el-button size="small" @click="totpOpen = false">取 消</el-button>
          <el-button type="primary" size="small" :loading="totpEnabling" @click="confirmTotp">确认开启</el-button>
        </div>
      </template>
      <div v-else class="tp-placeholder"></div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon } from '@iconify/vue'
import http from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const saving = ref(false)
const form = reactive({ old_password: '', new_password: '', confirm: '' })
const quoteToken = ref('')
const screenUrl = ref('')
const rankUrl = ref('')
const copiedKey = ref('')
const logoutAllLoading = ref(false)
let copiedTimer = null

// ===== 账号安全（TOTP 两步验证） =====
const totpEnabled = computed(() => !!auth.user?.totp_enabled)
const totpOpen = ref(false)
const totpLoading = ref(false)
const totpEnabling = ref(false)
const totpSetup = ref(null) // { secret, otpauth_uri, qr }
const totpCode = ref('')

async function openTotp() {
  totpCode.value = ''
  totpSetup.value = null
  totpOpen.value = true
  totpLoading.value = true
  try {
    totpSetup.value = await http.post('/auth/totp/setup')
  } catch {
    totpOpen.value = false
  } finally {
    totpLoading.value = false
  }
}

async function confirmTotp() {
  if (!/^\d{6}$/.test(totpCode.value)) {
    ElMessage.warning('请输入 6 位动态码')
    return
  }
  totpEnabling.value = true
  try {
    await http.post('/auth/totp/enable', { code: totpCode.value })
    auth.user.totp_enabled = true
    totpOpen.value = false
    ElMessage.success('两步验证已开启，下次登录需输入动态码')
  } catch { /* 拦截器处理 */ } finally {
    totpEnabling.value = false
  }
}

async function disableTotp() {
  let password
  try {
    const { value } = await ElMessageBox.prompt('为确认是本人操作，请输入登录密码', '关闭两步验证', {
      confirmButtonText: '确认关闭',
      cancelButtonText: '取 消',
      inputType: 'password',
      inputPlaceholder: '登录密码',
      inputValidator: (v) => (v && v.trim() ? true : '请输入登录密码'),
    })
    password = value.trim()
  } catch {
    return
  }
  totpLoading.value = true
  try {
    await http.post('/auth/totp/disable', { password })
    auth.user.totp_enabled = false
    ElMessage.success('两步验证已关闭')
  } catch { /* 拦截器处理 */ } finally {
    totpLoading.value = false
  }
}

async function copySecret(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('密钥已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}

const quoteUrl = computed(() => (quoteToken.value ? `${window.location.origin}/quote/${quoteToken.value}` : ''))
const lastLogin = computed(() =>
  auth.user?.last_login_at ? String(auth.user.last_login_at).replace('T', ' ').slice(0, 16) : '本次会话首次登录')
const permText = computed(() => ({
  admin: '全部数据与真实价',
  staff: '全部订单，无价格数据',
  agent: '自己名下的订单',
}[auth.user?.role] || '-'))

async function copyLink(url, name, key) {
  try {
    await copyText(url)
    copiedKey.value = key
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copiedKey.value = '' }, 1800)
    ElMessage.success(`${name}已复制`)
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

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

// ===== 退出所有设备 =====
async function logoutAll() {
  try {
    await ElMessageBox.confirm(
      '退出后所有设备（含当前设备）的登录会话将立即失效，需要重新登录。确定继续吗？',
      '退出所有设备',
      { confirmButtonText: '退出所有设备', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return
  }
  logoutAllLoading.value = true
  try {
    await http.post('/auth/logout-all')
    ElMessage.success('已退出所有设备，请重新登录')
    await auth.logout()
  } catch {
    logoutAllLoading.value = false
  }
}

function openLink(url) {
  window.open(url, '_blank')
}

function openQuote() {
  window.open(`/quote/${quoteToken.value}`, '_blank')
}

async function submit() {
  if (!form.old_password || !form.new_password) return ElMessage.warning('请填写完整')
  if (form.new_password.length < 6) return ElMessage.warning('新密码至少 6 位')
  if (form.new_password !== form.confirm) return ElMessage.warning('两次输入的新密码不一致')
  saving.value = true
  try {
    await http.post('/auth/change-password', {
      old_password: form.old_password, new_password: form.new_password,
    })
    form.old_password = form.new_password = form.confirm = ''
    ElMessage.success('密码已修改，所有设备需重新登录')
    // 后端已吊销全部会话（token_version +1），前端同步退出
    await auth.logout()
  } catch {
    // 错误文案由 axios 拦截器统一提示（旧密码错误等），这里只保证不抛出未处理的 rejection
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const data = await http.get('/quote/link')
    quoteToken.value = data.token
  } catch { /* 拦截器处理 */ }
  if (auth.isAdmin) {
    try {
      const data = await http.get('/screen/link')
      screenUrl.value = `${window.location.origin}/screen/${data.token}`
    } catch { /* 忽略 */ }
  }
  try {
    const data = await http.get('/rank/link')
    rankUrl.value = `${window.location.origin}/rank/${data.token}`
  } catch { /* 忽略 */ }
})

onBeforeUnmount(() => clearTimeout(copiedTimer))
</script>

<style scoped>
.profile-view {
  display: flex; flex-direction: column; gap: var(--content-gap);
  width: 100%;
}

/* ===== 顶部个人横幅：渐变封面 + 头像压边 + 信息内联 ===== */
.pv-banner {
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--card);
  animation: rise-in 0.42s cubic-bezier(0.4, 0, 0.2, 1) both;
}
.pv-cover {
  position: relative;
  height: 162px;
  display: flex; flex-direction: column; align-items: flex-start;
  padding: 20px 24px;
  background:
    radial-gradient(420px 150px at 18% 0%, color-mix(in srgb, var(--brand) 46%, transparent), transparent 62%),
    radial-gradient(460px 170px at 78% 15%, color-mix(in srgb, var(--purple) 34%, transparent), transparent 62%),
    linear-gradient(135deg, var(--card-3), var(--card-2));
}
.pv-banner-body {
  position: relative; z-index: 1;
  display: flex; flex-direction: column;
  padding: 16px 24px 22px;
}
.pv-sec-pill {
  position: absolute; top: 18px; right: 24px;
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 12px 6px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 600; letter-spacing: 0.01em;
  border: 1px solid transparent;
  backdrop-filter: blur(10px) saturate(1.1);
  -webkit-backdrop-filter: blur(10px) saturate(1.1);
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.pv-sec-pill-ic { font-size: 14px; }
.pv-sec-pill.off {
  color: color-mix(in srgb, var(--warning) 72%, #ffd48a);
  background: color-mix(in srgb, var(--warning-weak) 86%, var(--glass));
  border-color: color-mix(in srgb, var(--warning) 34%, transparent);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.16);
}
.pv-sec-pill.on {
  color: var(--success);
  background: color-mix(in srgb, var(--success-weak) 86%, var(--glass));
  border-color: color-mix(in srgb, var(--success) 32%, transparent);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
}
:global(html.light .pv-sec-pill.off) {
  color: #9a5b00;
  background: rgba(255, 174, 31, 0.16);
  border-color: rgba(180, 110, 0, 0.28);
  box-shadow: none;
}
:global(html.light .pv-sec-pill.on) {
  color: #0b8f78;
  background: rgba(19, 222, 185, 0.12);
  border-color: rgba(11, 143, 120, 0.24);
  box-shadow: none;
}
.pv-avatar {
  width: 68px; height: 68px; border-radius: 50%;
  background: var(--brand-grad); color: #fff;
  font-size: 28px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  border: 3px solid var(--card);
  box-shadow: var(--brand-glow);
}
.pv-name-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; width: 100%; margin-top: auto; padding-top: 12px; }
.pv-name { margin: 0; font-size: 19px; font-weight: 700; }
.pv-role-tag {
  font-size: 12px; padding: 2px 12px; border-radius: 999px;
  background: var(--brand-weak); color: var(--brand); font-weight: 600;
}
.pv-info-row { display: flex; align-items: center; gap: 22px; flex-wrap: wrap; }
.pi-item {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 12.5px; color: var(--text-2);
}
.pi-icon { font-size: 13px; color: var(--text-3); }

/* ===== 双列 ===== */
.pv-grid {
  display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  gap: 20px; align-items: start;
}
.pv-col { display: flex; flex-direction: column; gap: 20px; min-width: 0; }

.pv-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  animation: rise-in 0.42s cubic-bezier(0.4, 0, 0.2, 1) both;
}
.pv-col:nth-child(2) .pv-card { animation-delay: 0.06s; }

/* 右侧卡：统一头/体 */
.pc-head {
  padding: 14px 20px; font-size: 15px; font-weight: 600;
  color: var(--text);
  border-bottom: 1px solid var(--border);
  background: var(--card-2);
}
.pc-body { padding: 18px 20px; }

/* 账号安全（TOTP）卡 */
.sec-body { display: flex; flex-direction: column; gap: 14px; }
.sec-main { display: flex; align-items: center; gap: 14px; }
.sec-icon {
  width: 42px; height: 42px; border-radius: 10px; flex-shrink: 0;
  background: var(--hover); color: var(--text-2); font-size: 19px;
  display: flex; align-items: center; justify-content: center;
}
.sec-icon.on { background: var(--success-weak); color: var(--success); }
.sec-meta { flex: 1; min-width: 0; }
.sec-name { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.sec-desc { font-size: 12px; line-height: 1.6; }
.sec-actions { display: flex; justify-content: flex-end; }
.sec-btn-ic { font-size: 15px; margin-right: 4px; }

/* 登录设备 */
.device-body { display: flex; flex-direction: column; gap: 14px; }
.device-copy { display: flex; align-items: center; gap: 14px; }

/* 开启两步验证弹窗 */
.tp-body { min-height: 120px; }
.tp-placeholder { height: 120px; }
.tp-qr-wrap {
  width: fit-content; margin: 0 auto 14px; padding: 10px;
  background: #fff; border: 1px solid var(--border); border-radius: 12px;
}
.tp-qr-wrap img { width: 168px; height: 168px; display: block; }
.tp-tip { font-size: 12px; line-height: 1.7; text-align: center; margin: 0 0 12px; }
.tp-secret {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 8px 8px 8px 12px; margin-bottom: 14px;
  background: var(--card-2); border: 1px solid var(--border); border-radius: 8px;
}
.tp-secret span { font-size: 13px; font-weight: 600; letter-spacing: 1px; color: var(--brand); }
.tp-body :deep(.el-input .el-input__inner) { letter-spacing: 6px; font-weight: 600; text-align: center; }
.tp-code-ic { font-size: 16px; color: var(--text-2); }
.tp-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

/* 密码表单：原密码整行 + 新密码两列，按钮右对齐 */
.pc-form :deep(.el-form-item) { margin-bottom: 14px; }
.pf-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0 16px; }
.pf-extra { font-size: 12px; line-height: 1.6; margin-top: 4px; }
.pf-actions { display: flex; justify-content: flex-end; }

/* 分享页：卡片网格（2 列） */
.share-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
.sg-card {
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 14px; display: flex; flex-direction: column; gap: 10px;
  background: var(--card-2); transition: border-color 0.15s, transform 0.15s;
}
.sg-card:hover { border-color: var(--border-3); transform: translateY(-2px); }
.sg-head { display: flex; align-items: flex-start; gap: 11px; min-height: 52px; }
.sg-icon {
  width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0;
  background: var(--brand-weak); color: var(--brand); font-size: 17px;
  display: flex; align-items: center; justify-content: center;
}
.sg-meta { flex: 1; min-width: 0; }
.sg-name { font-size: 13.5px; font-weight: 600; margin-bottom: 3px; }
.sg-desc { font-size: 11.5px; line-height: 1.55; }
.sg-link {
  flex: 1; padding: 7px 10px;
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  font-size: 11px; word-break: break-all; color: var(--brand);
  display: flex; align-items: center; min-height: 34px;
}
.sg-actions { display: flex; justify-content: flex-end; gap: 8px; }

@media (max-width: 960px) {
  .pv-grid { grid-template-columns: 1fr; }
  .share-grid { grid-template-columns: 1fr; }
  .pv-info-row { gap: 12px; }
}
@media (max-width: 640px) {
  .pf-grid { grid-template-columns: 1fr; }
  .pv-banner-body { padding: 14px 16px 18px; }
  .pv-cover { height: 132px; padding: 14px 16px; }
  .pv-avatar { width: 56px; height: 56px; font-size: 22px; }
  .pv-name { font-size: 17px; }
  .pv-name-row { gap: 8px; padding-top: 10px; }
  .pv-sec-pill { top: 12px; right: 16px; gap: 6px; padding: 5px 10px 5px 8px; font-size: 11.5px; }
  .pv-sec-pill-ic { font-size: 13px; }
  .pv-info-row { gap: 10px 14px; }
  .pc-head { padding: 13px 16px; font-size: 14.5px; }
  .pc-body { padding: 15px 16px; }
  .sec-body { gap: 12px; }
  .sec-main, .device-copy { align-items: flex-start; }
  .sec-actions { justify-content: stretch; }
  .sec-actions :deep(.el-button) { width: 100%; }
  .sg-card { padding: 13px; }
  .sg-actions { flex-wrap: wrap; }
  .sg-actions :deep(.el-button) { flex: 1; }
  .tp-secret span { font-size: 12px; letter-spacing: 0.5px; }
}
</style>
