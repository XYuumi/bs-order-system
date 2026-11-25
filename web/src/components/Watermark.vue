<!-- 水印（art-design-pro 同款 ElWatermark：防截图/防外传，铺满所属定位容器） -->
<template>
  <el-watermark
    :content="[text]"
    :font="{ fontSize: fontSize + 2, color: `rgba(128, 128, 128, ${opacity * 2.4})`, fontWeight: 400 }"
    :gap="[gap, gap]"
    :rotate="rotate"
    :z-index="999"
    class="art-watermark"
  />
</template>

<script setup>
const props = defineProps({
  text: { type: String, default: '' },
  fontSize: { type: Number, default: 14 },
  gap: { type: Number, default: 170 },
  rotate: { type: Number, default: -22 },
  opacity: { type: Number, default: 0.08 },
})
</script>

<style scoped>
.art-watermark {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.art-watermark :deep(> div) { position: absolute !important; }
</style>
