<template>
  <span class="quality-badge" :style="{ color, background: `${color}16`, borderColor: `${color}4d` }">
    <span class="q-dot" :style="{ background: color }" />
    {{ name }}
  </span>
</template>

<script setup>
defineProps({
  name: { type: String, default: '' },
  color: { type: String, default: '#9ca3af' },
})
</script>

<style scoped>
.quality-badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 1px 8px; border-radius: 6px; border: 1px solid;
  font-size: 11.5px; font-weight: 500; white-space: nowrap; line-height: 19px;
}
.q-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
</style>
