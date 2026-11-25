<template>
  <div class="items-editor">
    <div v-for="(item, i) in modelValue" :key="i" class="item-row">
      <span class="item-no">{{ i + 1 }}</span>
      <el-input
        v-if="type === 'textarea'"
        type="textarea"
        :model-value="modelValue[i]"
        :autosize="{ minRows: 2, maxRows: 8 }"
        @update:model-value="(v) => setAt(i, v)"
      />
      <el-input v-else :model-value="modelValue[i]" @update:model-value="(v) => setAt(i, v)" />
      <el-button type="danger" text size="small" @click="removeAt(i)">
        <Icon icon="ri:delete-bin-line" />
      </el-button>
    </div>
    <el-button size="small" plain class="add-btn" @click="add">
      <Icon icon="ri:add-line" />
      {{ addText || '添加条目' }}
    </el-button>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

const props = defineProps({
  modelValue: { type: Array, required: true },
  type: { type: String, default: 'input' },
  addText: { type: String, default: '添加条目' },
})
const emit = defineEmits(['update:modelValue'])

function setAt(i, v) {
  const arr = props.modelValue.slice()
  arr[i] = v
  emit('update:modelValue', arr)
}
function removeAt(i) {
  const arr = props.modelValue.slice()
  arr.splice(i, 1)
  emit('update:modelValue', arr)
}
function add() {
  emit('update:modelValue', [...props.modelValue, ''])
}
</script>

<style scoped>
.items-editor { display: flex; flex-direction: column; gap: 8px; }
.item-row { display: flex; align-items: flex-start; gap: 8px; }
.item-no {
  min-width: 24px; height: 24px; margin-top: 4px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; color: var(--text-2); background: var(--hover); border-radius: 6px;
  flex-shrink: 0;
}
.item-row :deep(.el-input) { flex: 1; }
.add-btn { align-self: flex-start; }
</style>
