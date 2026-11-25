<template>
  <teleport to="body">
    <div
      v-if="visible"
      ref="menuEl"
      class="art-ctx-menu"
      :style="{ left: x + 'px', top: y + 'px' }"
      @contextmenu.prevent
      @click.stop
    >
      <button
        v-for="item in items"
        :key="item.key"
        type="button"
        class="ctx-item"
        :class="{ danger: !!item.danger }"
        :disabled="!!item.disabled"
        @click="choose(item)"
      >
        <Icon v-if="item.icon" :icon="item.icon" class="ctx-icon" />
        <span class="ctx-text">{{ item.label }}</span>
      </button>
    </div>
  </teleport>
</template>

<script setup>
/**
 * 通用右键菜单（art 风格：卡片底 + 圆角 10px + 阴影，teleport 到 body）
 * - props.items: [{ key, label, icon?, danger?, disabled? }]
 * - expose.show(mouseEvent)：以 clientX/Y 定位弹出，右/下溢出自动收边
 * - emit('select', key)：点击菜单项后关闭并抛出 key
 * - document 点击 / 任意滚动 / 窗口缩放自动关闭
 */
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'

defineProps({
  items: { type: Array, default: () => [] },
})
const emit = defineEmits(['select'])

const visible = ref(false)
const x = ref(0)
const y = ref(0)
const menuEl = ref(null)

async function show(e) {
  x.value = e.clientX
  y.value = e.clientY
  visible.value = true
  await nextTick()
  const el = menuEl.value
  if (!el) return
  // 渲染后量尺寸做右/下溢出收边（留 8px 安全边距）
  const pad = 8
  const w = el.offsetWidth
  const h = el.offsetHeight
  if (x.value + w > window.innerWidth - pad) x.value = Math.max(pad, window.innerWidth - pad - w)
  if (y.value + h > window.innerHeight - pad) y.value = Math.max(pad, window.innerHeight - pad - h)
}

function hide() {
  visible.value = false
}

function choose(item) {
  if (item.disabled) return
  hide()
  emit('select', item.key)
}

function onDocClick() {
  hide()
}
function onAnyScroll() {
  hide()
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  window.addEventListener('scroll', onAnyScroll, true)
  window.addEventListener('resize', hide)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  window.removeEventListener('scroll', onAnyScroll, true)
  window.removeEventListener('resize', hide)
})

defineExpose({ show, hide })
</script>

<style scoped>
.art-ctx-menu {
  position: fixed;
  z-index: 3000;
  min-width: 168px;
  padding: 4px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  transform-origin: top left;
}
.ctx-item {
  display: flex; align-items: center; gap: 8px;
  width: 100%; height: 34px; padding: 0 12px;
  border: none; background: transparent; cursor: pointer;
  border-radius: 6px; font-size: 12.5px; color: var(--text);
  transition: background 0.12s;
}
.ctx-item:hover { background: var(--hover); }
.ctx-item:disabled { color: var(--text-3); cursor: default; }
.ctx-item:disabled:hover { background: transparent; }
.ctx-item.danger { color: #ff7875; }
.ctx-item.danger:hover { background: rgba(255, 77, 79, 0.1); }
.ctx-icon { font-size: 14px; flex-shrink: 0; color: var(--text-2); }
.ctx-item.danger .ctx-icon { color: #ff7875; }
.ctx-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 入场：CSS keyframes（挂载即播，不依赖 Vue Transition，避免与 Teleport 组合的渲染问题） */
@keyframes ctx-menu-in {
  from { opacity: 0; transform: scale(0.92); }
  to { opacity: 1; transform: scale(1); }
}
.art-ctx-menu { animation: ctx-menu-in 0.14s ease both; }
</style>
