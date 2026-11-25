<template>
  <div class="tabs-bar">
    <div class="tabs-scroll" ref="scrollEl">
      <div
        v-for="tab in tabs" :key="tab.path"
        class="tab-item" :class="{ active: tab.path === route.path }"
        @click="router.push(tab.path)"
        @contextmenu.prevent="openMenu($event, tab)"
      >
        <span class="tab-dot" :class="{ on: tab.path === route.path }" />
        <span class="tab-label">{{ tab.title }}</span>
        <span
          v-if="tab.path !== homePath"
          class="tab-close"
          @click.stop="closeTab(tab)"
        >
          <Icon icon="ri:close-line" />
        </span>
      </div>
    </div>

    <el-dropdown trigger="click" @command="ctxAction">
      <div class="tabs-action" title="标签操作">
        <Icon icon="ri:arrow-down-s-line" />
      </div>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="refresh"><Icon icon="ri:refresh-line" /> 刷新当前页</el-dropdown-item>
          <el-dropdown-item command="close"><Icon icon="ri:close-line" /> 关闭当前</el-dropdown-item>
          <el-dropdown-item command="closeOthers"><Icon icon="ri:checkbox-multiple-blank-line" /> 关闭其他</el-dropdown-item>
          <el-dropdown-item command="closeRight"><Icon icon="ri:arrow-right-line" /> 关闭右侧</el-dropdown-item>
          <el-dropdown-item command="closeAll" class="danger-item"><Icon icon="ri:close-circle-line" /> 关闭全部</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <teleport to="body">
      <div
        v-if="menuVisible" class="tab-ctx-menu"
        :style="{ left: menuX + 'px', top: menuY + 'px' }"
        @click.stop
      >
        <button class="ctx-item" @click="ctxAction('refresh')"><Icon icon="ri:refresh-line" /> 刷新当前页</button>
        <button class="ctx-item" :disabled="ctxTab?.path === homePath" @click="ctxAction('close')"><Icon icon="ri:close-line" /> 关闭当前</button>
        <button class="ctx-item" @click="ctxAction('closeOthers')"><Icon icon="ri:checkbox-multiple-blank-line" /> 关闭其他</button>
        <button class="ctx-item" @click="ctxAction('closeRight')"><Icon icon="ri:arrow-right-line" /> 关闭右侧</button>
        <button class="ctx-item danger" @click="ctxAction('closeAll')"><Icon icon="ri:close-circle-line" /> 关闭全部</button>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'

const route = useRoute()
const router = useRouter()
const refreshPage = inject('refreshPage', null)
const homePath = '/'
const STORE = 'bs-work-tabs'
const MAX_TABS = 14

function titleFor(path) {
  const meta = router.resolve(path).meta || {}
  const title = meta.title || '页面'
  const segments = path.split('/')
  const child = segments[1] === 'orders' ? segments[2] : ''
  // 只有真实订单号才使用「订单 · 单号」，避免 /orders/board、/orders/calendar 被误判
  const orderId = child && !['create', 'board', 'calendar'].includes(child) ? child : ''
  if (orderId) {
    if (path.endsWith('/doc')) return `需求书 · ${orderId}`
    return `订单 · ${orderId}`
  }
  return title
}

function loadTabs() {
  try {
    const raw = JSON.parse(sessionStorage.getItem(STORE) || '[]')
    return Array.isArray(raw)
      ? raw.filter((t) => t && t.path && t.title && t.path.startsWith('/') && t.path !== '/login')
      : []
  } catch {
    return []
  }
}

const tabs = ref(loadTabs())
if (!tabs.value.length) tabs.value = [{ path: '/', title: '工作台' }]
if (!tabs.value.some((t) => t.path === '/')) tabs.value.unshift({ path: '/', title: '工作台' })

const scrollEl = ref(null)
function ensureVisible() {
  nextTick(() => {
    const active = scrollEl.value?.querySelector('.tab-item.active')
    active?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' })
  })
}

function addTab(path) {
  if (path === '/login') return
  if (!tabs.value.find((t) => t.path === path)) {
    tabs.value.push({ path, title: titleFor(path) })
    if (tabs.value.length > MAX_TABS) {
      const idx = tabs.value.findIndex((t) => t.path !== homePath && t.path !== path)
      if (idx >= 0) tabs.value.splice(idx, 1)
    }
  } else {
    const tab = tabs.value.find((t) => t.path === path)
    tab.title = titleFor(path)
  }
  ensureVisible()
}

watch(
  () => route.path,
  (path) => addTab(path),
  { immediate: true },
)
watch(tabs, () => {
  try { sessionStorage.setItem(STORE, JSON.stringify(tabs.value)) } catch { /* 忽略 */ }
}, { deep: true })

function closeTab(tab) {
  const idx = tabs.value.findIndex((t) => t.path === tab.path)
  tabs.value = tabs.value.filter((t) => t.path !== tab.path)
  if (!tabs.value.length) tabs.value = [{ path: homePath, title: '工作台' }]
  if (route.path === tab.path) {
    const next = tabs.value[Math.min(Math.max(idx, 0), tabs.value.length - 1)] || tabs.value[0]
    router.push(next.path)
  }
}

const menuVisible = ref(false)
const menuX = ref(0)
const menuY = ref(0)
const ctxTab = ref(null)

function openMenu(e, tab) {
  ctxTab.value = tab
  menuX.value = Math.min(e.clientX, window.innerWidth - 180)
  menuY.value = Math.min(e.clientY, window.innerHeight - 220)
  menuVisible.value = true
}

function closeMenu() { menuVisible.value = false }

function ctxAction(action) {
  const tab = ctxTab.value || { path: route.path }
  closeMenu()
  switch (action) {
    case 'refresh':
      if (route.path === tab.path) {
        if (refreshPage) refreshPage()
        else router.replace({ path: tab.path, query: { ...route.query, _t: Date.now() } })
      } else {
        router.push(tab.path)
      }
      break
    case 'close': closeTab(tab); break
    case 'closeOthers':
      tabs.value = tabs.value.filter((t) => t.path === homePath || t.path === tab.path)
      if (![homePath, tab.path].includes(route.path)) router.push(tab.path)
      break
    case 'closeRight': {
      const idx = tabs.value.findIndex((t) => t.path === tab.path)
      tabs.value = tabs.value.slice(0, idx + 1)
      if (!tabs.value.find((t) => t.path === route.path)) router.push(tab.path)
      break
    }
    case 'closeAll':
      tabs.value = [{ path: homePath, title: '工作台' }]
      router.push(homePath)
      break
  }
}

onMounted(() => document.addEventListener('click', closeMenu))
onBeforeUnmount(() => document.removeEventListener('click', closeMenu))
</script>

<style scoped>
.tabs-bar {
  height: 44px;
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 8px;
  position: sticky;
  top: var(--topbar-h);
  z-index: var(--z-tabs);
  flex-shrink: 0;
}
.tabs-scroll {
  display: flex; align-items: center; gap: 6px;
  overflow-x: auto; flex: 1; min-width: 0;
}
.tab-item {
  display: inline-flex; align-items: center; gap: 7px;
  height: 30px; padding: 0 8px 0 10px;
  border-radius: var(--radius-xs);
  font-size: 12px; color: var(--text-3);
  cursor: pointer; white-space: nowrap;
  border: 1px solid transparent;
  background: transparent;
  transition: color 0.16s, background 0.16s, border-color 0.16s;
  user-select: none; flex-shrink: 0;
}
.tab-item:hover { color: var(--text); background: var(--hover); }
.tab-item.active {
  color: var(--text); background: var(--card);
  border-color: var(--border-2);
  box-shadow: var(--shadow-card);
  font-weight: 550;
}
.tab-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--text-4); flex-shrink: 0; }
.tab-dot.on { background: var(--brand); box-shadow: 0 0 8px var(--brand); }
.tab-close {
  width: 16px; height: 16px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  color: var(--text-4); font-size: 11px;
  transition: all 0.15s; flex-shrink: 0;
}
.tab-close:hover { background: var(--danger-weak); color: var(--danger); }
.tabs-action {
  width: 30px; height: 30px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius-xs); cursor: pointer; color: var(--text-3);
  transition: background 0.15s, color 0.15s;
}
.tabs-action:hover { background: var(--hover); color: var(--text); }
.tab-ctx-menu {
  position: fixed; z-index: var(--z-modal); min-width: 164px;
  background: var(--card-2); border: 1px solid var(--border-2);
  border-radius: var(--radius-md); padding: 5px;
  box-shadow: var(--shadow-pop);
  animation: scale-in 0.16s ease both;
}
.ctx-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 7px 10px; border: none; background: transparent; cursor: pointer;
  border-radius: var(--radius-xs); font-size: 12.5px; color: var(--text-2);
  transition: background 0.12s, color 0.12s;
}
.ctx-item:hover { background: var(--hover); color: var(--text); }
.ctx-item:disabled { color: var(--text-4); cursor: default; }
.ctx-item:disabled:hover { background: transparent; }
.ctx-item.danger { color: var(--danger); }
.ctx-item.danger:hover { background: var(--danger-weak); }
.danger-item { color: var(--danger) !important; }
</style>