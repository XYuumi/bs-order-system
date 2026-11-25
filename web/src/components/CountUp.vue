<template>
  <span ref="el" class="count-up">{{ displayValue }}</span>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  duration: { type: Number, default: 1500 },
  prefix: { type: String, default: '' },
})

const el = ref(null)
const displayValue = ref('0')
let animFrame = null
let startTime = null

function format(n) {
  return props.prefix + Number(n).toLocaleString()
}

function animate() {
  if (!startTime) startTime = performance.now()
  const elapsed = performance.now() - startTime
  const progress = Math.min(elapsed / props.duration, 1)
  const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
  const current = Math.round(props.value * eased)
  displayValue.value = format(current)
  if (progress < 1) {
    animFrame = requestAnimationFrame(animate)
  }
}

function start() {
  cancelAnimationFrame(animFrame)
  startTime = null
  if (props.value === 0) {
    displayValue.value = format(0)
    return
  }
  animFrame = requestAnimationFrame(animate)
}

onMounted(start)
watch(() => props.value, start)
onBeforeUnmount(() => cancelAnimationFrame(animFrame))
</script>
