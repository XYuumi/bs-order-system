<template>
  <!-- 自研分片上传：原生 input 选文件，逻辑保持不变 -->
  <input
    ref="fileInputRef" type="file" class="upload-native-input"
    :accept="accept || undefined" multiple
    @change="onPick"
  />
  <el-button size="small" :type="btnType" :loading="uploading" @click="fileInputRef.click()">
    <Icon icon="ri:upload-2-line" />
    {{ uploading ? `上传中 ${percent}%` : label }}
  </el-button>
</template>

<script setup>
import { computed, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../api'

const props = defineProps({
  orderId: { type: String, required: true },
  category: { type: String, required: true },
  // 该分类下订单已有的文件：演示视频、程序包每单只保留 1 份，再传就是替换
  existing: { type: Array, default: () => [] },
})
const emit = defineEmits(['uploaded'])

const uploading = ref(false)
const percent = ref(0)
const fileInputRef = ref(null)
let active = 0

// 多文件并发时按「已传字节 / 总字节」聚合进度，避免各文件百分比互相覆盖跳变
const progressMap = new Map()

function refreshPercent() {
  let loaded = 0
  let total = 0
  progressMap.forEach((v) => {
    loaded += v.loaded
    total += v.total
  })
  percent.value = total > 0 ? Math.min(99, Math.round((loaded / total) * 100)) : 0
}

const LABELS = { package: '上传程序包', video: '上传视频', doc: '上传文档', other: '上传附件' }
// 已有文件时按钮改为「重新上传」。single / existingNames 在下面才声明：计算属性是渲染时才求值，这里可以先引用
const label = computed(() => (single && existingNames.value ? '重新上传' : LABELS[props.category] || '上传'))
const btnType = computed(() => (props.category === 'other' ? 'default' : 'primary'))
const accept = computed(() =>
  ({
    package: '.zip,.rar,.7z,.tar,.gz',
    video: '.mp4,.avi,.mov,.mkv,.wmv,.flv,.webm,.m4v',
    doc: '.doc,.docx,.pdf,.xls,.xlsx,.ppt,.pptx,.txt,.md',
    other: undefined,
  }[props.category])
)
// 演示视频与程序包是「每单一份」的分类：多选只取第 1 个，已有文件时先确认再替换
const single = props.category === 'video' || props.category === 'package'
const existingNames = computed(() => (props.existing || []).map((f) => f.original_name).join('、'))
const singleLabel = props.category === 'video' ? '演示视频' : '程序包'

const CHUNK_THRESHOLD = 8 * 1024 * 1024 // 超过 8MB 走分片
const CHUNK_SIZE = 5 * 1024 * 1024

function fpKey(file) {
  return `chunk-${props.orderId}-${props.category}-${file.name}-${file.size}-${file.lastModified}`
}

function onPick(e) {
  let files = Array.from(e.target.files || [])
  e.target.value = ''
  if (!files.length) return
  if (single) {
    if (files.length > 1) {
      ElMessage.warning(`${singleLabel}每单只保留 1 个文件，只上传所选的第 1 个`)
      files = files.slice(0, 1)
    }
    if (existingNames.value) {
      ElMessageBox.confirm(`该订单已有${singleLabel}：${existingNames.value}。上传后将替换旧文件，列表与客户交付链接同步更新。`, '替换上传', {
        confirmButtonText: '替换上传', cancelButtonText: '取消', type: 'warning',
      }).then(() => {
        doUpload({ file: files[0] })
      }).catch(() => {})
      return
    }
  }
  files.forEach((file) => doUpload({ file }))
}

async function doUpload({ file, onError, onSuccess }) {
  active += 1
  uploading.value = true
  progressMap.set(file, { loaded: 0, total: file.size })
  refreshPercent()
  try {
    if (file.size > CHUNK_THRESHOLD) {
      await uploadChunked(file)
    } else {
      await uploadDirect(file)
    }
    ElMessage.success(`「${file.name}」上传成功`)
    emit('uploaded')
    onSuccess && onSuccess()
  } catch (err) {
    onError && onError(err)
  } finally {
    progressMap.delete(file)
    active -= 1
    if (active <= 0) {
      active = 0
      uploading.value = false
      percent.value = 0
      progressMap.clear()
    }
  }
}

async function uploadDirect(file) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('category', props.category)
  await http.post(`/orders/${props.orderId}/files`, fd, {
    timeout: 0,
    onUploadProgress: (e) => {
      if (!e.total) return
      progressMap.set(file, { loaded: e.loaded, total: e.total })
      refreshPercent()
    },
  })
  progressMap.set(file, { loaded: file.size, total: file.size })
  refreshPercent()
}

async function uploadChunked(file) {
  const total = file.size
  const chunkCount = Math.ceil(total / CHUNK_SIZE)
  const key = fpKey(file)

  // 断点续传：同指纹会话直接查询已收分片
  let uploadId = null
  let received = new Set()
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null')
    if (saved?.upload_id) {
      try {
        const st = await http.get(`/orders/${props.orderId}/chunk-uploads/${saved.upload_id}`)
        if (st.size === total) {
          uploadId = saved.upload_id
          received = new Set(st.received)
          if (received.size) ElMessage.info(`检测到未完成的上传，已恢复 ${received.size}/${chunkCount} 片`)
        }
      } catch { /* 会话失效则重新创建 */ }
    }
  } catch { /* localStorage 不可用 */ }

  if (!uploadId) {
    const created = await http.post(`/orders/${props.orderId}/chunk-uploads`, {
      filename: file.name, category: props.category, size: total,
    })
    uploadId = created.upload_id
    try { localStorage.setItem(key, JSON.stringify({ upload_id: uploadId })) } catch { /* 忽略 */ }
  }

  let doneBytes = received.size * CHUNK_SIZE
  const mark = () => {
    progressMap.set(file, { loaded: Math.min(doneBytes, total), total })
    refreshPercent()
  }
  mark()
  for (let i = 0; i < chunkCount; i++) {
    if (received.has(i)) continue
    const blob = file.slice(i * CHUNK_SIZE, Math.min((i + 1) * CHUNK_SIZE, total))
    let ok = false
    for (let attempt = 0; attempt < 3 && !ok; attempt++) {
      try {
        await http.put(`/orders/${props.orderId}/chunk-uploads/${uploadId}/${i}`, blob, {
          headers: { 'Content-Type': 'application/octet-stream' },
          timeout: 0,
        })
        ok = true
      } catch (err) {
        if (attempt === 2) throw err
        await new Promise((r) => setTimeout(r, 800 * (attempt + 1)))
      }
    }
    doneBytes += blob.size
    mark()
  }

  await http.post(`/orders/${props.orderId}/chunk-uploads/${uploadId}/finish`, {})
  progressMap.set(file, { loaded: total, total })
  refreshPercent()
  try { localStorage.removeItem(key) } catch { /* 忽略 */ }
}
</script>

<style scoped>
.upload-native-input { display: none; }
</style>
