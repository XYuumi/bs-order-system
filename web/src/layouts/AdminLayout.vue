<template>
  <div class="layout">
    <aside class="sidebar" :class="{ collapsed: collapsed && !isMobile, 'mobile-open': drawerOpen }">
      <div class="brand" @click="router.push('/')">
        <div class="brand-logo">{{ (siteName || '毕').slice(0, 1) }}</div>
        <transition name="fade">
          <div v-if="!collapsed || isMobile" class="brand-copy">
            <span class="brand-name">{{ siteName || '毕设接单' }}</span>
            <span class="brand-sub">OPS · CONSOLE</span>
          </div>
        </transition>
      </div>
      <nav class="nav" aria-label="主导航">
        <el-menu
          class="art-menu"
          :default-active="activePath"
          :collapse="collapsed && !isMobile"
          :collapse-transition="false"
          :default-openeds="openMenus"
          unique-opened
          router
          popper-class="menu-left-popper"
          @open="onMenuOpen"
          @close="onMenuClose"
        >
          <template v-for="item in menuItems" :key="item.key || item.path">
            <el-sub-menu v-if="item.children" :index="item.key">
              <template #title>
                <span class="menu-icon"><Icon :icon="item.icon" /></span>
                <span class="menu-name">{{ item.label }}</span>
              </template>
              <el-menu-item v-for="c in item.children" :key="c.path" :index="c.path">
                <span class="menu-icon"><Icon :icon="c.icon" /></span>
                <template #title><span class="menu-name">{{ c.label }}</span></template>
              </el-menu-item>
            </el-sub-menu>
            <el-menu-item v-else :index="item.path">
              <span class="menu-icon"><Icon :icon="item.icon" /></span>
              <template #title><span class="menu-name">{{ item.label }}</span></template>
            </el-menu-item>
          </template>
        </el-menu>
      </nav>
      <div v-if="!collapsed || isMobile" class="sidebar-foot">
        <span class="ver">v{{ version }}</span>
        <span class="role">{{ auth.roleName }}</span>
      </div>
    </aside>
    <div v-if="drawerOpen" class="sidebar-mask" @click="drawerOpen = false"></div>

    <div class="main">
      <header class="topbar">
        <div class="tb-left">
          <button class="tb-icon-btn art-hover-rotate" aria-label="切换菜单" @click="toggleSidebar">
            <Icon icon="ri:menu-2-fill" />
          </button>
          <el-breadcrumb class="tb-breadcrumb" separator="/">
            <el-breadcrumb-item>
              <router-link to="/" class="bc-home">工作台</router-link>
            </el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentGroup && route.path !== '/'">
              <span class="bc-group">{{ currentGroup }}</span>
            </el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.path !== '/'">
              <span class="bc-current">{{ route.meta.title || '页面' }}</span>
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="tb-right">
          <!-- 写手不负责建单（路由也只放开给管理员与代理），顶栏快捷入口对他们隐藏 -->
          <button v-if="!auth.isStaffView || auth.isAdmin" class="tb-quick" title="新建订单" @click="router.push('/orders/create')">
            <Icon icon="ri:add-line" />
            <span>新建订单</span>
          </button>
          <button class="tb-search" title="全局搜索 (Ctrl+K)" @click="openSearch">
            <Icon icon="ri:search-line" class="ts-icon" />
            <span class="ts-text">搜索</span>
            <span class="ts-kbd">Ctrl K</span>
          </button>
          <button
            class="tb-icon-btn" :class="isFullscreen ? 'art-hover-shrink' : 'art-hover-expand'"
            :title="isFullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen"
          >
            <Icon :icon="isFullscreen ? 'ri:fullscreen-exit-line' : 'ri:fullscreen-fill'" />
          </button>
          <ReminderBell />
          <button class="tb-icon-btn art-hover-shake chat-btn" title="站内私信" @click="chatOpen = true">
            <Icon icon="ri:message-3-line" />
            <span v-if="chatUnread" class="chat-badge">{{ chatUnread > 99 ? '99+' : chatUnread }}</span>
            <span v-else class="chat-dot art-dot-breathe" />
          </button>
          <button class="tb-icon-btn art-hover-shake bot-btn" title="毕设助手（AI）" @click="botOpen = true">
            <Icon icon="ri:robot-2-fill" />
            <span class="bot-dot art-dot-breathe" />
          </button>
          <button
            class="tb-icon-btn art-hover-up" :title="themeStore.isDark ? '切换亮色' : '切换暗色'"
            @click="toggleTheme"
          >
            <Icon :icon="themeStore.isDark ? 'ri:sun-fill' : 'ri:moon-line'" />
          </button>
          <el-dropdown trigger="click" placement="bottom-end" popper-class="user-pop">
            <div class="user-avatar-wrap">
              <div class="avatar">{{ (auth.user?.display_name || auth.user?.username || '?').slice(0, 1) }}</div>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <div class="um-head">
                  <div class="um-avatar">{{ (auth.user?.display_name || auth.user?.username || '?').slice(0, 1) }}</div>
                  <div class="um-info">
                    <div class="um-name">{{ auth.user?.display_name || auth.user?.username }}</div>
                    <div class="um-role">{{ auth.roleName }}</div>
                  </div>
                </div>
                <el-dropdown-item @click="router.push('/profile')">
                  <Icon icon="ri:user-3-line" style="font-size: 15px" /> 个人中心
                </el-dropdown-item>
                <el-dropdown-item @click="themeStore.toggle()">
                  <Icon :icon="themeStore.isDark ? 'ri:sun-line' : 'ri:moon-line'" style="font-size: 15px" />
                  切换{{ themeStore.isDark ? '亮色' : '暗色' }}
                </el-dropdown-item>
                <el-dropdown-item divided @click="auth.logout()">
                  <Icon icon="ri:logout-box-r-line" style="font-size: 15px" /> 退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <GlobalSearch v-model:open="searchOpen" ref="globalSearchRef" />
      <AiBot v-model:open="botOpen" />
      <ChatDrawer v-model:open="chatOpen" @unread="chatUnread = $event" />
      <TabsBar />

      <main class="content">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" :key="route.path + ':' + refreshKey" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import AiBot from '../components/AiBot.vue'
import ChatDrawer from '../components/ChatDrawer.vue'
import { useThemeStore } from '../stores/theme'
import GlobalSearch from '../components/GlobalSearch.vue'
import ReminderBell from '../components/ReminderBell.vue'
import { useAuthStore } from '../stores/auth'
import http from '../api'
import TabsBar from '../components/TabsBar.vue'
import { closeWS, connectWS } from '../utils/ws'

import pkg from '../../package.json'

const ICONS = {
  dash: 'ri:dashboard-2-line',
  list: 'ri:file-list-3-line',
  api: 'ri:code-s-slash-line',
  log: 'ri:history-line',
  user: 'ri:user-settings-line',
  bill: 'ri:bill-line',
  trash: 'ri:delete-bin-6-line',
  setting: 'ri:settings-3-line',
  profile: 'ri:user-3-line',
  subOrders: 'ri:clipboard-line',
  subBoard: 'ri:kanban-view',
  subCalendar: 'ri:calendar-schedule-line',
  subBill: 'ri:bill-line',
  subApi: 'ri:braces-line',
  subLog: 'ri:file-history-line',
  subUser: 'ri:group-line',
  subTrash: 'ri:delete-bin-6-line',
  subSetting: 'ri:equalizer-line',
  subPerf: 'ri:medal-line',
  subSetGeneral: 'ri:settings-4-line',
  subSetAi: 'ri:robot-2-line',
  subSetHook: 'ri:webhook-line',
  subSetSec: 'ri:shield-keyhole-line',
  subSetBackup: 'ri:database-2-line',
  customer: 'ri:user-heart-line',
  subCustomer: 'ri:contacts-line',
  subAnn: 'ri:megaphone-line',
  subSuggest: 'ri:lightbulb-line',
  subMargin: 'ri:money-cny-circle-line',
  subTemplate: 'ri:file-copy-2-line',
  subHealth: 'ri:heart-pulse-line',
  ai: 'ri:sparkling-2-line',
  collab: 'ri:team-line',
  analysis: 'ri:bar-chart-box-line',
  ops: 'ri:shield-check-line',
}

const auth = useAuthStore()
const themeStore = useThemeStore()
const route = useRoute()
const router = useRouter()
const version = pkg.version || '1.15.0'
const siteName = ref('')
const isMobile = ref(false)
const drawerOpen = ref(false)
const collapsed = ref(localStorage.getItem('nav-collapsed') === '1')
const searchOpen = ref(false)
const botOpen = ref(false)
const chatOpen = ref(false)
const chatUnread = ref(0)
const globalSearchRef = ref(null)
const refreshKey = ref(0)
provide('pageRefreshKey', refreshKey)
provide('refreshPage', () => { refreshKey.value += 1 })

function openSearch() {
  searchOpen.value = true
  setTimeout(() => globalSearchRef.value?.focus(), 80)
}

function toggleTheme(e) {
  themeStore.toggle(e)
}

function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    openSearch()
  }
}

const openMenus = ref([])
const MENU_STORE = 'nav-open-menus'
try { openMenus.value = JSON.parse(localStorage.getItem(MENU_STORE) || '[]') } catch { openMenus.value = [] }

function persistMenus() {
  try { localStorage.setItem(MENU_STORE, JSON.stringify(openMenus.value)) } catch { /* 忽略 */ }
}
function onMenuOpen(key) {
  if (!openMenus.value.includes(key)) {
    openMenus.value = [...openMenus.value, key]
    persistMenus()
  }
}
function onMenuClose(key) {
  openMenus.value = openMenus.value.filter((k) => k !== key)
  persistMenus()
}

const activePath = computed(() => {
  const p = route.path
  // 先把所有可点击菜单路径摊平，再按「精确匹配 > 最长前缀匹配」判定高亮，
  // 避免 /orders 抢走 /orders/board 这类同级子菜单的高亮（原先按书写顺序 return，先命中者胜）。
  const paths = []
  for (const item of menuItems.value) {
    if (item.children) for (const c of item.children) paths.push(c.path)
    else paths.push(item.path)
  }
  if (paths.includes(p)) return p
  let best = ''
  for (const path of paths) {
    if (path === '/') continue
    if (p.startsWith(path + '/') && path.length > best.length) best = path
  }
  return best || p
})

const currentGroup = computed(() => {
  for (const item of menuItems.value) {
    if (item.children?.some((c) => activePath.value === c.path || route.path.startsWith(c.path + '/'))) {
      return item.label
    }
  }
  return ''
})

const isFullscreen = ref(false)
async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) await document.documentElement.requestFullscreen()
    else await document.exitFullscreen()
  } catch {
    ElMessage.warning('当前浏览器不允许全屏')
  }
}
function onFullscreenChange() { isFullscreen.value = !!document.fullscreenElement }

const menuItems = computed(() => {
  const items = [{ path: '/', label: '工作台', icon: ICONS.dash }]
  const orderChildren = [
    { path: '/orders', label: '订单列表', icon: ICONS.subOrders },
    { path: '/orders/board', label: '生产看板', icon: ICONS.subBoard },
    { path: '/orders/calendar', label: '订单日历', icon: ICONS.subCalendar },
  ]
  if (auth.isAdmin || auth.isAgent) orderChildren.push({ path: '/settlement', label: '对账单', icon: ICONS.subBill })
  orderChildren.push({ path: '/templates', label: '模板库', icon: ICONS.subTemplate })
  items.push({ key: 'order', label: '订单中心', icon: ICONS.list, children: orderChildren })

  const collabChildren = [
    { path: '/customers', label: '客户管理', icon: ICONS.subCustomer },
    { path: '/suggestions', label: '建议反馈', icon: ICONS.subSuggest },
  ]
  if (auth.isAdmin) collabChildren.push({ path: '/announcements', label: '公告管理', icon: ICONS.subAnn })
  items.push({ key: 'collab', label: '客户协作', icon: ICONS.collab, children: collabChildren })

  if (auth.isStaffView) items.push({ path: '/ai', label: 'AI 参谋', icon: ICONS.ai })

  const analysisChildren = []
  if (auth.isStaffView) analysisChildren.push({ path: '/writer-perf', label: '写手绩效', icon: ICONS.subPerf })
  if (auth.isAdmin) analysisChildren.push({ path: '/margin', label: '毛利分析', icon: ICONS.subMargin })
  if (analysisChildren.length) items.push({ key: 'analysis', label: '经营分析', icon: ICONS.analysis, children: analysisChildren })

  const opsChildren = []
  if (auth.isStaffView) opsChildren.push({ path: '/logs', label: '操作日志', icon: ICONS.subLog })
  if (auth.isAdmin) {
    opsChildren.push({ path: '/users', label: '用户管理', icon: ICONS.subUser })
    opsChildren.push({ path: '/trash', label: '回收站', icon: ICONS.subTrash })
    opsChildren.push({ path: '/health', label: '系统健康', icon: ICONS.subHealth })
  }
  if (opsChildren.length) items.push({ key: 'ops', label: '运维管理', icon: ICONS.ops, children: opsChildren })

  if (auth.isAdmin) {
    items.push({ key: 'system', label: '系统设置', icon: ICONS.setting, children: [
      { path: '/settings/general', label: '通用设置', icon: ICONS.subSetGeneral },
      { path: '/settings/pricing', label: '价格与品质', icon: ICONS.subBill },
      { path: '/settings/ai', label: 'AI 中心', icon: ICONS.subSetAi },
      { path: '/settings/integration', label: '集成通知', icon: ICONS.subSetHook },
      { path: '/settings/security', label: '安全设置', icon: ICONS.subSetSec },
      { path: '/settings/backup', label: '数据备份', icon: ICONS.subSetBackup },
    ] })
  }
  items.push({ key: 'dev', label: '开发者', icon: ICONS.api, children: [
    { path: '/api-docs', label: 'API 对接', icon: ICONS.subApi },
  ] })
  items.push({ path: '/profile', label: '个人中心', icon: ICONS.profile })
  return items
})

function toggleSidebar() {
  if (isMobile.value) drawerOpen.value = !drawerOpen.value
  else {
    collapsed.value = !collapsed.value
    localStorage.setItem('nav-collapsed', collapsed.value ? '1' : '0')
  }
}

function checkMobile() { isMobile.value = window.innerWidth < 900 }

let unreadTimer = null
async function pollUnread() {
  try {
    const data = await http.get('/messages/unread')
    chatUnread.value = data.unread || 0
  } catch { /* 忽略 */ }
}

function onWsMsg(e) {
  const msg = e.detail || {}
  if (msg.type === 'force_logout') {
    ElMessage.warning(msg.message || '登录状态已失效，请重新登录')
    auth.user = null
    router.push('/login')
    return
  }
  if (msg.type === 'chat' && !chatOpen.value) {
    chatUnread.value += 1
    ElMessage({ message: `📩 ${msg.from_name}：${msg.content}`, type: 'info', showClose: true, duration: 4000 })
  }
}

function onSiteName(e) {
  if (e.detail) {
    siteName.value = e.detail
    document.title = `${e.detail} · 管理后台`
  }
}

watch(() => route.path, () => {
  if (drawerOpen.value) drawerOpen.value = false
})
watch(drawerOpen, (open) => {
  document.body.style.overflow = open && isMobile.value ? 'hidden' : ''
})

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', checkMobile)
  window.addEventListener('ws', onWsMsg)
  window.addEventListener('site-name', onSiteName)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  checkMobile()
  pollUnread()
  unreadTimer = setInterval(pollUnread, 60000)
  connectWS()
  try {
    const data = await http.get('/settings/public')
    siteName.value = data.site_name
    document.title = siteName.value ? `${siteName.value} · 管理后台` : '毕设接单管理系统'
  } catch { /* 忽略 */ }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', checkMobile)
  window.removeEventListener('ws', onWsMsg)
  window.removeEventListener('site-name', onSiteName)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.body.style.overflow = ''
  if (unreadTimer) clearInterval(unreadTimer)
  // 离开后台（登出或跳到公开页）时关掉长连接，避免留下一个不会退避的僵尸 socket
  closeWS()
})
</script>

<style scoped>
.layout { display: flex; min-height: 100vh; background: var(--bg); }

/* ===== 侧边栏 ===== */
.sidebar {
  width: var(--sidebar-w);
  flex-shrink: 0;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
  z-index: var(--z-sidebar);
  transition: width 0.25s cubic-bezier(0.22, 0.61, 0.36, 1);
  overflow: hidden;
  user-select: none;
}
.sidebar.collapsed { width: var(--sidebar-collapsed); }
.brand {
  display: flex; align-items: center; gap: 12px;
  height: var(--topbar-h); cursor: pointer; overflow: hidden; flex-shrink: 0;
  padding: 0 16px;
}
.brand-logo {
  width: 36px; height: 36px; flex-shrink: 0;
  border-radius: 10px;
  background: var(--brand-grad);
  color: #fff; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  font-size: 17px;
  box-shadow: var(--brand-glow);
}
.brand-copy { display: flex; flex-direction: column; min-width: 0; }
.brand-name {
  font-weight: 650; color: var(--text); font-size: 15px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.brand-sub {
  font-size: 9px; letter-spacing: 0.16em; color: var(--text-4);
  font-weight: 600; margin-top: 1px;
}
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.nav { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 6px 0; }
.art-menu {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: var(--text-2);
  --el-menu-hover-bg-color: var(--hover);
  --el-menu-active-color: var(--brand);
  border-right: none;
  width: 100%;
  padding: 2px 0;
}
.nav :deep(.el-menu-item),
.nav :deep(.el-sub-menu__title) {
  height: 42px !important;
  line-height: 42px !important;
  width: calc(100% - 16px);
  margin-left: 8px;
  margin-bottom: 3px;
  border-radius: var(--radius-xs);
  position: relative;
}
.nav :deep(.el-menu-item .menu-name),
.nav :deep(.el-sub-menu__title .menu-name) {
  font-size: 13.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.menu-icon {
  margin-right: 9px;
  margin-left: -6px;
  font-size: 19px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  transition: color 0.2s, transform 0.2s;
}
.nav :deep(.el-menu-item:hover .menu-icon),
.nav :deep(.el-sub-menu__title:hover .menu-icon) { color: var(--text); transform: scale(1.05); }
.nav :deep(.el-menu-item.is-active .menu-icon),
.nav :deep(.el-sub-menu.is-active > .el-sub-menu__title .menu-icon) { color: var(--brand); }
.nav :deep(.el-menu-item.is-active) { background: var(--brand-weak); color: var(--brand); font-weight: 600; }
.nav :deep(.el-menu-item.is-active)::before {
  content: ''; position: absolute; left: -8px; top: 9px; bottom: 9px; width: 3px;
  border-radius: 0 3px 3px 0; background: var(--brand);
}
.nav :deep(.el-sub-menu__title:hover),
.nav :deep(.el-menu-item:not(.is-active):hover) { background: var(--hover); }
.nav :deep(.el-sub-menu .el-menu) { background: transparent; }
.nav :deep(.el-sub-menu__icon-arrow) { font-size: 12px; width: 12px; margin-right: 4px; color: var(--text-4); }
.nav :deep(.el-menu--collapse .el-menu-item .menu-icon),
.nav :deep(.el-menu--collapse .el-sub-menu__title .menu-icon) { margin: 0; }

@keyframes menu-in { from { opacity: 0; transform: translateX(-12px); } to { opacity: 1; transform: none; } }
.nav :deep(.el-menu > li) { animation: menu-in 0.4s cubic-bezier(0.22, 0.61, 0.36, 1) both; }
.nav :deep(.el-menu > li:nth-child(1)) { animation-delay: 0.02s; }
.nav :deep(.el-menu > li:nth-child(2)) { animation-delay: 0.06s; }
.nav :deep(.el-menu > li:nth-child(3)) { animation-delay: 0.1s; }
.nav :deep(.el-menu > li:nth-child(4)) { animation-delay: 0.14s; }
.nav :deep(.el-menu > li:nth-child(5)) { animation-delay: 0.18s; }
.nav :deep(.el-menu > li:nth-child(6)) { animation-delay: 0.22s; }
.nav :deep(.el-menu > li:nth-child(n+7)) { animation-delay: 0.26s; }

.sidebar-foot {
  padding: 13px 18px; font-size: 11px; color: var(--text-4);
  display: flex; align-items: center; gap: 8px;
  white-space: nowrap; flex-shrink: 0;
}
.ver {
  background: var(--card-2); color: var(--text-3);
  border: 1px solid var(--border);
  border-radius: 5px; padding: 1px 6px; font-size: 10px;
}
.role { color: var(--text-4); }

/* ===== 顶栏 ===== */
.topbar {
  height: var(--topbar-h);
  background: var(--topbar-bg);
  backdrop-filter: blur(14px) saturate(1.2);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  position: sticky;
  top: 0;
  z-index: var(--z-topbar);
  flex-shrink: 0;
}
.tb-left { display: flex; align-items: center; gap: 12px; min-width: 0; overflow: hidden; }
.tb-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.tb-icon-btn {
  width: 34px; height: 34px;
  display: inline-flex; align-items: center; justify-content: center;
  border: none; background: transparent; cursor: pointer;
  border-radius: var(--radius-xs);
  color: var(--text-2); font-size: 19px;
  transition: background 0.2s, color 0.2s, transform 0.15s;
}
.tb-icon-btn:hover { background: var(--hover); color: var(--text); }
.tb-icon-btn:active { transform: scale(0.94); }

.tb-quick {
  height: 34px; padding: 0 12px;
  display: inline-flex; align-items: center; gap: 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--brand-weak-2);
  background: var(--brand-weak);
  color: var(--brand); font-size: 12.5px; font-weight: 600; cursor: pointer;
  white-space: nowrap; flex-shrink: 0;
  transition: all 0.18s;
}
.tb-quick:hover { background: var(--brand); color: #fff; border-color: var(--brand); box-shadow: var(--brand-glow); }

.tb-search {
  display: inline-flex; align-items: center; justify-content: space-between;
  width: 168px; height: 34px;
  padding: 0 9px;
  border: 1px solid var(--border-2);
  border-radius: var(--radius-sm);
  background: var(--card-2);
  cursor: pointer;
  color: var(--text-3); font-size: 12px;
  transition: border-color 0.2s, background 0.2s;
  gap: 6px;
}
.tb-search:hover { border-color: var(--brand); background: var(--brand-weak); }
.ts-icon { font-size: 14px; }
.ts-text { flex: 1; text-align: left; }
.ts-kbd {
  font-size: 9.5px; color: var(--text-3);
  border: 1px solid var(--border-2); border-radius: 4px;
  padding: 0 4px; height: 19px;
  display: inline-flex; align-items: center;
}

.bot-btn, .chat-btn { position: relative; }
.bot-dot, .chat-dot {
  position: absolute; top: 5px; right: 5px;
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--success);
}
.chat-badge {
  position: absolute; top: 0; right: -1px;
  min-width: 15px; height: 15px; padding: 0 4px;
  border-radius: 8px;
  background: var(--danger); color: #fff;
  font-size: 9.5px; font-weight: 600; line-height: 15px; text-align: center;
  box-shadow: 0 0 0 2px var(--topbar-bg);
}

.user-avatar-wrap { cursor: pointer; padding: 2px; margin-left: 4px; }
.avatar {
  width: 34px; height: 34px; border-radius: 50%;
  background: var(--brand-grad);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 14px;
  transition: box-shadow 0.2s;
}
.user-avatar-wrap:hover .avatar { box-shadow: 0 0 0 3px var(--brand-weak); }
.um-head { display: flex; align-items: center; gap: 12px; padding: 12px 16px 8px; }
.um-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: var(--brand-grad); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 17px;
}
.um-name { font-size: 14px; font-weight: 600; color: var(--text); }
.um-role { font-size: 12px; color: var(--text-3); margin-top: 2px; }

.tb-breadcrumb { white-space: nowrap; }
.bc-home { color: var(--text-2); text-decoration: none; }
.bc-home:hover { color: var(--brand); }
.bc-group { color: var(--text-3); }
.bc-current { color: var(--text); font-weight: 500; }

/* ===== 主区域 ===== */
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.content {
  padding: var(--content-pad) var(--content-pad) 28px;
  width: 100%;
  max-width: var(--page-max);
  margin-inline: auto;
  flex: 1;
  min-width: 0;
}


/* ===== 4K / ultra-wide ===== */
@media (min-width: 2200px) {
  .brand { padding: 0 20px; gap: 14px; }
  .brand-logo { width: 42px; height: 42px; font-size: 20px; border-radius: 12px; }
  .brand-name { font-size: 16.5px; }
  .brand-sub { font-size: 10px; }
  .nav :deep(.el-menu-item),
  .nav :deep(.el-sub-menu__title) { height: 46px !important; line-height: 46px !important; margin-bottom: 4px; }
  .nav :deep(.el-menu-item .menu-name),
  .nav :deep(.el-sub-menu__title .menu-name) { font-size: 14.5px; }
  .menu-icon { height: 46px; font-size: 21px; margin-right: 11px; }
  .topbar { padding: 0 20px; }
  .tb-right { gap: 10px; }
  .tb-icon-btn { width: 38px; height: 38px; font-size: 21px; }
  .tb-quick { height: 38px; padding: 0 14px; font-size: 13.5px; }
  .tb-search { width: 210px; height: 38px; font-size: 13px; }
  .avatar { width: 38px; height: 38px; font-size: 15px; }
  .content { padding-bottom: 32px; }
}

@media (min-width: 3000px) {
  .brand { padding: 0 24px; gap: 16px; }
  .brand-logo { width: 48px; height: 48px; font-size: 23px; border-radius: 14px; }
  .brand-name { font-size: 18px; }
  .brand-sub { font-size: 11px; }
  .nav :deep(.el-menu-item),
  .nav :deep(.el-sub-menu__title) { height: 52px !important; line-height: 52px !important; margin-bottom: 5px; }
  .nav :deep(.el-menu-item .menu-name),
  .nav :deep(.el-sub-menu__title .menu-name) { font-size: 16px; }
  .menu-icon { height: 52px; font-size: 23px; margin-right: 13px; }
  .topbar { padding: 0 26px; }
  .tb-right { gap: 12px; }
  .tb-icon-btn { width: 44px; height: 44px; font-size: 24px; }
  .tb-quick { height: 44px; padding: 0 18px; font-size: 15px; }
  .tb-search { width: 250px; height: 44px; font-size: 14px; }
  .avatar { width: 44px; height: 44px; font-size: 17px; }
  .content { padding-bottom: 40px; }
}

@media (max-width: 1100px) {
  .tb-search { width: 128px; flex-shrink: 0; justify-content: flex-start; gap: 7px; }
  .ts-kbd { display: none; }
}
@media (min-width: 901px) and (max-width: 1000px) {
  .tb-breadcrumb .el-breadcrumb__item:nth-child(2) { display: none; }
}

/* ===== 移动端 ===== */
@media (max-width: 900px) {
  .sidebar {
    position: fixed;
    left: 0; top: 0;
    transform: translateX(-100%);
    transition: transform 0.24s cubic-bezier(0.22, 0.61, 0.36, 1);
    width: var(--sidebar-w) !important;
    box-shadow: none;
  }
  .sidebar.mobile-open { transform: translateX(0); box-shadow: 0 0 60px rgba(0, 0, 0, 0.55); }
  .sidebar-mask { position: fixed; inset: 0; background: var(--overlay); backdrop-filter: blur(2px); z-index: 55; }
  .content { padding: 12px 12px 24px; max-width: none; }
  .tb-breadcrumb { display: none; }
  .tb-search { display: none !important; }
  .tb-quick span { display: none; }
  .tb-quick { width: 34px; padding: 0; justify-content: center; }
}
@media (max-width: 640px) {
  .topbar { padding: 0 10px; }
  .tb-right { gap: 4px; }
  .tb-icon-btn { width: 32px; height: 32px; font-size: 18px; }
}
</style>

<style>
.menu-left-popper.el-popper { border-radius: var(--radius-md); overflow: hidden; }
.menu-left-popper .el-menu { border-radius: var(--radius-md); padding: 6px; background: var(--card-2); }
.menu-left-popper .el-menu .el-menu-item {
  height: 38px; line-height: 38px; border-radius: var(--radius-xs); margin-bottom: 2px;
  margin-left: 0; width: 100%;
}
.menu-left-popper .el-menu .el-menu-item:last-child { margin-bottom: 0; }
.menu-left-popper .el-menu .el-menu-item .menu-icon { margin-left: 0; height: 38px; }

/* AI 助手输入框单框兜底：即使上方规则失效也强制内层透明无边框 */
.ci-composer .el-textarea__inner {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  --el-input-border-color:transparent;
}
.ci-composer .el-textarea.is-focus .el-textarea__inner { box-shadow: none !important; }
.ci-composer .el-textarea {
  --el-input-bg-color:transparent;
  background: transparent !important;
}
</style>
