<template>
  <div class="settings-shell">
    <AppPageHeader :title="title" :description="description" :icon="icon" :icon-color="iconColor" :icon-bg="iconBg">
      <template v-if="$slots.actions" #actions>
        <slot name="actions" />
      </template>
    </AppPageHeader>

    <nav class="settings-subnav" aria-label="设置导航">
      <router-link
        v-for="item in tabs"
        :key="item.path"
        :to="item.path"
        class="settings-tab"
        :class="{ active: isActive(item.path) }"
        :aria-current="isActive(item.path) ? 'page' : undefined"
      >
        <Icon :icon="item.icon" />
        <span>{{ item.label }}</span>
      </router-link>
    </nav>

    <div v-loading="loading" class="settings-body page-card">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import AppPageHeader from './AppPageHeader.vue'

defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  icon: { type: String, default: 'ri:settings-3-line' },
  iconColor: { type: String, default: 'var(--brand)' },
  iconBg: { type: String, default: 'var(--brand-weak)' },
  loading: { type: Boolean, default: false },
})

const tabs = [
  { path: '/settings/general', label: '通用', icon: 'ri:settings-4-line' },
  { path: '/settings/pricing', label: '价格与品质', icon: 'ri:price-tag-3-line' },
  { path: '/settings/ai', label: 'AI 中心', icon: 'ri:robot-2-line' },
  { path: '/settings/integration', label: '集成通知', icon: 'ri:webhook-line' },
  { path: '/settings/security', label: '安全', icon: 'ri:shield-check-line' },
  { path: '/settings/backup', label: '数据备份', icon: 'ri:database-2-line' },
]

const route = useRoute()
const currentPath = computed(() => (route.path || '').replace(/\/+$/, ''))

function isActive(path) {
  return currentPath.value === path
}
</script>

<style scoped>
.settings-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  max-width: var(--settings-max);
  margin-inline: auto;
  min-width: 0;
}

/* 顶部设置子导航：移动端横向滚动 */
.settings-subnav {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
  -webkit-overflow-scrolling: touch;
}
.settings-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex: 0 0 auto;
  height: 36px;
  padding: 0 14px;
  border-radius: var(--radius-sm);
  color: var(--text-2);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}
.settings-tab .iconify { font-size: 16px; }
.settings-tab:hover { background: var(--hover); color: var(--text); }
.settings-tab.active { background: var(--brand-weak); color: var(--brand); font-weight: 600; }

/* 统一内容容器；整页由 .settings-shell 控制宽屏阅读宽度 */
.settings-body {
  width: 100%;
  min-height: 160px;
  padding: 22px;
  min-width: 0;
}

/* 分节与表单的共享骨架，供六个设置页复用（slot 内容） */
.settings-body :deep(.settings-stack) {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.settings-body :deep(.settings-section) {
  min-width: 0;
  padding: 18px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.settings-body :deep(.settings-section-head) {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.settings-body :deep(.settings-section-title) {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.01em;
}
.settings-body :deep(.settings-section-desc) {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.6;
}
.settings-body :deep(.settings-head-actions) {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.settings-body :deep(.settings-hint) {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.65;
}
.settings-body :deep(.settings-actions) {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 16px;
}

/* 宽屏：设置卡片两列排布，避免整页表单被拉成超长单列 */
@media (min-width: 1800px) {
  .settings-body > :deep(.settings-stack:not(.settings-stack-ai)) {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 20px;
    align-items: start;
  }
  .settings-body > :deep(.settings-stack:not(.settings-stack-ai)) > .settings-section:last-child:nth-child(odd) {
    grid-column: 1 / -1;
  }
}

@media (min-width: 2200px) {
  .settings-shell { gap: 20px; }
  .settings-subnav { padding: 5px; gap: 6px; }
  .settings-tab { height: 42px; padding: 0 18px; font-size: 14px; }
  .settings-tab .iconify { font-size: 18px; }
  .settings-body { padding: 28px; }
}

@media (min-width: 3000px) {
  .settings-shell { gap: 24px; }
  .settings-subnav { padding: 6px; gap: 8px; }
  .settings-tab { height: 48px; padding: 0 22px; font-size: 15.5px; }
  .settings-tab .iconify { font-size: 20px; }
  .settings-body { padding: 34px; }
}

@media (max-width: 768px) {
  .settings-shell { gap: 12px; }
  .settings-body { padding: 14px; }
  .settings-tab { height: 32px; padding: 0 11px; font-size: 12.5px; }
  .settings-body :deep(.settings-section) { padding: 14px; }
  .settings-body :deep(.settings-section-head) { margin-bottom: 12px; }
  .settings-body :deep(.settings-actions) { margin-top: 12px; }
}
</style>
