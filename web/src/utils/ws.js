/** WebSocket 实时推送客户端：通知/私信秒达。
 *
 * Cookie 是 HttpOnly，JS 无法读取；由后端在握手时校验。登录后调用 connectWS()，
 * 退出登录调用 closeWS()。断线按 2s/5s/10s/30s 退避重连；4401 表示会话失效，停止重连。
 */
let ws = null
let retryTimer = null
let heartbeatTimer = null
let retryDelay = 2000
let manualClose = false

export function connectWS() {
  if (typeof window === 'undefined') return
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  manualClose = false

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  try {
    ws = new WebSocket(`${proto}://${location.host}/ws`)
  } catch {
    scheduleReconnect()
    return
  }

  ws.onopen = () => {
    retryDelay = 2000
    if (heartbeatTimer) clearInterval(heartbeatTimer)
    heartbeatTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
    }, 30000)
  }
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'pong') return
      window.dispatchEvent(new CustomEvent('ws', { detail: msg }))
    } catch { /* 非 JSON 忽略 */ }
  }
  ws.onclose = (ev) => {
    ws = null
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
    if (ev.code === 4401) {
      window.dispatchEvent(new CustomEvent('ws', {
        detail: { type: 'force_logout', message: '登录状态已失效，请重新登录' },
      }))
      return
    }
    if (ev.code === 4403) return
    if (!manualClose) scheduleReconnect()
  }
  ws.onerror = () => {
    try { ws?.close() } catch { /* 忽略 */ }
  }
}

export function closeWS() {
  manualClose = true
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null }
  if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
  try { ws?.close(1000, 'client logout') } catch { /* 忽略 */ }
  ws = null
  retryDelay = 2000
}

function scheduleReconnect() {
  if (retryTimer || manualClose) return
  retryTimer = setTimeout(() => {
    retryTimer = null
    if (!document.hidden) connectWS()
    else scheduleReconnect()
  }, retryDelay)
  retryDelay = Math.min(retryDelay * 1.8, 30000)
}

// 页面从后台切回前台时立刻重连（浏览器可能已静默断开 socket）。
// 用 typeof 判断而不是 document?.，后者在 document 未声明的环境会抛 ReferenceError。
const onVisibilityChange = () => {
  if (!document.hidden && !manualClose) connectWS()
}
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', onVisibilityChange)
}
