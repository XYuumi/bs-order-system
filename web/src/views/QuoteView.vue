<template>
  <div class="quote-page">
    <main class="quote-card art-card">
      <template v-if="data">
        <header class="q-brand">
          <div class="q-logo">{{ brandInitial }}</div>
          <div class="q-brand-copy">
            <div class="q-site">{{ data.site_name }}</div>
            <div class="q-brand-sub">官方服务报价 · OFFICIAL QUOTE</div>
          </div>
          <span class="q-updated">
            <Icon icon="ri:calendar-check-line" />
            {{ data.updated_at }} 更新
          </span>
        </header>

        <div class="q-hero">
          <div class="q-eyebrow"><span class="q-eyebrow-dot" />品质分级 · 价格透明</div>
          <h1 class="q-title">服务报价单</h1>
          <p class="q-sub">不同品质对应不同制作标准与售后范围，按需求选择</p>
        </div>

        <div class="q-grid">
          <div
            v-for="(q, i) in data.qualities"
            :key="q.code"
            class="q-card-wrap rise-in"
            :style="{ animationDelay: `${i * 75}ms` }"
          >
            <article class="q-card" :style="{ '--qc': q.color || 'var(--brand)' }">
              <div class="qc-head">
                <span class="qc-dot" />
                <span class="qc-name">{{ q.name }}</span>
              </div>
              <div class="qc-price">
                <!-- 公开报价单面向客户：只展示客户价（price），不暴露写手价 -->
                <CountTo
                  :target="Number(q.price)"
                  prefix="¥"
                  :decimals="priceDecimals(q.price)"
                  :duration="1100"
                />
                <span class="qc-unit">起</span>
              </div>
              <div class="qc-note">基础报价 · 以最终沟通确认为准</div>
            </article>
          </div>
        </div>

        <footer class="q-foot">
          <p>以上为统一报价基准，最终价格以沟通确认为准（复杂需求可能上浮）。</p>
          <p>报价更新于 {{ data.updated_at }} · 如需下单请联系您的对接人</p>
        </footer>
      </template>

      <div v-else-if="error" class="q-state">
        <EmptyState icon="ri:lock-2-line" :title="error" description="请向对接人索取最新报价链接" />
      </div>

      <div v-else class="q-skel" aria-busy="true">
        <div class="sk-brand">
          <div class="skeleton sk-logo" />
          <div class="sk-brand-lines">
            <div class="skeleton sk-line w-120" />
            <div class="skeleton sk-line w-180" />
          </div>
        </div>
        <div class="skeleton sk-title" />
        <div class="skeleton sk-sub" />
        <div class="sk-grid">
          <div v-for="i in 4" :key="i" class="skeleton sk-qcard" />
        </div>
        <div class="skeleton sk-foot" />
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import CountTo from '../components/CountTo.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import { useThemeStore } from '../stores/theme'

const route = useRoute()
useThemeStore()

const data = ref(null)
const error = ref('')

const brandInitial = computed(() => (data.value?.site_name || '毕').slice(0, 1))

// 金额可能带小数：整数不补零，小数最多展示两位（与后端金额精度一致）
function priceDecimals(v) {
  const n = Number(v)
  if (!Number.isFinite(n) || Number.isInteger(n)) return 0
  const decimal = String(n).split('.')[1] || ''
  return Math.min(decimal.length, 2)
}

async function loadQuote() {
  try {
    const resp = await fetch(`/api/quote/${route.params.token}`)
    const body = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      error.value = typeof body.detail === 'string' ? body.detail : '报价单加载失败'
      return
    }
    data.value = body
    document.title = `${body.site_name} · 服务报价单`
  } catch {
    error.value = '报价单加载失败，请稍后重试'
  }
}

onMounted(loadQuote)
</script>

<style scoped>
.quote-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(18px, 4vw, 48px) 16px;
  overflow-x: hidden;
  background:
    radial-gradient(900px 480px at 12% -12%, color-mix(in srgb, var(--brand) 16%, transparent), transparent 62%),
    radial-gradient(820px 460px at 102% 112%, color-mix(in srgb, var(--purple) 13%, transparent), transparent 58%),
    var(--bg);
}

.quote-card {
  position: relative;
  width: min(var(--public-max), 100%);
  padding: clamp(24px, 4vw, 40px) clamp(20px, 4vw, 40px) clamp(20px, 3vw, 28px);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--card) 92%, transparent);
  box-shadow: var(--shadow-pop);
  backdrop-filter: blur(16px);
  overflow: hidden;
  animation: rise-in 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
.quote-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: linear-gradient(90deg, transparent, var(--brand), var(--purple), transparent);
  opacity: 0.9;
}

/* ===== 品牌头部 ===== */
.q-brand { display: flex; align-items: center; gap: 12px; }
.q-logo {
  width: 42px; height: 42px; flex-shrink: 0;
  border-radius: 12px;
  background: var(--brand-grad);
  box-shadow: var(--brand-glow);
  color: #fff; font-size: 19px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.q-brand-copy { min-width: 0; }
.q-site { font-size: 15.5px; font-weight: 650; color: var(--text); }
.q-brand-sub {
  margin-top: 2px;
  font-size: 10.5px; letter-spacing: 0.14em;
  color: var(--text-3); white-space: nowrap;
}
.q-updated {
  margin-left: auto; flex-shrink: 0;
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--card-2);
  font-size: 11.5px; color: var(--text-3);
  white-space: nowrap;
}
.q-updated .iconify { font-size: 13px; color: var(--brand); }

/* ===== 标题区 ===== */
.q-hero { margin: 28px 0 24px; }
.q-eyebrow {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px; font-weight: 500; letter-spacing: 0.08em;
  color: var(--text-3);
}
.q-eyebrow-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--brand);
  box-shadow: 0 0 0 4px var(--brand-weak);
}
.q-title {
  margin: 10px 0 8px;
  font-size: clamp(26px, 4vw, 36px);
  font-weight: 800;
  line-height: 1.2;
  letter-spacing: 0.02em;
  width: fit-content;
  background: linear-gradient(
    120deg,
    var(--brand) 0%,
    color-mix(in srgb, var(--brand) 55%, var(--purple)) 58%,
    var(--brand-3) 100%
  );
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.q-sub { margin: 0; font-size: 13px; color: var(--text-2); }

/* ===== 品质卡片 ===== */
.q-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(170px, 100%), 1fr));
  gap: 14px;
}
.q-card-wrap { display: flex; min-width: 0; }
.q-card {
  position: relative;
  width: 100%;
  min-width: 0;
  padding: 16px 16px 15px;
  border: 1px solid color-mix(in srgb, var(--qc) 28%, var(--border));
  border-radius: var(--radius);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--qc) 8%, var(--card-2)) 0%, var(--card-2) 62%);
  overflow: hidden;
  transition: transform 0.22s cubic-bezier(0.22, 0.61, 0.36, 1),
    border-color 0.22s ease, box-shadow 0.22s ease;
}
.q-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: linear-gradient(90deg, var(--qc), transparent 85%);
  opacity: 0.8;
}
.q-card:hover {
  transform: translateY(-5px);
  border-color: color-mix(in srgb, var(--qc) 55%, var(--border));
  box-shadow: 0 16px 34px color-mix(in srgb, var(--qc) 16%, transparent), var(--shadow-card);
}
.qc-head { display: flex; align-items: center; gap: 7px; }
.qc-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--qc);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--qc) 18%, transparent);
  flex-shrink: 0;
}
.qc-name { font-size: 13.5px; font-weight: 650; color: var(--text); }
.qc-mult {
  margin-left: auto;
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--qc) 12%, transparent);
  color: color-mix(in srgb, var(--qc) 82%, var(--text));
  font-size: 10.5px; font-weight: 600;
  white-space: nowrap;
}
.qc-price {
  display: flex; align-items: baseline; gap: 3px;
  margin-top: 14px;
  color: var(--text);
  font-size: clamp(23px, 2.6vw, 28px);
  font-weight: 750;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.qc-unit { font-size: 11.5px; font-weight: 500; color: var(--text-3); }
.qc-note { margin-top: 7px; font-size: 10.5px; color: var(--text-3); }

/* ===== 页脚 ===== */
.q-foot {
  margin-top: 26px; padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 12px; line-height: 1.8; color: var(--text-2);
}
.q-foot p { margin: 0; }

/* ===== 状态 / 骨架 ===== */
.q-state { padding: 22px 0 14px; }
.q-skel { display: flex; flex-direction: column; gap: 16px; }
.sk-brand { display: flex; align-items: center; gap: 12px; }
.sk-logo { width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0; }
.sk-brand-lines { display: flex; flex-direction: column; gap: 8px; }
.sk-line { height: 12px; border-radius: 6px; }
.w-120 { width: 120px; }
.w-180 { width: 180px; }
.sk-title { width: 260px; max-width: 70%; height: 34px; margin-top: 12px; border-radius: 10px; }
.sk-sub { width: 360px; max-width: 80%; height: 13px; border-radius: 6px; }
.sk-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin-top: 6px; }
.sk-qcard { height: 118px; border-radius: var(--radius); }
.sk-foot { height: 44px; border-radius: var(--radius-sm); margin-top: 10px; }

@media (min-width: 680px) {
  /* 桌面固定 3 列：6 个品质恰好 3×2，避免 1920 下出现 4+2 孤行 */
  .q-grid, .sk-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (min-width: 2200px) {
  .quote-card { padding: 48px 52px 38px; }
  .q-title { font-size: 48px; }
  .q-sub { font-size: 15px; }
  .q-card { padding: 22px 20px 20px; }
  .qc-name { font-size: 15px; }
  .qc-price { font-size: 34px; }
  .qc-note, .qc-unit { font-size: 12.5px; }
  .q-foot { font-size: 13.5px; }
}

@media (min-width: 3000px) {
  .quote-card { padding: 58px 64px 44px; }
  .q-title { font-size: 56px; }
  .q-sub { font-size: 17px; }
  .q-card { padding: 28px 24px 24px; }
  .qc-name { font-size: 17px; }
  .qc-price { font-size: 40px; }
  .qc-note, .qc-unit { font-size: 14px; }
  .q-foot { font-size: 15px; }
}

@media (max-width: 620px) {
  .quote-card { padding: 24px 18px 20px; }
  .q-brand { flex-wrap: wrap; }
  .q-updated { margin-left: 0; order: 3; }
  .q-hero { margin: 22px 0 18px; }
  .q-grid, .sk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .q-card { padding: 14px 13px; }
  .qc-price { font-size: 22px; margin-top: 11px; }
  .q-foot { margin-top: 22px; }
}
@media (max-width: 360px) {
  .q-grid, .sk-grid { grid-template-columns: 1fr; }
}
</style>
