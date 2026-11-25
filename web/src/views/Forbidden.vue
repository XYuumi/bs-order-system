<template>
  <div class="fb-page">
    <div class="fb-card rise-in">
      <div class="fb-art" aria-hidden="true">
        <Icon icon="ri:shield-keyhole-line" />
        <span class="fb-ring"></span>
      </div>
      <h1 class="fb-title">没有访问权限</h1>
      <p class="fb-desc">
        当前账号的角色<strong class="fb-role">{{ auth.roleName }}</strong>无权查看该页面。
        如需开通，请联系管理员调整账号角色。
      </p>
      <p v-if="from" class="fb-from">来源：<code>{{ from }}</code></p>
      <div class="fb-actions">
        <el-button type="primary" size="large" @click="goHome">
          <el-icon><Icon icon="ri:dashboard-line" /></el-icon>
          <span>回到工作台</span>
        </el-button>
        <el-button size="large" @click="goBack">返回上一页</el-button>
      </div>
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

const from = computed(() => {
  const raw = String(route.query.from || '')
  return raw.length > 80 ? raw.slice(0, 80) + '…' : raw
})

function goHome() {
  router.replace('/')
}

function goBack() {
  if (window.history.length > 1) router.back()
  else goHome()
}
</script>

<style scoped>
.fb-page {
  display: grid;
  place-items: center;
  min-height: calc(100vh - 220px);
  padding: 24px 16px;
}

.fb-card {
  width: min(520px, 100%);
  padding: 36px 30px 30px;
  text-align: center;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--card-2);
  box-shadow: var(--shadow-lg);
}

.fb-art {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 96px;
  height: 96px;
  margin-bottom: 14px;
  border-radius: 50%;
  font-size: 42px;
  color: var(--brand);
  background: color-mix(in srgb, var(--brand) 12%, transparent);
}

.fb-ring {
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 1px dashed color-mix(in srgb, var(--brand) 45%, transparent);
  animation: art-rotate 12s linear infinite;
}

.fb-title {
  margin: 0 0 10px;
  font-size: var(--fs-2xl, 24px);
  font-weight: 700;
  color: var(--text);
}

.fb-desc {
  margin: 0 0 8px;
  font-size: var(--fs-sm, 13px);
  line-height: 1.8;
  color: var(--text-3);
}

.fb-role {
  margin: 0 4px;
  color: var(--brand);
}

.fb-from {
  margin: 0 0 20px;
  font-size: 12px;
  color: var(--text-4);
  word-break: break-all;
}

.fb-from code {
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--card-3);
  color: var(--text-2);
}

.fb-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}

@media (max-width: 520px) {
  .fb-card { padding: 28px 18px 22px; }
  .fb-art { width: 78px; height: 78px; font-size: 34px; }
}
</style>
