<template>
  <section class="chart-card" :class="{ fill }">
    <header class="chart-head">
      <div class="title">
        <h4>{{ title }}</h4>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="actions"><slot name="actions" /></div>
    </header>
    <div class="chart-body" :class="{ 'is-fill': fill }" :style="fill ? undefined : { height }">
      <ChartBox v-if="option && !loading && !empty" :option="option" :fill="fill" />
      <div v-if="loading" class="chart-state">
        <span class="state-dot art-dot-breathe" /> 加载中
      </div>
      <div v-else-if="empty" class="chart-state empty">
        <Icon icon="ri:bar-chart-box-line" />
        <span>{{ emptyText }}</span>
      </div>
      <slot v-if="!option" />
    </div>
    <footer v-if="$slots.footer" class="chart-foot"><slot name="footer" /></footer>
  </section>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import ChartBox from '../ChartBox.vue'

defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  option: { type: Object, default: null },
  height: { type: String, default: '280px' },
  fill: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  empty: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
})
</script>

<style scoped>
.chart-card {
  display: flex; flex-direction: column; min-width: 0; min-height: 0;
  padding: 16px 18px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.chart-card:hover { border-color: var(--border-2); }
.chart-card.fill { height: 100%; }
.chart-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 12px; flex: none; }
.title h4 { margin: 0; font-size: 15px; font-weight: 600; color: var(--text); }
.title p { margin: 3px 0 0; font-size: 11.5px; color: var(--text-3); }
.actions { display: flex; align-items: center; gap: 6px; }
.chart-body { position: relative; min-height: 0; flex: 0 0 auto; display: flex; flex-direction: column; }
/* 非 fill 模式由 height 决定高度；fill 模式才跟随网格卡片拉伸 */
.chart-body.is-fill { flex: 1 1 0; height: 100%; }
.chart-state {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
  color: var(--text-3); font-size: 12.5px;
}
.chart-state.empty .iconify { font-size: 30px; opacity: 0.55; }
.state-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--brand); }
.chart-foot { flex: none; margin-top: 8px; }
</style>
