import { defineStore } from 'pinia'
import http from '../api'
import router from '../router'
import { closeWS } from '../utils/ws'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    loaded: false,
  }),
  getters: {
    isAgent: (s) => s.user?.role === 'agent',
    isStaffView: (s) => s.user && ['admin', 'staff'].includes(s.user.role),
    isAdmin: (s) => s.user?.role === 'admin',
    // 角色名称优先显示管理员自定义的角色标签（role_label），没有才用默认叫法
    roleName: (s) => s.user?.role_label || ({ admin: '管理员', staff: '写手', agent: '代理' }[s.user?.role] || '-'),
  },
  actions: {
    async fetchMe() {
      try {
        const data = await http.get('/auth/session')
        this.user = data.user || null
      } catch {
        this.user = null
      } finally {
        this.loaded = true
      }
    },
    async login(username, password, totp_code) {
      const payload = { username, password }
      if (totp_code) payload.totp_code = totp_code
      const data = await http.post('/auth/login', payload)
      // 已开启两步验证但未带动态码：后端返回 {totp_required: true}，由登录页进入第二步
      if (data.totp_required) return data
      this.user = data.user
      // 登录后已经拿到用户信息，避免首屏路由守卫再打一次 /auth/session
      this.loaded = true
      return data
    },
    async logout() {
      closeWS()
      await http.post('/auth/logout').catch(() => {})
      this.user = null
      // 清理只在当前会话有效的本地缓存（AI 摘要含客户信息与报价口径）
      try {
        Object.keys(sessionStorage)
          .filter((k) => k.startsWith('ai-sum-'))
          .forEach((k) => sessionStorage.removeItem(k))
      } catch { /* 隐私模式下忽略 */ }
      router.push('/login')
    },
  },
})
