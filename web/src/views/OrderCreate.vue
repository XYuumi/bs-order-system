<template>
  <div class="page-shell oc-page">
    <!-- 订单工作台头图：完成度 + 步骤导航 -->
    <section class="oc-hero">
      <div class="hero-grid" aria-hidden="true" />
      <div class="hero-glow" aria-hidden="true" />
      <div class="hero-copy">
        <div class="hero-eyebrow"><span class="hero-dot" /> NEW ORDER · 订单创建</div>
        <h1>把需求，变成一张<br /><em>可交付的订单。</em></h1>
        <p>题目、规格、价格一次确定；提交后自动编号，并进入详情页继续补充需求书与交付物。</p>
        <div class="hero-chips">
          <span><Icon icon="ri:hashtag" />自动编号</span>
          <span><Icon icon="ri:sparkling-2-line" />AI 需求书</span>
          <span><Icon icon="ri:send-plane-line" />客户交付链接</span>
        </div>
        <div class="hero-actions">
          <el-button @click="router.back()"><Icon icon="ri:arrow-left-line" class="btn-ic" />返回列表</el-button>
          <span class="hero-hint"><kbd>Ctrl</kbd><span>+</span><kbd>Enter</kbd> 快速创建</span>
        </div>
      </div>
      <div class="hero-progress">
        <div class="ring" :style="{ '--p': completion }">
          <div class="ring-inner">
            <b>{{ completion }}%</b>
            <span>完成度</span>
          </div>
        </div>
        <div class="hero-steps">
          <button
            v-for="step in progressSteps" :key="step.id"
            class="hero-step" :class="{ done: step.done, active: step.active }"
            type="button" @click="scrollToSection(step.id)"
          >
            <span class="hs-dot">
              <Icon v-if="step.done" icon="ri:check-line" />
              <span v-else>{{ step.no }}</span>
            </span>
            <span class="hs-label">{{ step.label }}</span>
          </button>
        </div>
      </div>
    </section>

    <div class="oc-layout">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        class="oc-main"
        @submit.prevent
      >
        <!-- 基础信息 -->
        <section id="sec-basic" data-step="01" class="art-card oc-section" :class="{ 'is-done': titleDone }" style="--i: 0">
          <div class="oc-sec-head">
            <div class="oc-sec-copy">
              <h3>基础信息 <span v-if="titleDone" class="sec-done-tag"><Icon icon="ri:check-line" />已填写</span></h3>
              <p>先写题目，可用 AI 辅助识别项目类型与技术栈</p>
            </div>
            <el-button
              class="ai-btn"
              type="primary"
              plain
              size="small"
              :loading="analyzing"
              :disabled="submitting"
              @click="doAnalyze"
            >
              <Icon v-if="!analyzing" icon="ri:flashlight-line" />
              {{ analyzing ? '分析中' : 'AI 分析' }}
            </el-button>
          </div>

          <el-form-item prop="title" label="论文题目">
            <el-input
              v-model="form.title"
              class="title-input"
              placeholder="例如：基于 SpringBoot 的养老院管理系统设计与实现"
              :maxlength="255"
              size="large"
              clearable
              @input="resetDuplicateCheck"
              @blur="checkDuplicate"
            />
          </el-form-item>

          <!-- 单号默认按日期自动生成；只有工作人员（管理员 / 写手）可以手动指定，用于导入历史项目 -->
          <el-form-item v-if="auth.isStaffView" label="订单编号">
            <el-input v-model="form.order_no" placeholder="留空按日期自动生成；导入历史项目可填原编号" :maxlength="16" clearable />
          </el-form-item>

          <transition name="fade">
            <div v-if="duplicates.length" class="dup-warn">
              <div class="dw-head">
                <Icon icon="ri:error-warning-line" class="dw-icon" />
                <span>发现 <b>{{ duplicates.length }}</b> 个相似订单，请确认不是重复接单</span>
              </div>
              <div v-for="d in duplicates" :key="d.id" class="dw-row">
                <span class="mono dw-id">{{ d.id }}</span>
                <span class="dw-title">{{ d.title }}</span>
                <span class="dw-status" :style="{ color: statusMeta(d.status).hex }">{{ statusMeta(d.status).label }}</span>
                <span class="dw-sim tnum">{{ d.similarity }}%</span>
              </div>
              <div class="text-3 dw-tip">如确认无冲突可继续提交</div>
            </div>
          </transition>

          <!-- AI 分析：加载骨架 / 失败 / 结果 三种互斥状态 -->
          <div v-if="analyzing" class="ai-panel ai-loading" aria-live="polite">
            <div class="ai-loading-head">
              <Icon icon="ri:flashlight-line" class="ai-loading-ic" />
              <span>AI 正在分析题目…</span>
              <span class="text-3">通常需要数秒</span>
            </div>
            <el-skeleton :rows="2" animated />
          </div>
          <div v-else-if="aiError" class="ai-panel ai-error">
            <Icon icon="ri:error-warning-line" />
            <span>{{ aiError }}</span>
            <el-button size="small" link type="primary" @click="doAnalyze">重试</el-button>
          </div>
          <div v-else-if="analysis" class="ai-panel">
            <div class="ai-panel-head">
              <Icon icon="ri:flashlight-line" />
              <span>AI 分析结果</span>
              <el-button size="small" link type="primary" class="ai-refresh" @click="doAnalyze">重新分析</el-button>
            </div>
            <div class="ai-row">
              <span class="ai-label">推荐项目类型</span>
              <ProjectTypeTag :project-type="analysis.project_type" />
              <span v-if="analysis.project_type_reason" class="text-3 ai-reason">{{ analysis.project_type_reason }}</span>
            </div>
            <div v-if="analysis.suggested_tech" class="ai-row">
              <span class="ai-label">推荐技术栈</span>
              <span class="ai-chip mono">{{ analysis.suggested_tech }}</span>
              <el-button size="small" link type="primary" @click="form.tech_stack = analysis.suggested_tech">采用</el-button>
            </div>
            <div v-if="analysis.difficulty" class="ai-row">
              <span class="ai-label">难度</span>
              <span class="ai-chip">{{ analysis.difficulty }}</span>
              <template v-if="analysis.suggested_quality">
                <span class="ai-label ai-label-gap">建议品质</span>
                <el-button size="small" link type="primary" @click="applySuggestedQuality">
                  设为 {{ qualityName(analysis.suggested_quality) }}
                </el-button>
              </template>
            </div>
          </div>
        </section>

        <!-- 原始需求 -->
        <section id="sec-context" data-step="02" class="art-card oc-section" :class="{ 'is-done': contextDone }" style="--i: 1">
          <div class="oc-sec-head">
            <div class="oc-sec-copy">
              <h3>原始需求 <span class="sec-optional">可选</span></h3>
              <p>上传客户需求文档或写下口头需求总结，AI 生成需求书时以此为准，而不是仅凭题目</p>
            </div>
          </div>

          <div
            class="src-upload" :class="{ dragging }"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="onDrop"
          >
            <input
              ref="fileInputRef" type="file" accept=".docx,.pdf,.txt,.md,.json"
              class="src-file-input" @change="onFileChosen"
            />
            <div v-if="!sourceDoc" class="src-drop">
              <span class="src-drop-icon"><Icon icon="ri:upload-cloud-2-line" /></span>
              <div class="src-drop-copy">
                <b>拖入需求文档，或点击上传</b>
                <span>支持 Word / PDF / TXT / Markdown / JSON，10MB 以内</span>
              </div>
              <el-button plain :loading="parsing" @click="fileInputRef?.click()">
                <Icon v-if="!parsing" icon="ri:upload-2-line" />
                {{ parsing ? '解析中…' : '选择文件' }}
              </el-button>
            </div>
            <div v-if="sourceDoc" class="src-card">
              <Icon
                :icon="sourceDoc.format_matched ? 'ri:file-check-line' : 'ri:file-list-3-line'"
                class="src-ic" :class="{ ok: sourceDoc.format_matched }"
              />
              <div class="src-info">
                <div class="src-name" :title="sourceDoc.filename">{{ sourceDoc.filename }}</div>
                <div class="src-meta text-3">
                  {{ sourceDoc.chars }} 字 · {{ sourceDoc.format_matched ? '格式匹配，可直接导入' : '将由 AI 转换为本系统格式' }}{{ sourceDoc.truncated ? ' · 原文过长已截断' : '' }}
                </div>
              </div>
              <el-button text type="danger" size="small" @click="clearSourceDoc">
                <Icon icon="ri:close-line" /> 移除
              </el-button>
            </div>
            <div v-else class="src-tip text-3">
              图片型扫描件无法提取文字；没有文档也可以直接填写下方需求要点
            </div>
          </div>

          <div v-if="sourceDoc" class="src-apply-mode">
            <el-checkbox v-model="sourceRefGen">
              以上传文档为参考，由 AI 重新生成需求书
            </el-checkbox>
            <div class="text-3 sam-hint">
              <template v-if="sourceRefGen">AI 会以上传的文档为基准，整理生成本系统九章需求书（内容可能被重新组织）</template>
              <template v-else><b>直接采用：</b>上传的文档将原样作为需求书，系统不做任何修改（预览、导出、留档均为原文）</template>
            </div>
          </div>

          <el-form-item label="需求要点（口头 / 零散需求总结）" style="margin-top: 14px">
            <el-input
              v-model="form.requirement_notes"
              type="textarea"
              :rows="3"
              :maxlength="4000"
              show-word-limit
              placeholder="例如：要有积分商城；管理员可导出报表；最好用微信小程序；客户强调不要短信功能…… 生成需求书时会逐条体现"
            />
          </el-form-item>
        </section>

        <!-- 项目类型：纯程序设计 / 纯论文 / 论文+设计 -->
        <section id="sec-project-type" data-step="03" class="art-card oc-section is-done" style="--i: 2">
          <div class="oc-sec-head">
            <div class="oc-sec-copy">
              <h3>项目类型 <span class="req-mark">必选</span><span class="sec-done-tag"><Icon icon="ri:check-line" />已选择</span></h3>
              <p>决定交付构成：含论文的类型将启用论文进度（任务书 → 开题报告 → 初稿 → 终稿）</p>
            </div>
          </div>
          <div class="cat-grid" role="radiogroup" aria-label="项目类型">
            <div
              v-for="pt in PROJECT_TYPES"
              :key="pt.value"
              class="cat-card"
              :class="{ selected: form.project_type === pt.value }"
              :style="ptStyle(pt)"
              role="radio"
              :aria-checked="form.project_type === pt.value"
              tabindex="0"
              @click="form.project_type = pt.value"
              @keydown.enter.prevent="form.project_type = pt.value"
              @keydown.space.prevent="form.project_type = pt.value"
            >
              <div class="cat-head">
                <span class="cat-icon" :style="{ background: pt.hex + '1a', color: pt.hex }">{{ pt.icon }}</span>
                <span class="cat-name">{{ pt.label }}</span>
              </div>
              <div class="cat-desc">{{ pt.desc }}</div>
              <div v-if="form.project_type === pt.value" class="cat-check" :style="{ background: pt.hex }">
                <Icon icon="ri:check-line" class="cat-check-ic" />
              </div>
            </div>
          </div>
          <transition name="fade">
            <div v-if="paperEnabled" class="pt-paper-hint">
              <Icon icon="ri:file-paper-2-line" />
              <span>论文类订单：初稿每次修改都会自动留档，至少修改 5 次才能提交终稿。</span>
            </div>
          </transition>
        </section>

        <!-- 品质与价格 -->
        <section id="sec-quality" data-step="04" class="art-card oc-section" :class="{ 'is-done': qualityDone }" style="--i: 3">
          <div class="oc-sec-head">
            <div class="oc-sec-copy">
              <h3>品质与价格 <span class="req-mark">必选</span><span v-if="qualityDone" class="sec-done-tag"><Icon icon="ri:check-line" />已选择</span></h3>
              <p>{{ auth.isAdmin ? '真实价可由管理员按本单调整' : '价格按品质倍率自动计算' }}</p>
            </div>
            <span v-if="auth.isAdmin" class="oc-head-hint">点铅笔调价</span>
          </div>

          <div v-loading="qualityLoading" class="quality-grid" role="radiogroup" aria-label="品质">
            <div
              v-for="q in qualities"
              :key="q.code"
              class="quality-card"
              :class="{ selected: form.quality_code === q.code, editing: editing === q.code }"
              :style="qualityStyle(q)"
              role="radio"
              :aria-checked="form.quality_code === q.code"
              :tabindex="editing === q.code ? -1 : 0"
              @click="selectQuality(q.code)"
              @keydown.enter.prevent="selectQuality(q.code)"
              @keydown.space.prevent="selectQuality(q.code)"
            >
              <template v-if="editing === q.code">
                <div class="q-head">
                  <span class="q-dot" :style="{ background: q.color }" />
                  <span class="q-name">{{ q.name }}</span>
                </div>
                <div class="q-edit" @click.stop>
                  <div class="q-num">
                    <span class="q-cur">¥</span>
                    <el-input-number
                      :ref="setEditInputRef"
                      v-model="editDraft"
                      :min="0"
                      :max="1000000"
                      :step="10"
                      :precision="2"
                      size="large"
                      class="q-input"
                      @keyup.enter="commitEdit(q)"
                    />
                  </div>
                  <div class="q-edit-ops">
                    <el-button size="small" type="primary" @click.stop="commitEdit(q)">确定</el-button>
                    <el-button size="small" text @click.stop="resetPrice(q)">恢复公式价</el-button>
                  </div>
                </div>
              </template>
              <template v-else>
                <div class="q-head">
                  <span class="q-dot" :style="{ background: q.color }" />
                  <span class="q-name">{{ q.name }}</span>
                  <!-- 倍数、写手价与调价按钮：管理员和代理都按「成交价」口径看，所以都能看到倍数、也都能调本单价 -->
                  <span v-if="auth.isAdmin || auth.isAgent" class="q-mult">×{{ q.multiplier }}</span>
                </div>
                <div class="q-price">
                  <span class="q-amount" :style="{ color: isEdited(q) ? q.color : undefined }">
                    ¥{{ priceText(q) }}
                  </span>
                  <span class="q-note">{{ priceNote(q) }}</span>
                  <span v-if="isEdited(q)" class="q-edited-mark">自定义</span>
                </div>
                <div v-if="auth.isAdmin" class="q-agent">写手价 ¥{{ formatMoney(q.agent_price) }}</div>
                <button
                  v-if="auth.isAdmin || auth.isAgent"
                  class="q-edit-btn"
                  type="button"
                  title="调整本单价格"
                  aria-label="调整本单价格"
                  @click.stop="startEdit(q)"
                >
                  <Icon icon="ri:pencil-line" />
                </button>
              </template>
            </div>
            <div v-if="!qualityLoading && !qualities.length" class="q-empty text-3">
              暂无可选品质，请联系管理员
            </div>
          </div>

          <div v-if="auth.isAdmin && hasAnyEdit" class="custom-price-tip">
            <Icon icon="ri:information-line" class="cpt-icon" />
            <span>已启用自定义价格：提交后仅覆盖本单真实价，代理仍按品质公式计价</span>
            <el-button size="small" link type="primary" @click="clearAllEdits">全部恢复</el-button>
          </div>
        </section>

        <!-- 交付与客户 -->
        <section id="sec-delivery" data-step="05" class="art-card oc-section" :class="{ 'is-done': deliveryDone }" style="--i: 4">
          <div class="oc-sec-head">
            <div class="oc-sec-copy">
              <h3>交付与客户 <span class="sec-optional">可选</span></h3>
              <p>可以留空稍后补充；技术栈可自由输入</p>
            </div>
          </div>

          <div class="form-row">
            <el-form-item label="交付期限">
              <el-date-picker
                v-model="form.deadline"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="未设置（可稍后补充）"
                :disabled-date="disabledDate"
                style="width: 100%"
              />
              <div class="quick-dates">
                <button v-for="q in quickDeadlines" :key="q.days" type="button" @click="setQuickDeadline(q.days)">{{ q.label }}</button>
                <button v-if="form.deadline" type="button" class="clear" @click="form.deadline = undefined">清除</button>
              </div>
            </el-form-item>
            <el-form-item label="技术栈偏好（可选）">
              <el-autocomplete
                v-model="form.tech_stack"
                :fetch-suggestions="suggestTech"
                placeholder="留空将由 AI 按题目与需求智能选择"
                clearable
                style="width: 100%"
              />
            </el-form-item>
          </div>

          <div v-if="auth.isStaffView" class="form-row">
            <el-form-item label="来源代理（可选）">
              <el-select v-model="form.agent_username" placeholder="自接单（不选）" clearable filterable style="width: 100%">
                <el-option v-for="a in agents" :key="a.username" :label="a.display_name || a.username" :value="a.username" />
              </el-select>
            </el-form-item>
            <el-form-item label="客户信息（可选）">
              <el-input v-model="form.customer_info" placeholder="客户称呼 / 联系方式 / 学校等" :maxlength="255" />
            </el-form-item>
          </div>
        </section>

        <!-- 备注 -->
        <section id="sec-remark" data-step="06" class="art-card oc-section" style="--i: 5">
          <div class="oc-sec-head">
            <div class="oc-sec-copy">
              <h3>备注 <span class="sec-optional">可选</span></h3>
              <p>补充特殊要求或对接说明</p>
            </div>
          </div>
          <el-form-item label="订单备注">
            <el-input
              v-model="form.remark"
              type="textarea"
              :rows="3"
              :maxlength="2000"
              show-word-limit
              placeholder="特殊要求、对接说明等"
            />
          </el-form-item>
        </section>
      </el-form>

      <!-- 右侧票据式摘要 -->
      <aside class="oc-aside">
        <section class="oc-summary art-card" style="--i: 6">
          <div class="ticket-head">
            <div class="summary-title"><Icon icon="ri:bill-line" />订单票据</div>
            <span class="ticket-draft">DRAFT</span>
          </div>

          <div class="ticket-rule" />

          <div class="sum-order-no">
            <Icon icon="ri:hashtag" />
            <span>提交后自动生成单号，并跳转订单详情</span>
          </div>

          <div class="sum-list">
            <div class="sum-row">
              <span class="sum-k">题目</span>
              <span class="sum-v sum-title" :class="{ 'is-empty': !form.title.trim() }">
                {{ form.title.trim() || '未填写' }}
              </span>
            </div>
            <div class="sum-row">
              <span class="sum-k">项目类型</span>
              <span class="sum-v"><ProjectTypeTag :project-type="form.project_type" /></span>
            </div>
            <div class="sum-row">
              <span class="sum-k">品质</span>
              <span class="sum-v">
                <QualityBadge v-if="selectedQuality" :name="selectedQuality.name" :color="selectedQuality.color" />
                <span v-else class="is-empty">未选择</span>
              </span>
            </div>
            <div class="sum-row">
              <span class="sum-k">期限</span>
              <span class="sum-v" :class="{ 'is-empty': !form.deadline }">{{ form.deadline || '未设置' }}</span>
            </div>
            <div v-if="sourceSummaryText" class="sum-row">
              <span class="sum-k">原始需求</span>
              <span class="sum-v">{{ sourceSummaryText }}</span>
            </div>
          </div>

          <div class="ticket-rule dashed" />

          <div class="sum-checks">
            <div v-for="item in completionItems" :key="item.key" class="sum-check" :class="{ done: item.done }">
              <span class="sc-icon"><Icon :icon="item.done ? 'ri:checkbox-circle-fill' : 'ri:circle-line'" /></span>
              <span>{{ item.label }}</span>
            </div>
          </div>

          <div class="sum-price-box">
            <template v-if="selectedQuality">
              <div class="sum-price-label">
                {{ auth.isAdmin ? '本单真实价' : auth.isAgent ? '本单成交价' : '本单价格' }}
                <span v-if="currentPriceIsEdited" class="sum-edited">已调价</span>
              </div>
              <div class="sum-price-line">
                <CountTo v-if="currentPrice != null" :target="currentPrice" prefix="¥" :decimals="priceDecimals" class="sum-price" />
                <span v-else class="sum-price">—</span>
                <span class="sum-price-mult">×{{ selectedQuality.multiplier }}</span>
              </div>
              <div v-if="auth.isAdmin" class="sum-agent-price">写手价 ¥{{ formatMoney(selectedQuality.agent_price) }}</div>
              <div class="sum-note text-3">
                {{ auth.isAdmin ? '按品质公式计算，可调整本单真实价' : '价格由品质与倍率自动计算' }}
              </div>
            </template>
            <div v-else class="sum-price-empty">
              <Icon icon="ri:price-tag-3-line" />
              <span>选择品质后显示价格</span>
            </div>
          </div>

          <div class="sum-actions">
            <el-button type="primary" size="large" class="sum-submit" :loading="submitting" @click="submit">
              {{ submitting ? '创建中…' : '创建订单' }}
              <Icon v-if="!submitting" icon="ri:arrow-right-line" class="submit-ic" />
            </el-button>
            <el-button size="large" class="sum-cancel" @click="router.back()">取消</el-button>
          </div>
          <p class="sum-foot text-3"><Icon icon="ri:lock-line" />提交后可在详情页继续补充资料</p>
          <div class="sum-shortcut"><kbd>Ctrl</kbd><span>+</span><kbd>Enter</kbd><span>快速创建</span></div>
        </section>
      </aside>
    </div>

    <!-- 移动端底部提交栏 -->
    <div class="oc-mobile-bar">
      <div class="mb-price">
        <span>{{ selectedQuality ? (auth.isAdmin ? '真实价' : '代理价') : '未选择品质' }}</span>
        <b v-if="selectedQuality">¥{{ formatMoney(currentPrice) }}</b>
        <b v-else>—</b>
      </div>
      <el-button type="primary" :loading="submitting" :disabled="!form.quality_code" @click="submit">
        创建订单
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { Icon } from '@iconify/vue'
import http from '../api'
import { sensitiveConfirm, withConfirm } from '../utils/sensitive'
import { useAuthStore } from '../stores/auth'
import ProjectTypeTag from '../components/ProjectTypeTag.vue'
import QualityBadge from '../components/QualityBadge.vue'
import CountTo from '../components/CountTo.vue'
import { PROJECT_TYPE_META, hasPaperWorkflow, statusMeta } from '../constants/orderMeta'

const auth = useAuthStore()
const router = useRouter()

const formRef = ref(null)
const qualities = ref([])
const qualityLoading = ref(true)
const agents = ref([])
const submitting = ref(false)
const analyzing = ref(false)
const analysis = ref(null)
const aiError = ref('')
const editing = ref('')
const editDraft = ref(0)
const editInputRef = ref(null)
const priceEdits = reactive({})
const duplicates = ref([])

// 原始需求资料：上传文档的解析结果 + 口头需求要点
const parsing = ref(false)
const dragging = ref(false)
const sourceDoc = ref(null) // { filename, chars, text, format_matched, truncated }
// 上传文档的应用方式：勾选=参考生成（默认，AI 重新组织）；不勾=原文直接采用，不做修改
const sourceRefGen = ref(true)
const fileInputRef = ref(null)

let dupTimer = null
let dupSeq = 0
let aiSeq = 0

const PT_DESC = {
  program: '只做程序设计，无论文交付',
  thesis: '只写论文，无程序设计',
  thesis_program: '论文与程序设计都包含（常见毕设形态）',
}
const PROJECT_TYPES = Object.entries(PROJECT_TYPE_META).map(([value, meta]) => ({
  value,
  ...meta,
  desc: PT_DESC[value] || '',
}))

const techOptions = [
  { value: 'SpringBoot+Vue3' }, { value: 'Django' }, { value: 'JSP+Servlet' },
  { value: 'Flask' }, { value: 'SpringBoot+Vue3+MySQL' }, { value: '微信小程序+SpringBoot' },
  { value: 'Vue3+Node.js' }, { value: 'Python数据分析' }, { value: 'Swing桌面应用' },
]

const form = reactive({
  order_no: '',
  deal_price: null,
  title: '',
  project_type: 'program',
  quality_code: '',
  deadline: undefined,
  tech_stack: undefined,
  agent_username: undefined,
  customer_info: '',
  remark: '',
  requirement_notes: '',
})

const paperEnabled = computed(() => hasPaperWorkflow(form.project_type))

function ptStyle(pt) {
  if (form.project_type !== pt.value) return {}
  return { borderColor: pt.hex, background: `color-mix(in srgb, ${pt.hex} 8%, transparent)` }
}

const sourceSummaryText = computed(() => {
  const parts = []
  if (sourceDoc.value) parts.push('文档')
  if (form.requirement_notes.trim()) parts.push('要点')
  return parts.join(' + ')
})

const rules = {
  title: [{
    required: true,
    trigger: 'blur',
    validator: (_rule, value, callback) => {
      const text = String(value || '').trim()
      if (!text) return callback(new Error('请输入论文题目'))
      if (text.length < 2) return callback(new Error('题目至少 2 个字'))
      callback()
    },
  }],
}

const selectedQuality = computed(() => qualities.value.find((q) => q.code === form.quality_code))
const hasAnyEdit = computed(() => Object.values(priceEdits).some((v) => v != null))

/* ---------- 完成度与步骤导航 ---------- */
const titleDone = computed(() => form.title.trim().length >= 2)
const contextDone = computed(() => Boolean(sourceDoc.value || form.requirement_notes.trim()))
const qualityDone = computed(() => Boolean(form.quality_code))
const deliveryDone = computed(() => Boolean(form.deadline || form.tech_stack || form.customer_info))
const completionItems = computed(() => [
  { key: 'title', label: '填写题目', done: titleDone.value },
  { key: 'quality', label: '选择品质', done: qualityDone.value },
  { key: 'delivery', label: '交付信息', done: deliveryDone.value },
  { key: 'context', label: '补充需求', done: contextDone.value },
])
const completion = computed(() => Math.round(
  (completionItems.value.filter((x) => x.done).length / completionItems.value.length) * 100,
))
const progressSteps = computed(() => {
  const steps = [
    { id: 'sec-basic', no: '01', label: '题目', done: titleDone.value },
    { id: 'sec-quality', no: '02', label: '品质', done: qualityDone.value },
    { id: 'sec-delivery', no: '03', label: '交付', done: deliveryDone.value },
    { id: 'sec-context', no: '04', label: '需求', done: contextDone.value },
  ]
  const firstOpen = steps.findIndex((s) => !s.done)
  return steps.map((s, i) => ({ ...s, active: i === firstOpen }))
})

const quickDeadlines = [
  { days: 7, label: '7 天' },
  { days: 15, label: '15 天' },
  { days: 30, label: '30 天' },
  { days: 45, label: '45 天' },
]

function setQuickDeadline(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  form.deadline = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function scrollToSection(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function toAmount(value) {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

const currentPrice = computed(() => {
  const q = selectedQuality.value
  if (!q) return null
  if (auth.isAdmin) {
    const edited = priceEdits[q.code]
    return toAmount(edited != null ? edited : (q.owner_price ?? q.agent_price))
  }
  // 代理看成交价（可被自己调整），写手看写手价
  return toAmount(auth.isAgent ? (priceEdits[q.code] != null ? Number(priceEdits[q.code]) : q.owner_price ?? null) : q.agent_price)
})

const priceDecimals = computed(() => {
  const n = Number(currentPrice.value)
  return Number.isFinite(n) && !Number.isInteger(n) ? 2 : 0
})

const currentPriceIsEdited = computed(() => {
  const q = selectedQuality.value
  return Boolean(q && auth.isAdmin && priceEdits[q.code] != null)
})

// 技术栈联想：按题目关键词向后端要建议，输入停顿 250ms 再请求；拿不到就退回本地固定列表
let suggestTimer = null
function suggestTech(_query, callback) {
  clearTimeout(suggestTimer)
  suggestTimer = setTimeout(() => {
    http.get('/orders/tech-suggestions', { params: { title: (form.title || '').trim() } })
      .then((data) => {
        callback((data.items || []).map((item) => ({ value: item.value })))
      })
      .catch(() => {
        callback(techOptions.map((o) => ({ value: o.value })))
      })
  }, 250)
}

function formatMoney(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function displayPrice(q) {
  if (auth.isAdmin) return q.owner_price ?? q.agent_price
  return auth.isAgent ? (priceEdits[q.code] != null ? Number(priceEdits[q.code]) : q.owner_price ?? null) : q.agent_price
}

function priceText(q) {
  const value = isEdited(q) ? priceEdits[q.code] : displayPrice(q)
  return value == null ? '—' : formatMoney(value)
}

function priceNote(q) {
  if (isEdited(q)) return '已调价'
  return auth.isAdmin ? '真实价' : auth.isAgent ? '成交价' : '代理价'
}

function isEdited(q) {
  return (auth.isAdmin || auth.isAgent) && priceEdits[q.code] != null
}

function qualityStyle(q) {
  const selected = form.quality_code === q.code
  return {
    '--q-color': q.color,
    ...(selected ? { borderColor: q.color, background: `color-mix(in srgb, ${q.color} 8%, transparent)` } : {}),
  }
}

function qualityName(code) {
  return qualities.value.find((q) => q.code === code)?.name || code
}

function setEditInputRef(el) {
  if (el) editInputRef.value = el
}

function basePrice(q) {
  return auth.isAgent ? Number(q.owner_price || 0) : Number(q.owner_price ?? q.agent_price ?? 0)
}

async function startEdit(q) {
  if (!auth.isAdmin && !auth.isAgent) return
  if (editing.value && editing.value !== q.code) {
    const current = qualities.value.find((x) => x.code === editing.value)
    if (current) commitEdit(current)
    if (editing.value) return
  }
  editDraft.value = priceEdits[q.code] != null ? Number(priceEdits[q.code]) : basePrice(q)
  editing.value = q.code
  await nextTick()
  editInputRef.value?.focus?.()
}

function commitEdit(q) {
  const value = editDraft.value == null || editDraft.value === '' ? NaN : Number(editDraft.value)
  if (!Number.isFinite(value) || value < 0) {
    ElMessage.warning('请输入有效的价格')
    return
  }
  if (value === basePrice(q)) delete priceEdits[q.code]
  else priceEdits[q.code] = value
  editing.value = ''
}

function resetPrice(q) {
  delete priceEdits[q.code]
  editing.value = ''
}

function clearAllEdits() {
  Object.keys(priceEdits).forEach((key) => delete priceEdits[key])
  editing.value = ''
}

function selectQuality(code) {
  if (editing.value === code) return
  // 切换品质前先把正在编辑的价格落定，避免草稿丢失
  if (editing.value) {
    const current = qualities.value.find((q) => q.code === editing.value)
    if (current) commitEdit(current)
    if (editing.value) return
  }
  form.quality_code = code
}

function applySuggestedQuality() {
  const code = analysis.value?.suggested_quality
  if (!code) return
  if (!qualities.value.some((q) => q.code === code)) {
    ElMessage.warning('建议品质当前不可用，请手动选择')
    return
  }
  form.quality_code = code
  editing.value = ''
  ElMessage.success(`已选择${qualityName(code)}`)
}

/* ---------- 撞单检测：debounce + 卸载清理 + 请求序号防旧覆盖 ---------- */
function resetDuplicateCheck() {
  if (dupTimer) {
    clearTimeout(dupTimer)
    dupTimer = null
  }
  // 题目变化后立即作废旧请求结果
  dupSeq += 1
  duplicates.value = []
}

function checkDuplicate() {
  resetDuplicateCheck()
  const title = form.title.trim()
  if (title.length < 4) return
  dupTimer = setTimeout(() => {
    dupTimer = null
    runDuplicateCheck(title)
  }, 500)
}

async function runDuplicateCheck(title) {
  const seq = ++dupSeq
  try {
    const data = await http.post('/orders/check-duplicate', { title })
    if (seq !== dupSeq) return
    duplicates.value = data.duplicates || []
  } catch {
    if (seq === dupSeq) duplicates.value = []
  }
}

/* ---------- AI 分析 ---------- */
async function doAnalyze() {
  if (analyzing.value) return
  const title = form.title.trim()
  if (title.length < 2) {
    ElMessage.warning('请先输入至少 2 个字的题目')
    return
  }
  const seq = ++aiSeq
  analyzing.value = true
  analysis.value = null
  aiError.value = ''
  try {
    const data = await http.post('/orders/ai/analyze-title', { title }, { timeout: 60000 })
    if (seq !== aiSeq) return
    if (!data.analysis) {
      aiError.value = '未获取到分析结果，请重试或手动选择'
      return
    }
    analysis.value = data.analysis
    if (PROJECT_TYPES.some((p) => p.value === data.analysis.project_type)) {
      form.project_type = data.analysis.project_type
    }
    ElMessage.success('AI 分析完成')
  } catch {
    if (seq === aiSeq) aiError.value = '分析失败，可重试或手动选择项目类型与品质'
  } finally {
    if (seq === aiSeq) analyzing.value = false
  }
}

/* ---------- 原始需求文档上传解析 ---------- */
async function onFileChosen(e) {
  const file = e.target.files?.[0]
  e.target.value = '' // 允许重复选择同一文件
  if (file) await handleFile(file)
}

async function onDrop(e) {
  dragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) await handleFile(file)
}

async function handleFile(file) {
  if (!file || parsing.value) return
  parsing.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const data = await http.post('/orders/parse-requirement-file', fd, { timeout: 120000 })
    sourceDoc.value = data
    ElMessage.success(data.message)
  } catch {
    /* 解析失败由拦截器提示，不阻塞建单 */
  } finally {
    parsing.value = false
  }
}

function clearSourceDoc() {
  sourceDoc.value = null
}

/* ---------- 提交 ---------- */
function todayKey() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function disabledDate(date) {
  const d = new Date(date)
  d.setHours(0, 0, 0, 0)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return d.getTime() < today.getTime()
}

async function submit() {
  // submitting 同时覆盖密码确认弹窗阶段：弹窗期间再次点击/快捷键不会叠开弹窗或重复建单
  if (submitting.value) return
  submitting.value = true
  try {
    await _doSubmit()
  } finally {
    submitting.value = false
  }
}

async function _doSubmit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (!form.quality_code) {
    ElMessage.warning('请选择品质')
    return
  }
  if (form.deadline && form.deadline < todayKey()) {
    ElMessage.warning('交付期限不能早于今天')
    return
  }

  const override = (auth.isAdmin || auth.isAgent) && priceEdits[form.quality_code] != null
    ? Number(priceEdits[form.quality_code])
    : null
  if (override != null && (!Number.isFinite(override) || override < 0)) {
    ElMessage.warning('自定义价格无效，请重新填写')
    return
  }

  // 覆盖「真实价」才需要密码二次确认；代理调的是自己的成交价，不用确认
  let confirmPwd = null
  if (auth.isAdmin && override != null) {
    confirmPwd = await sensitiveConfirm({
      title: '自定义价格确认',
      content: `本单真实价将覆盖为 ¥${override}，需要密码二次确认`,
    })
    if (confirmPwd == null) return
  }

  try {
    const payload = {
      title: form.title.trim(),
      order_no: (form.order_no || '').trim() || null,
      project_type: form.project_type,
      quality_code: form.quality_code,
      deadline: form.deadline || null,
      tech_stack: form.tech_stack || null,
      customer_info: form.customer_info || null,
      remark: form.remark || null,
      source_requirement: sourceDoc.value?.text || null,
      source_apply_mode: sourceDoc.value ? (sourceRefGen.value ? 'reference' : 'direct') : null,
      requirement_notes: form.requirement_notes || null,
    }
    if (auth.isStaffView && form.agent_username) payload.agent_username = form.agent_username
    if (override != null) payload.owner_price = override
    const data = await http.post('/orders', payload, confirmPwd ? withConfirm(confirmPwd) : {})
    ElMessage.success(`订单 ${data.order.id} 创建成功`)
    router.push(`/orders/${data.order.id}`)
  } catch {
    /* 错误由 axios 拦截器统一提示 */
  }
}

async function loadQualities() {
  qualityLoading.value = true
  try {
    const data = await http.get('/qualities', { params: { enabled_only: true } })
    qualities.value = data.qualities || []
  } catch {
    qualities.value = []
  } finally {
    qualityLoading.value = false
  }
}

async function loadAgents() {
  if (!auth.isStaffView) return
  try {
    const data = await http.get('/users')
    agents.value = (data.items || []).filter((x) => x.role === 'agent' && x.is_active)
  } catch {
    agents.value = []
  }
}

function onShortcut(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    submit()
  }
}

onMounted(() => {
  loadQualities()
  loadAgents()
  window.addEventListener('keydown', onShortcut)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onShortcut)
  if (dupTimer) clearTimeout(dupTimer)
  dupSeq += 1
  aiSeq += 1
})
</script>

<style scoped>
.oc-page { width: 100%; }
.btn-ic { margin-right: 4px; font-size: 14px; }

.oc-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  gap: var(--content-gap);
  align-items: start;
}
.oc-main { display: flex; flex-direction: column; gap: var(--content-gap); min-width: 0; }

/* 区块 stagger 上浮（prefers-reduced-motion 由 base.css 统一收敛） */
.oc-section,
.oc-summary {
  animation: rise-in 0.46s cubic-bezier(0.22, 0.61, 0.36, 1) both;
  animation-delay: calc(var(--i, 0) * 55ms);
}

.oc-sec-head { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
.oc-sec-icon {
  width: 34px; height: 34px; flex-shrink: 0;
  border-radius: var(--radius-sm);
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--brand-weak); color: var(--brand); font-size: 17px;
}
.oc-sec-copy { flex: 1; min-width: 0; }
.oc-sec-copy h3 {
  margin: 0; font-size: 14.5px; font-weight: 600; color: var(--text); letter-spacing: 0.01em;
}
.oc-sec-copy p { margin: 3px 0 0; font-size: 12px; color: var(--text-3); }
.oc-head-hint {
  flex-shrink: 0; font-size: 11px; color: var(--text-3);
  background: var(--card-2); border: 1px solid var(--border);
  padding: 2px 8px; border-radius: var(--radius-pill);
}
.req-mark {
  display: inline-block; margin-left: 6px; padding: 0 6px;
  font-size: 10.5px; font-weight: 500; line-height: 17px; vertical-align: 1px;
  color: var(--danger); background: var(--danger-weak); border-radius: var(--radius-pill);
}

.ai-btn .iconify { margin-right: 4px; font-size: 13px; }
.ai-btn { flex-shrink: 0; }

.oc-section :deep(.el-form-item) { margin-bottom: 0; }
.oc-section :deep(.el-form-item__label) { padding-bottom: 6px; }

.dup-warn {
  margin-top: 12px; padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--warning) 30%, transparent);
  border-radius: var(--radius-md);
  background: var(--warning-weak);
  display: flex; flex-direction: column; gap: 7px;
}
.dw-head { display: flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--text); }
.dw-icon { color: var(--warning); font-size: 15px; flex-shrink: 0; }
.dw-row {
  display: flex; align-items: center; gap: 10px; font-size: 12px;
  padding: 6px 9px; border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--card) 55%, transparent);
}
.dw-id { color: var(--text-2); font-size: 11px; flex-shrink: 0; }
.dw-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dw-status { flex-shrink: 0; font-size: 11px; font-weight: 500; }
.dw-sim { flex-shrink: 0; color: var(--warning); font-weight: 600; }
.dw-tip { font-size: 11.5px; }

.ai-panel {
  margin-top: 12px; padding: 13px 15px;
  display: flex; flex-direction: column; gap: 9px;
  border: 1px solid var(--border-2); border-radius: var(--radius-md);
  background: var(--card-2);
}
.ai-panel-head { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; color: var(--text-2); }
.ai-panel-head > .iconify { color: var(--brand); font-size: 14px; }
.ai-refresh { margin-left: auto; }
.ai-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12.5px; color: var(--text); }
.ai-label { font-weight: 600; color: var(--text-3); font-size: 11.5px; }
.ai-label-gap { margin-left: 6px; }
.ai-reason { font-size: 12px; }
.ai-chip {
  display: inline-flex; align-items: center; padding: 1px 8px;
  border: 1px solid var(--border); border-radius: var(--radius-xs);
  background: var(--card-3); color: var(--text-2);
  font-size: 12px; line-height: 19px;
}
.ai-loading-head { display: flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--text-2); }
.ai-loading-head .text-3 { margin-left: auto; font-size: 11.5px; }
.ai-loading-ic { color: var(--brand); animation: art-breathe 1.6s ease-in-out infinite; }
.ai-loading :deep(.el-skeleton__item) { height: 14px; border-radius: 4px; }
.ai-error {
  flex-direction: row; align-items: center; gap: 8px;
  border-color: color-mix(in srgb, var(--danger) 30%, transparent);
  background: var(--danger-weak);
  color: var(--text-2); font-size: 12.5px;
}
.ai-error > .iconify { color: var(--danger); flex-shrink: 0; }
.ai-error :deep(.el-button) { margin-left: auto; }

.cat-grid {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3); width: 100%;
}
.cat-card {
  position: relative; padding: 15px 16px;
  border: 1px solid var(--border-2); border-radius: var(--radius);
  background: var(--card-2); cursor: pointer; min-width: 0;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}
.cat-card:hover { transform: translateY(-2px); border-color: var(--border-3); box-shadow: var(--shadow-card); }
.cat-card:active { transform: translateY(0); }
.cat-head { display: flex; align-items: center; gap: 10px; min-width: 0; }
.cat-icon {
  width: 36px; height: 36px; flex-shrink: 0; border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center; font-size: 18px;
}
.cat-name { font-weight: 600; font-size: 13.5px; color: var(--text); }
.cat-desc { margin-top: 9px; font-size: 11.5px; line-height: 1.5; color: var(--text-3); }
.cat-check {
  position: absolute; top: -6px; right: -6px;
  width: 19px; height: 19px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.2);
}
.cat-check-ic { color: #fff; font-size: 10px; }

.quality-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
  gap: var(--space-3); width: 100%; min-height: 104px;
}
.quality-card {
  position: relative; min-height: 96px; min-width: 0;
  padding: 14px 15px 13px;
  border: 1px solid var(--border-2); border-radius: var(--radius);
  background: var(--card-2); cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}
.quality-card:hover { transform: translateY(-2px); border-color: var(--border-3); box-shadow: var(--shadow-card); }
.quality-card:active { transform: translateY(0); }
.quality-card.editing { cursor: default; transform: none; }
.q-head { display: flex; align-items: center; gap: 6px; padding-right: 26px; min-width: 0; }
.q-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.q-name { font-weight: 600; font-size: 13px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.q-mult {
  margin-left: auto; flex-shrink: 0;
  font-size: 10.5px; color: var(--text-3);
  background: var(--card-3); padding: 1px 7px; border-radius: var(--radius-pill);
}
.q-price { margin-top: 11px; display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.q-amount { font-size: 19px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.q-note { font-size: 10.5px; color: var(--text-3); }
.q-edited-mark {
  font-size: 10px; line-height: 16px; color: #fff;
  background: var(--brand); padding: 0 6px; border-radius: var(--radius-pill);
}
/* 编辑按钮：触屏/无 hover 设备默认可见，不做 hover 独占 */
.q-edit-btn {
  position: absolute; top: 9px; right: 9px;
  width: 26px; height: 26px; border-radius: var(--radius-xs);
  border: 1px solid var(--border); background: var(--card);
  color: var(--text-3); cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; opacity: 0.72;
  transition: opacity 0.15s ease, color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}
.quality-card:hover .q-edit-btn,
.q-edit-btn:focus-visible { opacity: 1; color: var(--brand); border-color: var(--brand); background: var(--brand-weak); }
@media (hover: none) {
  .q-edit-btn { opacity: 1; }
}

.q-edit { margin-top: 10px; display: flex; flex-direction: column; gap: 9px; }
.q-num { display: flex; align-items: center; gap: 6px; width: 100%; }
.q-cur { font-size: 14px; font-weight: 600; color: var(--text-2); }
.q-input { flex: 1; width: 100%; }
.q-edit-ops { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.q-edit-ops :deep(.el-button + .el-button) { margin-left: 0; }
.q-empty { grid-column: 1 / -1; padding: 24px 0; text-align: center; font-size: 12.5px; }

.custom-price-tip {
  display: flex; align-items: flex-start; gap: 6px; flex-wrap: wrap;
  margin-top: 10px; font-size: 11.5px; line-height: 1.5; color: var(--text-3);
}
.cpt-icon { color: var(--brand); font-size: 13px; margin-top: 2px; flex-shrink: 0; }
.custom-price-tip :deep(.el-button) { margin-left: auto; }

.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-row + .form-row { margin-top: 16px; }

/* ===== 原始需求上传 ===== */
.src-file-input { display: none; }
.src-upload { display: flex; flex-direction: column; gap: 10px; }
.src-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border-2); border-radius: var(--radius-md);
  background: var(--card-2);
}
.src-ic { font-size: 20px; color: var(--brand); flex-shrink: 0; }
.src-ic.ok { color: var(--success); }
.src-info { flex: 1; min-width: 0; }
.src-name {
  font-size: 13px; font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.src-meta { font-size: 11.5px; margin-top: 2px; }
.src-tip { font-size: 11.5px; line-height: 1.5; padding: 2px 0; }
.src-apply-mode {
  margin-top: 12px; padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--card-2); border: 1px solid var(--border);
}
.sam-hint { font-size: 11.5px; margin-top: 4px; line-height: 1.55; }
.sam-hint b { color: var(--brand); font-weight: 600; }

/* ===== 摘要 ===== */
.oc-aside {
  position: sticky;
  top: calc(var(--topbar-h) + var(--tabs-h) + var(--space-4));
  min-width: 0;
}
.oc-summary { display: flex; flex-direction: column; gap: 14px; padding: 18px; }
.summary-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.summary-title { display: flex; align-items: center; gap: 7px; font-size: 14px; font-weight: 600; color: var(--text); }
.summary-title .iconify { color: var(--brand); font-size: 16px; }
.summary-live {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px; border-radius: var(--radius-pill);
  font-size: 10.5px; color: var(--success); background: var(--success-weak);
}
.live-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--success); animation: art-breathe 1.8s ease-in-out infinite; }

.sum-order-no {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px; border: 1px dashed var(--border-2); border-radius: var(--radius-sm);
  background: var(--card-2); color: var(--text-3); font-size: 11.5px; line-height: 1.45;
}
.sum-order-no .iconify { flex-shrink: 0; }

.sum-list { display: flex; flex-direction: column; gap: 9px; }
.sum-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 22px; font-size: 12.5px; }
.sum-k { flex-shrink: 0; color: var(--text-3); }
.sum-v {
  flex: 1; min-width: 0;
  display: flex; align-items: center; justify-content: flex-end; gap: 4px;
  color: var(--text); text-align: right;
}
.sum-title { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.is-empty { color: var(--text-3); }

.sum-price-box {
  padding: 13px 14px;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--brand-weak), transparent 72%);
}
.sum-price-label { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--text-3); }
.sum-edited {
  padding: 0 6px; font-size: 10px; line-height: 16px;
  color: var(--brand); background: var(--brand-weak-2); border-radius: var(--radius-pill);
}
.sum-price-line { display: flex; align-items: baseline; margin-top: 4px; }
.sum-price { font-size: 29px; font-weight: 700; line-height: 1.3; letter-spacing: -0.03em; color: var(--text); }
.sum-agent-price { margin-top: 2px; font-size: 11.5px; color: var(--text-3); }
.sum-note { margin-top: 6px; font-size: 10.5px; line-height: 1.45; }
.sum-price-empty { display: flex; align-items: center; gap: 8px; color: var(--text-3); font-size: 12px; }
.sum-price-empty .iconify { font-size: 18px; }

.sum-actions { display: flex; flex-direction: column; gap: 8px; }
.sum-actions :deep(.el-button + .el-button) { margin-left: 0; }
.sum-submit { width: 100%; height: 42px; font-size: 14px; font-weight: 600; }
.sum-cancel { width: 100%; }
.sum-foot { display: flex; align-items: center; gap: 5px; margin: 0; font-size: 10.5px; }

/* 过渡 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .oc-section, .oc-summary { animation: none; }
}

@media (max-width: 1000px) {
  .oc-layout { grid-template-columns: minmax(0, 1fr); }
  .oc-aside { position: static; }
}
@media (max-width: 760px) {
  .cat-grid { grid-template-columns: 1fr; }
  .form-row { grid-template-columns: 1fr; }
  .form-row + .form-row { margin-top: 14px; }
  .oc-head-hint { display: none; }
}
@media (max-width: 560px) {
  .quality-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .quality-card { padding: 12px; min-height: 92px; }
  .q-amount { font-size: 17px; }
  .sum-price { font-size: 26px; }
  .oc-sec-head { gap: 10px; }
  .oc-sec-icon { width: 30px; height: 30px; font-size: 15px; }
}

/* ============================================================
   v1.15.1 订单工作台重设计
   ============================================================ */
.oc-page { padding-bottom: 24px; }

/* ---- Hero ---- */
.oc-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 310px;
  gap: 28px;
  align-items: center;
  padding: 28px 30px;
  overflow: hidden;
  border: 1px solid rgba(120, 150, 255, 0.2);
  border-radius: var(--radius-lg);
  background:
    radial-gradient(760px 240px at 4% -30%, rgba(93, 135, 255, 0.3), transparent 62%),
    radial-gradient(520px 240px at 96% 130%, rgba(19, 222, 185, 0.12), transparent 65%),
    linear-gradient(135deg, #151b30 0%, #101116 55%, #0d1017 100%);
  box-shadow: 0 20px 54px rgba(0, 0, 0, 0.24);
}
html.light .oc-hero {
  border-color: rgba(93, 135, 255, 0.16);
  background:
    radial-gradient(760px 240px at 4% -30%, rgba(93, 135, 255, 0.2), transparent 62%),
    radial-gradient(520px 240px at 96% 130%, rgba(19, 222, 185, 0.1), transparent 65%),
    linear-gradient(135deg, #eef3ff 0%, #ffffff 55%, #f4fbfa 100%);
  box-shadow: 0 16px 40px rgba(16, 24, 40, 0.07);
}
.hero-grid {
  position: absolute; inset: 0; pointer-events: none; opacity: 0.34;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
  background-size: 32px 32px;
  mask-image: linear-gradient(90deg, #000, transparent 75%);
}
html.light .hero-grid {
  background-image:
    linear-gradient(rgba(16, 24, 40, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(16, 24, 40, 0.05) 1px, transparent 1px);
}
.hero-glow {
  position: absolute; width: 300px; height: 300px; right: 100px; top: -180px;
  border-radius: 50%; background: radial-gradient(circle, rgba(93, 135, 255, 0.25), transparent 62%);
  pointer-events: none;
}
.hero-copy { position: relative; z-index: 1; min-width: 0; }
.hero-eyebrow {
  display: flex; align-items: center; gap: 8px;
  font-size: 10.5px; font-weight: 650; letter-spacing: 0.16em;
  color: rgba(255, 255, 255, 0.55);
}
html.light .hero-eyebrow { color: var(--text-3); }
.hero-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--success); box-shadow: 0 0 12px var(--success); }
.hero-copy h1 {
  text-wrap: balance;
  margin: 11px 0 0;
  font-size: 30px;
  line-height: 1.3;
  font-weight: 700;
  letter-spacing: -0.5px;
  color: #fff;
}
.hero-copy h1 em {
  font-style: normal;
  background: linear-gradient(100deg, #7fa2ff, #5be7cf);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
html.light .hero-copy h1 { color: var(--text); }
html.light .hero-copy h1 em { background: var(--brand-grad); -webkit-background-clip: text; background-clip: text; }
.hero-copy > p {
  max-width: 560px; margin: 10px 0 0;
  font-size: 12.5px; line-height: 1.7; color: rgba(255, 255, 255, 0.56);
}
html.light .hero-copy > p { color: var(--text-2); }
.hero-chips { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; margin-top: 14px; }
.hero-chips span {
  display: inline-flex; align-items: center; gap: 5px;
  height: 24px; padding: 0 9px;
  border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  font-size: 10.5px; color: rgba(255, 255, 255, 0.62);
}
.hero-chips .iconify { color: #8fa9ff; font-size: 12px; }
html.light .hero-chips span { border-color: var(--border-2); background: rgba(255, 255, 255, 0.7); color: var(--text-2); }
.hero-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 18px; }
.hero-actions .el-button { border-color: rgba(255, 255, 255, 0.18); background: rgba(255, 255, 255, 0.06); color: #fff; }
.hero-actions .el-button:hover { border-color: #fff; background: rgba(255, 255, 255, 0.12); color: #fff; }
html.light .hero-actions .el-button { border-color: var(--border-2); background: var(--card); color: var(--text-2); }
.hero-hint { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; color: rgba(255, 255, 255, 0.42); }
html.light .hero-hint { color: var(--text-3); }
.hero-hint kbd, .sum-shortcut kbd {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 19px; height: 19px; padding: 0 4px;
  border: 1px solid var(--border-2); border-radius: 4px;
  background: var(--card-2); color: var(--text-3);
  font-family: var(--font-mono); font-size: 9px; line-height: 1;
}
.hero-progress { position: relative; z-index: 1; display: flex; align-items: center; gap: 18px; justify-content: flex-end; }
.ring {
  --p: 0;
  width: 92px; height: 92px; flex-shrink: 0; border-radius: 50%;
  padding: 5px;
  background: conic-gradient(var(--brand) calc(var(--p) * 1%), rgba(255, 255, 255, 0.1) 0);
  transition: background 0.4s ease;
}
.ring-inner {
  width: 100%; height: 100%; border-radius: 50%;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: #12141d; border: 1px solid rgba(255, 255, 255, 0.08);
}
html.light .ring-inner { background: #fff; border-color: var(--border); }
.ring-inner b { font-size: 19px; font-weight: 700; color: #fff; font-variant-numeric: tabular-nums; line-height: 1; }
.ring-inner span { margin-top: 4px; font-size: 9px; letter-spacing: 0.12em; color: rgba(255, 255, 255, 0.42); }
html.light .ring-inner b { color: var(--text); }
html.light .ring-inner span { color: var(--text-3); }
.hero-steps { display: flex; flex-direction: column; gap: 8px; }
.hero-step {
  display: flex; align-items: center; gap: 8px;
  border: none; background: transparent; padding: 0; cursor: pointer;
  color: rgba(255, 255, 255, 0.48); font-size: 11.5px; text-align: left;
  transition: color 0.18s;
}
html.light .hero-step { color: var(--text-3); }
.hero-step:hover { color: rgba(255, 255, 255, 0.85); }
html.light .hero-step:hover { color: var(--text); }
.hs-dot {
  width: 20px; height: 20px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.18);
  font-size: 9px; font-variant-numeric: tabular-nums;
}
.hero-step.done { color: rgba(255, 255, 255, 0.82); }
.hero-step.done .hs-dot { background: var(--success-weak); border-color: rgba(19, 222, 185, 0.4); color: var(--success); }
.hero-step.active { color: #fff; font-weight: 600; }
.hero-step.active .hs-dot { border-color: var(--brand); background: var(--brand-weak); color: #9db6ff; box-shadow: 0 0 0 3px rgba(93, 135, 255, 0.12); }
html.light .hero-step.active { color: var(--text); }
html.light .hero-step.active .hs-dot { color: var(--brand); }

/* ---- 主栏编号卡 ---- */
.oc-layout { grid-template-columns: minmax(0, 1fr) 344px; }
.oc-section {
  position: relative;
  padding: 19px 22px 21px 64px;
  overflow: visible;
  scroll-margin-top: calc(var(--topbar-h) + var(--tabs-h) + 16px);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.oc-section:hover { border-color: var(--border-2); box-shadow: var(--shadow-card); }
.oc-section::before {
  content: attr(data-step);
  position: absolute; left: 18px; top: 19px;
  width: 30px; height: 30px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-2); background: var(--card-2);
  color: var(--text-3); font-family: var(--font-mono); font-size: 10.5px; font-weight: 600;
  z-index: 1;
}
.oc-section::after {
  content: ''; position: absolute; left: 32.5px; top: 56px; bottom: -20px;
  width: 1px; background: linear-gradient(var(--border-2), transparent);
  pointer-events: none;
}
.oc-main > .oc-section:last-of-type::after { display: none; }
.oc-section.is-done::before { border-color: rgba(19, 222, 185, 0.35); background: var(--success-weak); color: var(--success); }
.oc-sec-head { align-items: center; }
.oc-sec-copy h3 { font-size: 15px; }
.oc-sec-copy p { margin-top: 4px; line-height: 1.55; }
.sec-done-tag {
  display: inline-flex; align-items: center; gap: 3px;
  margin-left: 7px; padding: 0 6px;
  font-size: 9.5px; font-weight: 500; line-height: 17px; vertical-align: 1px;
  color: var(--success); background: var(--success-weak); border-radius: var(--radius-pill);
}
.sec-done-tag .iconify { font-size: 10px; }
.sec-optional {
  margin-left: 6px; padding: 0 6px; font-size: 9.5px; font-weight: 500; line-height: 17px;
  color: var(--text-3); background: var(--card-2); border: 1px solid var(--border);
  border-radius: var(--radius-pill); vertical-align: 1px;
}
.oc-sec-head .ai-btn { margin-left: auto; }
.oc-section :deep(.el-form-item) { margin-bottom: 0; }
.oc-section :deep(.el-form-item__label) { padding-bottom: 6px; }

/* 项目类型含论文时的流程提示条 */
.pt-paper-hint {
  display: flex; align-items: center; gap: 8px;
  margin-top: 14px; padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--brand) 7%, transparent);
  border: 1px solid color-mix(in srgb, var(--brand) 22%, transparent);
  color: var(--text-2); font-size: 12.5px;
}
.pt-paper-hint .iconify { color: var(--brand); font-size: 15px; flex-shrink: 0; }
.title-input :deep(.el-input__wrapper) { padding: 7px 13px; background: var(--card-2); }
.title-input :deep(.el-input__inner) { height: 30px; font-size: 16px; font-weight: 550; letter-spacing: 0.01em; }

/* ---- 上传区 ---- */
.src-upload {
  padding: 13px;
  border: 1px dashed var(--border-3);
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--card-2), color-mix(in srgb, var(--card-2) 55%, transparent));
  transition: border-color 0.18s ease, background 0.18s ease;
}
.src-upload.dragging { border-color: var(--brand); background: var(--brand-weak); }
.src-drop { display: flex; align-items: center; gap: 12px; min-width: 0; }
.src-drop-icon {
  width: 42px; height: 42px; flex-shrink: 0; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  background: var(--brand-weak); color: var(--brand); font-size: 20px;
}
.src-drop-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.src-drop-copy b { font-size: 12.5px; font-weight: 600; color: var(--text); }
.src-drop-copy span { font-size: 11px; color: var(--text-3); }
.src-drop .el-button { flex-shrink: 0; }
.src-card { border: none; background: transparent; padding: 0; }
.src-tip { padding: 0 2px 1px; }

/* ---- 品质卡 ---- */
.quality-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); min-height: 112px; }
.quality-card {
  min-height: 108px; padding: 15px 15px 13px;
  overflow: hidden;
  border-color: var(--border);
}
.quality-card::before {
  content: ''; position: absolute; left: 14px; right: 14px; top: 0; height: 2px;
  border-radius: 0 0 2px 2px; background: var(--q-color, var(--brand)); opacity: 0.5;
  transition: opacity 0.18s ease;
}
.quality-card.selected { box-shadow: 0 10px 30px color-mix(in srgb, var(--q-color) 12%, transparent); }
.quality-card.selected::before { opacity: 1; }
.q-amount { font-size: 21px; letter-spacing: -0.02em; }
.q-agent { margin-top: 3px; font-size: 10.5px; color: var(--text-3); }
.q-note { font-size: 9.5px; }
.q-edit-btn { opacity: 0.62; }
.quality-card:hover .q-edit-btn { opacity: 1; }

/* ---- 期限快捷 ---- */
.quick-dates { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-top: 7px; }
.quick-dates button {
  padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--card-2); color: var(--text-3); font-size: 10px; cursor: pointer;
  transition: all 0.15s;
}
.quick-dates button:hover { border-color: var(--brand); color: var(--brand); background: var(--brand-weak); }
.quick-dates button.clear { color: var(--text-4); }
.quick-dates button.clear:hover { border-color: var(--danger); color: var(--danger); background: var(--danger-weak); }

/* ---- 票据摘要 ---- */
.oc-aside { top: calc(var(--topbar-h) + var(--tabs-h) + 16px); }
.oc-summary {
  position: relative; overflow: hidden;
  padding: 20px;
  gap: 13px;
  border-radius: 18px;
  background:
    radial-gradient(240px 160px at 110% -10%, var(--brand-weak), transparent 70%),
    var(--card);
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.18);
}
html.light .oc-summary { box-shadow: 0 18px 38px rgba(16, 24, 40, 0.08); }
.oc-summary::after {
  content: ''; position: absolute; right: -52px; top: -60px;
  width: 150px; height: 150px; border-radius: 50%;
  border: 1px solid var(--brand-weak-2); pointer-events: none;
}
.ticket-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; position: relative; z-index: 1; }
.ticket-draft {
  font-family: var(--font-mono); font-size: 9px; font-weight: 600; letter-spacing: 0.16em;
  color: var(--brand); background: var(--brand-weak); border: 1px solid var(--brand-weak-2);
  border-radius: 4px; padding: 2px 6px;
}
.ticket-rule { height: 1px; background: var(--border); flex: none; }
.ticket-rule.dashed { background: repeating-linear-gradient(90deg, var(--border-2) 0 4px, transparent 4px 8px); }
.sum-order-no { border-style: dashed; background: color-mix(in srgb, var(--card-2) 60%, transparent); }
.sum-list { gap: 8px; }
.sum-row { min-height: 20px; }
.sum-checks { display: grid; grid-template-columns: 1fr 1fr; gap: 5px 10px; }
.sum-check { display: flex; align-items: center; gap: 5px; font-size: 10.5px; color: var(--text-3); }
.sum-check .sc-icon { display: inline-flex; font-size: 12px; color: var(--text-4); }
.sum-check.done { color: var(--text-2); }
.sum-check.done .sc-icon { color: var(--success); }
.sum-price-box { padding: 14px; background: linear-gradient(135deg, var(--brand-weak), color-mix(in srgb, var(--card-2) 75%, transparent)); border-color: var(--brand-weak-2); }
.sum-price-line { gap: 0; }
.sum-price { font-size: 32px; }
.sum-price-mult {
  margin-left: 8px; padding: 1px 6px; border-radius: 5px;
  background: var(--card-2); border: 1px solid var(--border);
  color: var(--text-3); font-size: 10px; font-weight: 500;
}
.sum-agent-price { margin-top: 3px; font-size: 11px; }
.sum-actions { gap: 8px; }
.sum-submit { height: 44px; font-size: 14px; font-weight: 600; }
.sum-submit .submit-ic { margin-left: 4px; font-size: 14px; }
.sum-shortcut { display: flex; align-items: center; justify-content: center; gap: 4px; font-size: 9.5px; color: var(--text-4); }
.sum-shortcut kbd { height: 17px; min-width: 17px; font-size: 8.5px; }

/* ---- 移动端底栏 ---- */
.oc-mobile-bar { display: none; }

@media (max-width: 1200px) {
  .oc-hero { grid-template-columns: minmax(0, 1fr) 260px; gap: 20px; }
  .ring { width: 82px; height: 82px; }
  .ring-inner b { font-size: 17px; }
}
@media (max-width: 1000px) {
  .oc-layout { grid-template-columns: minmax(0, 1fr); }
  .oc-aside { position: static; }
  .oc-hero { grid-template-columns: 1fr; align-items: start; }
  .hero-progress { justify-content: flex-start; }
  .hero-steps { flex-direction: row; flex-wrap: wrap; gap: 8px 14px; }
  .oc-mobile-bar {
    display: flex; align-items: center; gap: 12px;
    position: fixed; left: 14px; right: 14px; bottom: 14px; z-index: 45;
    padding: 9px 10px 9px 16px;
    border: 1px solid var(--border-2); border-radius: 16px;
    background: color-mix(in srgb, var(--card) 88%, transparent);
    box-shadow: 0 16px 46px rgba(0, 0, 0, 0.32);
    backdrop-filter: blur(18px);
  }
  .mb-price { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .mb-price span { font-size: 9.5px; color: var(--text-3); }
  .mb-price b { font-size: 18px; color: var(--text); font-variant-numeric: tabular-nums; }
  .oc-mobile-bar .el-button { min-width: 118px; height: 40px; }
  .oc-page { padding-bottom: 88px; }
}
@media (max-width: 760px) {
  .oc-hero { padding: 22px 20px; border-radius: var(--radius); }
  .hero-copy h1 { font-size: 25px; }
  .hero-copy > p { font-size: 12px; }
  .hero-chips { display: none; }
  .hero-actions { margin-top: 14px; }
  .hero-progress { gap: 12px; }
  .ring { width: 72px; height: 72px; padding: 4px; }
  .ring-inner b { font-size: 15px; }
  .ring-inner span { font-size: 8px; }
  .hero-step { font-size: 10.5px; }
  .hs-dot { width: 18px; height: 18px; font-size: 8px; }
  .oc-section { padding: 16px 16px 18px; border-radius: var(--radius); }
  .oc-section::before, .oc-section::after { display: none; }
  .oc-sec-head { align-items: flex-start; }
  .oc-sec-head .ai-btn { flex-shrink: 0; }
  .src-drop { flex-wrap: wrap; }
  .src-drop .el-button { width: 100%; }
  .src-drop-copy { flex-basis: calc(100% - 56px); }
  .quality-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .cat-grid { grid-template-columns: 1fr; }
  .form-row { grid-template-columns: 1fr; }
  .form-row + .form-row { margin-top: 14px; }
  .oc-head-hint { display: none; }
  .sum-price { font-size: 28px; }
}
@media (max-width: 420px) {
  .quality-grid { grid-template-columns: 1fr 1fr; gap: 8px; }
  .quality-card { padding: 12px; min-height: 100px; }
  .q-amount { font-size: 18px; }
  .q-agent { font-size: 9.5px; }
  .hero-copy h1 { font-size: 22px; }
}
</style>
