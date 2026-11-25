<template>
  <div class="table-toolbar">
    <div class="tt-left">
      <slot name="left" />
    </div>
    <div class="tt-right">
      <span v-if="count != null" class="tt-count">{{ count }} 条</span>
      <slot name="right" />
      <button v-if="refreshable" class="tt-btn art-hover-rotate" title="刷新" @click="$emit('refresh')">
        <Icon icon="ri:refresh-line" :class="{ spin: loading }" />
      </button>
      <slot name="after" />
    </div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  count: { type: [Number, String], default: null },
  refreshable: { type: Boolean, default: true },
  loading: { type: Boolean, default: false },
})
defineEmits(['refresh'])
</script>

<style scoped>
.table-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.tt-left, .tt-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tt-count { font-size: 12px; color: var(--text-3); padding: 2px 9px; border-radius: 999px; background: var(--card-2); border: 1px solid var(--border); }
.tt-btn {
  width: 32px; height: 32px; border: 1px solid var(--border); background: var(--card-2);
  border-radius: var(--radius-xs); color: var(--text-2); cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center; font-size: 15px;
  transition: all 0.15s;
}
.tt-btn:hover { color: var(--brand); border-color: var(--brand); background: var(--brand-weak); }
.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
