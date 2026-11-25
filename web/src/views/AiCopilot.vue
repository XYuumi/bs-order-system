<template>
  <div class="page-shell ai-page">
    <section class="ai-hero">
      <div class="hero-glow hero-glow-a"></div>
      <div class="hero-glow hero-glow-b"></div>
      <div class="hero-copy">
        <div class="eyebrow">
          <span class="live-dot"></span>
          AI OPERATIONS · 深度参谋
          <span class="chip mini" :class="aiReady ? 'ok' : 'warn'">{{ aiReady ? '模型就绪' : '未配置模型' }}</span>
        </div>
        <h2>让每一单，都有 AI 盯着。</h2>
        <p>交付风险雷达、需求书体检、客户回访与验收清单，把 AI 嵌进接单到交付的每一步，而不是只做一句摘要。</p>
        <div class="hero-actions">
          <el-button type="primary" :loading="briefLoading" @click="runBrief">
            <Icon icon="ri:sparkling-2-line" />生成今日作战简报
          </el-button>
          <el-button :loading="loading" @click="load">
            <Icon icon="ri:refresh-line" />刷新态势
          </el-button>
        </div>
      </div>
      <div class="hero-side">
        <div class="hero-orb">
          <div class="orb-ring ring-a"></div>
          <div class="orb-ring ring-b"></div>
          <div class="orb-core">
            <b>{{ stats.active }}</b>
            <span>在制订单</span>
          </div>
        </div>
        <div class="hero-mini">
          <div><b class="danger">{{ stats.high }}</b><span>高风险</span></div>
          <div><b class="warn">{{ stats.due_7 }}</b><span>7 天内到期</span></div>
          <div><b>{{ stats.avg_score }}</b><span>平均风险分</span></div>
        </div>
      </div>
    </section>

    <section v-if="brief" class="art-card brief-card">
      <div class="brief-head">
        <div class="brief-icon"><Icon icon="ri:radar-line" /></div>
        <div class="brief-title">
          <h3>{{ brief.headline }}</h3>
          <p>{{ brief.summary }}</p>
        </div>
        <button class="icon-close" title="收起" @click="brief = null"><Icon icon="ri:close-line" /></button>
      </div>
      <div v-if="brief.priorities?.length" class="brief-list">
        <div v-for="(p, i) in brief.priorities" :key="p.order_id + i" class="brief-item">
          <span class="brief-rank">{{ i + 1 }}</span>
          <div class="brief-main">
            <div class="brief-line">
              <router-link :to="'/orders/' + p.order_id" class="mono">{{ p.order_id }}</router-link>
              <span class="brief-order">{{ p.title }}</span>
              <span class="urgency" :class="p.urgency">{{ URGENCY[p.urgency] || '今日' }}</span>
            </div>
            <p><b>下一步</b>{{ p.action }}<span class="why">· {{ p.reason }}</span></p>
          </div>
        </div>
      </div>
      <div v-else class="brief-none">当前没有在制订单，AI 建议先沉淀交付模板与验收清单。</div>
    </section>

    <div class="stat-grid ai-stats">
      <StatCard label="在制订单" :value="stats.active" icon="ri:radar-line" color="#6366f1" :loading="loading" sub="待开始 / 制作中 / 已完成" />
      <StatCard label="高风险" :value="stats.high" icon="ri:error-warning-line" color="#ef4444" :loading="loading" sub="风险分 ≥ 60" />
      <StatCard label="7 天内到期" :value="stats.due_7" icon="ri:timer-flash-line" color="#f59e0b" :loading="loading" sub="含逾期订单" />
      <StatCard label="需求书缺失" :value="stats.no_requirement" icon="ri:file-text-line" color="#8b5cf6" :loading="loading" sub="阻碍交付与验收" />
    </div>

    <section class="art-card risk-panel">
      <div class="panel-head">
        <div class="panel-title">
          <div class="panel-icon"><Icon icon="ri:pulse-line" /></div>
          <div>
            <h3>交付风险雷达</h3>
            <p>期限、负责人、需求书、交付物、客户验收多维规则打分，AI 只负责解释与排序，不虚构数据。</p>
          </div>
        </div>
        <span class="chip">{{ stats.active }} 单在制 · {{ stats.overdue }} 单逾期</span>
      </div>

      <div v-if="risks.length" class="risk-list">
        <article v-for="r in risks" :key="r.order_id" class="risk-row">
          <div class="risk-score" :class="r.risk_level">
            <b>{{ r.risk_score }}</b>
            <span>{{ RISK_LEVEL[r.risk_level] }}</span>
          </div>
          <div class="risk-main">
            <div class="risk-line">
              <router-link :to="'/orders/' + r.order_id" class="mono order-link">{{ r.order_id }}</router-link>
              <span class="status-dot" :class="r.status">{{ r.status_label }}</span>
              <span class="risk-cat">{{ r.project_type_label }}</span>
            </div>
            <h4>{{ r.title || '未填写题目' }}</h4>
            <div class="reason-tags">
              <span v-for="reason in r.reasons" :key="reason.code" class="reason-tag" :class="reason.level">
                {{ reason.label }}
              </span>
              <span v-if="!r.reasons.length" class="reason-tag safe">暂无风险信号</span>
            </div>
          </div>
          <div class="risk-deadline">
            <span class="muted">交付期限</span>
            <b :class="{ overdue: r.days_left != null && r.days_left < 0 }">{{ r.deadline || '未设置' }}</b>
            <span v-if="r.days_left != null" class="days" :class="{ overdue: r.days_left < 0 }">
              {{ r.days_left < 0 ? '已逾期 ' + Math.abs(r.days_left) + ' 天' : '剩余 ' + r.days_left + ' 天' }}
            </span>
          </div>
          <div class="risk-ops">
            <el-button size="small" :loading="toolLoading === 'review:' + r.order_id" @click="runReview(r.order_id)">
              <Icon icon="ri:file-text-line" />需求书体检
            </el-button>
            <el-button size="small" text @click="openReply(r.order_id)">写回访</el-button>
            <el-button size="small" text @click="runAcceptance(r.order_id)">验收清单</el-button>
          </div>
        </article>
      </div>

      <div v-else class="risk-empty">
        <EmptyState compact icon="ri:shield-check-line" title="当前没有在制订单" description="所有订单都已交付或归档。AI 仍可对历史订单做需求书体检、回访与验收复盘。" />
        <div v-if="recent.length" class="recent-strip">
          <div class="recent-head"><span>最近交付</span><span class="muted">可继续做交付复盘或客户回访</span></div>
          <div class="recent-grid">
            <button v-for="o in recent" :key="o.order_id" class="recent-card" @click="selectOrder(o.order_id)">
              <div class="recent-top">
                <span class="mono">{{ o.order_id }}</span>
                <span class="chip mini">{{ o.project_type_label }}</span>
              </div>
              <b>{{ o.title }}</b>
              <div class="recent-foot">
                <span>{{ o.status_label }}</span>
                <span :class="o.customer_accepted ? 'ok-text' : 'muted'">{{ o.customer_accepted ? '客户已验收' : '客户未验收' }}</span>
                <span class="muted">{{ o.closed_at || '—' }}</span>
              </div>
            </button>
          </div>
        </div>
      </div>
    </section>

    <section class="art-card workbench">
      <div class="panel-head">
        <div class="panel-title">
          <div class="panel-icon violet"><Icon icon="ri:magic-line" /></div>
          <div>
            <h3>AI 工具台</h3>
            <p>选一单作为上下文，四类深度能力直接产出可执行结果。</p>
          </div>
        </div>
        <el-select
          v-model="toolOrder" filterable placeholder="选择订单作为 AI 上下文"
          class="order-select" :teleported="true"
        >
          <el-option
            v-for="o in orders" :key="o.order_id" :value="o.order_id"
            :label="o.order_id + ' · ' + o.title"
          >
            <div class="opt-row"><span class="mono">{{ o.order_id }}</span><span class="opt-title">{{ o.title }}</span><span class="muted">{{ o.status_label }}</span></div>
          </el-option>
        </el-select>
      </div>

      <div v-if="currentOrder" class="context-bar">
        <span class="context-label">当前上下文</span>
        <router-link :to="'/orders/' + currentOrder.order_id" class="mono">{{ currentOrder.order_id }}</router-link>
        <span class="context-title">{{ currentOrder.title }}</span>
        <span class="chip mini">{{ currentOrder.status_label }}</span>
      </div>

      <div class="tool-grid">
        <button class="tool-card" :disabled="!toolOrder || !!toolLoading" @click="runReview(toolOrder)">
          <span class="tool-icon blue"><Icon icon="ri:file-text-line" /></span>
          <b>需求书体检</b>
          <p>从清晰度、完整性、技术方案、可测试性等 6 个维度评分，指出最该改的地方。</p>
          <span class="tool-go"><Icon icon="ri:arrow-right-up-line" />开始体检</span>
        </button>
        <button class="tool-card" :disabled="!toolOrder || !!toolLoading" @click="openReply(toolOrder)">
          <span class="tool-icon green"><Icon icon="ri:message-3-line" /></span>
          <b>客户回访话术</b>
          <p>结合订单状态与交付节点，生成开场、催进度、风险沟通或验收后的回访消息。</p>
          <span class="tool-go"><Icon icon="ri:arrow-right-up-line" />生成话术</span>
        </button>
        <button class="tool-card" :disabled="!toolOrder || !!toolLoading" @click="runAcceptance(toolOrder)">
          <span class="tool-icon amber"><Icon icon="ri:clipboard-line" /></span>
          <b>验收清单</b>
          <p>把需求书转成客户能逐项勾选的验收/测试清单，附答辩演示备忘。</p>
          <span class="tool-go"><Icon icon="ri:arrow-right-up-line" />生成清单</span>
        </button>
        <button class="tool-card" :disabled="briefLoading || !!toolLoading" @click="runBrief">
          <span class="tool-icon violet"><Icon icon="ri:radar-line" /></span>
          <b>今日作战简报</b>
          <p>汇总全部在制订单的风险排序，给出今天先做哪一单、具体做什么。</p>
          <span class="tool-go"><Icon icon="ri:arrow-right-up-line" />生成简报</span>
        </button>
      </div>
    </section>

    <el-drawer v-model="reviewVisible" title="AI 需求书体检" size="620px" class="ai-drawer">
      <div v-if="review" class="review-body">
        <div class="score-row">
          <div class="score-ring" :style="{ '--pct': review.score }">
            <b>{{ review.score }}</b><span>综合分</span>
          </div>
          <div class="score-copy">
            <h4>{{ currentOrder?.title }}</h4>
            <p>{{ review.summary }}</p>
            <div class="score-metrics">
              <span>{{ review.metrics?.chars || 0 }} 字</span>
              <span>{{ review.metrics?.sections || 0 }} 章节</span>
              <span>{{ review.metrics?.numbers || 0 }} 处量化</span>
              <span v-if="review.metrics?.has_acceptance" class="ok-text">含验收</span>
              <span v-else class="warn-text">缺验收</span>
            </div>
          </div>
        </div>
        <div class="review-actions">
          <el-button size="small" @click="goDoc"><Icon icon="ri:edit-line" />去修改需求书</el-button>
          <span class="muted">优先改评分最低的维度，保存后重新体检</span>
        </div>
        <div class="dim-grid">
          <div v-for="d in review.dimensions" :key="d.key" class="dim-row">
            <div class="dim-top"><span>{{ d.label }}</span><b>{{ d.score }}</b></div>
            <div class="dim-bar"><i :style="{ width: d.score + '%', background: scoreColor(d.score) }"></i></div>
            <p>{{ d.comment }}</p>
          </div>
        </div>
        <div v-if="review.highlights?.length" class="issue-block">
          <h5><Icon icon="ri:check-line" />做得好的地方</h5>
          <ul><li v-for="(h, i) in review.highlights" :key="i">{{ h }}</li></ul>
        </div>
        <div v-if="review.issues?.length" class="issue-block">
          <h5><Icon icon="ri:error-warning-line" />优先修改</h5>
          <div v-for="(it, i) in review.issues" :key="i" class="issue-item" :class="it.severity">
            <div class="issue-head"><span class="sev">{{ SEVERITY[it.severity] || '建议' }}</span><b>{{ it.title }}</b></div>
            <p>{{ it.detail }}</p>
            <div class="suggest"><span>建议</span>{{ it.suggestion }}</div>
          </div>
        </div>
      </div>
      <div v-else class="drawer-loading" v-loading="true" element-loading-text="AI 正在逐项审阅需求书…"></div>
    </el-drawer>

    <el-drawer v-model="replyVisible" title="AI 客户回访" size="560px" class="ai-drawer">
      <div class="reply-config">
        <el-radio-group v-model="replyScene" size="small">
          <el-radio-button v-for="(v, k) in SCENES" :key="k" :value="k">{{ v }}</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="replyTone" size="small">
          <el-radio-button value="warm">亲切</el-radio-button>
          <el-radio-button value="professional">专业</el-radio-button>
          <el-radio-button value="concise">简洁</el-radio-button>
        </el-radio-group>
        <el-button type="primary" size="small" :loading="replyLoading" @click="runReply">生成 / 重新生成</el-button>
      </div>
      <div v-if="reply" class="reply-body">
        <div class="reply-bubble">{{ reply.message }}</div>
        <div class="reply-tools">
          <el-button size="small" @click="copy(reply.message)"><Icon icon="ri:file-copy-line" />复制话术</el-button>
          <el-button size="small" :loading="replySaving" @click="saveReplyNote"><Icon icon="ri:sticky-note-line" />记录到跟进</el-button>
          <span v-if="reply.suggested_time" class="muted"><Icon icon="ri:time-line" />{{ reply.suggested_time }}</span>
        </div>
        <div v-if="reply.tips?.length" class="tip-block">
          <h5>发送提示</h5>
          <p v-for="(t, i) in reply.tips" :key="i"><span>{{ i + 1 }}</span>{{ t }}</p>
        </div>
      </div>
      <div v-else class="reply-placeholder">
        <Icon icon="ri:message-3-line" />
        <p>选择场景与语气后生成，可复制到微信或飞书直接发送。</p>
      </div>
    </el-drawer>

    <el-drawer v-model="acceptanceVisible" title="AI 验收清单" size="680px" class="ai-drawer">
      <div v-if="acceptance" class="acceptance-body">
        <div class="acceptance-tools">
          <el-button size="small" @click="copy(acceptance)"><Icon icon="ri:file-copy-line" />复制 Markdown</el-button>
          <span class="muted">可直接粘贴到文档，或逐项发给客户确认</span>
        </div>
        <div class="md-body" v-html="renderMd(acceptance)"></div>
      </div>
      <div v-else class="drawer-loading" v-loading="true" element-loading-text="AI 正在根据需求书生成验收清单…"></div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { Icon } from '@iconify/vue'
import http from '../api'
import EmptyState from '../components/ui/EmptyState.vue'
import StatCard from '../components/StatCard.vue'

marked.setOptions({ breaks: true, gfm: true })

const RISK_LEVEL = { high: '高风险', medium: '关注', low: '安全' }
const URGENCY = { now: '立即', today: '今天', this_week: '本周' }
const SEVERITY = { high: '严重', medium: '中等', low: '轻微' }
const SCENES = {
  kickoff: '开工问候', progress: '进度同步', risk: '风险沟通', acceptance: '验收提醒', aftersale: '售后关怀',
}

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const briefLoading = ref(false)
const toolLoading = ref('')
const data = ref({})
const brief = ref(null)

const toolOrder = ref('')
const reviewVisible = ref(false)
const review = ref(null)
const replyVisible = ref(false)
const reply = ref(null)
const replyLoading = ref(false)
const replySaving = ref(false)
const replyScene = ref('progress')
const replyTone = ref('warm')
const acceptanceVisible = ref(false)
const acceptance = ref('')

const stats = computed(() => data.value.stats || { active: 0, high: 0, medium: 0, due_7: 0, overdue: 0, no_requirement: 0, avg_score: 0 })
const risks = computed(() => data.value.risks || [])
const recent = computed(() => data.value.recent || [])
const orders = computed(() => data.value.order_options || [])
const aiReady = computed(() => !!data.value.ai_ready)
const currentOrder = computed(() => orders.value.find((o) => o.order_id === toolOrder.value) || null)

function renderMd(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(String(text)))
}
function scoreColor(n) {
  const v = Number(n || 0)
  if (v < 55) return '#ef4444'
  if (v < 75) return '#f59e0b'
  return '#10b981'
}
function selectOrder(id) {
  toolOrder.value = id
  document.querySelector('.workbench')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
async function copy(text) {
  try {
    await navigator.clipboard.writeText(String(text || ''))
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

async function load() {
  loading.value = true
  try {
    data.value = await http.get('/ai-ops/overview')
    const wanted = String(route.query.order || '').trim()
    if (wanted && orders.value.some((o) => o.order_id === wanted)) toolOrder.value = wanted
    else if (!toolOrder.value && orders.value.length) toolOrder.value = orders.value[0].order_id
  } catch {
    // 拦截器已提示；保留空态，避免未处理的 Promise 异常打断页面渲染
    data.value = {}
  } finally {
    loading.value = false
  }
}

async function runBrief() {
  if (briefLoading.value) return
  briefLoading.value = true
  try {
    brief.value = await http.post('/ai-ops/risk-brief', {}, { timeout: 120000 })
    ElMessage.success('作战简报已生成')
  } catch {
    // 超时或模型异常时保留上一份简报，错误提示由 axios 拦截器统一处理
  } finally {
    briefLoading.value = false
  }
}

function goDoc() {
  if (toolOrder.value) router.push('/orders/' + toolOrder.value + '/doc')
}

async function saveReplyNote() {
  if (!toolOrder.value || !reply.value?.message) return
  replySaving.value = true
  try {
    await http.post('/orders/' + toolOrder.value + '/notes', {
      content: '【AI 回访话术】' + String(reply.value.message)
    })
    ElMessage.success('已写入客户跟进记录')
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    replySaving.value = false
  }
}

function openReply(orderId) {
  if (orderId) toolOrder.value = orderId
  reply.value = null
  replyVisible.value = true
  if (!replyLoading.value) runReply()
}

async function runReply() {
  if (!toolOrder.value) return ElMessage.warning('请先选择订单')
  replyLoading.value = true
  try {
    reply.value = await http.post('/ai-ops/reply', {
      order_id: toolOrder.value, scene: replyScene.value, tone: replyTone.value,
    }, { timeout: 120000 })
  } catch {
    // 抽屉保留输入区，用户可直接重试；错误提示由 axios 拦截器统一处理
    reply.value = null
  } finally {
    replyLoading.value = false
  }
}

async function runReview(orderId) {
  const id = orderId || toolOrder.value
  if (!id) return ElMessage.warning('请先选择订单')
  toolOrder.value = id
  review.value = null
  reviewVisible.value = true
  toolLoading.value = 'review:' + id
  try {
    review.value = await http.post('/ai-ops/requirement-review', { order_id: id }, { timeout: 180000 })
  } catch {
    // 失败时关闭抽屉，避免 v-loading 永久转圈
    reviewVisible.value = false
  } finally {
    toolLoading.value = ''
  }
}

async function runAcceptance(orderId) {
  const id = orderId || toolOrder.value
  if (!id) return ElMessage.warning('请先选择订单')
  toolOrder.value = id
  acceptance.value = ''
  acceptanceVisible.value = true
  toolLoading.value = 'acceptance:' + id
  try {
    const res = await http.post('/ai-ops/acceptance', { order_id: id }, { timeout: 180000 })
    acceptance.value = res.markdown || ''
    if (!acceptance.value) ElMessage.warning('AI 未返回清单内容，请重试')
  } catch {
    // 失败时关闭抽屉，避免 v-loading 永久转圈
    acceptanceVisible.value = false
  } finally {
    toolLoading.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.ai-page { gap: 16px; }

.ai-hero {
  position: relative; overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg, 16px);
  padding: 30px 32px;
  display: flex; align-items: center; justify-content: space-between; gap: 28px;
  background:
    radial-gradient(900px 300px at 88% 10%, rgba(99, 102, 241, 0.22), transparent 60%),
    radial-gradient(700px 260px at 8% 100%, rgba(14, 165, 233, 0.14), transparent 62%),
    linear-gradient(120deg, var(--card-2), var(--card));
  min-height: 218px;
}
.hero-glow { position: absolute; border-radius: 50%; filter: blur(2px); pointer-events: none; }
.hero-glow-a { width: 300px; height: 300px; right: 120px; top: -170px; border: 1px solid rgba(129, 140, 248, 0.24); }
.hero-glow-b { width: 190px; height: 190px; right: 174px; top: -115px; border: 1px solid rgba(129, 140, 248, 0.16); }
.hero-copy { position: relative; z-index: 1; max-width: 760px; }
.eyebrow { display: flex; align-items: center; gap: 8px; font-size: 11px; letter-spacing: 0.12em; color: var(--text-3); font-weight: 600; }
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: #34d399; box-shadow: 0 0 0 4px rgba(52, 211, 153, 0.12); }
.chip.mini { font-size: 10px; padding: 1px 7px; letter-spacing: 0; }
.chip.ok { color: #10b981; border-color: rgba(16, 185, 129, 0.35); background: rgba(16, 185, 129, 0.08); }
.chip.warn { color: #f59e0b; border-color: rgba(245, 158, 11, 0.35); background: rgba(245, 158, 11, 0.08); }
.ai-hero h2 { margin: 14px 0 10px; font-size: clamp(25px, 2.2vw, 36px); line-height: 1.2; letter-spacing: -0.02em; color: var(--text); }
.ai-hero p { margin: 0; font-size: 13px; line-height: 1.8; color: var(--text-3); max-width: 660px; }
.hero-actions { display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap; }
.hero-side { position: relative; z-index: 1; flex: none; display: flex; flex-direction: column; align-items: center; gap: 16px; padding-right: 10px; }
.hero-orb { position: relative; width: 150px; height: 150px; display: grid; place-items: center; }
.orb-ring { position: absolute; border-radius: 50%; border: 1px solid rgba(129, 140, 248, 0.28); }
.ring-a { inset: 4px; animation: spin 18s linear infinite; border-style: dashed; }
.ring-b { inset: 18px; border-color: rgba(56, 189, 248, 0.22); }
.orb-core {
  width: 96px; height: 96px; border-radius: 50%;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: radial-gradient(circle at 32% 28%, rgba(129, 140, 248, 0.38), rgba(15, 23, 42, 0.12) 68%);
  border: 1px solid rgba(129, 140, 248, 0.34);
  box-shadow: inset 0 1px 18px rgba(129, 140, 248, 0.18), 0 10px 38px rgba(79, 70, 229, 0.18);
}
.orb-core b { font-size: 30px; line-height: 1; color: var(--text); font-variant-numeric: tabular-nums; }
.orb-core span { margin-top: 5px; font-size: 10px; color: var(--text-3); }
.hero-mini { display: flex; gap: 20px; }
.hero-mini div { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.hero-mini b { font-size: 16px; color: var(--text); }
.hero-mini b.danger { color: #ef4444; }
.hero-mini b.warn { color: #f59e0b; }
.hero-mini span { font-size: 10px; color: var(--text-4); }
@keyframes spin { to { transform: rotate(360deg); } }

.brief-card { padding: 18px 20px; border-color: rgba(99, 102, 241, 0.3); background: linear-gradient(120deg, rgba(99, 102, 241, 0.08), transparent 55%), var(--card); }
.brief-head { display: flex; align-items: flex-start; gap: 12px; }
.brief-icon { width: 38px; height: 38px; flex: none; border-radius: 10px; display: grid; place-items: center; font-size: 20px; color: #a5b4fc; background: rgba(99, 102, 241, 0.14); border: 1px solid rgba(99, 102, 241, 0.24); }
.brief-title { flex: 1; min-width: 0; }
.brief-title h3 { margin: 1px 0 5px; font-size: 15px; color: var(--text); }
.brief-title p { margin: 0; font-size: 12px; color: var(--text-3); line-height: 1.6; }
.icon-close { border: none; background: transparent; color: var(--text-4); cursor: pointer; font-size: 17px; padding: 2px; }
.brief-list { margin-top: 14px; display: grid; gap: 8px; }
.brief-item { display: flex; gap: 10px; padding: 10px 12px; border-radius: 10px; background: var(--card-2); border: 1px solid var(--border); }
.brief-rank { width: 20px; height: 20px; flex: none; border-radius: 6px; display: grid; place-items: center; font-size: 11px; font-weight: 700; color: #a5b4fc; background: rgba(99, 102, 241, 0.14); margin-top: 2px; }
.brief-main { min-width: 0; flex: 1; }
.brief-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.brief-line a { font-size: 11px; color: var(--brand); text-decoration: none; }
.brief-order { font-size: 12.5px; font-weight: 600; color: var(--text); }
.urgency { font-size: 10px; padding: 1px 6px; border-radius: 4px; color: #f59e0b; background: rgba(245, 158, 11, 0.1); }
.urgency.now { color: #ef4444; background: rgba(239, 68, 68, 0.1); }
.brief-main p { margin: 6px 0 0; font-size: 11.5px; color: var(--text-3); line-height: 1.6; }
.brief-main p b { color: var(--text-2); margin-right: 5px; }
.why { color: var(--text-4); }
.brief-none { margin-top: 12px; font-size: 12px; color: var(--text-3); }

.ai-stats { grid-template-columns: repeat(4, minmax(0, 1fr)); }

.risk-panel, .workbench { padding: 18px 20px; }
.panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.panel-title { display: flex; gap: 12px; align-items: flex-start; min-width: 0; }
.panel-icon { width: 38px; height: 38px; border-radius: 10px; flex: none; display: grid; place-items: center; color: #a5b4fc; font-size: 19px; background: rgba(99, 102, 241, 0.12); border: 1px solid rgba(99, 102, 241, 0.2); }
.panel-icon.violet { color: #c4b5fd; background: rgba(139, 92, 246, 0.11); border-color: rgba(139, 92, 246, 0.2); }
.panel-title h3 { margin: 0 0 5px; font-size: 15px; color: var(--text); }
.panel-title p { margin: 0; font-size: 11.5px; line-height: 1.6; color: var(--text-4); }

.risk-list { display: grid; gap: 9px; }
.risk-row {
  display: grid; grid-template-columns: 56px minmax(0, 1fr) 120px auto; gap: 14px; align-items: center;
  padding: 12px 14px; border-radius: 12px; background: var(--card-2); border: 1px solid var(--border);
  transition: border-color 0.18s, transform 0.18s;
}
.risk-row:hover { border-color: rgba(99, 102, 241, 0.34); transform: translateY(-1px); }
.risk-score { width: 52px; height: 52px; border-radius: 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 1px solid transparent; }
.risk-score b { font-size: 19px; line-height: 1; }
.risk-score span { margin-top: 3px; font-size: 9px; }
.risk-score.high { color: #f87171; background: rgba(239, 68, 68, 0.09); border-color: rgba(239, 68, 68, 0.24); }
.risk-score.medium { color: #fbbf24; background: rgba(245, 158, 11, 0.09); border-color: rgba(245, 158, 11, 0.24); }
.risk-score.low { color: #34d399; background: rgba(16, 185, 129, 0.09); border-color: rgba(16, 185, 129, 0.24); }
.risk-main { min-width: 0; }
.risk-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.order-link { font-size: 11px; color: var(--brand); text-decoration: none; }
.status-dot { font-size: 10px; color: var(--text-3); background: var(--card); border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; }
.status-dot.in_progress { color: #fbbf24; border-color: rgba(245, 158, 11, 0.28); }
.status-dot.pending { color: var(--text-3); }
.status-dot.completed, .status-dot.closed { color: #34d399; border-color: rgba(16, 185, 129, 0.28); }
.risk-cat { font-size: 10px; color: var(--text-4); }
.risk-main h4 { margin: 5px 0 6px; font-size: 13px; font-weight: 600; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reason-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.reason-tag { font-size: 10px; padding: 1px 6px; border-radius: 4px; background: var(--card); color: var(--text-3); border: 1px solid var(--border); }
.reason-tag.high { color: #f87171; border-color: rgba(239, 68, 68, 0.22); background: rgba(239, 68, 68, 0.07); }
.reason-tag.medium { color: #fbbf24; border-color: rgba(245, 158, 11, 0.22); background: rgba(245, 158, 11, 0.07); }
.reason-tag.safe { color: #34d399; }
.risk-deadline { display: flex; flex-direction: column; gap: 3px; font-size: 11px; }
.risk-deadline b { font-size: 12px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.risk-deadline b.overdue, .days.overdue { color: #f87171; }
.days { font-size: 10px; color: var(--text-4); }
.risk-ops { display: flex; gap: 2px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }

.risk-empty { padding: 6px 0 0; }
.recent-strip { margin-top: 18px; border-top: 1px dashed var(--border); padding-top: 14px; }
.recent-head { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; font-weight: 600; color: var(--text-2); margin-bottom: 10px; }
.recent-head .muted { font-weight: 400; font-size: 11px; }
.recent-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; }
.recent-card { text-align: left; border: 1px solid var(--border); background: var(--card-2); border-radius: 10px; padding: 11px 12px; cursor: pointer; color: inherit; transition: all 0.18s; }
.recent-card:hover { border-color: rgba(99, 102, 241, 0.38); background: rgba(99, 102, 241, 0.05); }
.recent-top { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.recent-top .mono { font-size: 10px; color: var(--brand); }
.recent-card > b { display: block; margin: 6px 0 8px; font-size: 11.5px; line-height: 1.45; color: var(--text); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; min-height: 32px; }
.recent-foot { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 9.5px; color: var(--text-4); }
.ok-text { color: #34d399; }
.warn-text { color: #fbbf24; }
.muted { color: var(--text-4); }

.workbench .order-select { width: 340px; flex: none; }
.opt-row { display: flex; align-items: center; gap: 8px; }
.opt-row .mono { font-size: 11px; color: var(--brand); flex: none; }
.opt-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; color: var(--text-2); }
.context-bar { display: flex; align-items: center; gap: 8px; padding: 9px 12px; border-radius: 9px; background: rgba(99, 102, 241, 0.06); border: 1px solid rgba(99, 102, 241, 0.16); margin-bottom: 12px; font-size: 11.5px; min-width: 0; }
.context-label { color: var(--text-4); font-size: 10px; flex: none; }
.context-bar a { color: var(--brand); text-decoration: none; flex: none; }
.context-title { color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.tool-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.tool-card {
  text-align: left; border: 1px solid var(--border); background: var(--card-2);
  border-radius: 12px; padding: 15px 15px 13px; cursor: pointer; color: inherit;
  display: flex; flex-direction: column; gap: 8px; min-height: 158px;
  transition: transform 0.18s, border-color 0.18s, box-shadow 0.18s;
}
.tool-card:hover:not(:disabled) { transform: translateY(-2px); border-color: rgba(99, 102, 241, 0.4); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12); }
.tool-card:disabled { opacity: 0.55; cursor: not-allowed; }
.tool-icon { width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center; font-size: 18px; }
.tool-icon.blue { color: #93c5fd; background: rgba(59, 130, 246, 0.12); }
.tool-icon.green { color: #6ee7b7; background: rgba(16, 185, 129, 0.12); }
.tool-icon.amber { color: #fcd34d; background: rgba(245, 158, 11, 0.12); }
.tool-icon.violet { color: #c4b5fd; background: rgba(139, 92, 246, 0.12); }
.tool-card > b { font-size: 13px; color: var(--text); }
.tool-card > p { margin: 0; flex: 1; font-size: 11px; line-height: 1.65; color: var(--text-4); }
.tool-go { font-size: 10.5px; color: var(--brand); display: inline-flex; align-items: center; gap: 3px; }

.review-body { display: flex; flex-direction: column; gap: 18px; }
.score-row { display: flex; gap: 18px; align-items: center; padding: 16px; border-radius: 12px; background: var(--card-2); border: 1px solid var(--border); }
.score-ring { width: 92px; height: 92px; flex: none; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; background: conic-gradient(#6366f1 calc(var(--pct) * 1%), rgba(148, 163, 184, 0.12) 0); position: relative; }
.score-ring::before { content: ''; position: absolute; inset: 7px; border-radius: 50%; background: var(--card); }
.score-ring b, .score-ring span { position: relative; z-index: 1; }
.score-ring b { font-size: 25px; line-height: 1; color: var(--text); }
.score-ring span { margin-top: 3px; font-size: 9px; color: var(--text-4); }
.score-copy { min-width: 0; }
.score-copy h4 { margin: 0 0 6px; font-size: 13px; color: var(--text); }
.score-copy p { margin: 0 0 8px; font-size: 12px; line-height: 1.7; color: var(--text-3); }
.score-metrics { display: flex; flex-wrap: wrap; gap: 10px; font-size: 10px; color: var(--text-4); }
.review-actions { display: flex; align-items: center; gap: 10px; margin: 12px 0 16px; flex-wrap: wrap; }
.review-actions .muted { font-size: 11px; }
.dim-grid { display: grid; gap: 13px; }
.dim-row { display: grid; gap: 4px; }
.dim-top { display: flex; justify-content: space-between; font-size: 11.5px; color: var(--text-2); }
.dim-top b { color: var(--text); }
.dim-bar { height: 5px; border-radius: 4px; background: rgba(148, 163, 184, 0.13); overflow: hidden; }
.dim-bar i { display: block; height: 100%; border-radius: 4px; }
.dim-row p { margin: 2px 0 0; font-size: 10.5px; color: var(--text-4); line-height: 1.6; }
.issue-block h5 { display: flex; align-items: center; gap: 5px; margin: 0 0 9px; font-size: 12px; color: var(--text-2); }
.issue-block ul { margin: 0; padding-left: 17px; font-size: 11.5px; line-height: 1.8; color: var(--text-3); }
.issue-item { border: 1px solid var(--border); border-left: 3px solid var(--border-2); border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; background: var(--card-2); }
.issue-item.high { border-left-color: #ef4444; }
.issue-item.medium { border-left-color: #f59e0b; }
.issue-head { display: flex; align-items: center; gap: 7px; }
.issue-head .sev { font-size: 9px; padding: 1px 5px; border-radius: 3px; color: #f87171; background: rgba(239, 68, 68, 0.1); flex: none; }
.issue-head b { font-size: 12px; color: var(--text); }
.issue-item p { margin: 6px 0; font-size: 11px; line-height: 1.65; color: var(--text-3); }
.suggest { font-size: 11px; line-height: 1.6; color: var(--text-2); background: var(--card); border-radius: 6px; padding: 7px 9px; }
.suggest span { color: #34d399; margin-right: 6px; font-weight: 600; }
.drawer-loading { height: 300px; }

.reply-config { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; align-items: center; }
.reply-body { display: flex; flex-direction: column; gap: 12px; }
.reply-bubble { white-space: pre-wrap; font-size: 13px; line-height: 1.9; color: var(--text-2); background: var(--card-2); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.reply-tools { display: flex; align-items: center; gap: 12px; font-size: 11px; }
.reply-tools .muted { display: inline-flex; align-items: center; gap: 4px; }
.tip-block { border-top: 1px dashed var(--border); padding-top: 12px; }
.tip-block h5 { margin: 0 0 8px; font-size: 11px; color: var(--text-3); }
.tip-block p { margin: 0 0 7px; display: flex; gap: 7px; font-size: 11.5px; line-height: 1.7; color: var(--text-3); }
.tip-block p span { width: 16px; height: 16px; flex: none; border-radius: 50%; display: grid; place-items: center; font-size: 9px; color: var(--brand); background: rgba(99, 102, 241, 0.12); margin-top: 2px; }
.reply-placeholder { padding: 60px 20px; text-align: center; color: var(--text-4); }
.reply-placeholder svg { font-size: 38px; opacity: 0.5; }
.reply-placeholder p { font-size: 12px; }

.acceptance-tools { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 11px; }
.md-body { font-size: 12.5px; line-height: 1.85; color: var(--text-2); }
.md-body :deep(h1), .md-body :deep(h2), .md-body :deep(h3) { color: var(--text); font-size: 14px; margin: 18px 0 8px; padding-bottom: 5px; border-bottom: 1px solid var(--border); }
.md-body :deep(h1) { font-size: 17px; }
.md-body :deep(ul), .md-body :deep(ol) { padding-left: 20px; }
.md-body :deep(li) { margin: 4px 0; }
.md-body :deep(table) { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 11.5px; }
.md-body :deep(th), .md-body :deep(td) { border: 1px solid var(--border); padding: 6px 8px; text-align: left; }
.md-body :deep(th) { background: var(--card-2); color: var(--text-3); }
.md-body :deep(code) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; background: var(--card-2); padding: 1px 5px; border-radius: 4px; color: #a5b4fc; }
.md-body :deep(blockquote) { margin: 10px 0; padding: 8px 12px; border-left: 3px solid var(--brand); background: rgba(99, 102, 241, 0.06); color: var(--text-3); }

@media (max-width: 1400px) {
  .recent-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .tool-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 1200px) {
  .ai-hero { padding: 24px; }
  .hero-side { display: none; }
  .risk-row { grid-template-columns: 52px minmax(0, 1fr) 108px; }
  .risk-ops { grid-column: 2 / -1; justify-content: flex-start; margin-top: 2px; }
}
@media (max-width: 900px) {
  .ai-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .risk-row { grid-template-columns: 48px minmax(0, 1fr); gap: 10px; }
  .risk-deadline { grid-column: 2; flex-direction: row; align-items: center; gap: 8px; }
  .risk-ops { grid-column: 2; }
  .recent-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .workbench .order-select { width: 100%; }
  .panel-head { flex-direction: column; }
  .panel-head > .order-select { margin-top: 2px; }
}
@media (max-width: 640px) {
  .ai-hero { padding: 20px 16px; min-height: 0; border-radius: 14px; }
  .ai-hero h2 { font-size: 24px; margin-top: 10px; }
  .ai-hero p { font-size: 12px; line-height: 1.7; }
  .hero-actions { margin-top: 14px; }
  .hero-actions .el-button { flex: 1; }
  .ai-stats { grid-template-columns: 1fr 1fr; gap: 10px; }
  .risk-panel, .workbench { padding: 14px; }
  .risk-row { grid-template-columns: 44px minmax(0, 1fr); padding: 11px; }
  .risk-score { width: 44px; height: 44px; border-radius: 10px; }
  .risk-score b { font-size: 16px; }
  .risk-main h4 { white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .risk-ops { flex-wrap: wrap; }
  .recent-grid, .tool-grid { grid-template-columns: 1fr; }
  .recent-card > b { min-height: 0; }
  .score-row { flex-direction: column; align-items: flex-start; }
  .reply-config :deep(.el-radio-group) { display: flex; flex-wrap: wrap; }
  .acceptance-tools { align-items: flex-start; flex-direction: column; gap: 6px; }
}
</style>

<style>
.ai-drawer.el-drawer { max-width: 94vw; }
@media (max-width: 640px) {
  .ai-drawer.el-drawer { max-width: 100vw; }
  .ai-drawer .el-drawer__body { padding: 14px; }
}
</style>
