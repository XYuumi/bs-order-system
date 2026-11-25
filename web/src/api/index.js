import axios from 'axios'


// 默认 60s：普通接口超时能尽快失败并把错误抛给用户（原来 600s 会让 loading 卡十分钟）。
// 大文件上传/AI 生成等确实很慢的请求，在调用处单独传 { timeout: 0 } 或更大的值。
const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
  withCredentials: true,
})

http.interceptors.response.use(
  (resp) => resp.data,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail || error.message || '请求失败'
    // 主动取消（切换筛选、离开页面等）不算错误，静默丢弃
    if (error.code === 'ERR_CANCELED' || error.name === 'CanceledError') {
      return Promise.reject(error)
    }
    // 公开页（登录、报价单等）不做 401 跳转，避免把访客带到登录页；
    // 登录页由 Login.vue 自己提示「用户名或密码错误」，这里不重复弹框。
    const pathname = window.location.pathname
    const isPublicPage =
      pathname.startsWith('/login') || pathname.startsWith('/quote/') ||
      pathname.startsWith('/deliver/') || pathname.startsWith('/screen/') || pathname.startsWith('/rank/')
    if (status === 401) {
      if (!isPublicPage) window.location.href = '/login'
    } else if (status === 429) {
      ElMessage.warning(typeof detail === 'string' ? detail : '请求过于频繁，请稍后再试')
    } else {
      ElMessage.error(typeof detail === 'string' ? detail : '请求失败')
    }
    return Promise.reject(error)
  }
)

export default http
