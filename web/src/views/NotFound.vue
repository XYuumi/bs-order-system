<template>
  <div class="nf-page">
    <div class="nf-glow" aria-hidden="true"></div>
    <div class="nf-card rise-in">
      <div class="nf-art" aria-hidden="true">
        <span class="nf-digit">4</span>
        <span class="nf-orbit">
          <span class="nf-dot"></span>
        </span>
        <span class="nf-digit">4</span>
      </div>
      <h1 class="nf-title">页面走丢了</h1>
      <p class="nf-desc">
        你访问的地址不存在，或者已被改名、删除。
        <code class="nf-path">{{ path }}</code>
      </p>
      <div class="nf-actions">
        <el-button type="primary" size="large" @click="goHome">
          <el-icon><Icon icon="ri:home-4-line" /></el-icon>
          <span>{{ auth.user ? '回到工作台' : '前往登录' }}</span>
        </el-button>
        <el-button size="large" @click="goBack">返回上一页</el-button>
      </div>
      <p class="nf-hint">如果是系统内的链接失效，请联系管理员检查对应模块。</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const path = computed(() => route.fullPath.slice(0, 80))

function goHome() {
  router.replace(auth.user ? '/' : '/login')
}

function goBack() {
  if (window.history.length > 1) router.back()
  else goHome()
}
</script>

<style scoped>
.nf-page {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 20px;
  background: var(--bg, #070707);
  overflow: hidden;
}

.nf-glow {
  position: absolute;
  width: 560px;
  height: 560px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--brand-weak, rgba(67, 97, 238, 0.18)), transparent 68%);
  filter: blur(6px);
  animation: art-breathe 7s ease-in-out infinite;
}

.nf-card {
  position: relative;
  width: min(520px, 100%);
  padding: 40px 32px 32px;
  text-align: center;
  border-radius: var(--radius, 16px);
  border: 1px solid var(--border-2, rgba(255, 255, 255, 0.08));
  background: var(--card-2, rgba(22, 22, 24, 0.86));
  box-shadow: var(--shadow-lg, 0 24px 60px rgba(0, 0, 0, 0.35));
  backdrop-filter: blur(10px);
}

.nf-art {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 8px;
}

.nf-digit {
  font-size: 88px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -4px;
  background: linear-gradient(135deg, var(--brand, #4361ee), var(--brand-2, #7c5cff));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.nf-orbit {
  position: relative;
  width: 74px;
  height: 74px;
  border-radius: 50%;
  border: 2px dashed var(--border-3, rgba(255, 255, 255, 0.16));
  animation: art-rotate 9s linear infinite;
}

.nf-dot {
  position: absolute;
  top: -5px;
  left: 50%;
  width: 9px;
  height: 9px;
  margin-left: -4.5px;
  border-radius: 50%;
  background: var(--brand, #4361ee);
  box-shadow: 0 0 12px var(--brand, #4361ee);
}

.nf-title {
  margin: 6px 0 10px;
  font-size: var(--fs-2xl, 26px);
  font-weight: 700;
  color: var(--text-1, #f4f4f5);
}

.nf-desc {
  margin: 0 0 22px;
  font-size: var(--fs-sm, 13px);
  line-height: 1.7;
  color: var(--text-3, #9a9aa5);
}

.nf-path {
  display: inline-block;
  max-width: 100%;
  margin-top: 6px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--card-3, rgba(255, 255, 255, 0.05));
  color: var(--text-2, #c9c9d1);
  font-size: 12px;
  word-break: break-all;
}

.nf-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}

.nf-hint {
  margin: 22px 0 0;
  font-size: 12px;
  color: var(--text-4, #6f6f7a);
}

@media (max-width: 520px) {
  .nf-digit { font-size: 64px; }
  .nf-orbit { width: 54px; height: 54px; }
  .nf-card { padding: 30px 20px 24px; }
}
</style>
