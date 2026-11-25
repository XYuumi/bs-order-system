<template>
  <SettingsShell
    title="价格与品质"
    description="基础价格与品质倍率决定下单价格；下单时快照，改价不影响历史订单"
    icon="ri:price-tag-3-line"
    :loading="loading"
  >
    <div class="settings-stack">
      <!-- 基础价格 + 价格预览 -->
      <section class="settings-section">
        <div class="settings-section-head">
          <div>
            <div class="settings-section-title">基础价格（白色品质 ×1）</div>
            <p class="settings-section-desc">修改后需要输入登录密码二次确认；品质价格 = 基础价 × 品质倍率</p>
          </div>
          <div class="settings-head-actions">
            <el-button type="primary" :loading="savingBase" @click="saveBasePrices">保存价格</el-button>
          </div>
        </div>

        <div class="price-form">
          <div class="price-item">
            <div class="p-label">真实基础价（你看到的）</div>
            <el-input-number
              v-model="form.owner_base_price"
              :min="0"
              :precision="0"
              :step="50"
              size="large"
              controls-position="right"
              style="width: 180px"
            />
          </div>
          <div class="price-item">
            <div class="p-label">代理基础价（代理看到的）</div>
            <el-input-number
              v-model="form.agent_base_price"
              :min="0"
              :precision="0"
              :step="10"
              size="large"
              controls-position="right"
              style="width: 180px"
            />
          </div>
        </div>

        <el-alert
          type="info"
          show-icon
          :closable="false"
          class="price-tip"
          title="品质价格 = 基础价 × 品质倍率（下单时快照，改价不影响历史订单）"
        />

        <el-table :data="qualityPreview" size="small" class="price-table desktop-only" row-key="code">
          <el-table-column label="品质" width="110">
            <template #default="{ row }">
              <QualityBadge :name="row.name" :color="row.color" />
            </template>
          </el-table-column>
          <el-table-column label="倍率" width="90">
            <template #default="{ row }">×{{ row.multiplier }}</template>
          </el-table-column>
          <el-table-column label="你的价格">
            <template #default="{ row }">
              <b>¥{{ row.owner_price }}</b>
              <span class="text-2 price-note">{{ row.owner_price_override != null ? '自定义' : '×' + row.multiplier }}</span>
            </template>
          </el-table-column>
          <el-table-column label="代理价格">
            <template #default="{ row }">
              <b class="agent-price">¥{{ row.agent_price }}</b>
              <span class="text-2 price-note">{{ row.agent_price_override != null ? '自定义' : '×' + row.multiplier }}</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="preview-cards mobile-only">
          <div v-for="row in qualityPreview" :key="row.code" class="preview-card">
            <div class="pc-head">
              <QualityBadge :name="row.name" :color="row.color" />
              <span class="pc-mult">×{{ row.multiplier }}</span>
            </div>
            <div class="pc-prices">
              <div class="pc-price">
                <span class="pc-label">你的价格</span>
                <b>¥{{ row.owner_price }}</b>
                <span class="text-2 price-note">{{ row.owner_price_override != null ? '自定义' : '×' + row.multiplier }}</span>
              </div>
              <div class="pc-price">
                <span class="pc-label">代理价格</span>
                <b class="agent-price">¥{{ row.agent_price }}</b>
                <span class="text-2 price-note">{{ row.agent_price_override != null ? '自定义' : '×' + row.multiplier }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 品质与倍率编辑 -->
      <section class="settings-section">
        <div class="settings-section-head">
          <div>
            <div class="settings-section-title">品质与倍率</div>
            <p class="settings-section-desc">倍率必须大于 0；自定义价格留空表示按「基础价 × 倍率」计算</p>
          </div>
        </div>

        <el-table :data="qualities" size="small" row-key="code" class="q-table desktop-only">
          <el-table-column label="品质" width="128">
            <template #default="{ row }">
              <el-input v-model="row.name" size="small" style="width: 96px" />
            </template>
          </el-table-column>
          <el-table-column label="颜色" width="84">
            <template #default="{ row }">
              <label class="color-chip" :style="{ background: row.color }">
                <input type="color" v-model="row.color" />
              </label>
            </template>
          </el-table-column>
          <el-table-column label="倍率" width="134">
            <template #default="{ row }">
              <el-input-number
                v-model="row.multiplier"
                :min="0.5"
                :max="100"
                :step="1"
                :precision="2"
                size="small"
                controls-position="right"
                style="width: 108px"
              />
            </template>
          </el-table-column>
          <el-table-column label="自定义真实价" width="148">
            <template #default="{ row }">
              <el-input-number
                v-model="row.owner_price_override"
                :min="0"
                :precision="2"
                size="small"
                controls-position="right"
                style="width: 120px"
                placeholder="默认"
              />
            </template>
          </el-table-column>
          <el-table-column label="自定义代理价" width="148">
            <template #default="{ row }">
              <el-input-number
                v-model="row.agent_price_override"
                :min="0"
                :precision="2"
                size="small"
                controls-position="right"
                style="width: 120px"
                placeholder="默认"
              />
            </template>
          </el-table-column>
          <el-table-column label="排序" width="102">
            <template #default="{ row }">
              <el-input-number
                v-model="row.sort"
                :min="0"
                :max="99"
                size="small"
                controls-position="right"
                style="width: 82px"
              />
            </template>
          </el-table-column>
          <el-table-column label="启用" width="64">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="84">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain :loading="savingQ === row.code" @click="saveQuality(row)">保存</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="q-cards mobile-only">
          <div v-for="row in qualities" :key="row.code" class="q-card">
            <div class="qc-head">
              <el-input v-model="row.name" size="small" class="qc-name" />
              <label class="color-chip" :style="{ background: row.color }">
                <input type="color" v-model="row.color" />
              </label>
              <el-switch v-model="row.enabled" size="small" />
            </div>
            <div class="qc-grid">
              <label class="qc-field">
                <span>倍率</span>
                <el-input-number
                  v-model="row.multiplier"
                  :min="0.5"
                  :max="100"
                  :step="1"
                  :precision="2"
                  size="small"
                  controls-position="right"
                />
              </label>
              <label class="qc-field">
                <span>自定义真实价</span>
                <el-input-number
                  v-model="row.owner_price_override"
                  :min="0"
                  :precision="2"
                  size="small"
                  controls-position="right"
                  placeholder="默认"
                />
              </label>
              <label class="qc-field">
                <span>自定义代理价</span>
                <el-input-number
                  v-model="row.agent_price_override"
                  :min="0"
                  :precision="2"
                  size="small"
                  controls-position="right"
                  placeholder="默认"
                />
              </label>
              <label class="qc-field">
                <span>排序</span>
                <el-input-number
                  v-model="row.sort"
                  :min="0"
                  :max="99"
                  size="small"
                  controls-position="right"
                />
              </label>
            </div>
            <div class="qc-foot">
              <span class="mono text-2 qc-code">{{ row.code }}</span>
              <el-button size="small" type="primary" plain :loading="savingQ === row.code" @click="saveQuality(row)">保存</el-button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </SettingsShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import http from '../../api'
import QualityBadge from '../../components/QualityBadge.vue'
import SettingsShell from '../../components/ui/SettingsShell.vue'
import { sensitiveConfirm, withConfirm } from '../../utils/sensitive'

const loading = ref(false)
const savingBase = ref(false)
const savingQ = ref('')
const qualities = ref([])

const form = reactive({
  owner_base_price: 300,
  agent_base_price: 50,
})

const qualityPreview = computed(() =>
  qualities.value
    .filter((q) => q.enabled)
    .map((q) => ({
      code: q.code,
      name: q.name,
      color: q.color,
      multiplier: Number(q.multiplier),
      owner_price: q.owner_price,
      agent_price: q.agent_price,
      owner_price_override: q.owner_price_override ?? null,
      agent_price_override: q.agent_price_override ?? null,
    }))
)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const s = await http.get('/settings')
    const st = s.settings
    form.owner_base_price = Number(st.owner_base_price ?? 300)
    form.agent_base_price = Number(st.agent_base_price ?? 50)
    await loadQualities()
  } finally {
    loading.value = false
  }
}

async function loadQualities() {
  const q = await http.get('/qualities')
  qualities.value = q.qualities.map((x) => ({
    ...x,
    multiplier: Number(x.multiplier),
    owner_price_override: x.owner_price_override ?? null,
    agent_price_override: x.agent_price_override ?? null,
  }))
}

// 数值校验：非法/空/非 finite/负数都不允许提交
function isNumberValue(v) {
  return v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v))
}
function isValidNonNegative(v) {
  return isNumberValue(v) && Number(v) >= 0
}
function normalizeOverride(v) {
  if (v === null || v === undefined || v === '') return { ok: true, value: null }
  const n = Number(v)
  return { ok: Number.isFinite(n) && n >= 0, value: n }
}

async function saveBasePrices() {
  if (!isValidNonNegative(form.owner_base_price) || !isValidNonNegative(form.agent_base_price)) {
    ElMessage.warning('基础价格必须是不小于 0 的有效数字')
    return
  }
  const password = await sensitiveConfirm({
    title: '修改价格确认',
    content: '修改基础价格需要输入登录密码确认',
  })
  if (password == null) return

  savingBase.value = true
  try {
    await http.put(
      '/settings',
      {
        owner_base_price: Number(form.owner_base_price),
        agent_base_price: Number(form.agent_base_price),
      },
      withConfirm(password)
    )
    ElMessage.success('已保存')
    await loadQualities()
  } finally {
    savingBase.value = false
  }
}

async function saveQuality(row) {
  const name = String(row.name || '').trim()
  if (!name) {
    ElMessage.warning('品质名称不能为空')
    return
  }
  const multiplier = Number(row.multiplier)
  if (!Number.isFinite(multiplier) || multiplier <= 0) {
    ElMessage.warning('品质倍率必须是大于 0 的有效数字')
    return
  }
  const owner = normalizeOverride(row.owner_price_override)
  if (!owner.ok) {
    ElMessage.warning('自定义真实价必须是不小于 0 的有效数字，或留空')
    return
  }
  const agent = normalizeOverride(row.agent_price_override)
  if (!agent.ok) {
    ElMessage.warning('自定义代理价必须是不小于 0 的有效数字，或留空')
    return
  }
  if (!isValidNonNegative(row.sort)) {
    ElMessage.warning('排序必须是不小于 0 的有效数字')
    return
  }

  const password = await sensitiveConfirm({
    title: '修改品质确认',
    content: `保存「${name}」的品质配置需要输入登录密码确认`,
  })
  if (password == null) return

  savingQ.value = row.code
  try {
    await http.put(
      `/qualities/${encodeURIComponent(row.code)}`,
      {
        name,
        color: row.color,
        multiplier,
        sort: Number(row.sort),
        enabled: row.enabled,
        owner_price_override: owner.value,
        agent_price_override: agent.value,
      },
      withConfirm(password)
    )
    ElMessage.success(`${name} 已保存`)
    await loadQualities()
  } finally {
    savingQ.value = ''
  }
}
</script>

<style scoped>
/* ===== 基础价格双输入 ===== */
.price-form { display: flex; gap: 24px; align-items: flex-end; flex-wrap: wrap; }
.price-item { min-width: 0; }
.p-label { font-size: 12.5px; color: var(--text-2); margin-bottom: 6px; }
.price-tip { margin-top: 14px; }
.price-table { margin-top: 12px; }
.agent-price { color: var(--info); }
.price-note { font-size: 11px; margin-left: 6px; font-weight: 400; }

/* ===== 品质编辑表 ===== */
.color-chip {
  width: 40px; height: 24px; border-radius: 6px; display: inline-block;
  overflow: hidden; cursor: pointer; border: 1px solid var(--border-2);
}
.color-chip input { opacity: 0; width: 100%; height: 100%; cursor: pointer; }

/* ===== 移动端卡片（桌面隐藏） ===== */
.mobile-only { display: none; }
.preview-card,
.q-card {
  padding: 13px 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.pc-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.pc-mult { font-size: 12.5px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.pc-prices {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px; margin-top: 12px;
}
.pc-price { min-width: 0; display: flex; align-items: baseline; gap: 3px; flex-wrap: wrap; }
.pc-label { width: 100%; font-size: 11.5px; color: var(--text-3); margin-bottom: 2px; }
.pc-price b { font-size: 14px; font-variant-numeric: tabular-nums; }
.pc-price .price-note { margin-left: 2px; }

.qc-head { display: flex; align-items: center; gap: 10px; }
.qc-name { flex: 1; min-width: 0; }
.qc-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px; margin-top: 12px;
}
.qc-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.qc-field > span { font-size: 11.5px; color: var(--text-3); }
.qc-field :deep(.el-input-number) { width: 100%; }
.qc-foot {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-top: 12px; padding-top: 10px;
  border-top: 1px solid var(--border);
}
.qc-code { font-size: 11px; }

@media (max-width: 768px) {
  .desktop-only { display: none; }
  .mobile-only { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
  .price-form { gap: 14px; }
  .price-item { flex: 1 1 100%; }
  .price-item :deep(.el-input-number) { width: 100% !important; }
  .price-tip { margin-top: 12px; }
}

@media (max-width: 420px) {
  .qc-grid,
  .pc-prices { grid-template-columns: 1fr; }
}
</style>
