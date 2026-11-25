<template>
  <span
    class="status-tag"
    :class="{ working: status === 'in_progress' || status === 'after_sale' }"
    :style="{ color: meta.hex, background: meta.hex + '16', borderColor: meta.hex + '3d' }"
  >
    <span class="pulse" :style="{ background: meta.hex }" />{{ meta.label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { deployMeta, statusMeta } from '../constants/orderMeta'

const props = defineProps({
  status: { type: String, default: '' },
  kind: { type: String, default: 'order' },
})

const meta = computed(() => (props.kind === 'deploy' ? deployMeta(props.status) : statusMeta(props.status)))
</script>

<style scoped>
.status-tag {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 1px 8px; border-radius: 6px; border: 1px solid;
  font-size: 11.5px; font-weight: 500; white-space: nowrap; line-height: 19px;
}
.pulse { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.status-tag.working .pulse { animation: status-pulse 1.8s ease-in-out infinite; }
@keyframes status-pulse {
  0%, 100% { opacity: 0.55; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.25); }
}
</style>
