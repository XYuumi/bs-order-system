<template>
  <div class="table-editor">
    <div class="te-head">
      <div v-for="h in headers" :key="h" class="te-cell">{{ h }}</div>
      <div class="te-op"></div>
    </div>
    <div v-for="(row, i) in modelValue" :key="i" class="te-row">
      <div v-for="(_, c) in headers" :key="c" class="te-cell">
        <el-input :model-value="row[c] || ''" size="small" @update:model-value="(v) => setAt(i, c, v)" />
      </div>
      <div class="te-op">
        <el-button type="danger" text size="small" @click="removeRow(i)">
          <Icon icon="ri:delete-bin-line" />
        </el-button>
      </div>
    </div>
    <el-button size="small" plain style="margin-top: 8px" @click="addRow">
      <Icon icon="ri:add-line" />
      {{ addText || '添加行' }}
    </el-button>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

const props = defineProps({
  modelValue: { type: Array, required: true },
  headers: { type: Array, required: true },
  addText: String,
})
const emit = defineEmits(['update:modelValue'])

function setAt(r, c, v) {
  const rows = props.modelValue.map((row) => row.slice())
  rows[r][c] = v
  emit('update:modelValue', rows)
}
function removeRow(r) {
  const rows = props.modelValue.slice()
  rows.splice(r, 1)
  emit('update:modelValue', rows)
}
function addRow() {
  emit('update:modelValue', [...props.modelValue, Array(props.headers.length).fill('')])
}
</script>

<style scoped>
.table-editor { border: 1px solid var(--border); border-radius: 10px; overflow: hidden; padding-bottom: 10px; }
.te-head, .te-row { display: grid; grid-template-columns: 1fr 1fr 1.2fr 36px; gap: 6px; padding: 6px 8px; align-items: center; }
.te-head { background: var(--card-2); font-size: 12px; font-weight: 600; color: var(--text-2); }
.te-row { border-top: 1px solid var(--border); }
.te-op { text-align: center; }
</style>
