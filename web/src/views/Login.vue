<template>
  <div class="login-page">
    <!-- 两个动态光斑 + 网格底纹 -->
    <div class="glow g1" aria-hidden="true" />
    <div class="glow g2" aria-hidden="true" />
    <div class="grid-bg" aria-hidden="true" />

    <button
      type="button"
      class="theme-toggle"
      :title="themeStore.isDark ? '切换到亮色' : '切换到暗色'"
      :aria-label="themeStore.isDark ? '切换到亮色' : '切换到暗色'"
      @click="themeStore.toggle($event)"
    >
      <Icon :icon="themeStore.isDark ? 'ri:sun-line' : 'ri:moon-line'" />
    </button>

    <div class="login-card">
      <div class="card-glow" aria-hidden="true" />
      <div class="card-head">
        <div class="logo">{{ logoText }}</div>
        <h1 class="title">{{ displayName }}</h1>
        <p class="subtitle">论文毕设接单 · 订单 · 需求书 一站式管理</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" size="large" class="login-form" @submit.prevent>
        <!-- 两步验证提示（第二步时显示） -->
        <transition name="fade">
          <p v-if="totpRequired" class="totp-tip">
            <Icon icon="ri:shield-check-line" />
            已开启两步验证，请输入认证器动态码
          </p>
        </transition>

        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            clearable
            autocomplete="username"
            :disabled="totpRequired"
            @keyup.enter="onLogin"
          >
            <template #prefix><Icon icon="ri:user-3-line" class="login-ic" /></template>
          </el-input>
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="密码"
            autocomplete="current-password"
            :disabled="totpRequired"
            @keyup.enter="onLogin"
          >
            <template #prefix><Icon icon="ri:lock-2-line" class="login-ic" /></template>
          </el-input>
        </el-form-item>

        <el-form-item v-if="totpRequired" class="totp-item">
          <el-input
            ref="totpInputRef"
            v-model="totpCode"
            placeholder="动态验证码（6 位）"
            maxlength="6"
            inputmode="numeric"
            autocomplete="one-time-code"
            @input="totpCode = String($event).replace(/\D/g, '')"
            @keyup.enter="onLogin"
          >
            <template #prefix><Icon icon="ri:shield-keyhole-line" class="login-ic" /></template>
          </el-input>
        </el-form-item>

        <div class="login-options">
          <el-checkbox v-model="remember">记住用户名</el-checkbox>
          <span class="secure-hint"><Icon icon="ri:shield-keyhole-line" />仅保存用户名</span>
        </div>

        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="onLogin">
          {{ totpRequired ? '验 证' : '登 录' }}
        </el-button>
      </el-form>

      <div class="card-foot">
        <span>管理员 · 写手 · 代理</span>
        <span class="dot" />
        <span>价格数据隔离</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'

import http from '../api'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'

const REMEMBER_KEY = 'bs-remember-username'
const DEFAULT_SITE_NAME = '毕设接单管理系统'

const auth = useAuthStore()
const themeStore = useThemeStore()
const router = useRouter()

const loading = ref(false)
const siteName = ref('')
const formRef = ref(null)
const form = reactive({ username: '', password: '' })

const displayName = computed(() => siteName.value.trim() || DEFAULT_SITE_NAME)
const logoText = computed(() => Array.from(displayName.value)[0] || '')

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

// TOTP 两步验证：第一步密码正确但账号已开启动态码时，切换出第二步输入框
const totpRequired = ref(false)
const totpCode = ref('')
const totpInputRef = ref(null)

const remember = ref(false)

function loadRememberedUsername() {
  const saved = localStorage.getItem(REMEMBER_KEY)
  if (!saved) return
  form.username = saved
  remember.value = true
}

function persistUsername() {
  const name = form.username.trim()
  if (remember.value && name) localStorage.setItem(REMEMBER_KEY, name)
  else localStorage.removeItem(REMEMBER_KEY)
}

async function onLogin() {
  if (loading.value) return
  if (totpRequired.value && !/^\d{6}$/.test(totpCode.value)) {
    ElMessage.warning('请输入 6 位动态验证码')
    return
  }
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const data = await auth.login(form.username.trim(), form.password, totpCode.value)
    if (data.totp_required) {
      totpRequired.value = true
      totpCode.value = ''
      await nextTick()
      totpInputRef.value?.focus()
      return
    }
    persistUsername()
    router.push('/')
  } catch (error) {
    // 拦截器对公开页的 401 静默，登录页需自行提示凭据/动态码错误
    if (error?.response?.status === 401) {
      const detail = error.response?.data?.detail
      ElMessage.error(typeof detail === 'string' ? detail : '用户名或密码错误')
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  loadRememberedUsername()
  document.title = `${DEFAULT_SITE_NAME} · 登录`
  try {
    // 公开配置：无需登录即可读取站点名
    const data = await http.get('/settings/public')
    siteName.value = data?.site_name || ''
  } catch {
    /* 配置读取失败不阻塞登录 */
  }
  document.title = `${displayName.value} · 登录`
})
</script>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(16px, 4vw, 32px);
  overflow: hidden;
  background:
    radial-gradient(1100px 560px at 12% -12%, var(--brand-weak), transparent 62%),
    radial-gradient(900px 520px at 108% 112%, color-mix(in srgb, var(--purple) 12%, transparent), transparent 65%),
    var(--bg);
}

/* ===== 动态背景 ===== */
.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.42;
  pointer-events: none;
  will-change: transform;
  animation: login-float 12s ease-in-out infinite alternate;
}
.g1 {
  width: min(480px, 62vw); height: min(480px, 62vw);
  left: -12%; top: -18%;
  background: color-mix(in srgb, var(--brand) 34%, transparent);
}
.g2 {
  width: min(400px, 54vw); height: min(400px, 54vw);
  right: -10%; bottom: -20%;
  background: color-mix(in srgb, var(--purple) 28%, transparent);
  animation-delay: -5s;
}
@keyframes login-float {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(36px, 30px, 0) scale(1.08); }
}

.grid-bg {
  position: absolute; inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(color-mix(in srgb, var(--text) 4%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--text) 4%, transparent) 1px, transparent 1px);
  background-size: 46px 46px;
  -webkit-mask-image: radial-gradient(ellipse at center, #000 24%, transparent 74%);
  mask-image: radial-gradient(ellipse at center, #000 24%, transparent 74%);
}

/* ===== 主题切换 ===== */
.theme-toggle {
  position: fixed; top: 18px; right: 18px; z-index: 5;
  width: 40px; height: 40px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-2);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--card) 72%, transparent);
  backdrop-filter: blur(12px);
  color: var(--text-2); font-size: 18px; cursor: pointer;
  transition: color 0.18s ease, border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}
.theme-toggle:hover {
  color: var(--brand);
  border-color: var(--brand);
  background: var(--brand-weak);
  transform: translateY(-1px);
}
.theme-toggle:active { transform: translateY(0) scale(0.96); }

/* ===== 玻璃卡 ===== */
.login-card {
  position: relative;
  width: 100%;
  max-width: 410px;
  padding: 40px 36px 26px;
  border: 1px solid var(--border-2);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--card) 78%, transparent);
  box-shadow: var(--shadow-pop), inset 0 1px 0 color-mix(in srgb, #fff 6%, transparent);
  backdrop-filter: blur(18px) saturate(1.2);
  -webkit-backdrop-filter: blur(18px) saturate(1.2);
  animation: rise-in 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
/* art 玻璃描边 */
.login-card::before {
  content: '';
  position: absolute; inset: 0;
  padding: 1px;
  border-radius: inherit;
  background: linear-gradient(
    150deg,
    color-mix(in srgb, var(--brand) 48%, transparent),
    transparent 36%,
    transparent 64%,
    color-mix(in srgb, var(--purple) 34%, transparent)
  );
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}
.card-glow {
  position: absolute; left: -1px; right: -1px; top: -1px; height: 150px;
  border-radius: var(--radius-xl) var(--radius-xl) 50% 50%;
  background: radial-gradient(ellipse at 50% -28%, var(--brand-weak-2), transparent 72%);
  pointer-events: none;
}

.card-head { position: relative; text-align: center; margin-bottom: 24px; }
.logo {
  width: 58px; height: 58px; margin: 0 auto 15px;
  border-radius: 18px;
  display: flex; align-items: center; justify-content: center;
  background: var(--brand-grad);
  color: #fff; font-size: 25px; font-weight: 700;
  box-shadow: var(--brand-glow), inset 0 1px 0 rgba(255, 255, 255, 0.35);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.login-card:hover .logo { transform: translateY(-2px) rotate(-3deg); }
.title { margin: 0 0 6px; font-size: 20px; font-weight: 700; color: var(--text); letter-spacing: 0.01em; }
.subtitle { margin: 0; font-size: 12.5px; color: var(--text-3); }

.login-form { position: relative; }
.login-ic { font-size: 16px; color: var(--text-3); }

.login-options {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin: -2px 0 16px;
}
.login-options :deep(.el-checkbox) { height: 24px; }
.login-options :deep(.el-checkbox__label) { color: var(--text-3); font-size: 12.5px; }
.login-options :deep(.el-checkbox__inner) { border-radius: 4px; }
.secure-hint { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-4); }
.secure-hint .iconify { font-size: 12px; }

/* ===== 两步验证 ===== */
.totp-tip {
  display: flex; align-items: center; gap: 6px;
  margin: 0 0 14px; padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--success) 28%, transparent);
  border-radius: var(--radius-sm);
  background: var(--success-weak);
  color: var(--success); font-size: 12.5px; font-weight: 500;
}
.totp-item { animation: rise-in 0.3s ease both; }
.totp-item :deep(.el-input__inner) { letter-spacing: 6px; font-weight: 600; text-align: center; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ===== 主按钮 ===== */
.login-btn {
  width: 100%; height: 46px; margin-top: 2px;
  border: none; border-radius: var(--radius-md);
  background: var(--brand-grad);
  color: #fff; font-size: 15px; font-weight: 600;
  letter-spacing: 0.24em; text-indent: 0.24em;
  box-shadow: var(--brand-glow);
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
}
.login-btn:hover {
  background: var(--brand-grad) !important;
  transform: translateY(-2px);
  box-shadow: 0 14px 34px color-mix(in srgb, var(--brand) 42%, transparent);
  filter: brightness(1.05);
}
.login-btn:active { transform: translateY(0); filter: brightness(0.98); }

.card-foot {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  margin-top: 22px; font-size: 11.5px; color: var(--text-3);
}
.dot { width: 3px; height: 3px; border-radius: 50%; background: var(--text-4); }

@media (prefers-reduced-motion: reduce) {
  .glow, .login-card, .totp-item { animation: none; }
}

@media (max-width: 480px) {
  .login-page { padding: 16px; }
  .login-card { padding: 32px 22px 22px; border-radius: var(--radius-lg); }
  .title { font-size: 17.5px; }
  .subtitle { font-size: 12px; }
  .theme-toggle { top: 12px; right: 12px; width: 36px; height: 36px; font-size: 16px; }
  .glow { filter: blur(70px); }
  .secure-hint { display: none; }
}
</style>
