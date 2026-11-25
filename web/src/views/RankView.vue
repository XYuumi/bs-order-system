<template>
  <div class="rank-page">
    <main v-if="data" class="rank-card">
      <header class="rk-brand">
        <div class="rk-logo">{{ brandInitial }}</div>
        <div class="rk-brand-copy">
          <div class="rk-site">{{ data.site_name }}</div>
          <div class="rk-sub">
            <Icon icon="ri:calendar-line" />
            {{ data.month }} · 代理业绩榜
          </div>
        </div>
        <span class="rk-badge"><Icon icon="ri:trophy-line" /> TOP AGENTS</span>
      </header>

      <!-- 团队数据 -->
      <section class="rk-team" aria-label="团队数据">
        <div v-for="t in teamStats" :key="t.label" class="rt-cell">
          <span class="rt-icon" :style="{ color: t.color, background: t.bg }">
            <Icon :icon="t.icon" />
          </span>
          <div class="rt-num"><CountTo :target="Number(t.value)" :duration="1200" /></div>
          <div class="rt-label">{{ t.label }}</div>
        </div>
      </section>

      <template v-if="top3.length">
        <!-- 前三名领奖台（2-1-3 顺序，不足三人用虚位以待占位） -->
        <section class="rk-podium" aria-label="前三名">
          <div v-for="a in orderedTop3" :key="a.key" class="rp-col" :class="`no${a.rank}`">
            <template v-if="a.name">
              <div class="rp-figure">
                <span v-if="a.rank === 1" class="rp-crown"><Icon icon="ri:vip-crown-2-fill" /></span>
                <div class="rp-avatar" :class="`no${a.rank}`">{{ a.name.slice(0, 1) }}</div>
                <span class="rp-medal" :class="`no${a.rank}`"><Icon icon="ri:medal-fill" /></span>
              </div>
              <div class="rp-name" :title="a.name">{{ a.name }}</div>
              <div class="rp-stars" role="img" :aria-label="`${a.stars} 星`">
                <Icon v-for="s in a.stars" :key="`s${s}`" icon="ri:star-fill" />
                <Icon v-for="s in (5 - a.stars)" :key="`o${s}`" icon="ri:star-line" />
              </div>
              <div class="rp-block">
                <div class="rp-count"><CountTo :target="Number(a.month_count)" :duration="1100" /></div>
                <div class="rp-unit">本月 {{ a.month_count }} 单</div>
              </div>
            </template>
            <template v-else>
              <div class="rp-figure">
                <div class="rp-avatar ghost">?</div>
              </div>
              <div class="rp-name ghost-name">虚位以待</div>
              <div class="rp-stars"><Icon v-for="s in 5" :key="s" icon="ri:star-line" /></div>
              <div class="rp-block ghost-block">
                <div class="rp-unit">期待新伙伴加入</div>
              </div>
            </template>
          </div>
        </section>

        <!-- 完整榜单 -->
        <section v-if="rest.length" class="rk-list" aria-label="完整榜单">
          <div class="rk-list-head">
            <span class="rk-list-title">完整榜单</span>
            <span class="chip">共 {{ withRank.length }} 位</span>
          </div>
          <div
            v-for="(a, i) in rest"
            :key="a.key"
            class="rl-row rise-in"
            :style="{ animationDelay: `${Math.min(i, 8) * 45}ms` }"
          >
            <span class="rl-no">{{ a.rank }}</span>
            <span class="rl-name" :title="a.name">{{ a.name }}</span>
            <div
              class="rl-bar"
              role="progressbar"
              :aria-valuenow="a.month_count"
              aria-valuemin="0"
              :aria-valuemax="maxMonth"
            >
              <div
                class="rl-fill"
                :style="{
                  width: barsReady ? `${barPct(a)}%` : '0%',
                  transitionDelay: `${Math.min(i, 8) * 40}ms`,
                }"
              />
            </div>
            <span class="rl-count"><CountTo :target="Number(a.month_count)" :duration="1000" /><small> 单/月</small></span>
            <span class="rl-stars" aria-hidden="true">
              <Icon v-for="s in a.stars" :key="`s${s}`" icon="ri:star-fill" />
              <Icon v-for="s in (5 - a.stars)" :key="`o${s}`" icon="ri:star-line" />
            </span>
          </div>
        </section>
        <div v-else class="rk-list-empty">前三名以外暂无上榜 · 虚位以待</div>
      </template>

      <EmptyState
        v-else
        icon="ri:trophy-line"
        title="暂无上榜数据"
        description="本月还没有代理接单，产生数据后榜单会自动更新"
      />

      <footer class="rk-foot">
        <p>星级为系统按历史按时交付率自动评定；数据截至 {{ data.updated_at }}。</p>
        <p>如需服务请联系对应顾问 · 本页面由 {{ data.site_name }} 提供</p>
      </footer>
    </main>

    <div v-else-if="error" class="rank-state">
      <EmptyState icon="ri:lock-2-line" :title="error" description="请向管理员索取最新榜单链接" />
    </div>

    <main v-else class="rank-card rk-skeleton" aria-busy="true">
      <div class="sk-brand">
        <div class="skeleton sk-logo" />
        <div class="sk-lines">
          <div class="skeleton sk-line w-180" />
          <div class="skeleton sk-line w-120" />
        </div>
      </div>
      <div class="sk-team">
        <div v-for="i in 3" :key="i" class="skeleton sk-team-cell" />
      </div>
      <div class="sk-podium">
        <div class="skeleton sk-podium-col second" />
        <div class="skeleton sk-podium-col first" />
        <div class="skeleton sk-podium-col third" />
      </div>
      <div class="sk-rows">
        <div v-for="i in 3" :key="i" class="skeleton sk-row" />
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import CountTo from '../components/CountTo.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import { useThemeStore } from '../stores/theme'

const route = useRoute()
useThemeStore()

const data = ref(null)
const error = ref('')
const barsReady = ref(false)

const brandInitial = computed(() => (data.value?.site_name || '毕').slice(0, 1))

const withRank = computed(() =>
  (data.value?.agents || []).map((a, i) => ({ ...a, rank: i + 1, key: `agent-${i}-${a.name}` }))
)
// 领奖台三个坑位（2-1-3 顺序），不足补"虚位以待"占位
const podiumSlots = [2, 1, 3]
const orderedTop3 = computed(() => {
  const byRank = {}
  withRank.value.slice(0, 3).forEach((a) => { byRank[a.rank] = a })
  return podiumSlots.map((rank) => byRank[rank] || { key: `ghost-${rank}`, rank, name: '' })
})
const top3 = computed(() => withRank.value.slice(0, 3))
const rest = computed(() => withRank.value.slice(3))

const teamStats = computed(() => [
  {
    label: '本月接单', value: data.value?.team?.month_total ?? 0,
    icon: 'ri:calendar-check-line', color: 'var(--brand)', bg: 'var(--brand-weak)',
  },
  {
    label: '累计交付', value: data.value?.team?.total ?? 0,
    icon: 'ri:checkbox-circle-line', color: 'var(--success)', bg: 'var(--success-weak)',
  },
  {
    label: '服务顾问', value: data.value?.team?.agent_count ?? 0,
    icon: 'ri:team-line', color: 'var(--purple)', bg: 'var(--purple-weak)',
  },
])

const maxMonth = computed(() => Math.max(1, ...withRank.value.map((a) => Number(a.month_count) || 0)))
function barPct(a) {
  return Math.round((Number(a.month_count) / maxMonth.value) * 100)
}

onMounted(async () => {
  try {
    const resp = await fetch(`/api/rank/${route.params.token}`)
    const body = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      error.value = typeof body.detail === 'string' ? body.detail : '榜单加载失败'
      return
    }
    data.value = body
    document.title = `${body.site_name} · 代理业绩榜`
    // 先以 0 宽度渲染，再跨两帧点亮，确保浏览器先提交 0 宽度再触发过渡
    await nextTick()
    requestAnimationFrame(() => {
      requestAnimationFrame(() => { barsReady.value = true })
    })
  } catch {
    error.value = '榜单加载失败，请稍后重试'
  }
})
</script>

<style scoped>
.rank-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: clamp(20px, 4vw, 44px) 18px;
  overflow-x: hidden;
  background:
    radial-gradient(1100px 540px at 82% -12%, color-mix(in srgb, var(--brand) 26%, transparent), transparent 62%),
    radial-gradient(780px 440px at 0% 0%, color-mix(in srgb, var(--purple) 14%, transparent), transparent 56%),
    var(--bg);
}
.rank-page::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(color-mix(in srgb, var(--text) 3.5%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--text) 3.5%, transparent) 1px, transparent 1px);
  background-size: 46px 46px;
  mask-image: radial-gradient(ellipse at 50% 0%, #000 0%, transparent 72%);
}

.rank-card {
  position: relative;
  z-index: 1;
  width: min(var(--public-max), 100%);
  padding: clamp(24px, 4vw, 36px) clamp(18px, 4vw, 36px) 26px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--card) 88%, transparent);
  box-shadow: var(--shadow-pop);
  backdrop-filter: blur(18px);
  overflow: hidden;
  animation: rise-in 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
.rank-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: linear-gradient(90deg, transparent, var(--brand), var(--warning), transparent);
  opacity: 0.85;
}

/* ===== 品牌头 ===== */
.rk-brand { display: flex; align-items: center; gap: 14px; }
.rk-logo {
  width: 50px; height: 50px; flex-shrink: 0;
  border-radius: 14px;
  background: var(--brand-grad);
  box-shadow: var(--brand-glow);
  color: #fff; font-size: 23px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.rk-brand-copy { min-width: 0; }
.rk-site { font-size: clamp(20px, 3vw, 23px); font-weight: 750; color: var(--text); letter-spacing: 0.01em; }
.rk-sub {
  display: flex; align-items: center; gap: 5px;
  margin-top: 3px;
  font-size: 12.5px; color: var(--text-3);
}
.rk-sub .iconify { font-size: 14px; color: var(--brand); }
.rk-badge {
  margin-left: auto; flex-shrink: 0;
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 11px;
  border: 1px solid color-mix(in srgb, var(--warning) 30%, var(--border));
  border-radius: var(--radius-pill);
  background: var(--warning-weak);
  color: var(--warning);
  font-size: 10.5px; font-weight: 700; letter-spacing: 0.1em;
  white-space: nowrap;
}
.rk-badge .iconify { font-size: 13px; }

/* ===== 团队数据 ===== */
.rk-team {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 24px 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--card-2) 78%, transparent);
  overflow: hidden;
}
.rt-cell {
  position: relative;
  display: flex; flex-direction: column; align-items: center;
  padding: 18px 10px 16px;
  min-width: 0;
}
.rt-cell + .rt-cell { border-left: 1px solid var(--border); }
.rt-icon {
  width: 28px; height: 28px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; margin-bottom: 7px;
}
.rt-num {
  max-width: 100%;
  font-size: clamp(24px, 3.4vw, 34px);
  font-weight: 750;
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rt-label { margin-top: 4px; font-size: 12px; color: var(--text-3); }

/* ===== 领奖台 ===== */
.rk-podium {
  display: flex; align-items: flex-end; justify-content: center;
  gap: 18px; margin: 28px 0 6px;
}
.rp-col {
  position: relative;
  display: flex; flex-direction: column; align-items: center;
  gap: 7px;
  width: 150px;
  min-width: 0;
  --podium: var(--brand);
  animation: podium-in 0.68s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
.rp-col.no2 { --podium: var(--text-2); animation-delay: 0.04s; }
.rp-col.no1 { --podium: var(--warning); animation-delay: 0.18s; }
.rp-col.no3 { --podium: color-mix(in srgb, var(--warning) 55%, var(--danger)); animation-delay: 0.3s; }

.rp-figure { position: relative; display: flex; }
.rp-avatar {
  position: relative;
  width: 62px; height: 62px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 750; color: #fff;
}
.rp-avatar.no1 {
  width: 74px; height: 74px; font-size: 28px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--warning) 82%, var(--danger)), color-mix(in srgb, var(--warning) 48%, var(--danger)));
  box-shadow: 0 8px 24px color-mix(in srgb, var(--warning) 35%, transparent);
}
.rp-avatar.no2 { background: linear-gradient(135deg, var(--text-2), var(--text-3)); }
.rp-avatar.no3 {
  background: linear-gradient(135deg, color-mix(in srgb, var(--warning) 52%, var(--danger)), color-mix(in srgb, var(--warning) 30%, var(--danger)));
}
.rp-avatar.no1::after {
  content: '';
  position: absolute;
  inset: -7px;
  border-radius: 50%;
  border: 1px dashed color-mix(in srgb, var(--warning) 55%, transparent);
  animation: rk-spin 14s linear infinite;
}
.rp-crown {
  position: absolute;
  top: -27px; left: 50%;
  transform: translateX(-50%);
  color: var(--warning);
  font-size: 22px;
  line-height: 1;
  filter: drop-shadow(0 3px 8px color-mix(in srgb, var(--warning) 45%, transparent));
  animation: crown-float 2.6s ease-in-out infinite;
  z-index: 2;
}
.rp-medal {
  position: absolute;
  right: -7px; bottom: -4px;
  width: 24px; height: 24px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--card);
  border: 1px solid var(--border-2);
  font-size: 13px;
  color: var(--podium);
}
.rp-name {
  max-width: 140px;
  font-size: 14px; font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rp-stars {
  display: flex; align-items: center; gap: 1px;
  color: var(--warning); font-size: 12px;
  min-height: 16px;
}
.rp-block {
  width: 100%;
  padding: 12px 8px 0;
  text-align: center;
  border: 1px solid color-mix(in srgb, var(--podium) 34%, var(--border));
  border-bottom: none;
  border-radius: 12px 12px 0 0;
  background: linear-gradient(180deg, color-mix(in srgb, var(--podium) 20%, transparent), transparent);
}
.rp-col.no1 .rp-block { height: 112px; }
.rp-col.no2 .rp-block { height: 86px; }
.rp-col.no3 .rp-block { height: 70px; }
.rp-count {
  font-size: clamp(21px, 2.6vw, 26px);
  font-weight: 750;
  line-height: 1.2;
  color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rp-unit {
  margin-top: 3px;
  font-size: 11.5px; color: var(--text-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rp-avatar.ghost {
  background: var(--card-2);
  color: var(--text-4);
  border: 1px dashed var(--border-3);
}
.ghost-name { color: var(--text-3); }
.rp-block.ghost-block {
  display: flex; align-items: flex-end; justify-content: center;
  height: 64px; padding-bottom: 12px;
  background: var(--card-2);
  border-style: dashed;
  border-color: var(--border-2);
}
.rk-list-empty {
  margin-top: 22px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-3);
}

/* ===== 完整榜单 ===== */
.rk-list { margin-top: 24px; display: flex; flex-direction: column; gap: 9px; }
.rk-list-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-bottom: 2px;
}
.rk-list-title { font-size: 13.5px; font-weight: 650; color: var(--text); }
.rl-row {
  display: flex; align-items: center; gap: 12px;
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--card-2) 82%, transparent);
  font-size: 13px; color: var(--text-2);
  min-width: 0;
}
.rl-no {
  width: 26px; height: 26px; flex-shrink: 0;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  background: var(--brand-weak);
  color: var(--brand);
  font-size: 12px; font-weight: 700;
}
.rl-name {
  width: 110px; flex-shrink: 0;
  font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rl-bar {
  flex: 1; min-width: 40px; height: 7px;
  border-radius: var(--radius-pill);
  background: var(--card-3);
  overflow: hidden;
}
.rl-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  background: linear-gradient(90deg, var(--brand), var(--purple));
  box-shadow: 0 0 12px color-mix(in srgb, var(--brand) 35%, transparent);
  transition: width 0.9s cubic-bezier(0.22, 0.61, 0.36, 1);
}
.rl-count { flex-shrink: 0; color: var(--text-3); font-variant-numeric: tabular-nums; }
.rl-count small { font-size: 11px; }
.rl-count .count-to { color: var(--text); font-size: 14.5px; font-weight: 700; }
.rl-stars {
  display: flex; align-items: center; gap: 1px;
  flex-shrink: 0;
  color: var(--warning); font-size: 11px;
}

/* ===== 页脚 / 状态 ===== */
.rk-foot {
  margin-top: 26px; padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 12px; line-height: 1.8; color: var(--text-3);
}
.rk-foot p { margin: 0; }

.rank-state {
  width: 100%;
  min-height: calc(100vh - 96px);
  display: flex; align-items: center; justify-content: center;
}

/* ===== 骨架 ===== */
.rk-skeleton { display: flex; flex-direction: column; gap: 18px; }
.sk-brand { display: flex; align-items: center; gap: 14px; }
.sk-logo { width: 50px; height: 50px; border-radius: 14px; flex-shrink: 0; }
.sk-lines { display: flex; flex-direction: column; gap: 8px; }
.sk-line { height: 13px; border-radius: 6px; }
.w-180 { width: 180px; }
.w-120 { width: 120px; }
.sk-team { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; }
.sk-team-cell { height: 100px; border-radius: var(--radius); }
.sk-podium { display: flex; align-items: flex-end; justify-content: center; gap: 18px; margin-top: 6px; }
.sk-podium-col { width: 30%; max-width: 150px; border-radius: 12px 12px 0 0; }
.sk-podium-col.first { height: 210px; }
.sk-podium-col.second { height: 180px; }
.sk-podium-col.third { height: 160px; }
.sk-rows { display: flex; flex-direction: column; gap: 9px; }
.sk-row { height: 50px; border-radius: var(--radius); }

@keyframes podium-in {
  from { opacity: 0; transform: translateY(26px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes crown-float {
  0%, 100% { transform: translate(-50%, 0); }
  50% { transform: translate(-50%, -4px); }
}
@keyframes rk-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (min-width: 2200px) {
  .rank-card { padding: 44px 46px 34px; }
  .rp-col { width: 190px; }
  .rp-avatar { width: 78px; height: 78px; font-size: 30px; }
  .rp-avatar.no1 { width: 94px; height: 94px; font-size: 36px; }
  .rp-name { max-width: 180px; font-size: 16px; }
  .rp-count { font-size: 32px; }
  .rp-col.no1 .rp-block { height: 132px; }
  .rp-col.no2 .rp-block { height: 102px; }
  .rp-col.no3 .rp-block { height: 84px; }
  .rl-row { padding: 14px 18px; font-size: 14.5px; }
}

@media (min-width: 3000px) {
  .rank-card { padding: 52px 56px 40px; }
  .rp-col { width: 230px; }
  .rp-avatar { width: 92px; height: 92px; font-size: 36px; }
  .rp-avatar.no1 { width: 112px; height: 112px; font-size: 44px; }
  .rp-name { max-width: 220px; font-size: 18px; }
  .rp-count { font-size: 38px; }
  .rp-col.no1 .rp-block { height: 156px; }
  .rp-col.no2 .rp-block { height: 120px; }
  .rp-col.no3 .rp-block { height: 100px; }
  .rl-row { padding: 17px 22px; font-size: 16px; }
}

@media (max-width: 640px) {
  .rank-page { padding: 18px 12px; }
  .rank-card { padding: 22px 15px 20px; border-radius: var(--radius-lg); }
  .rk-brand { gap: 11px; flex-wrap: wrap; }
  .rk-logo { width: 44px; height: 44px; font-size: 20px; border-radius: 12px; }
  .rk-badge { order: 3; margin-left: 0; }
  .rk-team { margin-top: 18px; }
  .rt-cell { padding: 14px 6px 13px; }
  .rt-icon { display: none; }
  .rk-podium { gap: 8px; margin-top: 22px; }
  .rp-col { width: 31%; max-width: 130px; }
  .rp-avatar { width: 54px; height: 54px; font-size: 21px; }
  .rp-avatar.no1 { width: 64px; height: 64px; font-size: 24px; }
  .rp-name { max-width: 100%; font-size: 13px; }
  .rp-col.no1 .rp-block { height: 98px; }
  .rp-col.no2 .rp-block { height: 78px; }
  .rp-col.no3 .rp-block { height: 64px; }
  .rp-crown { top: -23px; font-size: 19px; }
  .rl-row { gap: 9px; padding: 10px 11px; }
  .rl-name { width: 76px; font-size: 12.5px; }
  .rl-stars { display: none; }
}
@media (max-width: 420px) {
  .rp-avatar { width: 46px; height: 46px; font-size: 18px; }
  .rp-avatar.no1 { width: 56px; height: 56px; font-size: 21px; }
  .rp-stars { font-size: 10px; }
  .rp-count { font-size: 19px; }
  .rp-unit { font-size: 10.5px; }
  .rl-count small { display: none; }
  .rl-name { width: 64px; }
}
</style>
