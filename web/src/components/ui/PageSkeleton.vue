<template>
  <div class="page-skeleton" aria-busy="true">
    <div class="sk-head">
      <div class="skeleton sk-icon" />
      <div class="sk-copy">
        <div class="skeleton sk-line lg" />
        <div class="skeleton sk-line sm" />
      </div>
    </div>
    <div v-if="stats" class="sk-stats">
      <div v-for="i in 4" :key="i" class="skeleton sk-stat" />
    </div>
    <div class="skeleton sk-card" />
    <div class="skeleton sk-card tall" />
  </div>
</template>

<script setup>
defineProps({ stats: { type: Boolean, default: true } })
</script>

<style scoped>
.page-skeleton { display: flex; flex-direction: column; gap: 18px; }
.sk-head { display: flex; align-items: center; gap: 14px; }
.sk-icon { width: 44px; height: 44px; border-radius: 12px; flex-shrink: 0; }
.sk-copy { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.sk-line { height: 14px; border-radius: 6px; }
.sk-line.lg { width: 180px; height: 20px; }
.sk-line.sm { width: 280px; max-width: 60%; }
.sk-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.sk-stat { height: 118px; border-radius: 16px; }
.sk-card { height: 220px; border-radius: 16px; }
.sk-card.tall { height: 360px; }
@media (max-width: 1100px) { .sk-stats { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px) { .sk-stats { grid-template-columns: 1fr; } }
</style>
