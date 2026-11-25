import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../layouts/AdminLayout.vue'),
    children: [
      { path: '', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '工作台' } },
      { path: 'orders', name: 'orders', component: () => import('../views/OrderList.vue'), meta: { title: '订单管理' } },
      { path: 'orders/board', name: 'order-board', component: () => import('../views/OrderBoard.vue'), meta: { title: '生产看板' } },
      { path: 'orders/calendar', name: 'order-calendar', component: () => import('../views/OrderCalendar.vue'), meta: { title: '订单日历' } },
      { path: 'orders/create', name: 'order-create', component: () => import('../views/OrderCreate.vue'), meta: { title: '新建订单', roles: ['admin', 'agent'] } },
      { path: 'orders/:id', name: 'order-detail', component: () => import('../views/OrderDetail.vue'), meta: { title: '订单详情' } },
      { path: 'orders/:id/doc', name: 'doc-editor', component: () => import('../views/DocEditor.vue'), meta: { title: '需求书编辑', roles: ['admin', 'staff', 'agent'] } },
      { path: 'logs', name: 'logs', component: () => import('../views/LogsView.vue'), meta: { title: '操作日志', roles: ['admin', 'staff'] } },
      { path: 'users', name: 'users', component: () => import('../views/UsersView.vue'), meta: { title: '用户管理', roles: ['admin'] } },
      { path: 'settings', redirect: '/settings/general' },
      { path: 'settings/general', name: 'set-general', component: () => import('../views/settings/General.vue'), meta: { title: '通用设置', roles: ['admin'] } },
      { path: 'settings/pricing', name: 'set-pricing', component: () => import('../views/settings/Pricing.vue'), meta: { title: '价格与品质', roles: ['admin'] } },
      { path: 'settings/ai', name: 'set-ai', component: () => import('../views/settings/AiCenter.vue'), meta: { title: 'AI 中心', roles: ['admin'] } },
      { path: 'settings/integration', name: 'set-integration', component: () => import('../views/settings/Integration.vue'), meta: { title: '集成通知', roles: ['admin'] } },
      { path: 'settings/security', name: 'set-security', component: () => import('../views/settings/Security.vue'), meta: { title: '安全设置', roles: ['admin'] } },
      { path: 'settings/backup', name: 'set-backup', component: () => import('../views/settings/Backup.vue'), meta: { title: '数据备份', roles: ['admin'] } },
      { path: 'api-docs', name: 'api-docs', component: () => import('../views/ApiDocs.vue'), meta: { title: 'API 对接' } },
      { path: 'settlement', name: 'settlement', component: () => import('../views/SettlementView.vue'), meta: { title: '对账单', roles: ['admin', 'agent'] } },
      { path: 'suggestions', name: 'suggestions', component: () => import('../views/Suggestions.vue'), meta: { title: '建议反馈' } },
      { path: 'templates', name: 'templates', component: () => import('../views/Templates.vue'), meta: { title: '模板库' } },
      { path: 'writer-perf', name: 'writer-perf', component: () => import('../views/WriterPerf.vue'), meta: { title: '写手绩效', roles: ['admin', 'staff'] } },
      { path: 'ai', name: 'ai-copilot', component: () => import('../views/AiCopilot.vue'), meta: { title: 'AI 参谋', roles: ['admin', 'staff'] } },
      { path: 'margin', name: 'margin', component: () => import('../views/MarginView.vue'), meta: { title: '毛利分析', roles: ['admin'] } },
      { path: 'health', name: 'health', component: () => import('../views/Health.vue'), meta: { title: '系统健康', roles: ['admin'] } },
      { path: 'customers', name: 'customers', component: () => import('../views/Customers.vue'), meta: { title: '客户管理' } },
      { path: 'announcements', name: 'announcements', component: () => import('../views/Announcements.vue'), meta: { title: '公告管理', roles: ['admin'] } },
      { path: 'trash', name: 'trash', component: () => import('../views/TrashView.vue'), meta: { title: '回收站', roles: ['admin'] } },
      { path: 'profile', name: 'profile', component: () => import('../views/Profile.vue'), meta: { title: '个人中心' } },
      { path: '403', name: 'forbidden', component: () => import('../views/Forbidden.vue'), meta: { title: '无权访问' } },
    ],
  },
  { path: '/quote/:token', name: 'quote', component: () => import('../views/QuoteView.vue'), meta: { public: true, title: '服务报价单' } },
  { path: '/deliver/:token', name: 'deliver', component: () => import('../views/DeliverView.vue'), meta: { public: true, title: '客户交付' } },
  { path: '/screen/:token', name: 'screen', component: () => import('../views/ScreenView.vue'), meta: { public: true, title: '经营大屏' } },
  { path: '/rank/:token', name: 'rank', component: () => import('../views/RankView.vue'), meta: { public: true, title: '代理业绩榜' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../views/NotFound.vue'), meta: { public: true, title: '页面不存在' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) await auth.fetchMe()
  if (to.meta.public) {
    if (auth.user) return to.path === '/login' ? { path: '/' } : true
    return true
  }
  if (!auth.user) return { path: '/login' }
  if (to.meta.roles && !to.meta.roles.includes(auth.user.role)) {
    ElMessage.warning('没有访问该页面的权限')
    // 跳到 403 页而不是静默回首页，用户才能知道是「权限不足」而不是「链接坏了」
    return { name: 'forbidden', query: { from: to.fullPath } }
  }
  return true
})

export default router
