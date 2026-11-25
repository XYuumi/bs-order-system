<template>
  <div class="deliver-page">
    <main class="dl-card art-card">
      <template v-if="data">
        <header class="dl-brand">
          <div class="dl-logo">{{ brandInitial }}</div>
          <div class="dl-brand-copy">
            <div class="dl-site">{{ data.site_name }}</div>
            <div class="dl-brand-sub">客户交付中心 · DELIVERY</div>
          </div>
          <span class="dl-private">
            <Icon icon="ri:shield-check-line" />
            私有交付链接
          </span>
        </header>

        <section class="dl-hero">
          <div class="dl-kicker">ORDER DELIVERY</div>
          <h1 class="dl-title">{{ data.order.title }}</h1>
          <div class="dl-meta">
            <span><Icon icon="ri:hashtag" /><span class="mono">{{ data.order.id }}</span></span>
            <span><Icon icon="ri:time-line" />更新于 {{ fmtDate(data.updated_at) }}</span>
            <span><Icon icon="ri:folder-3-line" />{{ files.length }} 个交付文件</span>
          </div>
        </section>

        <!-- 订单信息 / 验收状态 -->
        <section class="dl-overview">
          <div class="dl-info-card">
            <div class="di-head">
              <span class="di-icon"><Icon icon="ri:file-list-3-line" /></span>
              <span class="di-title">订单信息</span>
            </div>
            <div class="di-grid">
              <div class="di-item">
                <span>订单编号</span>
                <b class="mono">{{ data.order.id }}</b>
              </div>
              <div class="di-item">
                <span>交付截止</span>
                <b>{{ fmtDeadline(data.order.deadline) }}</b>
              </div>
              <div class="di-item">
                <span>最后更新</span>
                <b>{{ fmtDate(data.updated_at) }}</b>
              </div>
              <div class="di-item">
                <span>交付内容</span>
                <b>{{ files.length }} 个文件</b>
              </div>
            </div>
          </div>

          <div class="dl-status-card" :class="{ accepted }">
            <transition name="accept-pop" mode="out-in">
              <div :key="accepted ? 'accepted' : 'pending'" class="ds-body">
                <span class="ds-icon">
                  <Icon :icon="accepted ? 'ri:checkbox-circle-fill' : 'ri:time-line'" />
                </span>
                <div class="ds-copy">
                  <span class="ds-label">验收状态</span>
                  <strong class="ds-value">{{ accepted ? '已验收' : '待客户确认' }}</strong>
                  <span class="ds-desc">
                    {{ accepted
                      ? `${fmtAccept(data.order.accepted_at)} 已确认收到全部交付物`
                      : '请检查全部交付物，确认无误后点击验收' }}
                  </span>
                </div>
              </div>
            </transition>
            <span class="ds-glow" aria-hidden="true" />
          </div>
        </section>

        <!-- 验收操作条：未验收时展示，成功后平滑切换为已验收状态 -->
        <transition name="accept-pop">
          <div v-if="!accepted" class="dl-accept-bar">
            <div class="dl-accept-copy">
              <span class="dl-accept-title">确认交付内容无误？</span>
              <span class="dl-accept-hint">验收后订单将进入完成状态；如有问题请先联系对接人。</span>
            </div>
            <el-button
              type="success"
              size="large"
              class="dl-accept-btn"
              :loading="accepting"
              :disabled="accepting || confirming || accepted"
              @click="onAccept"
            >
              <Icon v-if="!accepting" icon="ri:checkbox-circle-line" class="dl-accept-ic" />
              确认验收
            </el-button>
          </div>
        </transition>

        <!-- 演示视频 -->
        <section v-if="videos.length" class="dl-section">
          <div class="dl-sec-head">
            <div class="dl-sec-title"><span class="sec-icon"><Icon icon="ri:play-circle-line" /></span>演示视频</div>
            <span class="chip">{{ videos.length }} 个</span>
          </div>
          <article v-for="f in videos" :key="f.id" class="dl-video">
            <div class="dl-video-frame">
              <video controls preload="metadata" playsinline :src="fileUrl(f)"></video>
            </div>
            <div class="dl-vinfo">
              <div class="dl-vinfo-main">
                <span class="dl-fname" :title="f.name">{{ f.name }}</span>
                <span class="dl-fmeta">
                  {{ fmtSize(f.size) }}<template v-if="f.remark"> · {{ f.remark }}</template>
                </span>
              </div>
              <!-- 带 ?download=1：点击即保存文件，而不是在浏览器里直接打开 -->
              <a
                class="dl-icon-btn"
                :href="fileUrl(f) + '?download=1'"
                :title="`下载 ${f.name}`"
                :aria-label="`下载 ${f.name}`"
              >
                <Icon icon="ri:download-2-line" />
              </a>
            </div>
          </article>
        </section>

        <!-- 交付包 -->
        <section v-if="packages.length" class="dl-section">
          <div class="dl-sec-head">
            <div class="dl-sec-title"><span class="sec-icon"><Icon icon="ri:file-zip-line" /></span>交付包</div>
            <span class="chip">{{ packages.length }} 个</span>
          </div>
          <div class="dl-file-list">
            <article v-for="f in packages" :key="f.id" class="dl-file">
              <div class="dl-ficon"><Icon :icon="fileIcon(f.name)" /></div>
              <div class="dl-finfo">
                <span class="dl-fname" :title="f.name">{{ f.name }}</span>
                <span class="dl-fmeta">
                  {{ fmtSize(f.size) }} · 上传于 {{ fmtDate(f.created_at) }}<template v-if="f.remark"> · {{ f.remark }}</template>
                </span>
              </div>
              <a class="dl-download" :href="fileUrl(f) + '?download=1'">
                <Icon icon="ri:download-2-line" /><span>下载</span>
              </a>
            </article>
          </div>
        </section>

        <EmptyState
          v-if="!files.length"
          compact
          icon="ri:inbox-archive-line"
          title="交付内容准备中"
          description="对接人上传后会自动出现在这里，请稍后再来看看"
        />

        <footer class="dl-foot">
          <p>链接仅包含您的交付内容，请勿转发给无关人员；播放视频可直接拖动进度条。</p>
          <p>下载遇到问题请联系您的对接人</p>
        </footer>
      </template>

      <div v-else-if="error" class="dl-state">
        <EmptyState icon="ri:lock-2-line" :title="error" description="请向对接人索取最新交付链接" />
      </div>

      <div v-else class="dl-skel" aria-busy="true">
        <div class="sk-brand">
          <div class="skeleton sk-logo" />
          <div class="sk-lines">
            <div class="skeleton sk-line w-140" />
            <div class="skeleton sk-line w-90" />
          </div>
        </div>
        <div class="skeleton sk-hero" />
        <div class="sk-pills">
          <div class="skeleton sk-pill" />
          <div class="skeleton sk-pill" />
          <div class="skeleton sk-pill" />
        </div>
        <div class="sk-overview">
          <div class="skeleton sk-card" />
          <div class="skeleton sk-card" />
        </div>
        <div class="skeleton sk-video" />
        <div v-for="i in 2" :key="i" class="skeleton sk-row" />
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'

import EmptyState from '../components/ui/EmptyState.vue'
import { useThemeStore } from '../stores/theme'

const route = useRoute()
useThemeStore()

const data = ref(null)
const error = ref('')
const accepting = ref(false)
const confirming = ref(false)

const files = computed(() => data.value?.files || [])
const videos = computed(() => files.value.filter((f) => f.category === 'video'))
const packages = computed(() => files.value.filter((f) => f.category === 'package'))
const accepted = computed(() => !!data.value?.order?.accepted_at)
const brandInitial = computed(() => (data.value?.site_name || '毕').slice(0, 1))

function fileUrl(f) {
  return `/api/deliver/${route.params.token}/files/${f.id}/download`
}

function fmtSize(n) {
  if (n == null) return '-'
  if (n < 1024) return n + ' B'
  if (n < 1024 ** 2) return (n / 1024).toFixed(1) + ' KB'
  if (n < 1024 ** 3) return (n / 1024 ** 2).toFixed(1) + ' MB'
  return (n / 1024 ** 3).toFixed(2) + ' GB'
}

function fmtDate(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : '-'
}

// 验收时间：MM-DD HH:mm
function fmtAccept(t) {
  return t ? String(t).replace('T', ' ').slice(5, 16) : ''
}

function fmtDeadline(t) {
  return t ? String(t).slice(0, 10) : '未设置'
}

// 交付包图标按扩展名做轻量区分，未知类型回退通用文件图标
function fileIcon(name) {
  const ext = String(name).split('.').pop()?.toLowerCase()
  return {
    zip: 'ri:file-zip-line',
    rar: 'ri:file-zip-line',
    '7z': 'ri:file-zip-line',
    pdf: 'ri:file-pdf-line',
    doc: 'ri:file-word-line',
    docx: 'ri:file-word-line',
    xls: 'ri:file-excel-line',
    xlsx: 'ri:file-excel-line',
    png: 'ri:image-line',
    jpg: 'ri:image-line',
    jpeg: 'ri:image-line',
    mp4: 'ri:video-line',
    mov: 'ri:video-line',
    txt: 'ri:file-text-line',
    md: 'ri:file-text-line',
  }[ext] || 'ri:file-3-line'
}

// 客户确认验收（该页为免登录公开页，沿用 fetch 直连 /api/deliver）
async function onAccept() {
  // 弹窗尚未关闭时的重复点击直接忽略
  if (accepting.value || confirming.value || accepted.value) return
  confirming.value = true
  try {
    await ElMessageBox.confirm('确认已收到全部交付物并验收通过？', '确认验收', {
      confirmButtonText: '确认验收',
      cancelButtonText: '再检查一下',
      type: 'success',
    })
  } catch {
    return
  } finally {
    confirming.value = false
  }
  // 确认弹窗期间可能已被验收或被重复触发
  if (accepting.value || accepted.value) return
  accepting.value = true
  try {
    const resp = await fetch(`/api/deliver/${route.params.token}/accept`, { method: 'POST' })
    const body = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      ElMessage.error(typeof body.detail === 'string' ? body.detail : '验收失败，请稍后重试')
      return
    }
    data.value.order.accepted_at = body.accepted_at || new Date().toISOString()
    if (body.already) {
      ElMessage.info('该订单已完成验收')
    } else {
      ElMessage.success('验收成功，感谢您的确认！')
    }
  } catch {
    ElMessage.error('网络异常，验收失败，请稍后重试')
  } finally {
    accepting.value = false
  }
}

onMounted(async () => {
  try {
    const resp = await fetch(`/api/deliver/${route.params.token}`)
    const body = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      error.value = typeof body.detail === 'string' ? body.detail : '交付链接加载失败'
      return
    }
    data.value = body
    document.title = `${body.order.title.slice(0, 20)} · 交付`
  } catch {
    error.value = '交付链接加载失败，请稍后重试'
  }
})
</script>

<style scoped>
.deliver-page {
  min-height: 100vh;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: clamp(18px, 4vw, 48px) 16px;
  overflow-x: hidden;
  background:
    radial-gradient(900px 500px at 88% -12%, color-mix(in srgb, var(--success) 9%, transparent), transparent 60%),
    radial-gradient(820px 480px at 0% 0%, color-mix(in srgb, var(--brand) 13%, transparent), transparent 58%),
    var(--bg);
}

.dl-card {
  position: relative;
  width: min(var(--deliver-max), 100%);
  padding: clamp(24px, 3.6vw, 36px);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--card) 93%, transparent);
  box-shadow: var(--shadow-pop);
  backdrop-filter: blur(16px);
  overflow: hidden;
  animation: rise-in 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
.dl-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: linear-gradient(90deg, transparent, var(--success), var(--brand), transparent);
  opacity: 0.86;
}

/* ===== 品牌头 ===== */
.dl-brand { display: flex; align-items: center; gap: 12px; }
.dl-logo {
  width: 42px; height: 42px; flex-shrink: 0;
  border-radius: 12px;
  background: var(--brand-grad);
  box-shadow: var(--brand-glow);
  color: #fff; font-size: 19px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.dl-brand-copy { min-width: 0; }
.dl-site { font-size: 15.5px; font-weight: 650; color: var(--text); }
.dl-brand-sub {
  margin-top: 2px;
  font-size: 10.5px; letter-spacing: 0.14em;
  color: var(--text-3); white-space: nowrap;
}
.dl-private {
  margin-left: auto; flex-shrink: 0;
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 11px;
  border: 1px solid color-mix(in srgb, var(--success) 26%, var(--border));
  border-radius: var(--radius-pill);
  background: var(--success-weak);
  color: var(--success);
  font-size: 11.5px; font-weight: 500;
  white-space: nowrap;
}
.dl-private .iconify { font-size: 13px; }

/* ===== 标题 ===== */
.dl-hero { margin: 26px 0 20px; }
.dl-kicker { font-size: 10.5px; letter-spacing: 0.18em; color: var(--text-3); }
.dl-title {
  margin: 8px 0 10px;
  font-size: clamp(22px, 3.2vw, 30px);
  font-weight: 750;
  line-height: 1.35;
  letter-spacing: 0.01em;
  color: var(--text);
}
.dl-meta {
  display: flex; flex-wrap: wrap; gap: 7px 16px;
  font-size: 12px; color: var(--text-3);
}
.dl-meta > span { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
.dl-meta .iconify { font-size: 14px; color: var(--brand); flex-shrink: 0; }

/* ===== 订单 / 验收状态卡 ===== */
.dl-overview {
  display: grid;
  grid-template-columns: 1.45fr 1fr;
  gap: 14px;
  margin-bottom: 18px;
}
.dl-info-card,
.dl-status-card {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--card-2);
  padding: 16px 18px;
}
.dl-info-card {
  background: linear-gradient(180deg, color-mix(in srgb, var(--brand) 5%, var(--card-2)), var(--card-2));
}
.di-head { display: flex; align-items: center; gap: 8px; margin-bottom: 13px; }
.di-icon {
  width: 28px; height: 28px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  background: var(--brand-weak); color: var(--brand); font-size: 15px;
}
.di-title { font-size: 13.5px; font-weight: 600; color: var(--text); }
.di-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 18px; }
.di-item { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.di-item span { font-size: 11.5px; color: var(--text-3); }
.di-item b {
  font-size: 13px; font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.dl-status-card {
  position: relative;
  display: flex;
  align-items: center;
  overflow: hidden;
  background: linear-gradient(135deg, color-mix(in srgb, var(--warning) 8%, var(--card-2)), var(--card-2));
  transition: border-color 0.3s ease, background 0.3s ease;
}
.dl-status-card.accepted {
  border-color: color-mix(in srgb, var(--success) 40%, var(--border));
  background: linear-gradient(135deg, var(--success-weak), var(--card-2));
}
.ds-body {
  position: relative; z-index: 1;
  display: flex; align-items: center; gap: 13px;
  min-width: 0;
}
.ds-icon {
  width: 44px; height: 44px; flex-shrink: 0;
  border-radius: 13px;
  display: flex; align-items: center; justify-content: center;
  background: var(--warning-weak); color: var(--warning);
  font-size: 22px;
}
.dl-status-card.accepted .ds-icon {
  background: var(--success-weak); color: var(--success);
  animation: success-pop 0.55s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.ds-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ds-label { font-size: 11px; letter-spacing: 0.06em; color: var(--text-3); }
.ds-value { font-size: 16px; font-weight: 700; color: var(--text); }
.dl-status-card.accepted .ds-value { color: var(--success); }
.ds-desc { font-size: 11.5px; color: var(--text-3); line-height: 1.5; }
.ds-glow {
  position: absolute;
  right: -46px; bottom: -54px;
  width: 130px; height: 130px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--warning-weak), transparent 70%);
  pointer-events: none;
}
.dl-status-card.accepted .ds-glow {
  background: radial-gradient(circle, var(--success-weak), transparent 70%);
}

/* ===== 验收操作条 ===== */
.dl-accept-bar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; flex-wrap: wrap;
  padding: 15px 18px;
  margin-bottom: 24px;
  border: 1px dashed color-mix(in srgb, var(--success) 38%, var(--border));
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--success) 6%, transparent);
}
.dl-accept-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.dl-accept-title { font-size: 13.5px; font-weight: 600; color: var(--text); }
.dl-accept-hint { font-size: 11.5px; color: var(--text-3); line-height: 1.5; }
.dl-accept-btn {
  height: 44px; padding: 0 28px;
  font-size: 14px; font-weight: 600; letter-spacing: 0.05em;
  border-radius: var(--radius);
  flex-shrink: 0;
}
.dl-accept-ic { font-size: 18px; margin-right: 6px; }

/* ===== 分区 ===== */
.dl-section { margin-bottom: 24px; }
.dl-sec-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-bottom: 12px;
}
.dl-sec-title {
  display: flex; align-items: center; gap: 9px;
  font-size: 14.5px; font-weight: 650; color: var(--text);
}
.sec-icon {
  width: 28px; height: 28px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  background: var(--brand-weak); color: var(--brand); font-size: 15px;
}

/* ===== 视频 ===== */
.dl-video {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--card-2);
  margin-bottom: 14px;
  transition: border-color 0.2s ease;
}
.dl-video:hover { border-color: var(--border-3); }
.dl-video-frame { background: #000; display: flex; justify-content: center; }
.dl-video video { width: 100%; max-height: 460px; display: block; }
.dl-vinfo {
  display: flex; align-items: center; gap: 12px;
  padding: 11px 14px;
  background: color-mix(in srgb, var(--card-2) 88%, transparent);
}
.dl-vinfo-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }

/* ===== 文件列表 ===== */
.dl-file-list { display: flex; flex-direction: column; gap: 9px; }
.dl-file {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--card-2) 86%, transparent);
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}
.dl-file:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--brand) 35%, var(--border));
  background: var(--card-2);
}
.dl-ficon {
  width: 42px; height: 42px; flex-shrink: 0;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  background: var(--brand-weak); color: var(--brand);
  font-size: 20px;
}
.dl-finfo { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.dl-fname {
  font-size: 13.5px; font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dl-fmeta {
  font-size: 11.5px; color: var(--text-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dl-download {
  display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0;
  height: 34px; padding: 0 15px;
  border-radius: var(--radius-sm);
  background: var(--brand-grad);
  color: #fff; font-size: 12.5px; font-weight: 600;
  box-shadow: 0 4px 14px var(--brand-weak-2);
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.dl-download:hover { color: #fff; opacity: 0.92; transform: translateY(-1px); }
.dl-icon-btn {
  width: 34px; height: 34px; flex-shrink: 0;
  border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  background: var(--card-3); color: var(--text-2);
  font-size: 16px;
  transition: background 0.18s ease, color 0.18s ease;
}
.dl-icon-btn:hover { background: var(--brand-weak); color: var(--brand); }

/* ===== 页脚 / 状态 ===== */
.dl-foot {
  margin-top: 8px; padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 12px; line-height: 1.8; color: var(--text-2);
}
.dl-foot p { margin: 0; }
.dl-state { padding: 24px 0 16px; }

/* ===== 骨架 ===== */
.dl-skel { display: flex; flex-direction: column; gap: 16px; }
.sk-brand { display: flex; align-items: center; gap: 12px; }
.sk-logo { width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0; }
.sk-lines { display: flex; flex-direction: column; gap: 8px; }
.sk-line { height: 12px; border-radius: 6px; }
.w-140 { width: 140px; }
.w-90 { width: 90px; }
.sk-hero { width: 62%; max-width: 420px; height: 30px; border-radius: 9px; margin-top: 8px; }
.sk-pills { display: flex; flex-wrap: wrap; gap: 8px; }
.sk-pill { width: 130px; height: 24px; border-radius: 999px; }
.sk-overview { display: grid; grid-template-columns: 1.45fr 1fr; gap: 14px; }
.sk-card { height: 124px; border-radius: var(--radius-lg); }
.sk-video { height: 240px; border-radius: var(--radius-lg); }
.sk-row { height: 66px; border-radius: var(--radius); }

@keyframes success-pop {
  0% { transform: scale(0.4); opacity: 0; }
  60% { transform: scale(1.12); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}
.accept-pop-enter-active { transition: opacity 0.28s ease, transform 0.28s cubic-bezier(0.22, 0.61, 0.36, 1); }
.accept-pop-leave-active { transition: opacity 0.12s ease, transform 0.12s ease; }
.accept-pop-enter-from { opacity: 0; transform: translateY(6px) scale(0.97); }
.accept-pop-leave-to { opacity: 0; transform: scale(0.99); }

@media (min-width: 2200px) {
  .dl-card { padding: 48px; }
  .dl-title { font-size: 38px; }
  .dl-info-card, .dl-status-card { padding: 22px 24px; }
  .di-title { font-size: 15px; }
  .di-item span { font-size: 12.5px; }
  .di-item b { font-size: 14.5px; }
}

@media (min-width: 3000px) {
  .dl-card { padding: 56px; }
  .dl-title { font-size: 44px; }
  .dl-info-card, .dl-status-card { padding: 26px 28px; }
  .di-title { font-size: 17px; }
  .di-item span { font-size: 14px; }
  .di-item b { font-size: 16px; }
}

@media (max-width: 700px) {
  .dl-card { padding: 22px 16px 20px; }
  .dl-brand { flex-wrap: wrap; }
  .dl-private { margin-left: 0; order: 3; }
  .dl-hero { margin: 20px 0 16px; }
  .dl-overview, .sk-overview { grid-template-columns: 1fr; }
  .dl-info-card, .dl-status-card { padding: 14px 15px; }
  .dl-accept-bar { align-items: stretch; }
  .dl-accept-btn { width: 100%; }
  .dl-video video { max-height: 320px; }
  .dl-section { margin-bottom: 20px; }
  .dl-foot { margin-top: 4px; }
}
@media (max-width: 520px) {
  .di-grid { grid-template-columns: 1fr; gap: 9px; }
  .dl-file { padding: 11px 12px; gap: 10px; }
  .dl-ficon { width: 38px; height: 38px; font-size: 18px; }
  .dl-fname { font-size: 13px; }
}
@media (max-width: 420px) {
  .dl-download { width: 34px; padding: 0; justify-content: center; }
  .dl-download span { display: none; }
  .dl-meta { font-size: 11.5px; }
}
</style>
