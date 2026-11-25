<template>
  <div class="stat-card" :class="{ clickable, loading }" @click="$emit('click')">
    <div class="stat-copy">
      <p class="stat-label">{{ label }}</p>
      <div v-if="loading" class="stat-value skeleton" />
      <div v-else class="stat-value">
        <CountTo
          v-if="typeof value === 'number'"
          :target="value" :prefix="prefix" :suffix="suffix" :decimals="decimals"
        />
        <template v-else>{{ value ?? '—' }}<span v-if="suffix" class="stat-suffix">{{ suffix }}</span></template>
      </div>
      <div v-if="delta != null" class="stat-delta">
        <span :class="delta >= 0 ? 'up' : 'down'">
          <Icon :icon="delta >= 0 ? 'ri:arrow-up-s-fill' : 'ri:arrow-down-s-fill'" />
          {{ Math.abs(delta) }}%
        </span>
        <span class="stat-vs">{{ deltaLabel }}</span>
      </div>
      <div v-else-if="sub" class="stat-sub">{{ sub }}</div>
    </div>
    <div v-if="icon" class="stat-icon" :style="iconStyle">
      <Icon :icon="icon" />
    </div>
    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import CountTo from './CountTo.vue'

const props = defineProps({
  label: { type: String, default: '' },
  value: { type: [String, Number], default: 0 },
  icon: { type: String, default: '' },
  color: { type: String, default: 'var(--brand)' },
  grad: { type: String, default: '' },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' },
  decimals: { type: Number, default: 0 },
  delta: { type: Number, default: null },
  deltaLabel: { type: String, default: '较上周' },
  sub: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  clickable: { type: Boolean, default: false },
})
defineEmits(['click'])

const iconStyle = computed(() => {
  if (props.grad) return { background: props.grad, color: '#fff', boxShadow: '0 8px 20px rgba(93,135,255,.22)' }
  return { background: `color-mix(in srgb, ${props.color} 14%, transparent)`, color: props.color }
})
</script>

<style scoped>
.stat-card {
  position: relative;
  min-height: 118px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 18px 18px 20px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
  animation: rise-in 0.44s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
.stat-card::before {
  content: '';
  position: absolute; inset: 0;
  background: radial-gradient(120px 80px at 92% 10%, color-mix(in srgb, var(--brand) 9%, transparent), transparent 70%);
  pointer-events: none;
}
.stat-card:hover { transform: translateY(-3px); border-color: var(--border-2); box-shadow: var(--shadow-glow); }
.stat-card.clickable { cursor: pointer; }
.stat-copy { min-width: 0; position: relative; z-index: 1; }
.stat-label { margin: 0; font-size: 12.5px; color: var(--text-2); }
.stat-value {
  margin-top: 7px;
  font-size: 26px;
  font-weight: 650;
  letter-spacing: -0.6px;
  line-height: 1.15;
  color: var(--text);
  min-height: 30px;
}
.stat-value.skeleton { width: 86px; height: 28px; margin-top: 8px; }
.stat-suffix { font-size: 12px; font-weight: 500; color: var(--text-3); margin-left: 4px; letter-spacing: 0; }
.stat-delta { display: flex; align-items: center; gap: 6px; margin-top: 7px; font-size: 12px; }
.stat-delta .up { color: var(--success); font-weight: 600; display: inline-flex; align-items: center; }
.stat-delta .down { color: var(--danger); font-weight: 600; display: inline-flex; align-items: center; }
.stat-vs { color: var(--text-3); }
.stat-sub { margin-top: 7px; font-size: 12px; color: var(--text-3); }
.stat-icon {
  width: 44px; height: 44px; flex-shrink: 0;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 19px;
  position: relative; z-index: 1;
  animation: icon-pop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  animation-delay: 0.15s;
}
@keyframes icon-pop { from { opacity: 0; transform: scale(0.4); } to { opacity: 1; transform: scale(1); } }
@media (min-width: 2200px) {
  .stat-card { min-height: 132px; padding: 22px 22px 22px 26px; gap: 16px; }
  .stat-label { font-size: 13.5px; }
  .stat-value { font-size: 30px; min-height: 34px; }
  .stat-suffix, .stat-delta, .stat-sub { font-size: 13px; }
  .stat-icon { width: 50px; height: 50px; font-size: 22px; border-radius: 14px; }
}

@media (min-width: 3000px) {
  .stat-card { min-height: 152px; padding: 26px 26px 26px 30px; gap: 20px; }
  .stat-label { font-size: 15px; }
  .stat-value { font-size: 36px; min-height: 40px; }
  .stat-suffix, .stat-delta, .stat-sub { font-size: 14.5px; }
  .stat-icon { width: 60px; height: 60px; font-size: 27px; border-radius: 16px; }
}

@media (max-width: 600px) {
  .stat-card { min-height: 104px; padding: 14px 16px; }
  .stat-value { font-size: 22px; }
  .stat-icon { width: 38px; height: 38px; font-size: 17px; }
}
</style>
