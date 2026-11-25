<template>
  <el-drawer
    v-model="visible"
    :size="isMobile ? '100%' : 'min(860px, 94vw)'"
    direction="rtl"
    :with-header="false"
    class="chat-drawer"
  >
    <!-- 左：联系人 -->
    <div class="cd-contacts" :class="{ 'is-mobile-hidden': isMobile && peer }">
      <div class="cdc-head">
        <div>
          <div class="cdc-title">私信</div>
          <div class="cdc-sub">与平台、上下级代理互聊</div>
        </div>
        <button v-if="isMobile" class="cdc-close" title="关闭" @click="visible = false">
          <Icon icon="ri:close-line" />
        </button>
      </div>
      <div class="cdc-search">
        <Icon icon="ri:search-line" />
        <input v-model="keyword" placeholder="搜索联系人" />
      </div>
      <div class="cdc-list-wrap" v-loading="loadingContacts" element-loading-background="transparent">
        <div class="cdc-list">
          <div v-if="!filteredContacts.length && !loadingContacts" class="cdc-empty">
            暂无联系人<br /><span class="text-3">代理可联系平台与自己的上下级</span>
          </div>
          <div
            v-for="c in filteredContacts" :key="c.id"
            class="cdc-item" :class="{ active: peer?.id === c.id }"
            @click="selectPeer(c)"
          >
            <div class="cdc-avatar" :class="c.role">{{ (c.display_name || '?').slice(0, 1) }}
              <span class="cdc-online" :class="isRecent(c.last_login_at) ? 'on' : ''" />
            </div>
            <div class="cdc-main">
              <div class="cdc-row">
                <span class="cdc-name">{{ c.display_name }}</span>
                <span class="cdc-role" :class="c.role">{{ c.role_cn }}</span>
              </div>
              <div class="cdc-row">
                <span class="cdc-last">{{ c.last_content ? (c.last_from_me ? '我：' : '') + c.last_content : '开始对话吧' }}</span>
                <span v-if="c.unread" class="cdc-unread">{{ c.unread > 99 ? '99+' : c.unread }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 右：消息流 -->
    <div class="cd-thread" :class="{ 'is-mobile-hidden': isMobile && !peer }">
      <template v-if="peer">
        <div class="cdt-head">
          <div class="cdt-id">
            <button v-if="isMobile" class="cdt-back" title="返回联系人" @click="backToContacts">
              <Icon icon="ri:arrow-left-line" />
            </button>
            <div class="cdt-avatar" :class="peer.role">{{ (peer.display_name || '?').slice(0, 1) }}</div>
            <div class="cdt-info">
              <div class="cdt-name">{{ peer.display_name }}</div>
              <div class="cdt-status">
                <span class="cdt-dot" :class="isRecent(peer.last_login_at) ? 'on' : 'off'" />
                {{ isRecent(peer.last_login_at) ? '最近在线' : '离线' }} · {{ peer.role_cn }}
              </div>
            </div>
          </div>
          <button class="cdt-close" title="关闭" @click="visible = false"><Icon icon="ri:close-line" /></button>
        </div>
        <div class="cdt-body" ref="threadBody">
          <div v-if="loadingThread" class="cdt-loading" v-loading="true" element-loading-background="transparent"></div>
          <div v-else-if="!messages.length" class="cdt-empty">
            <div class="cdt-empty-icon"><Icon icon="ri:chat-3-line" /></div>
            <div>和 {{ peer.display_name }} 说点什么…</div>
            <span>消息仅你和对方可见</span>
          </div>
          <template v-else>
            <div v-for="m in messages" :key="m.id" class="msg" :class="{ me: m.from_id === myId }">
              <div class="msg-avatar" :class="{ me: m.from_id === myId }">
                {{ (m.from_id === myId ? myName : peer.display_name || '?').slice(0, 1) }}
              </div>
              <div class="msg-col">
                <div class="msg-meta">
                  <span class="msg-sender">{{ m.from_id === myId ? myName : peer.display_name }}</span>
                  <span class="msg-time">{{ fmtTime(m.created_at) }}</span>
                </div>
                <div class="msg-bubble">{{ m.content }}</div>
              </div>
            </div>
          </template>
        </div>
        <div class="cdt-input">
          <div class="cdt-composer">
            <el-input
              v-model="draft" class="cdt-field" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
              maxlength="2000" resize="none"
              :placeholder="`发消息给 ${peer.display_name}…`"
              @keydown.enter.exact.prevent="send()"
            />
            <button class="cdt-send" :disabled="!draft.trim() || sending" title="发送" aria-label="发送" @click="send()">
              <Icon icon="ri:send-plane-2-fill" />
            </button>
          </div>
          <div class="cdt-foot">
            <span><Icon icon="ri:corner-down-left-line" /> Enter 发送 · Shift + Enter 换行</span>
            <span>{{ draft.length }}/2000</span>
          </div>
        </div>
      </template>
      <div v-else class="cdt-nopeer">
        <button class="cdt-nopeer-close" title="关闭" @click="visible = false"><Icon icon="ri:close-line" /></button>
        <div class="cdt-empty-icon"><Icon icon="ri:message-3-line" /></div>
        <div>选择左侧联系人开始聊天</div>
        <span>支持平台、上级代理与下级代理</span>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import http from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const visible = defineModel('open', { default: false })
const emit = defineEmits(['unread'])

const contacts = ref([])
const peer = ref(null)
const messages = ref([])
const draft = ref('')
const keyword = ref('')
const loadingContacts = ref(false)
const loadingThread = ref(false)
const sending = ref(false)
const threadBody = ref(null)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 700)

function onResize() {
  isMobile.value = window.innerWidth < 700
}

const myId = computed(() => auth.user?.id)
const myName = computed(() => auth.user?.display_name || auth.user?.username || '我')
const filteredContacts = computed(() => {
  if (!keyword.value.trim()) return contacts.value
  const k = keyword.value.trim().toLowerCase()
  return contacts.value.filter((c) =>
    c.display_name.toLowerCase().includes(k) || c.username.toLowerCase().includes(k))
})

function isRecent(t) {
  if (!t) return false
  return Date.now() - new Date(t).getTime() < 15 * 60 * 1000
}
function fmtTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(5, 16)
}

async function loadContacts() {
  loadingContacts.value = true
  try {
    const data = await http.get('/messages/contacts')
    contacts.value = data.items
    emit('unread', data.total_unread || 0)
    // 当前会话对象刷新未读后重选
    if (peer.value) {
      const fresh = data.items.find((c) => c.id === peer.value.id)
      if (fresh) peer.value = { ...peer.value, ...fresh }
    }
  } finally {
    loadingContacts.value = false
  }
}

// 会话请求序号：快速切换联系人时，先发的请求可能后到，必须整段丢弃，
// 否则 A 的聊天记录会显示在 B 的会话里（且输入框还指向 B）。
let threadSeq = 0
async function loadThread(scroll = true) {
  if (!peer.value) return
  const seq = ++threadSeq
  const peerId = peer.value.id
  loadingThread.value = true
  try {
    const data = await http.get('/messages', { params: { user_id: peerId } })
    if (seq !== threadSeq) return
    messages.value = data.items
    if (scroll) scrollToBottom()
    // 已读上报后刷新未读
    const u = await http.get('/messages/unread')
    if (seq !== threadSeq) return
    emit('unread', u.unread || 0)
  } finally {
    if (seq === threadSeq) loadingThread.value = false
  }
}

function selectPeer(c) {
  threadSeq++ // 主动作废正在飞的旧会话请求
  peer.value = c
  messages.value = []
  loadThread()
}

function backToContacts() {
  threadSeq++
  peer.value = null
  messages.value = []
}

async function send() {
  const content = draft.value.trim()
  if (!content || !peer.value || sending.value) return
  sending.value = true
  try {
    const m = await http.post('/messages', { to_user_id: peer.value.id, content })
    messages.value.push(m)
    draft.value = ''
    scrollToBottom()
    // 刷新联系人列表（最后一条消息）
    const c = contacts.value.find((x) => x.id === peer.value.id)
    if (c) { c.last_content = content; c.last_from_me = true; c.last_at = m.created_at }
  } catch {
    // 错误提示由 axios 拦截器统一处理；恢复输入内容，方便重试
    draft.value = content
  } finally {
    sending.value = false
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (threadBody.value) threadBody.value.scrollTop = threadBody.value.scrollHeight
  })
}

// 打开时加载 + 慢速轮询兜底 + WebSocket 秒达
let timer = null
function onWs(e) {
  const msg = e.detail || {}
  if (msg.type !== 'chat' || !visible.value) return
  if (peer.value && msg.from_id === peer.value.id) loadThread()
  else loadContacts()
}
window.addEventListener('ws', onWs)

function stopPolling() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

watch(visible, (open) => {
  stopPolling()
  if (open) {
    loadContacts()
    // WebSocket 负责秒达，轮询只做断线兜底，间隔放宽到 60s 减少重复请求
    timer = setInterval(() => {
      if (!visible.value) {
        stopPolling()
        return
      }
      loadContacts()
      if (peer.value) loadThread(false)
    }, 60000)
  }
}, { immediate: true })
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => {
  stopPolling()
  window.removeEventListener('resize', onResize)
  window.removeEventListener('ws', onWs)
})
</script>

<style scoped>
:global(.chat-drawer .el-drawer__body) {
  display: flex;
  flex-direction: row;
  padding: 0;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--card);
}

/* 左栏联系人 */
.cd-contacts {
  width: 280px; flex: 0 0 280px; height: 100%; min-height: 0;
  background: var(--card-2);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
}
.cdc-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 10px; padding: 18px 16px 12px; flex-shrink: 0;
}
.cdc-title { font-size: 16px; font-weight: 600; letter-spacing: 0.2px; }
.cdc-sub { font-size: 12px; color: var(--text-3); margin-top: 3px; }
.cdc-close, .cdt-nopeer-close {
  width: 28px; height: 28px; border: none; background: transparent;
  border-radius: 8px; cursor: pointer; color: var(--text-3); font-size: 19px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.cdc-close:hover, .cdt-nopeer-close:hover { background: var(--hover); color: var(--text); }
.cdc-search {
  display: flex; align-items: center; gap: 8px;
  margin: 0 12px 10px; padding: 0 11px;
  height: 36px; border: 1px solid var(--border-2); border-radius: 10px;
  color: var(--text-3); font-size: 15px; flex-shrink: 0;
  background: var(--card);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.cdc-search:focus-within { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-weak); }
.cdc-search input {
  flex: 1; border: none; outline: none; background: transparent;
  color: var(--text); font-size: 13px; min-width: 0;
}
.cdc-list-wrap { flex: 1; min-height: 0; display: flex; }
.cdc-list { flex: 1; height: 100%; overflow-y: auto; padding: 0 8px 14px; }
.cdc-list::-webkit-scrollbar { width: 6px; }
.cdc-list::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 3px; }
.cdc-empty { text-align: center; padding: 54px 16px; font-size: 13px; color: var(--text-2); line-height: 2; }
.text-3 { color: var(--text-3); font-size: 12px; }
.cdc-item {
  display: flex; align-items: center; gap: 11px;
  padding: 10px; border-radius: 10px; cursor: pointer;
  transition: background 0.15s; margin-bottom: 2px;
}
.cdc-item:hover { background: var(--hover); }
.cdc-item.active { background: var(--brand-weak); box-shadow: inset 2px 0 0 var(--brand); }
.cdc-avatar {
  width: 40px; height: 40px; border-radius: 12px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 15px; color: #fff;
  background: var(--brand-grad); position: relative;
}
.cdc-avatar.admin { background: var(--danger); }
.cdc-avatar.staff { background: var(--success); }
.cdc-online {
  position: absolute; right: -1px; bottom: -1px;
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--text-3); border: 2px solid var(--card-2);
}
.cdc-online.on { background: var(--success); }
.cdc-main { flex: 1; min-width: 0; }
.cdc-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.cdc-name { font-size: 13.5px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cdc-role {
  font-size: 10.5px; padding: 0 6px; border-radius: 5px; flex-shrink: 0;
  background: var(--hover); color: var(--text-3);
}
.cdc-role.admin { background: var(--danger-weak); color: var(--danger); }
.cdc-role.staff { background: var(--success-weak); color: var(--success); }
.cdc-last {
  font-size: 12px; color: var(--text-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}
.cdc-unread {
  min-width: 17px; height: 17px; padding: 0 5px; border-radius: 9px;
  background: var(--danger); color: #fff; font-size: 10.5px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
}

/* 右栏消息流 */
.cd-thread { flex: 1; min-width: 0; height: 100%; min-height: 0; display: flex; flex-direction: column; background: var(--card); }
.cdt-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 13px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  background: var(--card);
}
.cdt-id { display: flex; align-items: center; gap: 10px; min-width: 0; }
.cdt-avatar {
  width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--brand-grad); color: #fff; font-size: 13px; font-weight: 700;
}
.cdt-avatar.admin { background: var(--danger); }
.cdt-avatar.staff { background: var(--success); }
.cdt-info { min-width: 0; }
.cdt-name { font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cdt-status { font-size: 12px; color: var(--text-3); display: flex; align-items: center; gap: 5px; margin-top: 2px; }
.cdt-dot { width: 7px; height: 7px; border-radius: 50%; }
.cdt-dot.on { background: var(--success); }
.cdt-dot.off { background: var(--text-3); }
.cdt-back {
  width: 30px; height: 30px; border: none; background: transparent;
  border-radius: 8px; cursor: pointer; color: var(--text-2); font-size: 19px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.cdt-back:hover { background: var(--hover); color: var(--text); }
.cdt-close {
  width: 30px; height: 30px; border: none; background: transparent;
  border-radius: 8px; cursor: pointer; color: var(--text-3); font-size: 19px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.cdt-close:hover { background: var(--hover); color: var(--text); }

.cdt-body {
  flex: 1; min-height: 0; overflow-y: auto; padding: 20px 18px;
  display: flex; flex-direction: column; gap: 16px;
  background: var(--card);
}
.cdt-body::-webkit-scrollbar { width: 6px; }
.cdt-body::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 3px; }
.cdt-loading, .cdt-empty, .cdt-nopeer {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; color: var(--text-3); font-size: 13px; text-align: center;
}
.cdt-empty span, .cdt-nopeer span { font-size: 12px; color: var(--text-3); opacity: 0.8; }
.cdt-empty-icon {
  width: 54px; height: 54px; border-radius: 16px; margin-bottom: 2px;
  background: var(--brand-weak); color: var(--brand); font-size: 25px;
  display: flex; align-items: center; justify-content: center;
}
.cdt-nopeer { position: relative; }
.cdt-nopeer-close { position: absolute; top: 0; right: 0; }

.msg { display: flex; gap: 9px; align-items: flex-start; }
.msg.me { flex-direction: row-reverse; }
.msg-avatar {
  width: 30px; height: 30px; border-radius: 9px; flex-shrink: 0;
  background: var(--hover); color: var(--text-2);
  font-size: 13px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
}
.msg-avatar.me { background: var(--brand-grad); color: #fff; }
.msg-col { max-width: 76%; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.msg.me .msg-col { align-items: flex-end; }
.msg-meta { display: flex; gap: 6px; font-size: 11px; color: var(--text-3); padding: 0 2px; }
.msg.me .msg-meta { flex-direction: row-reverse; }
.msg-sender { font-weight: 500; }
.msg-bubble {
  padding: 9px 13px; border-radius: 12px;
  background: var(--card-2); border: 1px solid var(--border);
  font-size: 13px; line-height: 1.65; word-break: break-word; white-space: pre-wrap;
  border-bottom-left-radius: 4px;
}
.msg.me .msg-bubble {
  background: var(--brand); border-color: transparent; color: #fff;
  border-bottom-left-radius: 12px; border-bottom-right-radius: 4px;
}

/* 底部输入区：始终贴在抽屉底部 */
.cdt-input {
  padding: 12px 14px 10px; border-top: 1px solid var(--border);
  flex-shrink: 0; background: var(--card);
}
.cdt-composer {
  display: flex; align-items: flex-end; gap: 8px;
  padding: 6px 6px 6px 12px; border: 1px solid var(--border-2);
  border-radius: 14px; background: var(--card-2);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.cdt-composer:focus-within { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-weak); }
.cdt-field { flex: 1; min-width: 0; }
.cdt-field :deep(.el-textarea__inner) {
  background: transparent; border: none; box-shadow: none;
  padding: 5px 0; min-height: 28px !important;
  font-size: 13px; line-height: 1.6; color: var(--text);
}
.cdt-field :deep(.el-textarea__inner::placeholder) { color: var(--text-3); }
.cdt-send {
  width: 34px; height: 34px; border: none; border-radius: 10px;
  background: var(--brand); color: #fff; font-size: 17px;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; flex-shrink: 0; transition: filter 0.15s, transform 0.15s;
}
.cdt-send:hover:not(:disabled) { filter: brightness(1.1); transform: translateY(-1px); }
.cdt-send:disabled { opacity: 0.35; cursor: default; }
.cdt-foot {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-top: 6px; padding: 0 4px;
  font-size: 11px; color: var(--text-3);
}
.cdt-foot span { display: inline-flex; align-items: center; gap: 4px; }

@media (max-width: 700px) {
  .cd-contacts { width: 100%; flex-basis: 100%; border-right: none; }
  .cd-thread { width: 100%; }
  .is-mobile-hidden { display: none !important; }
  .cdc-head { padding: 16px 14px 10px; }
  .cdc-item { padding: 9px 8px; }
  .cdt-head { padding: 11px 12px; }
  .cdt-body { padding: 16px 12px; gap: 14px; }
  .cdt-input { padding: 10px 10px 8px; }
  .msg-col { max-width: 84%; }
  .cdt-foot span:first-child { display: none; }
  .cdt-foot { justify-content: flex-end; }
}
</style>
