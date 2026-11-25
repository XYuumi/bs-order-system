<template>
  <el-dropdown trigger="click" @command="onCommand">
    <el-button>
      <Icon icon="ri:file-excel-2-line" />
      Excel
      <Icon icon="ri:arrow-down-s-line" class="excel-caret" />
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="export">
          <Icon icon="ri:download-2-line" /> 导出 Excel
        </el-dropdown-item>
        <el-dropdown-item command="import" divided>
          <Icon icon="ri:upload-2-line" /> 导入 Excel
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>

  <el-dialog
    v-model="visible" :title="kind === 'orders' ? '批量导入订单' : '批量导入客户'"
    width="680px" destroy-on-close @closed="reset"
  >
    <div class="excel-tip">
      <Icon icon="ri:information-line" />
      <span>
        仅支持 .xlsx，单文件不超过 10MB。{{ requiredTip }}
        <el-button link type="primary" class="tpl-link" @click="downloadTemplate">下载导入模板</el-button>
        <br />
        先上传文件做「校验预览」，确认无误后再导入；校验不通过的行会被跳过并标出行号。
      </span>
    </div>

    <el-upload
      ref="uploadRef" drag :auto-upload="false" :limit="1" accept=".xlsx"
      :on-change="onFileChange" :on-exceed="onExceed" :on-remove="onRemove"
      class="excel-upload"
    >
      <Icon icon="ri:file-excel-2-line" class="excel-upload-icon" />
      <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
      <template #tip>
        <div class="el-upload__tip">按导入模板的表头填写；导出的 Excel 也可改完再导回。</div>
      </template>
    </el-upload>

    <div v-if="checking" class="excel-checking">
      <el-icon class="is-loading"><Icon icon="ri:loader-4-line" /></el-icon>
      正在校验文件…
    </div>

    <div v-else-if="result" class="excel-result">
      <div class="excel-summary">
        <span class="ok">可导入 {{ result.valid ?? result.created ?? 0 }} 行</span>
        <span v-if="result.total != null" class="muted">共 {{ result.total }} 行</span>
        <span v-if="failedRows.length" class="bad">失败 {{ failedRows.length }} 行</span>
        <span v-if="result.preview_truncated" class="muted">预览仅显示前 50 行</span>
      </div>

      <el-table v-if="previewRows.length" :data="previewRows" size="small" max-height="240" border>
        <el-table-column prop="row" label="行号" width="64" />
        <el-table-column
          v-if="kind === 'orders'" prop="title" label="标题" min-width="150" show-overflow-tooltip
        />
        <el-table-column
          v-if="kind === 'orders'" prop="quality_name" label="品质" width="80"
        />
        <el-table-column
          v-if="kind === 'orders'" prop="agent_username" label="代理" width="100"
        />
        <el-table-column
          v-if="kind === 'customers'" prop="name" label="客户名称" min-width="130"
        />
        <el-table-column
          v-if="kind === 'customers'" prop="contact" label="联系方式" width="130"
        />
        <el-table-column
          v-if="kind === 'customers'" prop="owner_username" label="归属" width="100"
        />
      </el-table>

      <div v-if="failedRows.length" class="excel-failed">
        <div class="excel-failed-title">以下行未通过校验</div>
        <div v-for="f in failedRows" :key="f.row" class="excel-failed-row">
          <span class="row-no">第 {{ f.row }} 行</span>
          <span>{{ f.error }}</span>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button :disabled="!file" :loading="checking" @click="dryRun">校验预览</el-button>
      <el-button
        type="primary" :disabled="!canImport" :loading="importing" @click="doImport"
      >
        确认导入{{ result?.valid ? `（${result.valid} 行）` : '' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../api'

const props = defineProps({
  kind: { type: String, default: 'orders' }, // orders | customers
  params: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['imported'])

const visible = ref(false)
const uploadRef = ref(null)
const file = ref(null)
const checking = ref(false)
const importing = ref(false)
const result = ref(null)

const requiredTip = computed(() => (
  props.kind === 'orders'
    ? '必填列：标题、品质代码（也接受中文品质名）；其余列选填。'
    : '必填列：客户名称；其余列选填。'
))
const failedRows = computed(() => result.value?.failed || [])
const previewRows = computed(() => result.value?.preview || [])
const canImport = computed(
  () => !!file.value && !!result.value && !checking.value && !importing.value
    && result.value.dry_run === true && (result.value.valid || 0) > 0,
)

function onCommand(cmd) {
  if (cmd === 'export') exportXlsx()
  else visible.value = true
}

function downloadTemplate() {
  window.open(`/api/excel/${props.kind}/template`, '_blank')
}

function exportXlsx() {
  const qs = new URLSearchParams()
  Object.entries(props.params || {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') qs.set(key, value)
  })
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  window.open(`/api/excel/${props.kind}/export${suffix}`, '_blank')
}

function onFileChange(uploadFile) {
  file.value = uploadFile.raw || null
  result.value = null
  if (file.value && !/\.xlsx$/i.test(file.value.name || '')) {
    ElMessage.warning('仅支持 .xlsx 文件，请另存为 .xlsx 后再上传')
    file.value = null
    uploadRef.value?.clearFiles()
    return
  }
  if (file.value) dryRun()
}

function onExceed(files) {
  uploadRef.value?.clearFiles()
  const raw = files?.[0]
  if (raw) {
    file.value = raw
    result.value = null
    dryRun()
  }
}

function onRemove() {
  file.value = null
  result.value = null
}

async function submit(dryRunFlag) {
  if (!file.value) return null
  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('dry_run', dryRunFlag ? '1' : '0')
  return http.post(`/excel/${props.kind}/import`, fd, { timeout: 0 })
}

async function dryRun() {
  if (!file.value || checking.value) return
  checking.value = true
  result.value = null
  try {
    const data = await submit(true)
    result.value = data
    if (data.failed?.length) ElMessage.warning(`有 ${data.failed.length} 行未通过校验`)
    else ElMessage.success(`校验通过，可导入 ${data.valid} 行`)
  } catch (e) {
    result.value = null
    const detail = e?.response?.data?.detail
    if (detail) ElMessage.error(detail)
  } finally {
    checking.value = false
  }
}

async function doImport() {
  if (!file.value || importing.value) return
  importing.value = true
  try {
    const data = await submit(false)
    result.value = { ...data, valid: data.created, preview: [] }
    if (data.created > 0) ElMessage.success(`成功导入 ${data.created} 行`)
    if (data.failed?.length) ElMessage.warning(`${data.failed.length} 行导入失败，详见列表`)
    if (data.created > 0) emit('imported')
    if (!data.failed?.length) visible.value = false
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (detail) ElMessage.error(detail)
  } finally {
    importing.value = false
  }
}

function reset() {
  file.value = null
  result.value = null
  checking.value = false
  importing.value = false
  uploadRef.value?.clearFiles()
}
</script>

<style scoped>
.excel-caret { margin-left: 2px; }
.excel-tip {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 10px 12px; margin-bottom: 14px; border-radius: 10px;
  background: var(--el-fill-color-light); color: var(--el-text-color-regular);
  font-size: 13px; line-height: 1.6;
}
.excel-tip .iconify { flex: none; margin-top: 2px; color: var(--el-color-primary); }
.excel-tip .tpl-link { margin-left: 4px; vertical-align: baseline; }
.excel-upload { display: block; }
.excel-upload-icon { font-size: 46px; color: var(--el-color-success); margin-bottom: 6px; }
.excel-checking {
  display: flex; align-items: center; gap: 8px; justify-content: center;
  padding: 18px; color: var(--el-text-color-secondary); font-size: 14px;
}
.excel-result { margin-top: 16px; }
.excel-summary { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 10px; font-size: 13px; }
.excel-summary .ok { color: var(--el-color-success); font-weight: 600; }
.excel-summary .bad { color: var(--el-color-danger); font-weight: 600; }
.excel-summary .muted { color: var(--el-text-color-secondary); }
.excel-failed {
  margin-top: 12px; max-height: 180px; overflow: auto;
  border: 1px solid var(--el-color-danger-light-5); border-radius: 10px;
  background: var(--el-color-danger-light-9); padding: 10px 12px;
}
.excel-failed-title { font-size: 13px; font-weight: 600; color: var(--el-color-danger); margin-bottom: 6px; }
.excel-failed-row { display: flex; gap: 10px; font-size: 12px; line-height: 1.9; color: var(--el-text-color-regular); }
.excel-failed-row .row-no { flex: none; color: var(--el-color-danger); font-weight: 600; }
</style>
