<template>
  <span class="count-to tnum">{{ display }}</span>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  target: { type: [Number, String], default: 0 },
  duration: { type: Number, default: 1300 },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' },
  decimals: { type: Number, default: 0 },
  separator: { type: Boolean, default: true },
})

const display = ref('')
let frame = null
let start = null

function fmt(n) {
  const fixed = Number(n).toFixed(Math.max(0, Math.min(props.decimals, 6)))
  const [int, dec] = fixed.split('.')
  const grouped = props.separator ? Number(int).toLocaleString('zh-CN') : int
  return props.prefix + grouped + (dec ? `.${dec}` : '') + props.suffix
}

function tick() {
  if (start == null) start = performance.now()
  const progress = Math.min((performance.now() - start) / props.duration, 1)
  const eased = 1 - Math.pow(1 - progress, 3)
  display.value = fmt(Number(props.target) * eased)
  if (progress < 1) frame = requestAnimationFrame(tick)
}

function play() {
  cancelAnimationFrame(frame)
  start = null
  if (typeof props.target !== 'number' || !isFinite(props.target)) {
    display.value = String(props.target ?? '')
    return
  }
  if (props.target === 0) {
    display.value = fmt(0)
    return
  }
  frame = requestAnimationFrame(tick)
}

onMounted(play)
watch(() => props.target, play)
onBeforeUnmount(() => cancelAnimationFrame(frame))
</script>

<style scoped>
.count-to { font-variant-numeric: tabular-nums; }
</style>
