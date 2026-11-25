<template>
  <div class="empty-state" :class="{ compact }">
    <div class="empty-icon" :style="{ color: tone }">
      <Icon :icon="icon" />
    </div>
    <div class="empty-title">{{ title }}</div>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <div v-if="$slots.default" class="empty-actions"><slot /></div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  icon: { type: String, default: 'ri:inbox-archive-line' },
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
  tone: { type: String, default: 'var(--text-3)' },
  compact: { type: Boolean, default: false },
})
</script>

<style scoped>
.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-align: center; padding: 48px 20px; min-height: 180px;
}
.empty-icon {
  width: 56px; height: 56px; border-radius: 18px;
  display: flex; align-items: center; justify-content: center;
  background: var(--card-2); border: 1px solid var(--border);
  font-size: 26px; margin-bottom: 14px;
}
.empty-title { font-size: 14px; font-weight: 600; color: var(--text); }
.empty-desc { margin: 6px 0 0; font-size: 12.5px; color: var(--text-3); max-width: 360px; line-height: 1.6; }
.empty-actions { margin-top: 16px; display: flex; gap: 8px; }
.empty-state.compact { padding: 24px 12px; min-height: 120px; }
.empty-state.compact .empty-icon { width: 44px; height: 44px; font-size: 21px; border-radius: 14px; margin-bottom: 10px; }
</style>
