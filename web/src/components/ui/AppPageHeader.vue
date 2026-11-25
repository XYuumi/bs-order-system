<template>
  <div class="app-page-header">
    <div class="ph-left">
      <div v-if="icon" class="ph-icon" :style="{ background: iconBg, color: iconColor }">
        <Icon :icon="icon" />
      </div>
      <div class="ph-copy">
        <div class="ph-title-row">
          <h1 class="ph-title">{{ title }}</h1>
          <slot name="badge" />
        </div>
        <p v-if="description" class="ph-desc">{{ description }}</p>
      </div>
    </div>
    <div v-if="$slots.actions" class="ph-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  icon: { type: String, default: '' },
  iconColor: { type: String, default: 'var(--brand)' },
  iconBg: { type: String, default: 'var(--brand-weak)' },
})
</script>

<style scoped>
.app-page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  min-width: 0;
}
.ph-left { display: flex; align-items: center; gap: 14px; min-width: 0; }
.ph-icon {
  width: 44px; height: 44px; flex-shrink: 0;
  border-radius: var(--radius);
  display: flex; align-items: center; justify-content: center;
  font-size: 22px;
  box-shadow: inset 0 0 0 1px var(--border);
}
.ph-copy { min-width: 0; }
.ph-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ph-title { margin: 0; font-size: 20px; font-weight: 650; letter-spacing: 0.01em; color: var(--text); }
.ph-desc { margin: 3px 0 0; font-size: 12.5px; color: var(--text-3); }
.ph-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
@media (max-width: 640px) {
  .ph-icon { width: 38px; height: 38px; font-size: 19px; border-radius: var(--radius-sm); }
  .ph-title { font-size: 18px; }
}
</style>
