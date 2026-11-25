<template>
  <div class="order-detail page-shell">
    <!-- 加载失败：明确报错并提供出口，不能让页面永久卡在骨架屏 -->
    <div v-if="loadError" class="page-card od-error-card">
      <EmptyState
        icon="ri:error-warning-line"
        :title="loadError"
        description="订单可能不存在、已被移入回收站，或网络异常"
      >
        <el-button type="primary" @click="loadPage()">重试</el-button>
        <el-button @click="router.push('/orders')">返回订单列表</el-button>
      </EmptyState>
    </div>
    <PageSkeleton v-else-if="!order" />
    <!-- 防截图水印（Element Plus，art-design-pro 同款 ElWatermark；管理员可在通用设置关闭） -->
    <el-watermark
      v-else
      :content="watermarkOn ? `${auth.user?.display_name || auth.user?.username || ''} · ${order.id}` : []"
      :font="{ color: 'rgba(128,128,128,0.2)' }"
      :gap="[180, 180]"
      :z-index="999"
    >
    <!-- ===== 顶部紧凑头卡：单号+标签+操作 / 标题 / AI 摘要 ===== -->
    <div class="page-card head-card">
      <div class="head-top">
        <div class="head-title-row">
          <span class="mono order-no">{{ order.id }}</span>
          <ProjectTypeTag v-if="order.project_type" :project-type="order.project_type" />
          <QualityBadge :name="order.quality.name" :color="order.quality.color" />
          <StatusTag :status="order.status" />
          <StatusTag :status="order.deploy_status" kind="deploy" />
        </div>
        <div class="head-actions">
          <el-button v-if="auth.isAgent" size="small" @click="router.push(`/suggestions?order=${order.id}`)">
            <Icon icon="ri:lightbulb-line" /> 提建议
          </el-button>
          <!-- 收款凭证只给管理员与代理看：写手不需要 -->
          <el-button v-if="auth.isAdmin || auth.isAgent" size="small" @click="downloadReceipt">
            <Icon icon="ri:bill-line" /> 收款凭证
          </el-button>
          <el-button v-if="auth.isStaffView || auth.isAgent" size="small" @click="downloadReceiptPdf">
            <Icon icon="ri:file-pdf-2-line" /> 验收单 PDF
          </el-button>
          <el-button v-if="auth.isStaffView" size="small" @click="router.push({ path: '/ai', query: { order: order.id } })">
            <Icon icon="ri:sparkling-2-line" /> AI 参谋
          </el-button>
          <el-button v-if="auth.isStaffView" size="small" @click="openEdit">
            <Icon icon="ri:edit-line" /> 编辑信息
          </el-button>
          <el-button v-if="auth.isAdmin" size="small" type="danger" @click="trashOrder">
            <Icon icon="ri:delete-bin-line" /> 回收站
          </el-button>
        </div>
      </div>

      <h2 class="order-title">{{ order.title }}</h2>

      <div v-if="aiSummary" class="ai-summary">
        <Icon icon="ri:flashlight-line" class="ai-sum-icon" />
        <span>{{ aiSummary }}</span>
      </div>
      <div v-else-if="auth.isStaffView || auth.isAgent" class="ai-summary-btn">
        <el-button size="small" :loading="summaryLoading" @click="fetchSummary">
          <Icon icon="ri:flashlight-line" />
          AI 摘要
        </el-button>
      </div>
    </div>

    <!-- ===== 左右分栏：左主栏（指标/流转/选项卡）+ 右栏（信息/交付验收/视频速览） ===== -->
    <div class="od-layout">
      <!-- 左主栏 -->
      <div class="od-main">
        <!-- ① 指标磁贴 -->
        <div class="page-card">
          <div class="info-strip">
            <div v-if="auth.isAdmin" class="strip-item price">
              <span class="strip-label">真实价（客户）</span>
              <span class="strip-value">¥{{ Number(order.owner_price || 0).toLocaleString() }}</span>
            </div>
            <!-- 价格口径按角色：管理员看写手价，代理看自己的成交价，写手看写手价 -->
            <div class="strip-item">
              <span class="strip-label">{{ auth.isAgent ? '成交价' : '写手价' }}</span>
              <span class="strip-value" :class="{ 'agent-price': !auth.isAdmin }">¥{{ Number((auth.isAgent ? order.owner_price : order.agent_price) || 0).toLocaleString() }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">品质</span>
              <span class="strip-value">{{ order.quality.name }}<template v-if="auth.isAdmin"> ×{{ order.multiplier }}</template></span>
            </div>
            <div class="strip-item">
              <span class="strip-label">交付期限</span>
              <span class="strip-value" :class="{ overdue }">{{ order.deadline || '—' }}</span>
              <span v-if="countdown" class="strip-sub" :class="countdown.cls">{{ countdown.text }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">项目类型</span>
              <span class="strip-value">{{ ptText }}</span>
            </div>
          </div>
        </div>

        <!-- ② 状态流转 + 状态操作 -->
        <div class="page-card">
          <div v-if="order.status !== 'cancelled'" class="flow-area">
            <el-steps :active="stepIndex" :process-status="order.status === 'after_sale' ? 'error' : 'process'" class="flow-steps">
              <el-step title="待开始" :description="fmt(order.created_at)" />
              <el-step title="制作中" :description="fmt(order.accepted_at)" />
              <el-step title="已完成" :description="fmt(order.completed_at)" />
              <el-step title="已结单" :description="fmt(order.closed_at)" />
            </el-steps>
            <el-alert
              v-if="order.status === 'after_sale'" type="warning" show-icon :closable="false" class="flow-alert"
              title="售后处理中" description="处理完成后请切换回「已结单」状态"
            />
          </div>
          <el-alert
            v-else type="error" show-icon :closable="false" class="flow-alert"
            title="订单已取消" description="已取消的订单不能恢复，如需继续请新建订单"
          />

          <!-- 代理确认开工：需求书与客户定稿后，代理自己通知后台开始制作 -->
          <div
            v-if="auth.isAgent && order && order.status === 'pending' && order.has_requirement" key="agentstart"
            class="sa-row" style="margin-top: 8px"
          >
            <span class="sa-label">代理确认：</span>
            <el-button size="small" type="primary" @click="confirmStart()">✅ 确认开工（已与客户定稿，通知后台制作）</el-button>
          </div>

          <div v-if="auth.isStaffView" class="status-actions">
            <span class="sa-label">状态流转：</span>
            <template v-if="nextActions.length">
              <el-button
                v-for="act in nextActions" :key="act.value" size="small" :type="act.danger ? 'danger' : act.type"
                :loading="statusLoading" :disabled="statusLoading || !!order.status_revert" @click="changeStatus(act.value)"
              >{{ act.label }}</el-button>
            </template>
            <span v-else class="sa-empty">{{ order.status_revert ? '请先处理撤回申请' : '当前角色无可执行的状态操作' }}</span>
            <el-divider direction="vertical" />
            <span class="sa-label">部署：</span>
            <el-radio-group :model-value="order.deploy_status" size="small" :disabled="deployLoading" @change="changeDeploy">
              <el-radio-button value="undeployed">未部署</el-radio-button>
              <el-radio-button value="deployed">已部署</el-radio-button>
              <el-radio-button value="not_required">无需部署</el-radio-button>
            </el-radio-group>
          </div>

          <!-- 写手撤回审批：申请 / 待审批 / 管理员审批均内联在状态卡 -->
          <div v-if="auth.isStaffView" class="revert-area">
            <div v-if="order.status_revert" class="revert-pending">
              <div class="rp-icon"><Icon icon="ri:time-line" /></div>
              <div class="rp-main">
                <div class="rp-title">
                  撤回申请待{{ auth.isAdmin ? '你' : '管理员' }}审批
                  <span class="rp-status">{{ order.status_revert.status_cn }}</span>
                </div>
                <div class="rp-sub">
                  {{ order.status_revert.from_status_cn }} → {{ order.status_revert.to_status_cn }}
                  · 申请人 {{ order.status_revert.username }}
                  · {{ fmt(order.status_revert.created_at) }}
                </div>
                <div class="rp-reason">原因：{{ order.status_revert.reason }}</div>
              </div>
              <div v-if="auth.isAdmin" class="rp-actions">
                <el-button size="small" :loading="reviewLoading" :disabled="reviewLoading" @click="reviewRevert('reject')">驳回</el-button>
                <el-button size="small" type="primary" :loading="reviewLoading" :disabled="reviewLoading" @click="reviewRevert('approve')">同意撤回</el-button>
              </div>
              <el-button
                v-else-if="order.status_revert.requested_by === auth.user?.id"
                size="small" :loading="revertLoading" :disabled="revertLoading" @click="cancelRevert"
              >撤回申请</el-button>
              <span v-else class="rp-wait">等待管理员处理</span>
            </div>
            <div v-else-if="canRequestRevert" class="revert-entry">
              <Icon icon="ri:arrow-go-back-line" />
              <span>状态点错了？可申请管理员把订单从「{{ STATUS_TEXT[order.status] }}」撤回为「{{ STATUS_TEXT[order.revert_target] }}」。</span>
              <el-button size="small" @click="openRevert">申请撤回</el-button>
            </div>
            <div v-else-if="!auth.isAdmin && order.status === 'pending'" class="revert-hint">
              <Icon icon="ri:information-line" />
              <span>待开始订单无需撤回；若误操作已进入制作中/已完成，可在这里申请退回。</span>
            </div>
          </div>
        </div>

        <!-- ③ 选项卡：论文进度 / 需求书 / 文件 / 客户跟进 / 操作历史 -->
        <div class="page-card tabs-card">
          <el-tabs v-model="tab">
            <el-tab-pane v-if="paperTabVisible" name="paper" label="论文进度">
              <div v-loading="paperLoading" class="paper-panel">
                <!-- 进度总览条 -->
                <div class="pp-overview">
                  <div class="ppo-left">
                    <Icon icon="ri:file-paper-2-line" class="ppo-ic" />
                    <span>论文交付流程</span>
                    <span class="text-3 ppo-sub">任务书 → 开题报告 → 初稿（至少修改 {{ paperData?.min_revisions ?? 5 }} 次）→ 终稿</span>
                  </div>
                  <div class="ppo-right">
                    <span class="ppo-stat" :class="{ ok: paperDoneCount === 4 }">{{ paperDoneCount }}/4 阶段已交付</span>
                  </div>
                </div>

                <!-- 四阶段卡片 -->
                <div class="pp-grid">
                  <div v-for="d in paperDocs" :key="d.doc_type" class="pp-card" :class="{ done: d.count > 0 }">
                    <div class="ppc-head">
                      <span class="ppc-no">{{ paperIndex(d) }}</span>
                      <span class="ppc-label">{{ d.label }}</span>
                      <span v-if="d.count > 0" class="ppc-badge ok">已提交 · 第 {{ d.latest.round }} 版</span>
                      <span v-else class="ppc-badge">未提交</span>
                    </div>

                    <!-- 初稿：修改次数进度 -->
                    <template v-if="d.doc_type === 'draft'">
                      <div class="ppc-progress">
                        <div class="ppp-text">
                          <span>修改留档</span>
                          <b :class="{ ok: (paperData?.draft_revisions ?? 0) >= (paperData?.min_revisions ?? 5) }">
                            {{ paperData?.draft_revisions ?? 0 }}/{{ paperData?.min_revisions ?? 5 }} 次
                          </b>
                        </div>
                        <el-progress
                          :percentage="paperDraftPercent" :show-text="false" :stroke-width="8"
                          :color="(paperData?.draft_revisions ?? 0) >= (paperData?.min_revisions ?? 5) ? '#13deb9' : '#ffae1f'"
                        />
                        <div class="text-3 ppp-hint">初稿每次重新上传都会自动留档，达到次数才能提交终稿</div>
                      </div>
                    </template>

                    <!-- 终稿：门槛提示 -->
                    <template v-else-if="d.doc_type === 'final' && d.count === 0">
                      <div class="ppc-gate" :class="{ ready: d.ready }">
                        <Icon :icon="d.ready ? 'ri:checkbox-circle-line' : 'ri:time-line'" />
                        <span v-if="d.ready">初稿修改次数已达标，可以提交终稿</span>
                        <span v-else>初稿还需修改 {{ paperGap }} 次才能提交终稿</span>
                      </div>
                    </template>

                    <!-- 最新版本信息 -->
                    <div v-if="d.latest" class="ppc-latest">
                      <div class="ppl-name" :title="d.latest.file?.name">
                        <Icon icon="ri:file-word-2-line" />
                        <span>{{ d.latest.file?.name || '文件已缺失' }}</span>
                      </div>
                      <div class="text-3 ppl-meta">
                        {{ fmtSize(d.latest.file?.size) }} · {{ d.latest.username }} · {{ fmt(d.latest.created_at) }}
                        <template v-if="d.latest.note"> · {{ d.latest.note }}</template>
                      </div>
                      <div class="ppl-actions">
                        <el-button v-if="d.latest.file" size="small" text type="primary" @click="downloadFile(d.latest.file.id)">
                          下载
                        </el-button>
                        <el-button size="small" text @click="openPaperHistory(d)">留档记录（{{ d.count }}）</el-button>
                      </div>
                    </div>

                    <div class="ppc-ops">
                      <el-button v-if="auth.isStaffView" size="small" type="primary" plain @click="openPaperUpload(d)">
                        <Icon icon="ri:upload-2-line" />{{ d.count ? '上传新版本' : '提交' }}
                      </el-button>
                      <el-button v-if="d.count > 0 && !d.latest" size="small" text @click="openPaperHistory(d)">
                        留档记录（{{ d.count }}）
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane name="doc" label="需求书">
              <div v-if="!order.has_requirement" class="doc-empty">
                <template v-if="auth.isStaffView || auth.isAgent">
                  <div class="empty-icon"><Icon icon="ri:file-text-line" /></div>
                  <div class="empty-title">还没有需求书</div>
                  <div class="empty-sub">输入题目后一键生成，可在网页中编辑并导出 Word（格式统一）</div>
                  <div v-if="(auth.isStaffView || auth.isAgent) && hasSourceMaterial" class="empty-sub src-hint">
                    <Icon icon="ri:file-paper-2-line" />
                    <template v-if="directApply">
                      已附带{{ sourceMaterialText }}，点击下方按钮将<b>原样采用</b>（系统不做任何修改）
                    </template>
                    <template v-else>已附带{{ sourceMaterialText }}，生成时将以此为准（而非仅凭题目）</template>
                  </div>
                  <div class="empty-btns">
                    <el-button type="primary" :loading="generatingMode === 'auto'" :disabled="generating" @click="generate('auto')">
                      <Icon :icon="directApply ? 'ri:file-check-line' : 'ri:flashlight-line'" />
                      {{ directApply ? '直接采用上传文档' : (aiReady ? 'AI 智能生成（DeepSeek）' : 'AI 未配置，将使用模板生成') }}
                    </el-button>
                    <el-button :loading="generatingMode === 'template'" :disabled="generating" @click="generate('template')">纯模板生成</el-button>
                  </div>
                </template>
                <template v-else>
                  <div class="empty-title">需求书尚未生成</div>
                  <div class="empty-sub">点击上方按钮生成需求书</div>
                </template>
              </div>
              <div v-else class="doc-panel">
                <div class="doc-meta">
                  <el-tag size="small" :type="order.requirement_source === 'ai' ? 'success' : order.requirement_source === 'manual' ? 'warning' : 'primary'">
                    {{ { ai: 'AI 生成', template: '模板生成', manual: previewDoc?.mode === 'raw' ? '原文直用' : '人工编辑' }[order.requirement_source] || order.requirement_source }}
                  </el-tag>
                  <span class="text-2">更新于 {{ fmt(order.requirement_updated_at) }}</span>
                  <span
                    v-if="auth.isStaffView && hasSourceMaterial"
                    class="src-badge" :title="directApply ? '重新生成将原样采用上传文档，不做修改' : `重新生成将基于${sourceMaterialText}`"
                  ><Icon icon="ri:file-paper-2-line" /> 原始需求</span>
                  <div class="doc-btns">
                    <el-button size="small" type="primary" @click="downloadDoc">
                      <Icon icon="ri:download-2-line" /> 下载 Word
                    </el-button>
                    <el-button v-if="auth.isStaffView || auth.isAgent" size="small" @click="openDiff">
                      <Icon icon="ri:arrow-left-right-line" /> 修改对比
                    </el-button>
                    <el-button v-if="auth.isStaffView || auth.isAgent" size="small" @click="router.push(`/orders/${order.id}/doc`)">
                      <Icon icon="ri:edit-line" /> 编辑内容
                    </el-button>
                    <el-button v-if="auth.isStaffView || auth.isAgent" size="small" :loading="generatingMode === 'auto'" :disabled="generating" @click="generate('auto')">{{ directApply ? '重新采用原文' : '重新生成' }}</el-button>
                    <el-button size="small" @click="openVersions"><Icon icon="ri:history-line" /> 历史版本</el-button>
                    <el-button size="small" type="warning" plain @click="uploadReplaceRequirement()">
                      <Icon icon="ri:upload-2-line" /> 上传替换
                    </el-button>
                    <el-button v-if="previewDoc" key="delreq" size="small" type="danger" plain @click="deleteRequirement()">
                      <Icon icon="ri:delete-bin-line" /> 删除
                    </el-button>
                  </div>
                </div>
                <DocPreview v-if="previewDoc" :document="previewDoc" />
              </div>
            </el-tab-pane>

            <el-tab-pane name="files" :label="`文件（${order.files.length}）`">
              <div class="deliver-bar">
                <div class="db-info">
                  <span class="db-title"><Icon icon="ri:send-plane-line" /> 客户交付</span>
                  <span class="text-2 db-desc">生成免登录链接发给客户，仅包含「程序包 + 演示视频」，客户可直接在线播放和下载</span>
                </div>
                <el-button size="small" type="primary" plain @click="openDeliver">获取交付链接</el-button>
              </div>
              <div v-for="cat in fileCats" :key="cat.key" class="file-group">
                <div class="fg-head">
                  <div class="fg-title">{{ cat.label }}<span class="text-2 fg-count">{{ filesOf(cat.key).length }} 个</span></div>
                  <UploadBtn
                    v-if="auth.isStaffView || cat.key === 'other'"
                    :order-id="order.id" :category="cat.key" :existing="filesOf(cat.key)" @uploaded="reload"
                  />
                </div>
                <el-empty v-if="filesOf(cat.key).length === 0" :image-size="42" description="暂无文件" />
                <div v-else class="file-list">
                  <div v-for="f in filesOf(cat.key)" :key="f.id" class="file-item" :class="{ video: cat.key === 'video' }">
                    <div class="f-icon"><Icon v-if="cat.key !== 'video'" icon="ri:file-zip-line" /><Icon v-else icon="ri:video-line" /></div>
                    <div class="f-info">
                      <span class="f-name" :title="f.original_name">{{ f.original_name }}</span>
                      <span class="text-2 f-meta">{{ fmtSize(f.size) }} · {{ fmt(f.created_at) }}<template v-if="f.remark"> · {{ f.remark }}</template></span>
                    </div>
                    <div class="f-actions">
                      <el-button v-if="cat.key === 'video'" size="small" text type="primary" @click="preview(f)">预览</el-button>
                      <el-button size="small" text type="primary" @click="download(f)">下载</el-button>
                      <el-button v-if="auth.isStaffView" size="small" text type="danger" @click="removeFile(f)">删除</el-button>
                    </div>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane name="notes" :label="`客户跟进${notes.length ? `（${notes.length}）` : ''}`">
              <div class="nc-input">
                <el-input
                  v-model="noteText" type="textarea" :rows="2" :maxlength="1000"
                  placeholder="记录与客户的沟通进展、约定事项、变更要求…（Ctrl+Enter 保存）"
                  @keydown.ctrl.enter="addNote"
                />
                <el-button type="primary" size="small" :loading="noteSaving" :disabled="!noteText.trim()" @click="addNote">记一笔</el-button>
              </div>
              <el-timeline v-if="notes.length" class="note-timeline">
                <el-timeline-item v-for="n in notes" :key="n.id" :type="noteColor(n.role)">
                  <div class="note-line">
                    <b>{{ n.username }}</b>
                    <span class="note-role text-2">{{ n.role_label || ({ admin: '管理员', staff: '写手', agent: '代理' }[n.role] || n.role || '-') }}</span>
                    <span class="text-2 note-time">{{ fmt(n.created_at) }}</span>
                  </div>
                  <div class="note-content">{{ n.content }}</div>
                </el-timeline-item>
              </el-timeline>
              <div v-else class="note-empty text-2">还没有跟进记录，把和客户聊的关键信息记下来吧</div>
            </el-tab-pane>

            <el-tab-pane name="logs" label="操作历史">
              <el-timeline v-if="order.logs.length" class="log-timeline">
                <el-timeline-item v-for="lg in order.logs" :key="lg.id" :type="logColor(lg.action)">
                  <div class="log-line">
                    <b>{{ lg.username }}</b>
                    <span class="log-role text-2">{{ lg.role_label || ({ admin: '管理员', staff: '写手', agent: '代理', '-': '系统' }[lg.role] || lg.role) }}</span>
                    <span class="log-action">{{ ACTION_TEXT[lg.action] || lg.action }}</span>
                  </div>
                  <div v-if="lg.detail" class="log-detail text-2">{{ detailText(lg) }}</div>
                  <div class="log-time text-2">{{ fmt(lg.created_at) }}<template v-if="lg.ip"> · {{ lg.ip }}</template></div>
                </el-timeline-item>
              </el-timeline>
              <el-empty v-else :image-size="54" description="暂无操作记录" />
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>

      <!-- 右栏（sticky） -->
      <div class="od-side">
        <!-- ① 订单信息（两列紧凑描述） -->
        <div class="page-card side-card">
          <h4 class="sc-title">订单信息</h4>
          <div class="side-meta">
            <div class="meta-cell">
              <div class="meta-label">来源代理</div>
              <div class="meta-value">{{ order.agent ? (order.agent.display_name || order.agent.username) : '自接单' }}</div>
            </div>
            <div class="meta-cell">
              <div class="meta-label">制作负责人</div>
              <div class="meta-value">{{ order.assignee ? (order.assignee.display_name || order.assignee.username) : '未指定' }}</div>
            </div>
            <div class="meta-cell">
              <div class="meta-label">创建人</div>
              <div class="meta-value">{{ order.created_by }}</div>
            </div>
            <div class="meta-cell">
              <div class="meta-label">技术栈</div>
              <div class="meta-value">{{ order.tech_stack || '-' }}</div>
            </div>
            <div class="meta-cell">
              <div class="meta-label">创建时间</div>
              <div class="meta-value">{{ fmt(order.created_at) }}</div>
            </div>
            <div class="meta-cell">
              <div class="meta-label">接单时间</div>
              <div class="meta-value">{{ fmt(order.accepted_at) }}</div>
            </div>
            <div class="meta-cell">
              <div class="meta-label">完成时间</div>
              <div class="meta-value">{{ fmt(order.completed_at) }}</div>
            </div>
            <div class="meta-cell">
              <div class="meta-label">结单时间</div>
              <div class="meta-value">{{ fmt(order.closed_at) }}</div>
            </div>
            <div class="meta-cell">
              <div class="meta-label">客户信息</div>
              <div class="meta-value">{{ order.customer_info || '-' }}</div>
            </div>
            <div class="meta-cell wide">
              <div class="meta-label">备注</div>
              <div class="meta-value pre">{{ order.remark || '-' }}</div>
            </div>
          </div>
        </div>

        <!-- ② 交付与验收 -->
        <div class="page-card side-card">
          <h4 class="sc-title">交付与验收</h4>
          <div class="dc-stats">
            <div class="dc-stat">
              <span class="dcs-num">{{ deliverStatsData ? deliverStatsData.views : '—' }}</span>
              <span class="dcs-label">客户浏览（次）</span>
            </div>
            <div class="dc-stat">
              <span class="dcs-num">{{ deliverStatsData ? deliverStatsData.downloads : '—' }}</span>
              <span class="dcs-label">累计下载（次）</span>
            </div>
          </div>
          <el-button class="dc-btn" size="small" type="primary" plain @click="openDeliver">
            <Icon icon="ri:send-plane-line" /> 获取交付链接
          </el-button>
          <div class="dc-accept">
            <template v-if="order.customer_accepted_at">
              <span class="dc-accepted">
                <Icon icon="ri:checkbox-circle-fill" />
                已验收 · {{ fmt(order.customer_accepted_at) }}
              </span>
              <el-button
                v-if="auth.isAdmin" size="small" text type="danger"
                :loading="revokeLoading" @click="revokeAccept"
              >撤销验收</el-button>
            </template>
            <span v-else class="text-2 dc-none">客户未验收</span>
          </div>
        </div>

        <!-- ③ 演示视频速览（无视频省略） -->
        <div v-if="order.video" class="page-card side-card">
          <div class="vc-head">
            <h4 class="sc-title">演示视频</h4>
            <span v-if="videoFiles.length > 1" class="text-2 vc-count">{{ videoFiles.length }} 个视频</span>
          </div>
          <video :key="currentVideo.id" :src="`/api/files/${currentVideo.id}/download`" controls preload="metadata" class="vc-player" />
          <div v-if="videoFiles.length > 1" class="vc-list">
            <button
              v-for="v in videoFiles" :key="v.id"
              class="vc-item" :class="{ active: v.id === currentVideo.id }"
              @click="currentVideoId = v.id"
            >
              <Icon icon="ri:play-circle-line" class="vc-item-icon" />
              <span class="vc-item-name" :title="v.original_name">{{ v.original_name }}</span>
              <span class="text-2 vc-item-meta">{{ fmtSize(v.size) }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" title="编辑订单" width="600px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-position="top" style="margin-top: 8px">
        <el-form-item label="题目" prop="title">
          <el-input v-model="editForm.title" :maxlength="255" />
        </el-form-item>
        <el-form-item label="项目类型（决定是否启用论文进度留档）">
          <el-select v-model="editForm.project_type" style="width: 100%" placeholder="未设置（不启用论文进度）" clearable>
            <el-option label="⌨️ 纯程序设计（无论文）" value="program" />
            <el-option label="📑 纯论文" value="thesis" />
            <el-option label="📘 论文+设计" value="thesis_program" />
          </el-select>
        </el-form-item>
        <el-form-item label="品质" prop="quality_code">
          <el-select v-model="editForm.quality_code" style="width: 100%">
            <el-option
              v-for="q in qualities" :key="q.code" :value="q.code"
              :label="auth.isAdmin
                ? `${q.name}（×${q.multiplier}，真实 ¥${q.owner_price} / 代理 ¥${q.agent_price}）`
                : `${q.name}（代理 ¥${q.agent_price}）`"
            />
          </el-select>
        </el-form-item>
        <div class="edit-row">
          <el-form-item v-if="auth.isAdmin" label="真实价（改品质后自动重算，可手动覆盖）" prop="owner_price">
            <el-input-number v-model="editForm.owner_price" :min="0" :precision="2" style="width: 100%" />
          </el-form-item>
          <el-form-item label="交付期限" prop="deadline">
            <el-date-picker v-model="editForm.deadline" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </div>
        <el-form-item label="技术栈偏好（可选可自定义）">
          <el-select
            v-model="editForm.tech_stack" style="width: 100%" placeholder="选择或直接输入"
            filterable allow-create default-first-option clearable
          >
            <el-option v-for="t in techOptions" :key="t.value" :label="t.value" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="auth.isAdmin" label="来源代理">
          <el-select v-model="editForm.agent_username" placeholder="自接单" style="width: 100%" clearable filterable>
            <el-option
              v-for="a in agents" :key="a.username" :value="a.username"
              :label="a.display_name || a.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="auth.isStaffView" label="制作负责人">
          <el-select v-model="editForm.assignee_username" placeholder="未指定" style="width: 100%" clearable filterable>
            <el-option
              v-for="s in staffList" :key="s.username" :value="s.username"
              :label="s.display_name || s.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="客户信息">
          <el-input v-model="editForm.customer_info" :maxlength="255" />
        </el-form-item>
        <el-form-item v-if="auth.isStaffView || auth.isAgent" label="需求要点（口头/零散需求总结，AI 生成需求书时逐条体现）">
          <el-input v-model="editForm.requirement_notes" type="textarea" :rows="3" :maxlength="4000" show-word-limit />
        </el-form-item>
        <el-form-item v-if="auth.isStaffView || auth.isAgent" label="原始需求文档全文（上传解析的文本，可修正补漏）">
          <el-input
            v-model="editForm.source_requirement" type="textarea" :rows="5"
            :maxlength="20000" show-word-limit
            placeholder="客户需求书的提取文本；若为本系统九章 JSON，生成时将直接导入而不经过 AI"
          />
          <div class="bs-req-tools">
            <button class="bs-req-link" type="button" @click="pickSourceFile"> 上传文档替换 </button>
            <button class="bs-req-link" type="button" @click="editForm.source_requirement = ''"> 清空（保存后移除原始需求） </button>
          </div>
        </el-form-item>
        <el-form-item v-if="(auth.isStaffView || auth.isAgent) && editForm.source_requirement" label="需求书应用方式">
          <el-radio-group v-model="editForm.source_apply_mode">
            <el-radio value="reference">作为参考，由 AI 生成</el-radio>
            <el-radio value="direct">直接采用原文（不做修改）</el-radio>
          </el-radio-group>
          <div class="text-3" style="font-size: 11.5px; margin-top: 2px">
            切换后点击需求书页签的「重新生成 / 重新采用原文」生效
          </div>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.remark" type="textarea" :rows="3" :maxlength="2000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 需求书历史版本 -->
    <el-drawer v-model="verVisible" title="需求书历史版本" size="480px">
      <div v-loading="verLoading">
        <el-empty v-if="!verLoading && !versions.length" description="暂无历史版本（编辑/重新生成前会自动存档）" />
        <div v-for="v in versions" :key="v.id" class="ver-item">
          <div class="ver-main">
            <div class="ver-line1">
              <el-tag size="small" :type="v.source === 'ai' ? 'success' : v.source === 'manual' ? 'warning' : 'primary'" style="margin: 0">
                {{ { ai: 'AI 生成', template: '模板', manual: '人工编辑' }[v.source] || v.source }}
              </el-tag>
              <span class="text-2 ver-user">{{ v.username }}</span>
              <span class="text-2 ver-time">{{ fmt(v.created_at) }}</span>
            </div>
            <div v-if="v.remark" class="text-2 ver-remark">{{ v.remark }}</div>
          </div>
          <el-button v-if="auth.isStaffView" size="small" type="primary" plain @click="restoreVersion(v)">回滚</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 需求书修改对比抽屉 -->
    <el-drawer v-model="diffVisible" title="需求书修改对比" size="620px">
      <div class="diff-toolbar">
        <span class="text-2 diff-label">对比基准</span>
        <el-select
          v-model="diffVersionId" style="width: 260px" size="small"
          placeholder="选择历史版本" :loading="diffVersionsLoading"
          @change="loadDiff"
        >
          <el-option
            v-for="v in diffVersions" :key="v.id" :value="v.id"
            :label="`${fmt(v.created_at)} · ${({ ai: 'AI', template: '模板', manual: '人工' })[v.source] || v.source}${v.remark ? ' · ' + v.remark : ''}`"
          />
        </el-select>
        <el-button size="small" :loading="diffAiLoading" :disabled="!diffData?.diffs?.length" @click="loadDiff(true)">AI 总结</el-button>
      </div>
      <div v-loading="diffLoading">
        <template v-if="diffData">
          <div class="diff-meta text-2">
            对比 {{ fmt(diffData.version.created_at) }}（{{ diffData.version.username }}）→ 当前（{{ fmt(diffData.current_updated_at) }}），
            共 <b>{{ diffData.diffs.length }}</b> 处差异
          </div>
          <div v-if="diffData.summary" class="diff-ai">
            <Icon icon="ri:flashlight-line" class="da-icon" />
            <span>{{ diffData.summary }}</span>
          </div>
          <div v-if="!diffData.diffs.length" class="diff-empty">两个版本内容完全一致</div>
          <div v-for="(d, i) in diffData.diffs" :key="i" class="diff-item">
            <div class="di-head">
              <span class="di-kind" :class="d.kind">{{ { changed: '修改', added: '新增', removed: '删除' }[d.kind] }}</span>
              <span class="di-label">{{ d.label }}</span>
            </div>
            <!-- 字符级内联差异（后端 old_ops/new_ops）：红删绿增，直观到改了哪几个字 -->
            <template v-if="d.kind === 'changed' && d.old_ops">
              <div class="di-old"><span class="di-tag">改前</span><span v-for="(op, j) in d.old_ops" :key="'o' + j" :class="{ 'op-del': op.t === 'del' }">{{ op.s }}</span></div>
              <div class="di-new"><span class="di-tag">改后</span><span v-for="(op, j) in d.new_ops" :key="'n' + j" :class="{ 'op-ins': op.t === 'ins' }">{{ op.s }}</span></div>
            </template>
            <template v-else>
              <div v-if="d.old" class="di-old"><span class="di-tag">改前</span>{{ d.old }}</div>
              <div v-if="d.new" class="di-new"><span class="di-tag">改后</span>{{ d.new }}</div>
            </template>
          </div>
        </template>
        <div v-else-if="!diffLoading" class="diff-empty">选择一个历史版本开始对比</div>
      </div>
    </el-drawer>

    <!-- 客户交付链接 -->
    <el-dialog v-model="deliverOpen" title="客户交付链接" width="560px">
      <div class="dv-body">
        <div class="dv-link mono">{{ deliverUrl }}</div>
        <div class="text-2 dv-tip">链接免登录可打开：客户能在线播放演示视频、下载程序包；不包含内部文档与其他订单信息。请只发给对应客户。</div>
        <div v-if="deliverStatsData" class="dv-stats">
          <span>客户浏览 <b>{{ deliverStatsData.views }}</b> 次</span>
          <el-divider direction="vertical" />
          <span>下载 <b>{{ deliverStatsData.downloads }}</b> 次</span>
        </div>
        <div class="dv-actions">
          <el-button type="primary" @click="copyDeliver"><Icon icon="ri:file-copy-line" /> 复制链接</el-button>
          <el-button @click="openDeliverPreview">打开预览</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 写手申请撤回状态 -->
    <el-dialog v-model="revertVisible" title="申请撤回状态" width="460px" destroy-on-close>
      <div class="revert-dialog">
        <div class="rd-flow">
          <span class="rd-chip">{{ STATUS_TEXT[order?.status] }}</span>
          <Icon icon="ri:arrow-right-line" class="rd-arrow" />
          <span class="rd-chip rd-target">{{ STATUS_TEXT[order?.revert_target] }}</span>
        </div>
        <div class="rd-tip">
          提交后订单状态暂不变动，管理员会在消息中心收到审批通知；通过后自动回退。请说明误操作经过，便于管理员判断。
        </div>
        <el-input
          v-model="revertReason" type="textarea" :rows="3" maxlength="300" show-word-limit
          placeholder="例如：误点了「标记完成」，实际还在修改中（至少 2 个字）"
        />
      </div>
      <template #footer>
        <el-button @click="revertVisible = false">取消</el-button>
        <el-button type="primary" :loading="revertLoading" :disabled="revertLoading" @click="submitRevert">提交申请</el-button>
      </template>
    </el-dialog>

    <!-- 论文文档上传（任务书/开题报告/初稿/终稿，每次提交自动留档） -->
    <el-dialog v-model="paperUpVisible" :title="`提交${paperUpLabel}`" width="480px" destroy-on-close>
      <div class="pu-body">
        <div v-if="paperUpType === 'final' && !paperFinalReady" class="pu-gate">
          <Icon icon="ri:error-warning-line" />
          <span>初稿已修改 {{ paperData?.draft_revisions ?? 0 }} 次，需至少 {{ paperData?.min_revisions ?? 5 }} 次才能提交终稿</span>
        </div>
        <div class="pu-round text-3">
          当前{{ paperUpLabel }}留档 {{ paperUpCount }} 版，本次提交为第 {{ paperUpCount + 1 }} 版
          <template v-if="paperUpType === 'draft' && paperUpCount > 0">（第 {{ paperUpCount }} 次修改）</template>
        </div>
        <el-form label-position="top">
          <el-form-item label="文档文件（doc/docx/pdf/txt/md）" required>
            <div class="pu-file" @click="paperFileInput?.click()">
              <input
                ref="paperFileInput" type="file"
                accept=".doc,.docx,.pdf,.txt,.md" class="pu-file-input" @change="onPaperFileChosen"
              />
              <Icon v-if="!paperUpFile" icon="ri:upload-cloud-2-line" class="puf-ic" />
              <div class="puf-copy">
                <b>{{ paperUpFile ? paperUpFile.name : '点击选择文件' }}</b>
                <span v-if="paperUpFile" class="text-3">{{ fmtSize(paperUpFile.size) }}</span>
                <span v-else class="text-3">每次提交/修改都会永久留档，历史版本不可删除</span>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="修改说明（选填）">
            <el-input
              v-model="paperUpNote" type="textarea" :rows="2" maxlength="500" show-word-limit
              :placeholder="paperUpType === 'draft' ? '例如：按导师意见调整第三章结构、补充实验数据…' : '例如：已按学校模板修订…'"
            />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="paperUpVisible = false">取消</el-button>
        <el-button type="primary" :loading="paperUpSending" :disabled="!paperUpFile" @click="submitPaperUpload">
          {{ paperUpType === 'draft' && paperUpCount > 0 ? '提交修改留档' : '提交' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 论文留档记录 -->
    <el-drawer v-model="paperHisVisible" :title="`${paperHisLabel}留档记录`" size="460px">
      <div v-loading="paperHisLoading">
        <el-empty v-if="!paperHisLoading && !paperHisDocs.length" description="暂无留档" />
        <div v-for="d in paperHisDocs" :key="d.id" class="ph-item">
          <div class="ph-round" :class="{ first: d.round === 1 }">第 {{ d.round }} 版</div>
          <div class="ph-main">
            <div class="ph-name" :title="d.file?.name">
              <Icon icon="ri:file-word-2-line" />
              <span>{{ d.file?.name || '文件已缺失' }}</span>
            </div>
            <div class="text-3 ph-meta">
              {{ fmtSize(d.file?.size) }} · {{ d.username }} · {{ fmt(d.created_at) }}
              <template v-if="d.note"> · {{ d.note }}</template>
            </div>
          </div>
          <el-button v-if="d.file" size="small" text type="primary" @click="downloadFile(d.file.id)">下载</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 视频预览 -->
    <el-dialog v-model="videoVisible" :title="videoFile?.original_name" width="880px" destroy-on-close>
      <video v-if="videoFile" :src="`/api/files/${videoFile.id}/download`" controls autoplay style="width: 100%; max-height: 70vh; background: #000; border-radius: 8px" />
    </el-dialog>
    </el-watermark>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Icon } from '@iconify/vue'
import http from '../api'
import { sensitiveConfirm, withConfirm } from '../utils/sensitive'
import { useAuthStore } from '../stores/auth'
import QualityBadge from '../components/QualityBadge.vue'
import ProjectTypeTag from '../components/ProjectTypeTag.vue'
import StatusTag from '../components/StatusTag.vue'
import { deadlineState, hasPaperWorkflow, projectTypeMeta } from '../constants/orderMeta'
import UploadBtn from '../components/UploadBtn.vue'
import DocPreview from '../components/DocPreview.vue'
import PageSkeleton from '../components/ui/PageSkeleton.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const order = ref(null)
const loadError = ref('')
const tab = ref('doc')
const generatingMode = ref('') // 正在生成的模式：'' | 'auto' | 'template'，只让被点击的按钮转圈
const generating = computed(() => generatingMode.value !== '')
const watermarkOn = ref(true) // 订单详情水印开关（管理员在通用设置里控制）
const aiReady = ref(false)
const saving = ref(false)
const qualities = ref([])
const agents = ref([])
const staffList = ref([])
const editVisible = ref(false)
const videoVisible = ref(false)
const videoFile = ref(null)
const previewDoc = ref(null)
const aiSummary = ref('')
const summaryLoading = ref(false)
const verVisible = ref(false)
const verLoading = ref(false)
const versions = ref([])
const statusLoading = ref(false)
const deployLoading = ref(false)
const revertVisible = ref(false)
const revertReason = ref('')
const revertLoading = ref(false)
const reviewLoading = ref(false)
const editForm = reactive({})

const techOptions = [
  { value: 'SpringBoot+Vue3' }, { value: 'Django' }, { value: 'JSP+Servlet' },
  { value: 'Flask' }, { value: '微信小程序+SpringBoot' }, { value: 'Vue3+Node.js' },
]

const ACTION_TEXT = {
  login: '登录系统', login_failed: '登录失败', change_password: '修改密码',
  order_create: '创建订单', order_update: '修改订单信息', order_status: '变更订单状态',
  order_deploy_status: '变更部署状态',
  status_revert_request: '申请撤回状态', status_revert_approve: '通过撤回申请',
  status_revert_reject: '驳回撤回申请', status_revert_cancel: '撤回申请',
  status_revert_auto_reject: '撤回申请自动失效',
  file_upload: '上传文件', file_delete: '删除文件', file_download: '下载文件',
  requirement_generate: '生成需求书', requirement_update: '编辑需求书', requirement_download: '下载需求书',
  requirement_ai_revise: 'AI 修改需求书',
  paper_doc_upload: '上传论文留档',
  user_create: '创建用户', user_update: '修改用户', api_key_reset: '重置 API Key', api_key_reset_self: '重置 API Key',
  api_order_create: '通过 API 创建订单', api_requirement_download: '通过 API 下载需求书', api_file_download: '通过 API 下载文件',
}

const fileCats = [
  { key: 'package', label: '程序包' },
  { key: 'video', label: '演示视频' },
  { key: 'doc', label: '文档' },
  { key: 'other', label: '其他附件' },
]

const STATUS_TEXT = {
  pending: '待开始', in_progress: '制作中', completed: '已完成',
  closed: '已结单', after_sale: '售后中', cancelled: '已取消',
}
// 后端 allowed_statuses 给出当前角色可推进的目标，前端只负责按钮文案。
const STATUS_ACTION = {
  pending: { label: '退回待开始', type: 'default' },
  in_progress: { label: '开始制作', type: 'primary' },
  completed: { label: '标记完成', type: 'primary' },
  closed: { label: '结单', type: 'primary' },
  after_sale: { label: '转售后', type: 'default' },
  cancelled: { label: '取消订单', type: 'danger', danger: true },
}
const DEPLOY_TEXT = { undeployed: '未部署', deployed: '已部署', not_required: '无需部署' }

const stepIndex = computed(() => {
  const map = { pending: 0, in_progress: 1, completed: 2, closed: 3, after_sale: 2 }
  return map[order.value?.status] ?? 0
})

const ptText = computed(() => (order.value?.project_type ? projectTypeMeta(order.value.project_type).label : '未设置'))

// ===== 论文进度（含论文项目类型：任务书/开题报告/初稿/终稿留档） =====
const paperTabVisible = computed(() => hasPaperWorkflow(order.value?.project_type))
const paperData = ref(null)
const paperLoading = ref(false)
const paperDocs = computed(() => paperData.value?.docs || [])
const paperDoneCount = computed(() => paperDocs.value.filter((d) => d.count > 0).length)
const paperGap = computed(() => Math.max(
  0, (paperData.value?.min_revisions ?? 5) - (paperData.value?.draft_revisions ?? 0),
))
const paperDraftPercent = computed(() => {
  const min = paperData.value?.min_revisions ?? 5
  if (!min) return 100
  return Math.min(100, Math.round(((paperData.value?.draft_revisions ?? 0) / min) * 100))
})
const paperFinalReady = computed(() =>
  (paperData.value?.draft_revisions ?? 0) >= (paperData.value?.min_revisions ?? 5),
)

function paperIndex(d) {
  return String(paperDocs.value.findIndex((x) => x.doc_type === d.doc_type) + 1).padStart(2, '0')
}

async function loadPaper() {
  if (!paperTabVisible.value || !orderId.value) return
  paperLoading.value = true
  try {
    paperData.value = await http.get(`/orders/${orderId.value}/paper`)
  } catch {
    paperData.value = null
  } finally {
    paperLoading.value = false
  }
}

// ---- 上传/修改留档 ----
const paperUpVisible = ref(false)
const paperUpType = ref('task_book')
const paperUpLabel = computed(() => paperDocs.value.find((d) => d.doc_type === paperUpType.value)?.label || '')
const paperUpCount = computed(() => paperDocs.value.find((d) => d.doc_type === paperUpType.value)?.count || 0)
const paperUpNote = ref('')
const paperUpFile = ref(null)
const paperUpSending = ref(false)
const paperFileInput = ref(null)

function openPaperUpload(d) {
  paperUpType.value = d.doc_type
  paperUpNote.value = ''
  paperUpFile.value = null
  paperUpVisible.value = true
}

function onPaperFileChosen(e) {
  paperUpFile.value = e.target.files?.[0] || null
  e.target.value = '' // 允许重复选择同一文件
}

async function submitPaperUpload() {
  if (!paperUpFile.value || paperUpSending.value) return
  paperUpSending.value = true
  try {
    const fd = new FormData()
    fd.append('doc_type', paperUpType.value)
    fd.append('file', paperUpFile.value)
    if (paperUpNote.value.trim()) fd.append('note', paperUpNote.value.trim())
    const data = await http.post(`/orders/${orderId.value}/paper/docs`, fd, { timeout: 120000 })
    paperData.value = data
    paperUpVisible.value = false
    ElMessage.success(`${paperUpLabel.value}第 ${data.uploaded?.round ?? ''} 版已留档`)
    reload() // 文件列表/日志同步刷新
  } catch { /* 拦截器提示（如终稿门槛不足 400） */ } finally {
    paperUpSending.value = false
  }
}

// ---- 留档记录抽屉 ----
const paperHisVisible = ref(false)
const paperHisLoading = ref(false)
const paperHisDocs = ref([])
const paperHisLabel = computed(() => paperDocs.value.find((d) => d.doc_type === paperUpType.value)?.label || '')

async function openPaperHistory(d) {
  paperUpType.value = d.doc_type
  paperHisVisible.value = true
  paperHisLoading.value = true
  paperHisDocs.value = []
  try {
    const data = await http.get(`/orders/${orderId.value}/paper/docs`, { params: { doc_type: d.doc_type } })
    paperHisDocs.value = data.docs || []
  } catch { /* 拦截器提示 */ } finally {
    paperHisLoading.value = false
  }
}

function downloadFile(fileId) {
  window.open(`/api/files/${fileId}/download?download=1`, '_blank')
}

const countdown = computed(() => {
  const o = order.value
  if (!o?.deadline || ['completed', 'closed', 'cancelled'].includes(o.status)) return null
  const days = Math.floor((new Date(o.deadline + 'T23:59:59') - new Date()) / 86400000)
  if (days < 0) return { text: `已逾期 ${-days} 天`, cls: 'cd-over' }
  if (days === 0) return { text: '今天交付', cls: 'cd-today' }
  if (days <= 3) return { text: `剩 ${days} 天`, cls: 'cd-soon' }
  return { text: `剩 ${days} 天`, cls: 'cd-far' }
})

const nextActions = computed(() => {
  const o = order.value
  if (!o || o.status_revert) return []
  return (o.allowed_statuses || [])
    .filter((s) => STATUS_ACTION[s])
    .map((s) => ({ value: s, ...STATUS_ACTION[s] }))
})

const canRequestRevert = computed(() =>
  auth.isStaffView && !auth.isAdmin
  && !!order.value?.revert_target && !order.value?.status_revert,
)

const overdue = computed(() => {
  if (!order.value?.deadline) return false
  if (['completed', 'closed', 'cancelled'].includes(order.value.status)) return false
  // 与看板/列表同一判定（本地时区），避免 UTC 日期在东八区凌晨误判逾期
  return deadlineState(order.value.deadline).key === 'overdue'
})

// 原始需求资料（仅工作人员视图下发）：生成需求书时作为基准
const hasSourceMaterial = computed(() => !!(order.value?.source_requirement || order.value?.requirement_notes))
const sourceMaterialText = computed(() => {
  const parts = []
  if (order.value?.source_requirement) parts.push('原始需求文档')
  if (order.value?.requirement_notes) parts.push('需求要点')
  return parts.join('与')
})
// 直接采用：上传的需求书原文即需求书（生成时不调 AI、不改写）
const directApply = computed(() =>
  order.value?.source_apply_mode === 'direct' && !!order.value?.source_requirement,
)

function filesOf(cat) {
  return (order.value?.files || []).filter((f) => f.category === cat)
}

function fmt(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : '-'
}

function fmtSize(n) {
  if (n == null) return '-'
  if (n < 1024) return n + ' B'
  if (n < 1024 ** 2) return (n / 1024).toFixed(1) + ' KB'
  if (n < 1024 ** 3) return (n / 1024 ** 2).toFixed(1) + ' MB'
  return (n / 1024 ** 3).toFixed(2) + ' GB'
}

function logColor(action) {
  if (action.includes('delete') || action.includes('failed')) return 'danger'
  if (action === 'status_revert_approve') return 'success'
  if (action === 'status_revert_reject' || action === 'status_revert_auto_reject') return 'danger'
  if (action === 'order_create') return 'primary'
  if (action.startsWith('requirement')) return 'success'
  return 'info'
}

function detailText(lg) {
  const d = lg.detail || {}
  if (lg.action === 'order_status') return `${STATUS_TEXT[d.before] || d.before} → ${STATUS_TEXT[d.after] || d.after}`
  if (lg.action === 'order_deploy_status') return `${DEPLOY_TEXT[d.before] || d.before} → ${DEPLOY_TEXT[d.after] || d.after}`
  if (lg.action === 'status_revert_request') {
    return `${STATUS_TEXT[d.from] || d.from} → ${STATUS_TEXT[d.to] || d.to}；原因：${d.reason || '-'}`
  }
  if (lg.action === 'status_revert_approve') return `${d.applicant || '-'} 的申请已通过${d.note ? '；备注：' + d.note : ''}`
  if (lg.action === 'status_revert_reject') return `${d.applicant || '-'} 的申请被驳回${d.note ? '；原因：' + d.note : ''}`
  if (lg.action === 'status_revert_auto_reject') return d.reason || '订单状态已变化，申请自动失效'
  // 文件上传：替换上传时 detail.replaced 带回被替换掉的旧文件名
  if (d.file) {
    return `${d.file}${d.size != null ? '（' + fmtSize(d.size) + '）' : ''}${Array.isArray(d.replaced) && d.replaced.length ? '；替换了旧文件：' + d.replaced.join('、') : ''}`
  }
  if (lg.action === 'order_create') return `题目：${d.title || ''}`
  if (lg.action === 'requirement_generate') {
    return `来源：${{ ai: 'AI 生成', template: '模板生成' }[d.source] || d.source || '-'}${d.note ? '；' + d.note : ''}`
  }
  if (lg.action === 'requirement_ai_revise') {
    return `修改建议：${d.instruction || '-'}`
  }
  if (d.before || d.after) {
    return Object.keys(d.after || {}).map((k) => `${k}: ${JSON.stringify(d.before?.[k]) ?? '-'} → ${JSON.stringify(d.after[k])}`).join('；')
  }
  return ''
}

async function reload(seq) {
  const id = orderId.value
  const stale = () => seq != null && seq !== loadSeq
  const data = await http.get(`/orders/${id}`)
  if (stale()) return
  order.value = data.order
  if (order.value.has_requirement) {
    try {
      const rd = await http.get(`/orders/${id}/requirement`)
      if (stale()) return
      previewDoc.value = rd.document
    } catch {
      if (!stale()) previewDoc.value = null
    }
  } else {
    previewDoc.value = null
  }
}

async function generate(mode) {
  if (generating.value) return
  generatingMode.value = mode
  try {
    const data = await http.post(`/orders/${orderId.value}/requirement/generate`, { mode }, { timeout: 300000 })
    if (data.source === 'ai') ElMessage.success('AI 生成完成，可在线编辑或直接下载')
    else ElMessage.success(data.note || '模板生成完成')
    await reload()
    tab.value = 'doc'
  } finally {
    generatingMode.value = ''
  }
}

async function openVersions() {
  verVisible.value = true
  verLoading.value = true
  try {
    const data = await http.get(`/orders/${orderId.value}/requirement/versions`)
    versions.value = data.versions
  } finally {
    verLoading.value = false
  }
}

async function restoreVersion(v) {
  try {
    await ElMessageBox.confirm(`确定回滚到 ${fmt(v.created_at)} 的版本吗？当前内容会先自动存档。`, '回滚需求书', {
      confirmButtonText: '回滚', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  await http.post(`/orders/${orderId.value}/requirement/versions/${v.id}/restore`)
  ElMessage.success('已回滚')
  verVisible.value = false
  reload()
}

async function trashOrder() {
  try {
    await ElMessageBox.confirm(`确定将订单 ${order.value.id} 移入回收站吗？可随时在回收站恢复。`, '移入回收站', {
      confirmButtonText: '移入', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger',
    })
  } catch { return }
  const pwd = await sensitiveConfirm({ title: '删除订单确认', content: '移入回收站需要密码二次确认' })
  if (pwd == null) return
  await http.delete(`/orders/${order.value.id}`, withConfirm(pwd))
  ElMessage.success('已移入回收站')
  router.push('/orders')
}

async function fetchSummary() {
  summaryLoading.value = true
  try {
    const data = await http.get(`/orders/${orderId.value}/ai/summary`, { timeout: 60000 })
    aiSummary.value = data.summary
    try { sessionStorage.setItem(`ai-sum-${orderId.value}`, data.summary) } catch { /* 隐私模式等场景忽略 */ }
  } catch { /* 拦截器处理 */ } finally { summaryLoading.value = false }
}

function downloadDoc() {
  window.open(`/api/orders/${orderId.value}/requirement/docx`, '_blank')
}

function downloadReceipt() {
  window.open(`/api/orders/${orderId.value}/receipt`, '_blank')
}

function downloadReceiptPdf() {
  window.open(`/api/orders/${orderId.value}/receipt.pdf`, '_blank')
}

function download(f) {
  window.open(`/api/files/${f.id}/download?download=1`, '_blank')
}

// ===== 客户交付链接 =====
const deliverOpen = ref(false)
const deliverUrl = ref('')
const deliverStatsData = ref(null)

async function openDeliver() {
  try {
    const [link, stats] = await Promise.allSettled([
      http.get(`/orders/${order.value.id}/deliver-link`),
      http.get(`/orders/${order.value.id}/deliver-stats`),
    ])
    if (link.status === 'fulfilled') {
      deliverUrl.value = `${window.location.origin}/deliver/${link.value.token}`
      deliverOpen.value = true
    }
    if (stats.status === 'fulfilled') deliverStatsData.value = stats.value
  } catch { /* 拦截器处理 */ }
}

async function copyDeliver() {
  try {
    await navigator.clipboard.writeText(deliverUrl.value)
    ElMessage.success('交付链接已复制')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

function openDeliverPreview() {
  window.open(deliverUrl.value, '_blank')
}

// 右栏「交付与验收」卡：进页即拉一次浏览/下载统计（同一接口，openDeliver 弹窗内仍会刷新）
async function loadDeliverStats() {
  try {
    deliverStatsData.value = await http.get(`/orders/${orderId.value}/deliver-stats`)
  } catch { /* 拦截器处理 */ }
}

// 管理员撤销客户验收（密码二次确认 → POST /orders/{id}/accept-revoke）
const revokeLoading = ref(false)

async function revokeAccept() {
  const pwd = await sensitiveConfirm({ title: '撤销验收确认', content: '撤销客户验收标记需要密码二次确认' })
  if (pwd == null) return
  revokeLoading.value = true
  try {
    await http.post(`/orders/${orderId.value}/accept-revoke`, {}, withConfirm(pwd))
    ElMessage.success('已撤销验收')
    reload()
  } finally {
    revokeLoading.value = false
  }
}

function preview(f) {
  videoFile.value = f
  videoVisible.value = true
}

async function removeFile(f) {
  try {
    await ElMessageBox.confirm(`确定删除「${f.original_name}」吗？`, '删除文件', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger',
    })
  } catch { return }
  const pwd = await sensitiveConfirm({ title: '删除文件确认', content: '删除文件需要密码二次确认' })
  if (pwd == null) return
  await http.delete(`/files/${f.id}`, withConfirm(pwd))
  ElMessage.success('已删除')
  reload()
}

async function changeStatus(status) {
  try {
    await ElMessageBox.confirm(`确定将订单状态改为「${STATUS_TEXT[status]}」吗？`, '状态流转', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  statusLoading.value = true
  try {
    await http.post(`/orders/${orderId.value}/status`, { status })
    ElMessage.success('状态已更新')
    await reload()
  } catch { /* 拦截器处理 */ } finally {
    statusLoading.value = false
  }
}

function openRevert() {
  revertReason.value = ''
  revertVisible.value = true
}

async function submitRevert() {
  const reason = revertReason.value.trim()
  if (reason.length < 2) {
    ElMessage.warning('请填写撤回原因（至少 2 个字）')
    return
  }
  const target = order.value?.revert_target
  if (!target) {
    ElMessage.warning('当前订单不支持申请撤回')
    return
  }
  revertLoading.value = true
  try {
    await http.post(`/orders/${orderId.value}/status-revert`, { to_status: target, reason })
    ElMessage.success('申请已提交，等待管理员审批')
    revertVisible.value = false
    await reload()
  } catch { /* 拦截器处理 */ } finally {
    revertLoading.value = false
  }
}

async function cancelRevert() {
  const req = order.value?.status_revert
  if (!req) return
  try {
    await ElMessageBox.confirm('撤回后本次申请作废，订单状态保持不变。确定撤回吗？', '撤回申请', {
      confirmButtonText: '确定撤回', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  revertLoading.value = true
  try {
    await http.post(`/status-reverts/${req.id}/cancel`)
    ElMessage.success('已撤回申请')
    await reload()
  } catch { /* 拦截器处理 */ } finally {
    revertLoading.value = false
  }
}

async function reviewRevert(action) {
  const req = order.value?.status_revert
  if (!req) return
  const approve = action === 'approve'
  let note = ''
  try {
    const { value } = await ElMessageBox.prompt(
      approve
        ? `通过后订单将从「${req.from_status_cn}」自动回退为「${req.to_status_cn}」。可填写审批备注。`
        : '驳回后订单状态保持不变。可填写驳回原因。',
      approve ? '同意撤回申请' : '驳回撤回申请',
      {
        confirmButtonText: approve ? '同意撤回' : '确认驳回',
        cancelButtonText: '取消',
        inputPlaceholder: '审批备注（选填，最多 300 字）',
        inputValidator: (v) => !v || v.length <= 300 || '最多 300 字',
        type: 'warning',
      },
    )
    note = (value || '').trim()
  } catch { return }
  reviewLoading.value = true
  try {
    await http.post(`/status-reverts/${req.id}/review`, { action, note: note || null })
    ElMessage.success(approve ? '已通过，订单状态已回退' : '已驳回该申请')
    await reload()
  } catch { /* 拦截器处理 */ } finally {
    reviewLoading.value = false
  }
}

async function changeDeploy(v) {
  if (order.value?.deploy_status === v) return
  deployLoading.value = true
  try {
    await http.post(`/orders/${orderId.value}/deploy-status`, { deploy_status: v })
    ElMessage.success('部署状态已更新')
    await reload()
  } catch { /* 拦截器处理 */ } finally {
    deployLoading.value = false
  }
}

function openEdit() {
  const o = order.value
  Object.assign(editForm, {
    title: o.title,
    project_type: o.project_type || undefined,
    tech_stack: o.tech_stack || undefined,
    quality_code: o.quality.code,
    owner_price: o.owner_price,
    deadline: o.deadline || undefined,
    agent_username: o.agent?.username || undefined,
    assignee_username: o.assignee?.username || undefined,
    customer_info: o.customer_info || '',
    remark: o.remark || '',
    requirement_notes: o.requirement_notes || '',
    source_requirement: o.source_requirement || '',
    source_apply_mode: o.source_apply_mode || 'reference',
  })
  editVisible.value = true
}

const editFormRef = ref(null)
// 只校验「用户改过」的字段：已逾期的历史订单不该因为期限早于今天而无法保存其它信息
const editRules = {
  title: [
    { required: true, message: '请填写题目', trigger: 'blur' },
    { min: 2, max: 255, message: '题目需 2-255 个字符', trigger: 'blur' },
  ],
  quality_code: [{ required: true, message: '请选择品质', trigger: 'change' }],
  owner_price: [
    {
      validator: (_rule, value, cb) => (value == null || Number(value) >= 0
        ? cb() : cb(new Error('真实价不能为负数'))),
      trigger: 'blur',
    },
  ],
  deadline: [
    {
      validator: (_rule, value, cb) => {
        if (!value || value === order.value?.deadline) return cb()
        const today = new Date()
        today.setHours(0, 0, 0, 0)
        return new Date(`${value}T00:00:00`) >= today ? cb() : cb(new Error('交付期限不能早于今天'))
      },
      trigger: 'change',
    },
  ],
}

async function saveEdit() {
  if (editFormRef.value) {
    try {
      await editFormRef.value.validate()
    } catch {
      return
    }
  }
  let confirmPwd = null
  const priceChanged = auth.isAdmin && editForm.owner_price != null
    && Number(editForm.owner_price) !== Number(order.value.owner_price)
  if (priceChanged) {
    confirmPwd = await sensitiveConfirm({ title: '修改真实价确认', content: '调整真实价需要密码二次确认' })
    if (confirmPwd == null) return
  }
  saving.value = true
  try {
    const payload = {
      title: editForm.title,
      project_type: editForm.project_type || null,
      tech_stack: editForm.tech_stack || null,
      quality_code: editForm.quality_code,
      deadline: editForm.deadline || null,
      customer_info: editForm.customer_info,
      remark: editForm.remark,
      agent_username: editForm.agent_username || '',
      assignee_username: editForm.assignee_username || '',
    }
    // 原始需求资料仅工作人员可见/可改；代理视图无这些字段
    if (auth.isStaffView) {
      payload.requirement_notes = editForm.requirement_notes || null
      payload.source_requirement = editForm.source_requirement || null
      if (editForm.source_requirement) payload.source_apply_mode = editForm.source_apply_mode
    }
    // 只在管理员真的改了真实价时才携带：只改品质时让后端按新品质自动重算，
    // 且不会因携带旧价触发后端对品质变更路径的无条件密码确认（403）
    if (priceChanged) payload.owner_price = editForm.owner_price
    await http.patch(`/orders/${orderId.value}`, payload, confirmPwd ? withConfirm(confirmPwd) : {})
    ElMessage.success('已保存')
    editVisible.value = false
    reload()
  } finally {
    saving.value = false
  }
}

/** 代理确认开工：需求书已与客户定稿，由代理通知后台开始制作（订单转为「制作中」） */
async function confirmStart() {
  try {
    await ElMessageBox.confirm('确认客户已定稿需求书并开始制作？确认后订单将转为「制作中」，管理员与写手会收到开工通知。', '确认开工', {
      type: 'warning', confirmButtonText: '确认开工', cancelButtonText: '再等等',
    })
  } catch { return }
  try {
    await http.post(`/orders/${orderId.value}/start-production`, {}, { timeout: 60000 })
    ElMessage.success('已通知后台开始制作')
    reload()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '确认开工失败，请稍后重试')
  }
}

/** 删除当前需求书：删除前会自动存档，可从「历史版本」恢复 */
async function deleteRequirement() {
  try {
    await ElMessageBox.confirm('确定删除当前需求书？删除前会自动保存历史版本，可随时从「历史版本」恢复。', '删除需求书', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch { return }
  try {
    await http.delete(`/orders/${orderId.value}/requirement`)
    ElMessage.success('需求书已删除')
    reload()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  }
}

/** 需求书「上传替换」：把整份需求书文件交给后端解析，并替换当前需求书 */
function uploadReplaceRequirement() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json,.docx,.pdf,.txt,.md'
  input.onchange = async () => {
    const file = input.files && input.files[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    ElMessage.info('正在解析上传的需求书…')
    try {
      const res = await http.post(`/orders/${orderId.value}/requirement/upload`, fd, { timeout: 120000 })
      ElMessage.success(res.note || '需求书已替换')
      reload()
    } catch (err) {
      ElMessage.error(err?.response?.data?.detail || '上传失败，请检查文件格式')
    }
  }
  input.click()
}

// ===== 演示视频速览（右栏小播放器） =====
const videoFiles = computed(() => (order.value?.files || []).filter((f) => f.category === 'video'))
const currentVideoId = ref(null)
const currentVideo = computed(() => {
  const found = videoFiles.value.find((v) => v.id === currentVideoId.value)
  return found || videoFiles.value[0] || order.value?.video || { id: 0, name: '' }
})

// ===== 需求书修改对比 =====
const diffVisible = ref(false)
const diffVersions = ref([])
const diffVersionsLoading = ref(false)
const diffVersionId = ref(null)
const diffData = ref(null)
const diffLoading = ref(false)
const diffAiLoading = ref(false)

async function openDiff() {
  diffVisible.value = true
  if (diffVersions.value.length) return
  diffVersionsLoading.value = true
  try {
    const data = await http.get(`/orders/${orderId.value}/requirement/versions`)
    diffVersions.value = data.versions
    if (data.versions.length && !diffVersionId.value) {
      diffVersionId.value = data.versions[0].id
      loadDiff()
    }
  } finally {
    diffVersionsLoading.value = false
  }
}

async function loadDiff(ai = false) {
  if (!diffVersionId.value) return
  // 请求序号守卫：快速切换基准版本时，晚到的旧响应不得覆盖新结果
  const seq = ++diffSeq
  if (ai === true) diffAiLoading.value = true
  else diffLoading.value = true
  try {
    const data = await http.get(`/orders/${orderId.value}/requirement/diff`, {
      params: { version_id: diffVersionId.value, ai: ai === true },
    })
    if (seq !== diffSeq) return
    diffData.value = data
  } catch { /* 拦截器处理 */ } finally {
    if (seq === diffSeq) {
      diffLoading.value = false
      diffAiLoading.value = false
    }
  }
}

// ===== 客户跟进记录 =====
const notes = ref([])
const noteText = ref('')
const noteSaving = ref(false)

function noteColor(role) {
  if (role === 'admin') return 'primary'
  if (role === 'staff') return 'success'
  if (role === 'agent') return 'warning'
  return 'info'
}

async function loadNotes() {
  try {
    const data = await http.get(`/orders/${orderId.value}/notes`)
    notes.value = data.notes
  } catch { /* 拦截器处理 */ }
}

async function addNote() {
  const content = noteText.value.trim()
  if (!content) return
  noteSaving.value = true
  try {
    await http.post(`/orders/${orderId.value}/notes`, { content })
    noteText.value = ''
    ElMessage.success('已记录')
    loadNotes()
  } catch { /* 拦截器处理 */ } finally {
    noteSaving.value = false
  }
}

async function loadMeta() {
  try {
    const pub = await http.get('/settings/public')
    aiReady.value = !!pub.ai_ready
    watermarkOn.value = pub.watermark_enabled !== false
  } catch {
    aiReady.value = false
    watermarkOn.value = true
  }
  if (auth.isStaffView) {
    try {
      const q = await http.get('/qualities')
      qualities.value = q.qualities || []
      const u = await http.get('/users')
      agents.value = (u.items || []).filter((x) => x.role === 'agent')
      staffList.value = (u.items || []).filter((x) => ['admin', 'staff'].includes(x.role))
    } catch { /* 非管理角色或网络异常时保持空列表 */ }
  }
}

async function loadPage() {
  const my = ++loadSeq
  orderId.value = String(route.params.id || '')
  order.value = null
  loadError.value = ''
  previewDoc.value = null
  notes.value = []
  deliverStatsData.value = null
  paperData.value = null
  versions.value = []
  diffVersions.value = []
  diffData.value = null
  diffVersionId.value = null
  currentVideoId.value = null
  aiSummary.value = ''
  try { aiSummary.value = sessionStorage.getItem(`ai-sum-${orderId.value}`) || '' } catch { /* 忽略 */ }
  try {
    await reload(my)
    if (my !== loadSeq) return
    await Promise.allSettled([loadNotes(), loadDeliverStats(), loadMeta(), loadPaper()])
    if (my !== loadSeq) return
    if (route.query.edit === '1' && auth.isStaffView) openEdit()
  } catch (e) {
    // 加载失败要落到错误态（可重试/返回），而不是退回骨架屏永久“加载中”
    if (my === loadSeq) {
      order.value = null
      loadError.value = e?.response?.data?.detail || '订单加载失败'
    }
  }
}

// ---- 请求序号：切换订单时旧响应必须作废，否则 A 单数据会覆盖 B 单页面 ----
let loadSeq = 0
// 需求书修改对比的请求序号（与 loadSeq 同理：旧响应作废）
let diffSeq = 0
// 当前正在展示的订单号快照。所有请求都用它，而不是 route.params.id，
// 因为 await 之后路由可能已经切到别的订单。
const orderId = ref('')

watch(() => route.params.id, () => { loadPage() })
onMounted(() => { loadPage() })
onBeforeUnmount(() => { loadSeq++ })
/** 编辑弹窗里的「上传文档替换」：只解析文档并回填原始需求全文，点保存后才生效 */
function pickSourceFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.docx,.pdf,.txt,.md,.json'
  input.onchange = async () => {
    const file = input.files && input.files[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await http.post('/orders/parse-requirement-file', fd, { timeout: 120000 })
      editForm.source_requirement = res.text || ''
      ElMessage.success(`已解析 ${file.name}（${res.chars || 0}字），保存后生效`)
    } catch (err) {
      ElMessage.error('解析失败：' + (err?.response?.data?.detail || '请检查文件格式'))
    }
  }
  input.click()
}
</script>

<style scoped>
/* ===== 页面容器（全宽，间距由 page-shell 统一） ===== */
.order-detail { position: relative; width: 100%; }
.od-error-card { padding: 56px 20px; }
.head-card { margin-bottom: 0; }

/* ===== 左右分栏：minmax(0,1fr) 主栏 + 340px 右栏（≤1000px 单列） ===== */
.od-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 18px;
  align-items: start;
}
.od-main { min-width: 0; display: flex; flex-direction: column; gap: 18px; }
.od-side { min-width: 0; position: sticky; top: calc(var(--topbar-h) + var(--tabs-h) + 12px); display: flex; flex-direction: column; gap: 18px; }
@media (max-width: 1000px) {
  .od-layout { grid-template-columns: 1fr; }
  .od-side { position: static; }
}

/* ===== 头部卡片（紧凑：标签行 / 标题 / AI 摘要） ===== */
.head-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.head-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.order-no {
  font-weight: 700; font-size: 14px; letter-spacing: 0.5px;
  background: var(--brand-grad);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; color: transparent;
}
.order-title {
  margin: 10px 0 12px; font-size: 22px; font-weight: 700; line-height: 1.4; letter-spacing: 0.2px;
}
.ai-summary {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 10px 14px;
  background: var(--brand-weak);
  border: 1px solid var(--brand-weak-2); border-radius: var(--radius);
  border-left: 3px solid var(--brand);
  font-size: 13px; color: var(--text); line-height: 1.65;
}
.ai-sum-icon { color: var(--brand); font-size: 14px; margin-top: 3px; }

/* ===== 指标磁贴（art-design-pro 描述列表风格：浅灰底+垂直标签上值下） ===== */
.info-strip {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}
.strip-item {
  padding: 12px 14px;
  display: flex; flex-direction: column; gap: 4px;
  background: var(--card-2); border-radius: var(--radius);
  border: 1px solid var(--border);
}
.strip-label { font-size: 11px; color: var(--text-3); }
.strip-value { font-size: 17px; font-weight: 700; font-variant-numeric: tabular-nums; }
.strip-item.price .strip-value { color: var(--brand); }
.strip-value.agent-price { color: var(--info); }
.strip-value.overdue { color: var(--danger); }
.strip-sub { font-size: 11px; font-weight: 600; }
.strip-sub.cd-over { color: var(--danger); }
.strip-sub.cd-today { color: var(--warning); }
.strip-sub.cd-soon { color: #e0a13a; }
html.light .strip-sub.cd-soon { color: #b77900; }
.strip-sub.cd-far { color: var(--text-3); font-weight: 400; }

/* ===== 状态流转（轻量：浅底容器+步骤） ===== */
.flow-area {
  margin-bottom: 4px; padding: 12px 16px 8px;
  background: var(--card-2); border-radius: var(--radius);
}
.flow-steps { margin-bottom: 8px; }
.flow-alert { margin-bottom: 14px; }
.status-actions {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 12px;
  padding: 10px 14px; background: var(--card-2); border-radius: var(--radius);
}
.sa-label { font-size: 12.5px; color: var(--text-2); }
.sa-empty { font-size: 12.5px; color: var(--text-3); }

/* ===== 写手撤回审批：内联状态卡 ===== */
.revert-area { margin-top: 10px; }
.revert-pending {
  display: flex; align-items: flex-start; gap: 10px; flex-wrap: wrap;
  padding: 11px 13px;
  border: 1px solid rgba(255, 174, 31, .3); border-radius: var(--radius);
  background: rgba(255, 174, 31, .075);
}
.rp-icon {
  width: 32px; height: 32px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  border-radius: 9px; background: rgba(255, 174, 31, .15); color: #e0a13a; font-size: 17px;
}
.rp-main { flex: 1; min-width: 200px; }
.rp-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; font-weight: 600; }
.rp-status {
  padding: 1px 7px; border-radius: 999px;
  background: rgba(255, 174, 31, .16); color: #d99a2b; font-size: 10.5px; font-weight: 600;
}
.rp-sub { margin-top: 3px; font-size: 11.5px; color: var(--text-3); }
.rp-reason { margin-top: 5px; font-size: 12px; color: var(--text-2); line-height: 1.55; word-break: break-all; }
.rp-actions { display: flex; gap: 8px; flex-shrink: 0; margin-left: auto; }
.rp-wait { font-size: 11.5px; color: var(--text-3); white-space: nowrap; padding-top: 6px; }
.revert-entry {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 9px 12px;
  border: 1px dashed var(--border-2); border-radius: var(--radius);
  font-size: 12.5px; color: var(--text-2);
}
.revert-entry > .iconify { color: var(--brand); font-size: 15px; flex-shrink: 0; }
.revert-entry .el-button { margin-left: auto; }
.revert-hint {
  display: flex; align-items: center; gap: 7px;
  padding: 7px 2px 0; font-size: 11.5px; color: var(--text-3);
}
.revert-hint > .iconify { font-size: 14px; }

.revert-dialog .rd-flow { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.rd-chip {
  padding: 4px 11px; border-radius: 999px;
  border: 1px solid var(--border); background: var(--card-2);
  font-size: 12.5px; font-weight: 600;
}
.rd-chip.rd-target { border-color: rgba(93, 135, 255, .35); background: var(--brand-weak); color: var(--brand); }
.rd-arrow { color: var(--text-3); font-size: 15px; }
.rd-tip { margin-bottom: 12px; font-size: 12.5px; line-height: 1.65; color: var(--text-2); }

/* ===== 右栏卡片 ===== */
.sc-title { margin: 0 0 12px; font-size: 15px; font-weight: 600; color: var(--text); }

/* 订单信息：两列紧凑描述（备注全宽） */
.side-meta { display: grid; grid-template-columns: 1fr 1fr; }
.side-meta .meta-cell {
  padding: 8px 12px 8px 0;
  border-bottom: 1px dashed var(--border);
  min-width: 0;
}
.side-meta .meta-cell:nth-child(2n) { padding-right: 0; }
.side-meta .meta-cell.wide { grid-column: 1 / -1; border-bottom: none; padding-bottom: 0; }
.meta-label { font-size: 11px; color: var(--text-3); margin-bottom: 2px; }
.meta-value { font-size: 12.5px; word-break: break-all; }
.meta-value.pre { white-space: pre-wrap; }

/* 交付与验收 */
.dc-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.dc-stat {
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 10px 8px;
  background: var(--card-2); border: 1px solid var(--border); border-radius: var(--radius);
}
.dcs-num { font-size: 18px; font-weight: 700; color: var(--brand); font-variant-numeric: tabular-nums; }
.dcs-label { font-size: 11px; color: var(--text-3); }
.dc-btn { width: 100%; margin: 12px 0; }
.dc-accept { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.dc-accepted {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px;
  border: 1px solid rgba(19,222,185,.3); border-radius: 999px;
  background: var(--success-weak); color: var(--success);
  font-size: 12px; font-weight: 600;
}
.dc-none { font-size: 12.5px; color: var(--text-3); }

/* 演示视频速览：16:9 小播放器 */
.vc-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.vc-head .sc-title { margin: 0; }
.vc-count { font-size: 12px; color: var(--text-2); }
.vc-player {
  width: 100%; aspect-ratio: 16/9;
  border-radius: 10px; background: #000; display: block;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
}
.vc-list { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.vc-item {
  display: inline-flex; align-items: center; gap: 7px; max-width: 100%;
  padding: 6px 12px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--card-2); cursor: pointer; transition: all 0.15s;
  font-size: 12px;
}
.vc-item:hover { border-color: var(--brand-weak-2); }
.vc-item.active { border-color: var(--brand); background: var(--brand-weak); }
.vc-item-icon { color: var(--brand); font-size: 14px; }
.vc-item-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vc-item-meta { font-size: 11px; flex-shrink: 0; color: var(--text-3); }

/* ===== 客户跟进（notes 选项卡内） ===== */
.nc-input { display: flex; gap: 10px; align-items: flex-end; margin-bottom: 14px; }
.nc-input :deep(.el-textarea) { flex: 1; }
.note-timeline { padding-top: 4px; }
.note-line { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.note-role { font-size: 12px; }
.note-time { font-size: 11.5px; }
.note-content { font-size: 13.5px; line-height: 1.7; margin-top: 3px; white-space: pre-wrap; word-break: break-all; }
.note-empty { text-align: center; padding: 20px 0 14px; font-size: 13px; color: var(--text-3); }

/* ===== 修改对比抽屉 ===== */
.diff-toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
.diff-label { font-size: 12.5px; }
.diff-meta { font-size: 12.5px; margin-bottom: 12px; }
.diff-ai {
  display: flex; gap: 8px; padding: 10px 12px; margin-bottom: 14px;
  background: var(--brand-weak);
  border: 1px solid var(--brand-weak-2); border-radius: var(--radius); font-size: 12.5px; line-height: 1.7;
}
.da-icon { color: var(--brand); margin-top: 3px; }
.diff-empty { text-align: center; padding: 40px 0; color: var(--text-3); font-size: 13px; }
.diff-item { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; margin-bottom: 10px; }
.di-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.di-kind { font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px; flex-shrink: 0; }
.di-kind.changed { background: var(--warning-weak); color: var(--warning); }
.di-kind.added { background: var(--success-weak); color: var(--success); }
.di-kind.removed { background: var(--danger-weak); color: var(--danger); }
.di-label { font-size: 12px; color: var(--text-2); }
.di-old, .di-new {
  font-size: 12.5px; line-height: 1.7; padding: 7px 10px; border-radius: 7px; margin-top: 6px;
  display: flex; gap: 8px; word-break: break-all;
}
.di-old { background: rgba(255, 77, 79, 0.08); color: var(--text-2); }
.di-new { background: rgba(19, 222, 185, 0.08); }
.di-old .di-tag, .di-new .di-tag { flex-shrink: 0; font-size: 11px; font-weight: 600; opacity: 0.8; }
/* 字符级内联差异：删红增绿 */
.op-del { background: rgba(255, 77, 79, 0.22); color: #ffa39e; border-radius: 3px; text-decoration: line-through; }
.op-ins { background: rgba(19, 222, 185, 0.20); color: var(--success); border-radius: 3px; font-weight: 600; }
.di-old .di-tag { color: var(--danger); }
.di-new .di-tag { color: var(--success); }

/* ===== 文档/文件/日志 ===== */
.doc-empty { text-align: center; padding: 44px 0 30px; }
.empty-icon { color: var(--text-4); margin-bottom: 12px; font-size: 42px; }
.empty-title { font-size: 16px; font-weight: 600; }
.empty-sub { font-size: 12.5px; color: var(--text-2); margin: 8px 0 20px; }
.src-hint {
  display: inline-flex; align-items: center; gap: 5px; margin: -12px 0 20px;
  color: var(--brand);
}
.src-hint .iconify { flex-shrink: 0; }
.src-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 1px 8px; border-radius: var(--radius-pill);
  font-size: 11px; color: var(--brand);
  background: var(--brand-weak); cursor: help;
}
.empty-btns { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
.doc-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.doc-btns { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }

.file-group { margin-bottom: 20px; }
.deliver-bar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  padding: 10px 14px; margin-bottom: 16px;
  background: var(--brand-weak); border: 1px solid var(--brand-weak-2); border-radius: var(--radius);
}
.db-info { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; min-width: 0; }
.db-title { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; font-size: 13.5px; color: var(--brand); }
.db-desc { font-size: 12.5px; }
.dv-body { display: flex; flex-direction: column; gap: 14px; padding: 6px 0 2px; }
.dv-link {
  padding: 10px 12px; background: var(--card-2); border: 1px solid var(--border);
  border-radius: 8px; font-size: 12.5px; word-break: break-all; color: var(--brand);
}
.dv-tip { font-size: 12.5px; line-height: 1.7; }
.dv-stats {
  display: flex; align-items: center; gap: 8px; font-size: 13px;
  padding: 8px 12px; background: var(--card-2); border-radius: 8px;
}
.dv-stats b { color: var(--brand); }
.dv-actions { display: flex; gap: 10px; }
.file-group:last-child { margin-bottom: 4px; }
.fg-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.fg-title { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.fg-count { font-weight: 400; font-size: 12px; }
.file-list { display: flex; flex-direction: column; gap: 8px; }
.file-item {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  padding: 10px 14px; border: 1px solid var(--border); border-radius: 10px;
  transition: border-color 0.18s, background 0.18s;
}
.file-item:hover { border-color: var(--brand-weak-2); background: var(--hover); }
.f-icon {
  width: 36px; height: 36px; border-radius: 8px; flex-shrink: 0;
  background: var(--brand-weak); color: var(--brand);
  display: flex; align-items: center; justify-content: center; font-size: 15px;
}
.file-item.video .f-icon { background: var(--danger-weak); color: var(--danger); }
.f-info { min-width: 0; flex: 1; }
.f-name { font-weight: 500; word-break: break-all; display: block; }
.f-meta { font-size: 12px; display: block; margin-top: 2px; }
.f-actions { display: flex; gap: 2px; flex-shrink: 0; }

.log-timeline { padding-top: 8px; }
.log-line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.log-role { font-size: 12px; }
.log-action { color: var(--brand); font-weight: 500; }
.log-detail { font-size: 12px; margin-top: 3px; word-break: break-all; }
.log-time { font-size: 11.5px; margin-top: 2px; }

.ver-item {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; margin-bottom: 10px;
}
.ver-line1 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ver-user { font-size: 12px; }
.ver-time { font-size: 11.5px; }
.ver-remark { font-size: 12px; margin-top: 5px; }
.edit-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

@media (max-width: 768px) {
  /* 指标磁贴固定 2 列，视频列表/跟进输入纵向堆叠 */
  .info-strip { grid-template-columns: repeat(2, 1fr); }
  .edit-row { grid-template-columns: 1fr; }
  .side-meta { grid-template-columns: 1fr; }
  .side-meta .meta-cell { padding-right: 0; }
  .flow-steps { padding: 8px 0; }
  .vc-list { flex-direction: column; align-items: stretch; }
  .vc-item { max-width: none; }
  .nc-input { flex-direction: column; align-items: stretch; }
  .nc-input > .el-button { align-self: flex-end; }
  .doc-btns { margin-left: 0; width: 100%; }
  .rp-main { min-width: 0; }
  .rp-actions { width: 100%; margin-left: 0; justify-content: flex-end; }
  .rp-wait { width: 100%; padding-top: 0; }
  .revert-entry .el-button { margin-left: 0; width: 100%; }
}

/* ===== 论文进度面板 ===== */
.paper-panel { min-height: 200px; }
.pp-overview {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; margin-bottom: 14px;
  border-radius: var(--radius-sm);
  background: var(--card-2); border: 1px solid var(--border);
}
.ppo-left { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 13px; font-weight: 550; }
.ppo-ic { color: var(--brand); font-size: 16px; flex-shrink: 0; }
.ppo-sub { font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ppo-stat {
  flex-shrink: 0; font-size: 12px; padding: 2px 10px; border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--warning) 12%, transparent); color: var(--warning);
}
.ppo-stat.ok { background: color-mix(in srgb, var(--success) 12%, transparent); color: var(--success); }

.pp-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
@media (max-width: 900px) { .pp-grid { grid-template-columns: 1fr; } }
.pp-card {
  padding: 14px; border-radius: var(--radius-md);
  background: var(--card-2); border: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 10px;
}
.pp-card.done { border-color: color-mix(in srgb, var(--success) 30%, var(--border)); }
.ppc-head { display: flex; align-items: center; gap: 8px; }
.ppc-no {
  width: 24px; height: 24px; border-radius: 7px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11.5px; font-weight: 600;
  background: var(--brand-weak); color: var(--brand);
}
.pp-card.done .ppc-no { background: color-mix(in srgb, var(--success) 14%, transparent); color: var(--success); }
.ppc-label { font-size: 13.5px; font-weight: 600; }
.ppc-badge {
  margin-left: auto; font-size: 11px; padding: 1px 8px; border-radius: var(--radius-pill);
  color: var(--text-3); background: var(--card); border: 1px solid var(--border); white-space: nowrap;
}
.ppc-badge.ok {
  color: var(--success); background: color-mix(in srgb, var(--success) 10%, transparent);
  border-color: color-mix(in srgb, var(--success) 28%, transparent);
}

.ppc-progress { display: flex; flex-direction: column; gap: 6px; }
.ppp-text { display: flex; justify-content: space-between; font-size: 12.5px; color: var(--text-2); }
.ppp-text b { color: var(--warning); }
.ppp-text b.ok { color: var(--success); }
.ppp-hint { font-size: 11.5px; }

.ppc-gate {
  display: flex; align-items: center; gap: 8px; font-size: 12.5px;
  padding: 8px 10px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--warning) 8%, transparent); color: var(--text-2);
}
.ppc-gate .iconify { color: var(--warning); flex-shrink: 0; }
.ppc-gate.ready { background: color-mix(in srgb, var(--success) 9%, transparent); }
.ppc-gate.ready .iconify { color: var(--success); }

.ppc-latest {
  padding: 10px 12px; border-radius: var(--radius-sm);
  background: var(--card); border: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 4px;
}
.ppl-name {
  display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 550;
  white-space: nowrap; overflow: hidden;
}
.ppl-name .iconify { color: var(--brand); flex-shrink: 0; }
.ppl-name span { overflow: hidden; text-overflow: ellipsis; }
.ppl-meta { font-size: 11.5px; }
.ppl-actions { display: flex; gap: 4px; margin-top: 2px; }
.ppl-actions .el-button + .el-button { margin-left: 0; }
.ppc-ops { display: flex; gap: 8px; }

/* 上传弹窗 */
.pu-body { display: flex; flex-direction: column; gap: 12px; }
.pu-gate {
  display: flex; align-items: center; gap: 8px; font-size: 12.5px;
  padding: 9px 12px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--warning) 9%, transparent); color: var(--warning);
}
.pu-round { font-size: 12px; }
.pu-file {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 14px; border-radius: var(--radius-sm); cursor: pointer;
  border: 1px dashed var(--border); background: var(--card-2);
  transition: border-color .15s;
}
.pu-file:hover { border-color: var(--brand); }
.pu-file-input { display: none; }
.puf-ic { font-size: 24px; color: var(--brand); flex-shrink: 0; }
.puf-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; font-size: 13px; }
.puf-copy span { font-size: 11.5px; }

/* 留档记录抽屉 */
.ph-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; margin-bottom: 8px; border-radius: var(--radius-sm);
  background: var(--card-2); border: 1px solid var(--border);
}
.ph-round {
  flex-shrink: 0; width: 52px; text-align: center; font-size: 11.5px; font-weight: 600;
  padding: 3px 0; border-radius: var(--radius-pill);
  background: var(--brand-weak); color: var(--brand);
}
.ph-round.first { background: color-mix(in srgb, var(--warning) 12%, transparent); color: var(--warning); }
.ph-main { flex: 1; min-width: 0; }
.ph-name { display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 550; white-space: nowrap; overflow: hidden; }
.ph-name .iconify { color: var(--brand); flex-shrink: 0; }
.ph-name span { overflow: hidden; text-overflow: ellipsis; }
.ph-meta { font-size: 11.5px; }
</style>
