<template>
  <SettingsShell
    title="通用设置"
    description="站点名称、需求书页眉与客户交付链接等基础配置"
    icon="ri:home-gear-line"
    :loading="loading"
  >
    <div class="settings-stack">
      <section class="settings-section">
        <div class="settings-section-head">
          <div>
            <div class="settings-section-title">站点与界面</div>
            <p class="settings-section-desc">站点名称、浏览器标题与订单详情防截图水印</p>
          </div>
        </div>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="站点名称">
            <el-input v-model="form.site_name" :maxlength="30" placeholder="毕设接单管理系统" />
            <div class="settings-hint">显示在浏览器标题与客户可见页面（报价单 / 交付页）；保存后立即生效。</div>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="savingKey === 'site'" @click="saveSite">保存站点</el-button>
          </el-form-item>
        </el-form>
        <div class="wm-divider" />
        <div class="wm-row" :class="{ off: !form.watermark_enabled }">
          <span class="wm-icon"><Icon icon="ri:drop-line" /></span>
          <div class="wm-copy">
            <div class="wm-title">订单详情水印</div>
            <div class="wm-desc">订单详情页叠加「用户名 · 单号」防截图水印，防止内容截图外传；关闭后所有角色不再显示。</div>
          </div>
          <div class="wm-ops">
            <span class="wm-state">{{ form.watermark_enabled ? '已开启' : '已关闭' }}</span>
            <el-switch v-model="form.watermark_enabled" :loading="wmSaving" @change="toggleWatermark" />
          </div>
        </div>
      </section>

      <section class="settings-section">
        <div class="settings-section-head">
          <div>
            <div class="settings-section-title">交付与文档</div>
            <p class="settings-section-desc">需求书 Word 页眉与客户免登录交付链接的有效期</p>
          </div>
        </div>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="需求书 Word 页眉（学校名）">
            <el-input v-model="form.docx_school" :maxlength="60" placeholder="例如：XX大学 计算机科学与技术学院" />
            <div class="settings-hint">生成的需求书 Word 每页页眉居中显示；留空不加页眉。</div>
          </el-form-item>
          <el-form-item label="客户交付链接有效期（天）">
            <el-input-number
              v-model="form.deliver_expire_days"
              :min="0"
              :max="3650"
              :precision="0"
              controls-position="right"
              style="width: 180px"
            />
            <div class="settings-hint">发给客户的免登录交付页超过该天数后自动失效；0 = 永久有效。</div>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="savingKey === 'delivery'" @click="saveDelivery">保存</el-button>
          </el-form-item>
        </el-form>
      </section>
    </div>
  </SettingsShell>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../../api'
import SettingsShell from '../../components/ui/SettingsShell.vue'

const loading = ref(false)
const savingKey = ref('')
// 水印开关：独立于两个表单分组，拨动后立即保存
const wmSaving = ref(false)

const form = reactive({
  site_name: '',
  docx_school: '',
  deliver_expire_days: 0,
  watermark_enabled: true,
})

onMounted(load)

async function load() {
  loading.value = true
  try {
    const s = await http.get('/settings')
    const st = s.settings
    form.site_name = st.site_name || ''
    form.docx_school = st.docx_school || ''
    form.deliver_expire_days = Number(st.deliver_expire_days || 0)
    form.watermark_enabled = st.watermark_enabled !== '0'
  } finally {
    loading.value = false
  }
}

async function toggleWatermark() {
  if (wmSaving.value) return
  const target = form.watermark_enabled
  wmSaving.value = true
  try {
    await http.put('/settings', { watermark_enabled: target ? '1' : '0' })
    ElMessage.success(target ? '水印已开启' : '水印已关闭')
  } catch {
    form.watermark_enabled = !target // 保存失败回弹，错误由拦截器提示
  } finally {
    wmSaving.value = false
  }
}

async function saveSite() {
  savingKey.value = 'site'
  try {
    const siteName = form.site_name.trim()
    await http.put('/settings', { site_name: siteName })
    form.site_name = siteName
    ElMessage.success('已保存')
    // 通知 AdminLayout 立即刷新侧边栏站点名与浏览器标题
    window.dispatchEvent(new CustomEvent('site-name', { detail: siteName }))
  } finally {
    savingKey.value = ''
  }
}

async function saveDelivery() {
  const days = Number(form.deliver_expire_days)
  if (!Number.isFinite(days) || days < 0) {
    ElMessage.warning('有效期必须是不小于 0 的整数')
    return
  }
  savingKey.value = 'delivery'
  try {
    await http.put('/settings', {
      docx_school: form.docx_school.trim(),
      deliver_expire_days: String(days),
    })
    ElMessage.success('已保存')
  } finally {
    savingKey.value = ''
  }
}
</script>

<style scoped>
/* ===== 水印开关：分区内的扁平行（表单下方细分隔线过渡），拨动即生效 ===== */
.wm-divider { height: 1px; background: var(--border); margin: 2px 0 2px; }
.wm-row {
  display: flex; align-items: center; gap: 13px;
  padding: 13px 12px; margin-top: 2px;
  border-radius: var(--radius-md);
  transition: background 0.15s ease;
}
.wm-row:hover { background: var(--hover); }
.wm-icon {
  width: 36px; height: 36px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: var(--radius-sm);
  background: var(--brand-weak); color: var(--brand); font-size: 17px;
  transition: background 0.18s ease, color 0.18s ease;
}
.wm-row.off .wm-icon { background: var(--card-3); color: var(--text-3); }
.wm-copy { flex: 1; min-width: 0; }
.wm-title { font-size: 13.5px; font-weight: 600; color: var(--text); }
.wm-desc { margin-top: 4px; font-size: 12px; color: var(--text-3); line-height: 1.6; }
.wm-ops { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.wm-state { font-size: 11.5px; font-weight: 600; color: var(--success); }
.wm-row.off .wm-state { color: var(--text-3); font-weight: 500; }

@media (max-width: 640px) {
  .wm-row { flex-wrap: wrap; padding: 12px 10px; }
  .wm-ops { width: 100%; justify-content: space-between; margin-left: 49px; }
}
</style>
