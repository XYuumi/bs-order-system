<template>
  <div class="filter-bar">
    <div class="filter-fields"><slot /></div>
    <div class="filter-actions">
      <slot name="actions" />
      <el-button v-if="showSearch" type="primary" :loading="loading" @click="$emit('search')">
        <Icon icon="ri:search-line" /> 查询
      </el-button>
      <el-button v-if="showReset" @click="$emit('reset')">
        <Icon icon="ri:refresh-line" /> 重置
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  loading: { type: Boolean, default: false },
  showSearch: { type: Boolean, default: true },
  showReset: { type: Boolean, default: true },
})
defineEmits(['search', 'reset'])
</script>

<style scoped>
.filter-bar {
  display: flex; align-items: flex-end; justify-content: space-between; gap: 14px; flex-wrap: wrap;
  padding: 14px 16px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
.filter-fields { display: flex; align-items: flex-end; gap: 10px; flex-wrap: wrap; flex: 1; min-width: 0; }
.filter-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.filter-fields :deep(.el-form-item) { margin: 0; }
.filter-fields :deep(.el-form-item__label) { font-size: 12px; color: var(--text-3); padding-bottom: 4px; }
@media (max-width: 900px) {
  .filter-fields { flex-direction: column; align-items: stretch; }
  .filter-fields :deep(.el-select),
  .filter-fields :deep(.el-date-editor),
  .filter-fields :deep(.el-input) { width: 100% !important; }
  .filter-actions { width: 100%; }
  .filter-actions :deep(.el-button) { flex: 1; }
}
</style>
