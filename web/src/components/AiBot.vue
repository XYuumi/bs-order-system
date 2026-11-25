<template>
  <el-drawer
    v-model="visible"
    :size="isMobile ? '100%' : '480px'"
    direction="rtl"
    :with-header="false"
    class="bot-drawer"
  >
    <!-- 头部 -->
    <div class="ch-head">
      <div class="ch-id">
        <div class="ch-avatar"><Icon icon="ri:robot-2-fill" /></div>
        <div class="ch-info">
          <div class="ch-name">毕设助手</div>
          <div class="ch-status">
            <span class="ch-dot" :class="!aiChecked ? 'wait' : (aiReady ? 'on' : 'off')" />
            <span>{{ !aiChecked ? '检测中…' : (aiReady ? '在线 · 随时待命' : '离线（AI 未配置）') }}</span>
          </div>
        </div>
      </div>
      <button class="ch-clear" title="清空对话记录" @click="clearChat"><Icon icon="ri:eraser-line" /></button>
      <button class="ch-close" title="关闭" @click="visible = false"><Icon icon="ri:close-line" /></button>
    </div>

    <div class="ch-body">
      <!-- 消息区 -->
      <div class="chat-body" ref="chatBody">
        <!-- 欢迎屏 -->
        <div v-if="!messages.length" class="chat-welcome">
          <div class="cw-icon"><Icon icon="ri:robot-2-fill" /></div>
          <div class="cw-title">你好，我是毕设助手</div>
          <div class="cw-sub">除了答疑，还能直接帮你查订单、建订单、改状态、看经营数据</div>
          <div class="cw-suggestions">
            <button v-for="s in suggestions" :key="s" class="cw-chip" @click="send(s)">{{ s }}</button>
          </div>
        </div>

        <template v-for="(msg, i) in messages" :key="i">
          <div class="msg" :class="{ me: msg.role === 'user' }">
            <div class="msg-avatar" :class="{ me: msg.role === 'user' }">
              <Icon v-if="msg.role === 'assistant'" icon="ri:robot-2-fill" />
              <template v-else>{{ myInitial }}</template>
            </div>
            <div class="msg-col">
              <div class="msg-meta">
                <span class="msg-sender">{{ msg.role === 'user' ? myName : '毕设助手' }}</span>
                <span class="msg-time">{{ fmtTime(msg.at) }}</span>
              </div>
              <!-- 工具动作胶囊 -->
              <div v-if="msg.role === 'assistant' && msg.actions?.length" class="msg-actions">
                <div v-for="(a, j) in msg.actions" :key="j" class="action-chip" :class="a.ok ? 'ok' : 'fail'">
                  <Icon :icon="actionIcon(a.name)" />
                  <span>{{ a.summary }}</span>
                </div>
              </div>
              <div class="msg-bubble" :class="{ me: msg.role === 'user' }">
                <div v-if="msg.role === 'assistant'" class="msg-text md" v-html="renderMd(msg.content)"></div>
                <div v-else class="msg-text">{{ msg.content }}</div>
              </div>
            </div>
          </div>
        </template>

        <div v-if="loading" class="msg">
          <div class="msg-avatar"><Icon icon="ri:robot-2-fill" /></div>
          <div class="msg-col">
            <div class="msg-meta"><span class="msg-sender">毕设助手</span></div>
            <div class="msg-bubble typing">
              <span class="typing-dot" /><span class="typing-dot" /><span class="typing-dot" />
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区：紧凑 composer，始终贴底 -->
      <div class="chat-input">
        <div class="ci-composer">
          <el-input
            v-model="input"
            class="ci-field"
            :style="{ '--el-input-border-color': 'transparent', '--el-input-bg-color': 'transparent' }"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            maxlength="2000"
            resize="none"
            placeholder="输入消息，Enter 发送…"
            @keydown.enter.exact.prevent="send()"
          />
          <button class="ci-send" :disabled="!input.trim() || loading" title="发送" aria-label="发送" @click="send()">
            <Icon icon="ri:send-plane-2-fill" />
          </button>
        </div>
        <div class="ci-foot">
          <span class="ci-hint"><Icon icon="ri:flashlight-line" /> AI 可查单 / 建单 / 改状态</span>
          <span>{{ input.length }}/2000</span>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import http from '../api'
import { useAuthStore } from '../stores/auth'
import { Icon } from '@iconify/vue'

marked.setOptions({ breaks: true, gfm: true })

const ACTION_ICONS = {
  query_orders: 'ri:file-search-line',
  get_order_detail: 'ri:search-line',
  create_order: 'ri:file-add-line',
  update_order_status: 'ri:swap-line',
  get_stats: 'ri:line-chart-line',
  list_qualities: 'ri:price-tag-3-line',
}
function actionIcon(name) {
  return ACTION_ICONS[name] || 'ri:flashlight-line'
}
function renderMd(text) {
  if (!text) return ''
  const html = marked.parse(String(text))
  return DOMPurify.sanitize(html, { ADD_ATTR: ['target'] })
}
function fmtTime(at) {
  const d = at ? new Date(at) : new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const auth = useAuthStore()
const visible = defineModel('open', { default: false })
const messages = ref([])
const input = ref('')
const loading = ref(false)
const aiReady = ref(false)
const aiChecked = ref(false)
const chatBody = ref(null)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 640)

// 对话记录存在浏览器本地：刷新或下次打开还能接着看（只保留最近 200 条）；坏数据直接忽略
const CHAT_STORE_KEY = 'bs-ai-chat'
try {
  const saved = JSON.parse(localStorage.getItem(CHAT_STORE_KEY) || '[]')
  if (Array.isArray(saved) && saved.length) messages.value = saved.filter((m) => m && m.role && m.content).slice(-200)
} catch { /* 隐私模式或数据损坏时从空对话开始 */ }

function saveChat() {
  localStorage.setItem(CHAT_STORE_KEY, JSON.stringify(messages.value.slice(-200)))
}

function clearChat() {
  messages.value = []
  localStorage.removeItem(CHAT_STORE_KEY)
}

function onResize() {
  isMobile.value = window.innerWidth < 640
}

const myName = computed(() => auth.user?.display_name || auth.user?.username || '我')
const myInitial = computed(() => myName.value.slice(0, 1))

const suggestions = [
  '📊 这个月有多少订单？经营情况如何',
  '➕ 帮我建一单「校园二手交易平台」，蓝色品质，计算机类',
  '🔍 查一下包含「图书馆」的订单',
  '💰 绿色品质的价格是多少？',
  '❓ 写手能看到什么价格？',
]

function scrollToBottom() {
  nextTick(() => {
    setTimeout(() => {
      if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight
    }, 100)
  })
}

async function send(text) {
  const content = (text || input.value).trim()
  if (!content || loading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content, at: new Date().toISOString() })
  scrollToBottom()
  saveChat()

  loading.value = true
  try {
    const data = await http.post('/chat', {
      messages: messages.value.slice(-10).map((m) => ({ role: m.role, content: m.content })),
    }, { timeout: 90000 })
    messages.value.push({ role: 'assistant', content: data.reply, actions: data.actions || [], at: new Date().toISOString() })
    saveChat()
  } catch (err) {
    // 发送失败：恢复输入内容，方便用户重试
    input.value = content
    const detail = err?.response?.data?.detail
    messages.value.push({ role: 'assistant', content: `抱歉，AI 暂时无法回复：${typeof detail === 'string' ? detail : '请稍后再试'}`, at: new Date().toISOString() })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

onMounted(async () => {
  window.addEventListener('resize', onResize)
  try {
    const data = await http.get('/settings/public')
    aiReady.value = !!data.ai_ready
  } catch {
    aiReady.value = false
  } finally {
    aiChecked.value = true
  }
})

onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
:global(.bot-drawer .el-drawer__body) {
  padding: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--card);
}

/* ===== 头部 ===== */
.ch-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  flex-shrink: 0; background: var(--card);
}
.ch-id { display: flex; align-items: center; gap: 10px; min-width: 0; }
.ch-avatar {
  width: 38px; height: 38px; border-radius: 12px; flex-shrink: 0;
  background: var(--brand-grad); color: #fff; font-size: 20px;
  display: flex; align-items: center; justify-content: center;
}
.ch-info { min-width: 0; }
.ch-name { font-size: 15.5px; font-weight: 600; }
.ch-status {
  margin-top: 2px; display: flex; align-items: center; gap: 5px;
  font-size: 12px; color: var(--text-3);
}
.ch-dot { width: 7px; height: 7px; border-radius: 50%; }
.ch-dot.on { background: var(--success); animation: art-breathe 1.5s ease-in-out infinite; }
.ch-dot.off { background: var(--danger); }
.ch-dot.wait { background: var(--text-3); }
.ch-close {
  width: 30px; height: 30px; border: none; background: transparent;
  border-radius: 8px; cursor: pointer; color: var(--text-3); font-size: 19px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.ch-close:hover { background: var(--hover); color: var(--text); }

/* ===== 主体：消息区 + 输入区 ===== */
.ch-body {
  display: flex; flex-direction: column;
  flex: 1; min-height: 0; overflow: hidden;
}

/* 消息区 */
.chat-body {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 20px 16px;
  display: flex; flex-direction: column; gap: 18px;
}
.chat-body::-webkit-scrollbar { width: 6px; }
.chat-body::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 3px; }

/* 欢迎屏 */
.chat-welcome { text-align: center; padding: 24px 10px 12px; }
.cw-icon {
  width: 56px; height: 56px; margin: 0 auto 14px; border-radius: 16px;
  background: var(--brand-weak); color: var(--brand); font-size: 26px;
  display: flex; align-items: center; justify-content: center;
}
.cw-title { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
.cw-sub { font-size: 12.5px; color: var(--text-2); margin-bottom: 18px; line-height: 1.7; }
.cw-suggestions { display: flex; flex-direction: column; gap: 8px; align-items: stretch; }
.cw-chip {
  padding: 9px 14px; border-radius: 10px; text-align: left;
  border: 1px solid var(--border-2); background: var(--card-2);
  color: var(--text-2); font-size: 12.5px; cursor: pointer;
  transition: all 0.15s;
}
.cw-chip:hover { border-color: var(--brand); color: var(--brand); background: var(--brand-weak); transform: translateY(-1px); }

/* 消息行 */
.msg { display: flex; align-items: flex-start; gap: 8px; }
.msg.me { flex-direction: row-reverse; }
.msg-avatar {
  width: 30px; height: 30px; border-radius: 9px; flex-shrink: 0;
  background: var(--brand-grad); color: #fff; font-size: 14px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.msg-avatar.me { background: var(--hover); color: var(--text-2); border: 1px solid var(--border); }
.msg-col { max-width: 82%; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.msg.me .msg-col { align-items: flex-end; }
.msg-meta { display: flex; gap: 8px; font-size: 11.5px; color: var(--text-3); padding: 0 2px; }
.msg.me .msg-meta { flex-direction: row-reverse; }
.msg-sender { font-weight: 500; }

/* 气泡 */
.msg-bubble {
  padding: 9px 13px;
  border-radius: 12px;
  font-size: 13px; line-height: 1.6;
  word-break: break-word;
  background: var(--card-2);
  border: 1px solid var(--border);
  color: var(--text);
  border-bottom-left-radius: 4px;
}
.msg-bubble.me {
  background: var(--brand); color: #fff;
  border-color: transparent;
  border-bottom-left-radius: 12px;
  border-bottom-right-radius: 4px;
}
.msg-bubble .msg-text { white-space: pre-wrap; }
.msg-bubble:not(.me) .msg-text { white-space: normal; }

/* 工具动作胶囊 */
.msg-actions { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 2px; }
.action-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; padding: 4px 10px; border-radius: 14px;
  border: 1px solid transparent;
}
.action-chip.ok { background: var(--success-weak); color: var(--success); border-color: color-mix(in srgb, var(--success) 25%, transparent); }
.action-chip.fail { background: var(--danger-weak); color: var(--danger); border-color: color-mix(in srgb, var(--danger) 25%, transparent); }

.msg-bubble.typing { display: flex; gap: 4px; align-items: center; padding: 14px; width: fit-content; }
.typing-dot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--text-3);
  animation: typing 1.2s ease-in-out infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.15s; }
.typing-dot:nth-child(3) { animation-delay: 0.3s; }
@keyframes typing { 0%,60%,100% { transform: translateY(0); opacity: 0.4; } 30% { transform: translateY(-4px); opacity: 1; } }

/* ===== 底部输入区 ===== */
.chat-input { padding: 12px 14px 10px; border-top: 1px solid var(--border); flex-shrink: 0; background: var(--card); }
.ci-composer {
  display: flex; align-items: flex-end; gap: 8px;
  padding: 6px 6px 6px 12px; border: 1px solid var(--border-2);
  border-radius: 14px; background: var(--card-2);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ci-composer:focus-within { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-weak); }
.ci-field { flex: 1; min-width: 0; }
.ci-field :deep(.el-textarea__inner) {
  background: transparent; border: none; box-shadow: none;
  padding: 5px 0; min-height: 28px !important;
  font-size: 13px; line-height: 1.6; color: var(--text);
}
.ci-field :deep(.el-textarea__inner::placeholder) { color: var(--text-3); }
.ci-send {
  width: 34px; height: 34px; border: none; border-radius: 10px;
  background: var(--brand); color: #fff; font-size: 17px;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; flex-shrink: 0; transition: filter 0.15s, transform 0.15s;
}
.ci-send:hover:not(:disabled) { filter: brightness(1.1); transform: translateY(-1px); }
.ci-send:disabled { opacity: 0.35; cursor: default; }
.ci-foot {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-top: 6px; padding: 0 4px;
  font-size: 11px; color: var(--text-3);
}
.ci-hint { display: inline-flex; align-items: center; gap: 4px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Markdown 内容样式 */
.md :deep(p) { margin: 0 0 6px; }
.md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(ul), .md :deep(ol) { margin: 4px 0; padding-left: 18px; }
.md :deep(li) { margin: 2px 0; }
.md :deep(strong) { color: var(--brand); font-weight: 600; }
.md :deep(code) {
  background: var(--card-3); border-radius: 4px; padding: 1px 5px;
  font-size: 12px; font-family: var(--font-mono);
}
.md :deep(pre) {
  background: var(--code-bg); border: 1px solid var(--code-border); border-radius: 8px; padding: 10px 12px;
  overflow-x: auto; margin: 6px 0;
}
.md :deep(pre code) { background: transparent; padding: 0; }
.md :deep(table) { border-collapse: collapse; margin: 6px 0; font-size: 12.5px; width: 100%; display: block; overflow-x: auto; }
.md :deep(th), .md :deep(td) { border: 1px solid var(--border); padding: 4px 8px; text-align: left; white-space: nowrap; }
.md :deep(th) { background: var(--card-2); }
.md :deep(blockquote) {
  margin: 6px 0; padding: 4px 10px; border-left: 3px solid var(--brand);
  background: var(--brand-weak); border-radius: 0 6px 6px 0; color: var(--text-2);
}
.md :deep(a) { color: var(--brand); text-decoration: none; }
.md :deep(a:hover) { text-decoration: underline; }
.md :deep(h1), .md :deep(h2), .md :deep(h3), .md :deep(h4) {
  font-size: 13.5px; font-weight: 600; margin: 8px 0 4px; color: var(--text);
}
.md :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 8px 0; }

@media (max-width: 640px) {
  .ch-head { padding: 12px 14px; }
  .chat-body { padding: 16px 12px; gap: 16px; }
  .chat-input { padding: 10px 10px 8px; }
  .msg-col { max-width: 86%; }
  .ci-hint { display: none; }
  .ci-foot { justify-content: flex-end; }
  .cw-sub { font-size: 12px; }
  .cw-chip { font-size: 12px; }
}

</style>
