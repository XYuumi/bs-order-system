<template>
  <span v-if="projectType" class="pt-tag" :style="{ color: meta.hex, background: meta.hex + '14', borderColor: meta.hex + '3d' }">
    <span class="pt-icon">{{ meta.icon }}</span>{{ meta.label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { projectTypeMeta } from '../constants/orderMeta'

const props = defineProps({
  projectType: { type: String, default: '' },
})
const meta = computed(() => projectTypeMeta(props.projectType))
</script>

<style scoped>
.pt-tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 1px 8px; border-radius: 6px; border: 1px solid;
  font-size: 11.5px; font-weight: 500; white-space: nowrap; line-height: 19px;
}
.pt-icon { font-size: 11px; }
</style>
