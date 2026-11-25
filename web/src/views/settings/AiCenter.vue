<template>
  <div class="ai-page">
    <SettingsShell
      title="AI 中心"
      description="模型与密钥、Bot 知识库与工具、技能提示词、Token 用量统计"
      icon="ri:robot-2-line"
      :loading="loading"
    >
      <div class="settings-stack settings-stack-ai">
        <!-- AI 控制台头图 -->
        <section class="ai-hero">
          <div class="ai-hero-grid" aria-hidden="true" />
          <div class="ai-hero-glow" aria-hidden="true" />
          <div class="ai-hero-main">
            <div class="ai-eyebrow"><span class="ai-live-dot" /> AI CONTROL ROOM · 智能中枢</div>
            <h2>模型、知识、用量，<em>一处掌控。</em></h2>
            <p>配置 DeepSeek 连接，管理 Bot 知识库与工具边界，追踪每一次 AI 调用的成本。</p>
            <div class="ai-hero-actions">
              <span class="ai-state-pill" :class="keySet ? 'ok' : 'off'">
                <Icon :icon="keySet ? 'ri:checkbox-circle-fill' : 'ri:error-warning-line'" />
                {{ keySet ? 'AI 已就绪' : '未配置 API Key' }}
              </span>
              <span class="ai-model-pill"><Icon icon="ri:cpu-line" />{{ form.deepseek_model }}</span>
              <button type="button" class="ai-link-btn" @click="active = 'usage'">
                <Icon icon="ri:pulse-line" />查看用量
              </button>
              <button type="button" class="ai-link-btn" @click="openBuiltin">
                <Icon icon="ri:book-open-line" />内置知识库
              </button>
            </div>
          </div>
          <div class="ai-hero-metrics">
            <div class="ahm-item">
              <span>近 {{ usageDays }} 天调用</span>
              <b>{{ usageReady ? compactNum(totals.calls) : '—' }}</b>
            </div>
            <div class="ahm-item">
              <span>Tokens</span>
              <b>{{ usageReady ? compactNum(totals.tokens) : '—' }}</b>
            </div>
            <div class="ahm-item">
              <span>估算成本</span>
              <b>{{ heroCost }}</b>
            </div>
          </div>
        </section>

        <el-tabs v-model="active" tab-position="top" class="ai-tabs">
          <!-- ===== 区域 1：模型 ===== -->
          <el-tab-pane name="model">
            <template #label>
              <span class="ai-tab">
                <span class="ai-tab-ic"><Icon icon="ri:cpu-line" /></span>
                <span class="ai-tab-copy"><b>模型</b><small>接口与密钥</small></span>
              </span>
            </template>

            <el-form label-position="top" class="model-workspace" @submit.prevent>
              <section class="ai-panel model-panel">
                <div class="settings-section-head">
                  <div>
                    <div class="settings-section-title">模型选择</div>
                    <p class="settings-section-desc">需求书 / 摘要 / 周报 / AI 助手共用此模型</p>
                  </div>
                  <span class="zone-chip"><Icon icon="ri:flashlight-line" />DeepSeek · OpenAI 兼容</span>
                </div>
                <div class="model-cards">
                  <div
                    v-for="m in modelOptions"
                    :key="m.value"
                    class="model-card"
                    :class="{ active: form.deepseek_model === m.value }"
                    role="button"
                    @click="form.deepseek_model = m.value"
                  >
                    <div class="mc-top">
                      <span class="mc-icon-box"><Icon :icon="m.icon" class="mc-icon" /></span>
                      <div class="mc-body">
                        <div class="mc-head">
                          <span class="mc-name mono">{{ m.value }}</span>
                          <span v-if="m.badge" class="mc-badge">{{ m.badge }}</span>
                        </div>
                        <div class="mc-desc">{{ m.desc }}</div>
                      </div>
                      <Icon v-if="form.deepseek_model === m.value" icon="ri:checkbox-circle-fill" class="mc-check" />
                    </div>
                    <div class="mc-tags">
                      <span v-for="tag in m.tags" :key="tag">{{ tag }}</span>
                    </div>
                    <div class="mc-foot">
                      <span class="mc-latency"><Icon icon="ri:speed-line" />{{ m.latency }}</span>
                      <span v-if="form.deepseek_model === m.value" class="mc-active">当前使用</span>
                    </div>
                  </div>
                </div>
                <div class="model-note">
                  <Icon icon="ri:information-line" />
                  切换模型只影响后续请求；已生成的需求书与历史摘要不会重新生成。
                </div>
              </section>

              <div class="model-side">
                <section class="ai-panel connection-panel">
                  <div class="settings-section-head">
                    <div>
                      <div class="settings-section-title">连接与密钥</div>
                      <p class="settings-section-desc">密钥仅保存在服务端，读取时始终脱敏</p>
                    </div>
                    <span class="zone-chip" :class="{ ok: keySet }">
                      <Icon :icon="keySet ? 'ri:lock-2-line' : 'ri:lock-unlock-line'" />
                      {{ keySet ? '已配置' : '未配置' }}
                    </span>
                  </div>
                  <el-form-item label="API Key">
                    <el-input
                      v-model="form.deepseek_api_key"
                      type="password"
                      show-password
                      :placeholder="keySet ? '已配置（留空表示不修改）' : 'sk-... 填入后即可使用 AI 生成'"
                    />
                  </el-form-item>
                  <el-form-item label="接口地址">
                    <el-input v-model="form.deepseek_base_url" placeholder="https://api.deepseek.com">
                      <template #prefix><Icon icon="ri:link" /></template>
                    </el-input>
                  </el-form-item>
                  <div class="connection-state" :class="{ ok: keySet }">
                    <span class="cs-dot" />
                    {{ keySet ? '密钥已保存，AI 功能可用' : '尚未配置密钥，AI 生成将回退模板' }}
                  </div>
                </section>

                <section class="ai-panel param-panel">
                  <div class="settings-section-head">
                    <div>
                      <div class="settings-section-title">生成参数</div>
                      <p class="settings-section-desc">控制超时与成本估算</p>
                    </div>
                  </div>
                  <div class="param-grid">
                    <el-form-item label="超时（秒）">
                      <el-input-number
                        v-model="form.deepseek_timeout"
                        :min="30"
                        :max="600"
                        :step="30"
                        controls-position="right"
                        style="width: 100%"
                      />
                    </el-form-item>
                    <el-form-item label="单价（元 / 1K tokens）">
                      <el-input-number
                        v-model="form.ai_price_per_1k"
                        :min="0"
                        :max="1000"
                        :step="0.001"
                        :precision="4"
                        controls-position="right"
                        style="width: 100%"
                      />
                    </el-form-item>
                  </div>
                  <div class="param-presets">
                    <span>常用超时</span>
                    <button v-for="v in [60, 180, 300]" :key="v" type="button" :class="{ active: form.deepseek_timeout === v }" @click="form.deepseek_timeout = v">{{ v }}s</button>
                  </div>
                  <div class="settings-hint">单价用于 Token 统计页的成本估算，不影响实际计费。</div>
                </section>
              </div>

              <div class="model-savebar">
                <span><Icon icon="ri:save-3-line" />保存后新请求立即使用最新配置</span>
                <el-button type="primary" :loading="savingKey === 'ai'" @click="saveSettings('ai')">保存 AI 配置</el-button>
              </div>
            </el-form>
          </el-tab-pane>

          <!-- ===== 区域 2：权限与工具 ===== -->
          <el-tab-pane name="agent">
            <template #label>
              <span class="ai-tab">
                <span class="ai-tab-ic"><Icon icon="ri:shield-user-line" /></span>
                <span class="ai-tab-copy"><b>权限与工具</b><small>知识库 · 工具边界</small></span>
              </span>
            </template>

            <div class="perm-page">
              <section class="ai-panel perm-panel">
                <div class="settings-section-head">
                  <div>
                    <div class="settings-section-title">工具权限 <span class="kh-status">{{ activeRoleLabel }} · {{ checkedCount(activeRole) }}/{{ capsCount(activeRole) }}</span></div>
                    <p class="settings-section-desc">先选择角色，再决定 Bot 在该角色下可以调用哪些工具；带锁的工具属于角色硬上限，无法开启</p>
                  </div>
                  <div class="settings-head-actions">
                    <el-button type="primary" size="small" :loading="savingKey === 'perms'" @click="savePermissions">保存权限</el-button>
                  </div>
                </div>

                <div class="role-switch">
                  <button
                    v-for="r in ROLE_KEYS" :key="r" type="button"
                    class="role-seg" :class="{ active: activeRole === r, custom: !permIsDefault[r] }"
                    @click="activeRole = r"
                  >
                    <span class="rs-icon" :class="r"><Icon :icon="ROLE_ICONS[r]" /></span>
                    <span class="rs-copy">
                      <b>{{ ROLE_LABELS[r] }}</b>
                      <small>{{ permIsDefault[r] ? '系统默认' : '已自定义' }}</small>
                    </span>
                    <span class="rs-count">{{ checkedCount(r) }}<em>/{{ capsCount(r) }}</em></span>
                  </button>
                </div>

                <div class="perm-toolbar">
                  <el-input v-model="toolSearch" class="perm-search" placeholder="搜索工具 / 能力" clearable>
                    <template #prefix><Icon icon="ri:search-line" /></template>
                  </el-input>
                  <div class="perm-actions">
                    <button type="button" class="perm-act" @click="selectAll(activeRole)"><Icon icon="ri:checkbox-multiple-line" />全选</button>
                    <button type="button" class="perm-act" @click="clearRole(activeRole)"><Icon icon="ri:checkbox-blank-line" />清空</button>
                    <button type="button" class="perm-act" @click="restoreRoleDefault(activeRole)"><Icon icon="ri:restart-line" />恢复默认</button>
                    <span class="perm-divider" />
                    <button type="button" class="perm-act" @click="toggleAllGroups">
                      <Icon :icon="allGroupsCollapsed ? 'ri:arrow-down-double-line' : 'ri:arrow-up-double-line'" />{{ allGroupsCollapsed ? '展开' : '收起' }}
                    </button>
                  </div>
                </div>

                <div class="perm-list" v-loading="toolsLoading">
                  <section
                    v-for="g in toolGroups" :key="g.group"
                    class="perm-group" :class="{ open: !collapsedGroups[g.group] }"
                  >
                    <button type="button" class="perm-group-head" @click="toggleGroup(g.group)">
                      <span class="pg-icon" :class="groupTone(g.group)"><Icon :icon="groupIcon(g.group)" /></span>
                      <span class="pg-name">{{ g.group }}</span>
                      <span class="pg-count">{{ groupOn(g.group) }}<em>/{{ g.tools.length }}</em></span>
                      <span class="pg-line" />
                      <Icon :icon="collapsedGroups[g.group] ? 'ri:arrow-down-s-line' : 'ri:arrow-up-s-line'" class="pg-arrow" />
                    </button>

                    <div v-show="!collapsedGroups[g.group]" class="perm-rows">
                      <article
                        v-for="t in g.tools" :key="t.name"
                        class="perm-row" :class="{ locked: !canUse(t, activeRole) }"
                      >
                        <span class="pr-icon" :class="groupTone(g.group)"><Icon :icon="groupIcon(g.group)" /></span>
                        <div class="pr-copy">
                          <div class="pr-title">
                            <b>{{ toolLabel(t) }}</b>
                            <span class="mono pr-key">{{ t.name }}</span>
                            <span v-if="t.sensitive" class="pr-sens"><Icon icon="ri:shield-keyhole-line" />敏感</span>
                          </div>
                          <p class="pr-desc">{{ t.desc }}</p>
                        </div>
                        <div class="pr-control">
                          <el-switch
                            v-if="canUse(t, activeRole)"
                            :model-value="isChecked(activeRole, t.name)"
                            size="small"
                            :aria-label="`${activeRoleLabel} · ${toolLabel(t)}`"
                            @change="(v) => togglePerm(activeRole, t.name, v)"
                          />
                          <span v-else class="pr-locked" title="该角色无此工具权限（硬上限），无法开启">
                            <Icon icon="ri:lock-line" />上限外
                          </span>
                        </div>
                      </article>
                    </div>
                  </section>

                  <EmptyState
                    v-if="!toolGroups.length"
                    compact
                    icon="ri:tools-line"
                    :title="toolsCatalog.length ? '没有匹配的工具' : '工具目录未加载'"
                    :description="toolsCatalog.length ? '换个关键词试试' : '请稍后重试，或检查后端服务是否可用'"
                  />
                </div>
                <div class="perm-footer">
                  <span><Icon icon="ri:information-line" />关闭工具后 Bot 将无法调用对应能力；「恢复默认」保存时写 null，跟随系统默认。</span>
                  <el-button type="primary" size="small" :loading="savingKey === 'perms'" @click="savePermissions">保存权限</el-button>
                </div>
              </section>

              <div class="knowledge-grid">
                <section class="ai-panel knowledge-card">
                  <div class="settings-section-head">
                    <div>
                      <div class="settings-section-title">知识库 <span class="kh-status" :class="{ custom: form.bot_knowledge.trim() }">{{ form.bot_knowledge.trim() ? '自定义' : '内置' }}</span></div>
                      <p class="settings-section-desc">支持 Markdown；留空使用内置默认知识库</p>
                    </div>
                    <div class="settings-head-actions">
                      <el-button text size="small" @click="openBuiltin">
                        <Icon icon="ri:book-open-line" style="margin-right: 4px" />查看内置
                      </el-button>
                      <el-button v-if="form.bot_knowledge.trim()" text size="small" @click="clearKnowledge">清空</el-button>
                      <el-button type="primary" size="small" :loading="savingKey === 'knowledge'" @click="saveKnowledge">保存知识库</el-button>
                    </div>
                  </div>
                  <el-input
                    v-model="form.bot_knowledge"
                    type="textarea"
                    :rows="10"
                    class="mono-area knowledge-area"
                    placeholder="留空使用内置知识库"
                  />
                  <div class="settings-hint">Bot 回答问题、执行操作前都会参考这份知识库；留空则使用内置默认知识库。</div>
                </section>

                <section class="ai-panel prompt-card">
                  <div class="settings-section-head">
                    <div>
                      <div class="settings-section-title">系统提示词前缀 <span class="kh-status" :class="{ custom: form.bot_system_prompt.trim() }">{{ form.bot_system_prompt.trim() ? '自定义' : '默认' }}</span></div>
                      <p class="settings-section-desc">用于微调 Bot 的人设与回答风格</p>
                    </div>
                    <div class="settings-head-actions">
                      <el-button v-if="form.bot_system_prompt.trim()" text size="small" @click="form.bot_system_prompt = ''">清空</el-button>
                      <el-button type="primary" size="small" :loading="savingKey === 'botPrompt'" @click="saveBotPrompt">保存提示词</el-button>
                    </div>
                  </div>
                  <el-input
                    v-model="form.bot_system_prompt"
                    type="textarea"
                    :rows="8"
                    class="prompt-area"
                    placeholder="例如：回答前先确认用户角色；语气保持专业简洁。"
                  />
                  <div class="settings-hint">会拼接在 Bot 内置系统提示词之前；留空不拼接。建议只写 1~3 句风格约束。</div>
                </section>
              </div>
            </div>
          </el-tab-pane>

          <!-- ===== 区域 3：技能 ===== -->
          <el-tab-pane name="skills">
            <template #label>
              <span class="ai-tab">
                <span class="ai-tab-ic"><Icon icon="ri:magic-line" /></span>
                <span class="ai-tab-copy"><b>技能</b><small>提示词与启停</small></span>
              </span>
            </template>

            <div class="skills-page">
              <section class="ai-panel skills-panel">
                <div class="settings-section-head">
                  <div>
                    <div class="settings-section-title">技能编排 <span class="kh-status">{{ enabledSkills }} / {{ skills.length }} 已启用</span></div>
                    <p class="settings-section-desc">关闭技能后对应功能回退为普通模式；自定义提示词可覆写内置提示词（留空使用默认）</p>
                  </div>
                  <div class="settings-head-actions">
                    <el-button type="primary" size="small" :loading="savingKey === 'skills'" @click="saveSkills">保存技能配置</el-button>
                  </div>
                </div>

                <div class="skills-toolbar">
                  <div class="skills-stats">
                    <span><b>{{ enabledSkills }}</b> 已启用</span>
                    <span><b>{{ skills.length - enabledSkills }}</b> 已暂停</span>
                    <span v-if="customSkillCount"><b>{{ customSkillCount }}</b> 个自定义提示词</span>
                  </div>
                  <div class="skills-controls">
                    <el-radio-group v-model="skillFilter" size="small">
                      <el-radio-button value="all">全部</el-radio-button>
                      <el-radio-button value="enabled">已启用</el-radio-button>
                      <el-radio-button value="off">已暂停</el-radio-button>
                    </el-radio-group>
                    <el-button size="small" @click="toggleAllSkills">
                      <Icon :icon="allSkillsEnabled ? 'ri:pause-circle-line' : 'ri:play-circle-line'" />
                      {{ allSkillsEnabled ? '全部暂停' : '全部启用' }}
                    </el-button>
                  </div>
                </div>

                <div class="skill-grid">
                  <div v-for="s in filteredSkills" :key="s.key" class="skill-card" :class="{ off: !s.enabled }">
                    <span class="sk-accent" />
                    <div class="sk-top">
                      <div class="sk-ic"><Icon :icon="s.icon" /></div>
                      <div class="sk-texts">
                        <div class="sk-head">
                          <span class="sk-name">{{ s.name }}</span>
                          <span class="sk-group">{{ s.group }}</span>
                          <span v-if="s.prompt" class="sk-badge">已自定义</span>
                        </div>
                        <div class="sk-desc text-2">{{ s.desc }}</div>
                      </div>
                      <el-switch v-model="s.enabled" size="small" />
                    </div>
                    <div class="sk-prompt" :class="{ custom: s.prompt }">
                      <Icon :icon="s.prompt ? 'ri:quill-pen-line' : 'ri:sparkling-2-line'" />
                      <span>{{ s.prompt || '使用内置提示词' }}</span>
                    </div>
                    <div class="sk-foot">
                      <span class="mono text-2 sk-key">{{ s.key }}</span>
                      <el-button size="small" type="primary" plain @click="openSkillDrawer(s)">
                        <span class="sk-btn-inner"><Icon icon="ri:quill-pen-line" />自定义提示词</span>
                      </el-button>
                    </div>
                  </div>
                </div>
                <EmptyState
                  v-if="!filteredSkills.length"
                  compact
                  icon="ri:magic-line"
                  title="没有符合条件的技能"
                  description="切换筛选条件查看其他技能"
                />
              </section>
            </div>
          </el-tab-pane>

          <!-- ===== 区域 4：Token 用量 ===== -->
          <el-tab-pane name="usage" lazy>
            <template #label>
              <span class="ai-tab">
                <span class="ai-tab-ic"><Icon icon="ri:coins-line" /></span>
                <span class="ai-tab-copy"><b>Token 统计</b><small>用量与成本</small></span>
              </span>
            </template>

            <div class="settings-stack">
              <section class="settings-section">
                <div class="usage-bar">
                  <div>
                    <div class="settings-section-title">用量概览</div>
                    <p class="settings-section-desc">按所选周期统计 AI 调用次数、Token 与估算成本</p>
                  </div>
                  <div class="usage-controls">
                    <el-radio-group v-model="usageDays" size="small">
                      <el-radio-button :value="7">近 7 天</el-radio-button>
                      <el-radio-button :value="30">近 30 天</el-radio-button>
                      <el-radio-button :value="90">近 90 天</el-radio-button>
                    </el-radio-group>
                    <el-button size="small" :loading="usageLoading" @click="loadUsage">
                      <Icon icon="ri:refresh-line" />刷新
                    </el-button>
                  </div>
                </div>

                <div class="stat-grid" v-loading="usageLoading">
                  <StatCard
                    label="总 Tokens"
                    :value="totals.tokens"
                    icon="ri:coins-line"
                    color="var(--brand)"
                    :sub="tokenBreakdown"
                  />
                  <StatCard
                    label="调用次数"
                    :value="totals.calls"
                    icon="ri:pulse-line"
                    color="var(--info)"
                    sub="全部 AI 场景合计"
                  />
                  <StatCard
                    label="估算成本"
                    :value="totals.cost"
                    prefix="¥"
                    :decimals="2"
                    icon="ri:money-cny-circle-line"
                    color="var(--success)"
                    :sub="costSub"
                  />
                  <StatCard
                    label="平均耗时"
                    :value="avgText"
                    icon="ri:timer-line"
                    color="var(--warning)"
                    :sub="avgSub"
                  />
                </div>
              </section>

              <div class="chart-grid">
                <section class="settings-section">
                  <div class="settings-section-head">
                    <div>
                      <div class="settings-section-title">按场景用量</div>
                      <p class="settings-section-desc">各 AI 场景消耗的 Tokens</p>
                    </div>
                  </div>
                  <ChartBox :option="sceneOption" height="260px" :loading="usageLoading" empty-text="暂无用量数据" />
                </section>
                <section class="settings-section">
                  <div class="settings-section-head">
                    <div>
                      <div class="settings-section-title">按天趋势</div>
                      <p class="settings-section-desc">所选周期内的每日 Tokens 趋势</p>
                    </div>
                  </div>
                  <ChartBox :option="dayOption" height="260px" :loading="usageLoading" empty-text="暂无用量数据" />
                </section>
              </div>

              <section class="settings-section">
                <DataTableToolbar :count="usage?.recent?.length || 0" :loading="usageLoading" @refresh="loadUsage">
                  <template #left>
                    <div>
                      <div class="settings-section-title">最近调用明细</div>
                      <p class="settings-section-desc">最多展示 100 条</p>
                    </div>
                  </template>
                </DataTableToolbar>
                <el-table :data="usage?.recent || []" size="small" v-loading="usageLoading">
                  <el-table-column label="场景" width="112">
                    <template #default="{ row }">{{ row.scene }}</template>
                  </el-table-column>
                  <el-table-column label="模型" width="150" show-overflow-tooltip>
                    <template #default="{ row }"><span class="mono text-2">{{ row.model }}</span></template>
                  </el-table-column>
                  <el-table-column label="输入" width="90" align="right">
                    <template #default="{ row }">{{ fmtNum(row.prompt_tokens) }}</template>
                  </el-table-column>
                  <el-table-column label="输出" width="90" align="right">
                    <template #default="{ row }">{{ fmtNum(row.completion_tokens) }}</template>
                  </el-table-column>
                  <el-table-column label="总 Tokens" width="100" align="right">
                    <template #default="{ row }"><b>{{ fmtNum(row.total_tokens) }}</b></template>
                  </el-table-column>
                  <el-table-column label="耗时" width="86">
                    <template #default="{ row }">{{ fmtDuration(row.duration_ms) }}</template>
                  </el-table-column>
                  <el-table-column label="时间" min-width="150">
                    <template #default="{ row }"><span class="text-2">{{ fmtTime(row.created_at) }}</span></template>
                  </el-table-column>
                  <template #empty>
                    <EmptyState
                      compact
                      icon="ri:time-line"
                      title="暂无调用记录"
                      description="AI 调用后这里会显示明细"
                    />
                  </template>
                </el-table>
              </section>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </SettingsShell>

    <!-- 技能自定义提示词抽屉 -->
    <el-drawer v-model="skillDrawer" :title="`自定义提示词：${editing?.name || ''}`" size="560px">
      <div v-if="editing">
        <div class="text-2 skd-meta">
          技能 <span class="mono">{{ editing.key }}</span> · {{ editing.desc }}。留空使用内置默认提示词。
        </div>
        <el-input
          v-model="draftPrompt"
          type="textarea"
          :rows="16"
          class="mono-area"
          placeholder="留空使用内置默认提示词"
        />
      </div>
      <template #footer>
        <el-button @click="skillDrawer = false">取消</el-button>
        <el-button type="primary" :loading="savingKey === 'skills'" @click="confirmSkillDrawer">保存</el-button>
      </template>
    </el-drawer>

    <!-- 内置知识库只读查看（Markdown 渲染，方便对照自定义） -->
    <el-drawer v-model="builtinOpen" title="内置知识库（只读）" size="560px">
      <div v-loading="builtinLoading" class="builtin-md md-readonly" v-html="builtinHtml"></div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { Icon } from '@iconify/vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import http from '../../api'
import ChartBox from '../../components/ChartBox.vue'
import StatCard from '../../components/StatCard.vue'
import DataTableToolbar from '../../components/ui/DataTableToolbar.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import SettingsShell from '../../components/ui/SettingsShell.vue'
import { useThemeStore } from '../../stores/theme'
import {
  ART_COLORS, animCallbacks, artGrid, artTooltip, buildArea, buildBar, catAxis, labelColor, valueAxis,
} from '../../utils/artChart'

const themeStore = useThemeStore()
const loading = ref(false)
const savingKey = ref('')

// ===== 内置知识库只读视图 =====
const builtinOpen = ref(false)
const builtinLoading = ref(false)
const builtinHtml = ref('')
let builtinLoaded = false
async function openBuiltin() {
  builtinOpen.value = true
  if (builtinLoaded) return
  builtinLoading.value = true
  try {
    const data = await http.get('/chat/builtin-knowledge')
    builtinHtml.value = DOMPurify.sanitize(marked.parse(data.knowledge || ''))
    builtinLoaded = true
  } finally {
    builtinLoading.value = false
  }
}
const keySet = ref(false)
const active = ref('model')

function clearKnowledge() {
  form.bot_knowledge = ''
  ElMessage.info('已清空自定义知识库，点击「保存知识库」后生效')
}

const modelOptions = [
  {
    value: 'deepseek-flash', icon: 'ri:flashlight-line', badge: '推荐',
    desc: '快且便宜，生成大文档首选', latency: '低延迟 · 低成本',
    tags: ['大文档生成', '批量摘要', '日常对话'],
  },
  {
    value: 'deepseek-v4-pro', icon: 'ri:rocket-line', badge: '',
    desc: '更强更贵，复杂需求更稳', latency: '高精度 · 高成本',
    tags: ['复杂需求', '长链推理', '质量优先'],
  },
]

const form = reactive({
  deepseek_api_key: '',
  deepseek_base_url: 'https://api.deepseek.com',
  deepseek_model: 'deepseek-flash',
  deepseek_timeout: 180,
  ai_price_per_1k: 0,
  bot_knowledge: '',
  bot_system_prompt: '',
})

// ===== AI 权限矩阵（bot_permissions JSON：{role:[工具名]|null}，null/缺省/空数组 = 用默认；只能在上限内收窄） =====
const ROLE_KEYS = ['admin', 'staff', 'agent']
const ROLE_LABELS = { admin: '管理员', staff: '写手', agent: '代理' }
const ROLE_ICONS = {
  admin: 'ri:shield-star-line',
  staff: 'ri:quill-pen-line',
  agent: 'ri:user-heart-line',
}
const activeRole = ref('admin')
const activeRoleLabel = computed(() => ROLE_LABELS[activeRole.value])
const toolsLoading = ref(false)
const toolsCatalog = ref([]) // [{name,group,desc,caps:[role],sensitive}]，来自 GET /chat/tools
const roleDefaults = reactive({ admin: [], staff: [], agent: [] })
const perm = reactive({ admin: [], staff: [], agent: [] }) // 当前勾选的工具名（已按 caps 裁剪）
const permIsDefault = reactive({ admin: true, staff: true, agent: true }) // 该角色是否处于默认态（保存时写 null）

const toolSearch = ref('')
const toolGroups = computed(() => {
  const groups = []
  const map = new Map()
  const keyword = toolSearch.value.trim().toLowerCase()
  for (const t of toolsCatalog.value) {
    if (keyword) {
      const hay = `${t.name} ${t.desc || ''} ${t.group || ''}`.toLowerCase()
      if (!hay.includes(keyword)) continue
    }
    if (!map.has(t.group)) {
      map.set(t.group, [])
      groups.push(t.group)
    }
    map.get(t.group).push(t)
  }
  return groups.map((g) => ({ group: g, tools: map.get(g) }))
})

const collapsedGroups = reactive({})
const GROUP_ICONS = {
  订单: 'ri:file-list-3-line',
  统计: 'ri:bar-chart-box-line',
  用户: 'ri:user-settings-line',
  协作: 'ri:team-line',
  客户: 'ri:user-heart-line',
  系统: 'ri:settings-3-line',
}
const GROUP_TONES = {
  订单: 'brand',
  统计: 'info',
  用户: 'purple',
  协作: 'success',
  客户: 'warning',
  系统: 'danger',
}
function groupIcon(name) {
  return GROUP_ICONS[name] || 'ri:tools-line'
}
function groupTone(name) {
  return GROUP_TONES[name] || 'brand'
}
function toggleGroup(name) {
  collapsedGroups[name] = !collapsedGroups[name]
}
const allGroupsCollapsed = computed(
  () => toolGroups.value.length > 0 && toolGroups.value.every((g) => collapsedGroups[g.group])
)
function toggleAllGroups() {
  const next = !allGroupsCollapsed.value
  for (const g of toolGroups.value) collapsedGroups[g.group] = next
}

function capsOf(role) {
  return toolsCatalog.value.filter((t) => (t.caps || []).includes(role)).map((t) => t.name)
}
function capsCount(role) {
  return capsOf(role).length
}
function checkedCount(role) {
  const caps = new Set(capsOf(role))
  return perm[role].filter((n) => caps.has(n)).length
}
function canUse(t, role) {
  return (t.caps || []).includes(role)
}
function isChecked(role, name) {
  return perm[role].includes(name)
}
function togglePerm(role, name, v) {
  permIsDefault[role] = false
  const i = perm[role].indexOf(name)
  if (v && i === -1) perm[role].push(name)
  if (!v && i !== -1) perm[role].splice(i, 1)
}
function selectAll(role) {
  permIsDefault[role] = false
  perm[role] = capsOf(role)
}
function clearRole(role) {
  permIsDefault[role] = false
  perm[role] = []
}
function groupOn(name) {
  const group = toolGroups.value.find((g) => g.group === name)
  if (!group) return 0
  const role = activeRole.value
  return group.tools.filter((t) => canUse(t, role) && isChecked(role, t.name)).length
}
function restoreRoleDefault(role) {
  permIsDefault[role] = true // 保存时该角色写 null（而非空数组），后端回退默认
  const caps = new Set(capsOf(role))
  perm[role] = (roleDefaults[role] || []).filter((n) => caps.has(n))
}
// 目录只给 key（如 query_orders）与整句 desc，取 desc 首个短句做展示名
function toolLabel(t) {
  const seg = String(t.desc || '').split(/[（(。：:；;]/)[0].trim()
  return seg && seg.length >= 2 ? seg.slice(0, 16) : t.name
}

function applyToolsData(data, savedPerms) {
  toolsCatalog.value = data.catalog || []
  const rd = data.role_defaults || {}
  for (const r of ROLE_KEYS) roleDefaults[r] = Array.isArray(rd[r]) ? rd[r] : []
  for (const r of ROLE_KEYS) {
    const caps = new Set(capsOf(r))
    const v = savedPerms ? savedPerms[r] : undefined
    if (Array.isArray(v)) {
      // 已配置：按数组勾选（仅在 caps 内；越界项忽略——后端同样只收窄不放权）
      permIsDefault[r] = false
      perm[r] = [...new Set(v)].filter((n) => caps.has(n))
    } else if (savedPerms) {
      // 显式 null / 缺省：跟随默认
      permIsDefault[r] = true
      perm[r] = roleDefaults[r].filter((n) => caps.has(n))
    } else {
      // 无保存配置 / 首次加载：使用该角色的系统默认勾选
      permIsDefault[r] = true
      perm[r] = roleDefaults[r].filter((n) => caps.has(n))
    }
  }
}

async function loadToolMatrix(savedPerms) {
  toolsLoading.value = true
  try {
    const data = await http.get('/chat/tools')
    applyToolsData(data, savedPerms)
  } catch {
    toolsCatalog.value = [] // 拦截器已提示
  } finally {
    toolsLoading.value = false
  }
}

// ===== 技能（bot_skills JSON：[{key,enabled,prompt}]，未配置的 key 用默认） =====
const SKILL_DEFS = [
  { key: 'title_analyze', name: '题目分析', group: '分析', icon: 'ri:lightbulb-line', desc: '建单时推荐项目类型与技术栈' },
  { key: 'order_summary', name: '订单摘要', group: '分析', icon: 'ri:file-text-line', desc: '为订单自动生成智能摘要' },
  { key: 'biz_report', name: '经营周报', group: '分析', icon: 'ri:bar-chart-box-line', desc: '基于真实数据生成经营周报/月报' },
  { key: 'req_diff', name: '差异总结', group: '文档', icon: 'ri:file-copy-2-line', desc: '需求书版本差异 AI 总结' },
  { key: 'docgen', name: '需求书生成', group: '文档', icon: 'ri:file-word-line', desc: '从题目与要求智能生成需求书初稿' },
]
const skills = ref(SKILL_DEFS.map((s) => ({ ...s, enabled: true, prompt: '' })))
const enabledSkills = computed(() => skills.value.filter((s) => s.enabled).length)
const skillFilter = ref('all')
const filteredSkills = computed(() => {
  if (skillFilter.value === 'enabled') return skills.value.filter((s) => s.enabled)
  if (skillFilter.value === 'off') return skills.value.filter((s) => !s.enabled)
  return skills.value
})
const customSkillCount = computed(() => skills.value.filter((s) => s.prompt).length)
const allSkillsEnabled = computed(() => skills.value.every((s) => s.enabled))

function toggleAllSkills() {
  const next = !allSkillsEnabled.value
  skills.value.forEach((s) => { s.enabled = next })
}

// ===== Token 统计 =====
const usage = ref(null)
const usageDays = ref(30)
const usageLoading = ref(false)

const totals = computed(() => {
  const t = usage.value?.totals
  return {
    calls: Number(t?.calls ?? 0),
    tokens: Number(t?.tokens ?? 0),
    prompt: Number(t?.prompt ?? 0),
    completion: Number(t?.completion ?? 0),
    cost: Number(t?.cost ?? 0),
    price_1k: Number(t?.price_1k ?? 0),
  }
})
const avgMs = computed(() => {
  const r = usage.value?.recent || []
  if (!r.length) return null
  return Math.round(r.reduce((a, b) => a + (b.duration_ms || 0), 0) / r.length)
})
const sceneData = computed(() => usage.value?.by_scene || [])
const dayData = computed(() => usage.value?.by_day || [])

function compactNum(n) {
  const value = Number(n || 0)
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 10000) return `${(value / 10000).toFixed(1)}万`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return value.toLocaleString('zh-CN')
}
const heroCost = computed(() => (usage.value ? `¥${Number(totals.value.cost || 0).toFixed(2)}` : '—'))
const usageReady = computed(() => !!usage.value)

function fmtNum(n) {
  return Number(n || 0).toLocaleString('zh-CN')
}
const tokenBreakdown = computed(() => `输入 ${fmtNum(totals.value.prompt)} · 输出 ${fmtNum(totals.value.completion)}`)
const costSub = computed(() =>
  totals.value.price_1k ? `按 ¥${totals.value.price_1k} / 1K tokens 估算` : '未配置单价（模型页可设置）'
)
const avgText = computed(() => fmtDuration(avgMs.value))
const avgSub = computed(() => `最近 ${usage.value?.recent?.length || 0} 次调用`)

const sceneOption = computed(() => {
  void themeStore.isDark // 依赖主题：切换时重建图表配色
  const list = sceneData.value
  return {
    tooltip: artTooltip({ trigger: 'axis', axisPointer: { type: 'shadow' } }),
    grid: artGrid({ right: 52, top: 8, bottom: 0 }),
    xAxis: valueAxis(),
    yAxis: catAxis(list.map((s) => s.scene), { inverse: true }),
    series: [{
      type: 'bar',
      name: 'Tokens',
      barMaxWidth: 14,
      data: list.map((s) => s.tokens),
      itemStyle: { borderRadius: [0, 4, 4, 0], color: buildBar(ART_COLORS[0]) },
      label: { show: true, position: 'right', color: labelColor(), fontSize: 11 },
      ...animCallbacks(60),
    }],
  }
})

const dayOption = computed(() => {
  void themeStore.isDark // 依赖主题：切换时重建图表配色
  const list = dayData.value
  return {
    tooltip: artTooltip({ trigger: 'axis' }),
    grid: artGrid({ right: 14, top: 20, bottom: 0 }),
    xAxis: catAxis(list.map((d) => d.day)),
    yAxis: valueAxis(),
    series: [{
      type: 'line',
      name: 'Tokens',
      smooth: true,
      symbolSize: 4,
      data: list.map((d) => d.tokens),
      lineStyle: { width: 2, color: ART_COLORS[3] },
      itemStyle: { color: ART_COLORS[3] },
      areaStyle: { color: buildArea(ART_COLORS[3]) },
      ...animCallbacks(40),
    }],
  }
})

function fmtDuration(ms) {
  if (ms == null) return '—'
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}
function fmtTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '—'
}

function parseJsonArray(raw) {
  try {
    const v = JSON.parse(raw)
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}

onMounted(() => {
  load()
  loadUsage()
})

async function load() {
  loading.value = true
  try {
    const s = await http.get('/settings')
    const st = s.settings
    keySet.value = !!st.deepseek_key_set
    Object.assign(form, {
      deepseek_api_key: '',
      deepseek_base_url: st.deepseek_base_url,
      deepseek_model: st.deepseek_model,
      deepseek_timeout: Number(st.deepseek_timeout),
      ai_price_per_1k: Number(st.ai_price_per_1k || 0),
      bot_knowledge: st.bot_knowledge || '',
      bot_system_prompt: st.bot_system_prompt || '',
    })
    // 权限矩阵：bot_permissions（JSON 对象，未配置/损坏 = 全部按默认勾选）
    let savedPerms = null
    try {
      const p = JSON.parse(st.bot_permissions)
      if (p && typeof p === 'object' && !Array.isArray(p)) savedPerms = p
    } catch {
      savedPerms = null
    }
    await loadToolMatrix(savedPerms)
    // 技能：合并已存配置，未配置的 key 保持默认（enabled=true、prompt=''）
    const savedSkills = parseJsonArray(st.bot_skills).filter((x) => x && typeof x === 'object')
    skills.value = SKILL_DEFS.map((d) => {
      const c = savedSkills.find((x) => x.key === d.key)
      return {
        ...d,
        enabled: c ? c.enabled !== false : true,
        prompt: c && typeof c.prompt === 'string' ? c.prompt : '',
      }
    })
  } finally {
    loading.value = false
  }
}

async function loadUsage() {
  usageLoading.value = true
  try {
    usage.value = await http.get('/stats/ai-usage', { params: { days: usageDays.value } })
  } catch {
    usage.value = null // 拦截器已提示
  } finally {
    usageLoading.value = false
  }
}
watch(usageDays, loadUsage)

async function saveSettings(which) {
  savingKey.value = which
  try {
    const payload = {
      deepseek_base_url: form.deepseek_base_url,
      deepseek_model: form.deepseek_model,
      deepseek_timeout: String(form.deepseek_timeout),
      ai_price_per_1k: String(form.ai_price_per_1k ?? 0),
    }
    if (form.deepseek_api_key) payload.deepseek_api_key = form.deepseek_api_key
    const s = await http.put('/settings', payload)
    keySet.value = !!s.settings.deepseek_key_set
    form.deepseek_api_key = ''
    ElMessage.success('已保存')
  } finally {
    savingKey.value = ''
  }
}

async function saveKnowledge() {
  savingKey.value = 'knowledge'
  try {
    await http.put('/settings', { bot_knowledge: form.bot_knowledge })
    ElMessage.success('知识库已保存')
  } finally {
    savingKey.value = ''
  }
}

async function saveBotPrompt() {
  savingKey.value = 'botPrompt'
  try {
    await http.put('/settings', { bot_system_prompt: form.bot_system_prompt })
    ElMessage.success('系统提示词已保存')
  } finally {
    savingKey.value = ''
  }
}

async function savePermissions() {
  savingKey.value = 'perms'
  try {
    // 全勾（上限内）或处于默认态 → 写 null（等效默认）；未勾满才写数组（可为空数组，后端同样回退默认）
    const payload = {}
    for (const r of ROLE_KEYS) {
      const caps = capsOf(r)
      const checked = caps.filter((n) => perm[r].includes(n))
      payload[r] = (permIsDefault[r] || checked.length === caps.length) ? null : checked
    }
    // 顺带清空旧全局白名单 bot_tools：矩阵是唯一入口，避免遗留的隐藏收窄
    await http.put('/settings', { bot_permissions: JSON.stringify(payload), bot_tools: '' })
    for (const r of ROLE_KEYS) permIsDefault[r] = payload[r] === null
    ElMessage.success('权限矩阵已保存')
    await loadToolMatrix(payload)
  } finally {
    savingKey.value = ''
  }
}

// ===== 技能抽屉 =====
const skillDrawer = ref(false)
const editing = ref(null)
const draftPrompt = ref('')

function openSkillDrawer(s) {
  editing.value = s
  draftPrompt.value = s.prompt || ''
  skillDrawer.value = true
}

async function confirmSkillDrawer() {
  if (editing.value) editing.value.prompt = draftPrompt.value.trim()
  skillDrawer.value = false
  await saveSkills()
}

async function saveSkills() {
  savingKey.value = 'skills'
  try {
    const payload = skills.value.map((s) => ({ key: s.key, name: s.name, enabled: s.enabled, prompt: s.prompt || '' }))
    await http.put('/settings', { bot_skills: JSON.stringify(payload) })
    ElMessage.success('技能配置已保存')
  } finally {
    savingKey.value = ''
  }
}
</script>

<style scoped>
.ai-page { min-width: 0; }

/* ===== AI 状态条 ===== */
.ai-status {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 13px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  line-height: 1.6;
}
.ai-status .iconify { font-size: 15px; flex-shrink: 0; margin-top: 1px; }
.ai-status.ok { background: var(--success-weak); color: var(--success); }
.ai-status.off { background: var(--warning-weak); color: var(--warning); }

/* ===== 四个区域的大标签 ===== */
.ai-tabs :deep(.el-tabs__header) { margin: 0 0 18px; }
.ai-tabs :deep(.el-tabs__nav-wrap::after) { height: 1px; background: var(--border); }
.ai-tabs :deep(.el-tabs__active-bar) { height: 3px; border-radius: 3px; background: var(--brand); }
.ai-tabs :deep(.el-tabs__item) {
  height: 44px;
  padding: 0 16px;
  font-size: 13.5px;
  color: var(--text-2);
  transition: color 0.15s;
}
.ai-tabs :deep(.el-tabs__item:hover) { color: var(--text); }
.ai-tabs :deep(.el-tabs__item.is-active) { color: var(--brand); font-weight: 600; }
.ai-tab { display: inline-flex; align-items: center; gap: 7px; }
.ai-tab .iconify { font-size: 16px; }

/* ===== 区域状态徽标 ===== */
.zone-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  background: var(--card-3);
  border: 1px solid var(--border);
  color: var(--text-2);
  font-size: 11.5px;
  white-space: nowrap;
}
.zone-chip .iconify { font-size: 13px; }
.zone-chip.ok { background: var(--success-weak); color: var(--success); border-color: transparent; }

/* ===== 模型选择卡 ===== */
.model-cards { display: flex; gap: 12px; flex-wrap: wrap; }
.model-card {
  flex: 1 1 280px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  background: var(--card);
  border: 1px solid var(--border);
  transition: background 0.15s, border-color 0.15s;
}
.model-card:hover { background: var(--hover); }
.model-card.active { background: var(--brand-weak); border-color: var(--brand); }
.mc-icon { font-size: 22px; color: var(--text-2); flex-shrink: 0; }
.model-card.active .mc-icon { color: var(--brand); }
.mc-body { min-width: 0; flex: 1; }
.mc-head { display: flex; align-items: center; gap: 8px; }
.mc-name { font-size: 13.5px; font-weight: 600; }
.mc-badge {
  font-size: 10.5px;
  font-weight: 500;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--brand);
  color: var(--text-inverse);
  flex-shrink: 0;
}
.mc-desc { font-size: 12px; color: var(--text-2); margin-top: 3px; line-height: 1.5; }
.mc-check { font-size: 17px; color: var(--brand); flex-shrink: 0; }

/* ===== 模型表单双列 ===== */
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.span-2 { grid-column: 1 / -1; }

/* ===== 等宽文本域（知识库/提示词） ===== */
.mono-area :deep(.el-textarea__inner) {
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.7;
}

/* ===== 内置知识库只读渲染 ===== */
.md-readonly { font-size: 13px; line-height: 1.8; color: var(--text); }
.md-readonly :deep(h1),
.md-readonly :deep(h2) { font-size: 16px; margin: 18px 0 8px; color: var(--brand); }
.md-readonly :deep(h3) { font-size: 14px; margin: 14px 0 6px; }
.md-readonly :deep(p) { margin: 6px 0; }
.md-readonly :deep(ul),
.md-readonly :deep(ol) { padding-left: 20px; margin: 6px 0; }
.md-readonly :deep(li) { margin: 3px 0; }
.md-readonly :deep(code) { background: var(--hover); border-radius: 4px; padding: 1px 5px; font-size: 12px; }
.md-readonly :deep(strong) { color: var(--brand); }
.md-readonly :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 12px 0; }

/* ===== 技能卡 ===== */
.skill-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.skill-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: var(--radius-sm);
  background: var(--card);
  border: 1px solid var(--border);
  transition: opacity 0.15s;
}
.skill-card.off { opacity: 0.55; }
.sk-top { display: flex; align-items: flex-start; gap: 11px; }
.sk-ic {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand-weak);
  color: var(--brand);
  font-size: 17px;
}
.sk-texts { min-width: 0; flex: 1; }
.sk-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sk-name { font-size: 13.5px; font-weight: 600; }
.sk-badge {
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: var(--brand-weak);
  color: var(--brand);
}
.sk-desc { font-size: 12px; margin-top: 3px; line-height: 1.5; }
.sk-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--border);
  padding-top: 10px;
}
.sk-key { font-size: 11px; }
.sk-btn-inner { display: inline-flex; align-items: center; gap: 5px; }
.sk-btn-inner .iconify { font-size: 13px; }

/* ===== 技能抽屉 ===== */
.skd-meta { font-size: 12.5px; line-height: 1.7; margin-bottom: 12px; }

/* ===== Token 统计 ===== */
.usage-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 1100px) {
  .chart-grid { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  .form-grid { grid-template-columns: 1fr; }
  .span-2 { grid-column: auto; }
  .ai-tabs :deep(.el-tabs__item) { height: 40px; padding: 0 11px; font-size: 13px; }
  .ai-tabs :deep(.el-tabs__nav-scroll) { overflow-x: auto; }
  .ai-tab { gap: 6px; }
}
@media (max-width: 700px) {
  .skill-grid { grid-template-columns: 1fr; }
}

/* ============================================================
   v1.15.1 AI 控制台重设计
   ============================================================ */
.ai-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: center;
  padding: 24px 26px;
  overflow: hidden;
  border: 1px solid rgba(120, 150, 255, 0.2);
  border-radius: var(--radius-lg);
  background:
    radial-gradient(680px 220px at 2% -30%, rgba(93, 135, 255, 0.3), transparent 62%),
    radial-gradient(520px 220px at 100% 130%, rgba(180, 141, 243, 0.12), transparent 65%),
    linear-gradient(135deg, #151b30 0%, #101116 58%, #0d1017 100%);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.22);
}
html.light .ai-hero {
  border-color: rgba(93, 135, 255, 0.16);
  background:
    radial-gradient(680px 220px at 2% -30%, rgba(93, 135, 255, 0.2), transparent 62%),
    radial-gradient(520px 220px at 100% 130%, rgba(180, 141, 243, 0.08), transparent 65%),
    linear-gradient(135deg, #eef3ff 0%, #ffffff 58%, #f8f5ff 100%);
  box-shadow: 0 16px 38px rgba(16, 24, 40, 0.07);
}
.ai-hero-grid {
  position: absolute; inset: 0; opacity: 0.3; pointer-events: none;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
  background-size: 30px 30px;
  mask-image: linear-gradient(90deg, #000, transparent 78%);
}
html.light .ai-hero-grid {
  background-image:
    linear-gradient(rgba(16, 24, 40, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(16, 24, 40, 0.05) 1px, transparent 1px);
}
.ai-hero-glow {
  position: absolute; right: 90px; top: -170px; width: 300px; height: 300px;
  border-radius: 50%; background: radial-gradient(circle, rgba(93, 135, 255, 0.24), transparent 62%);
  pointer-events: none;
}
.ai-hero-main { position: relative; z-index: 1; min-width: 0; }
.ai-eyebrow {
  display: flex; align-items: center; gap: 8px;
  font-size: 10.5px; font-weight: 650; letter-spacing: 0.16em;
  color: rgba(255, 255, 255, 0.52);
}
html.light .ai-eyebrow { color: var(--text-3); }
.ai-live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--success); box-shadow: 0 0 12px var(--success); }
.ai-hero-main h2 {
  text-wrap: balance;
  margin: 9px 0 0; font-size: 27px; line-height: 1.3; font-weight: 700;
  letter-spacing: -0.5px; color: #fff;
}
.ai-hero-main h2 em {
  font-style: normal;
  background: linear-gradient(100deg, #8fa9ff, #d6b6ff);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
html.light .ai-hero-main h2 { color: var(--text); }
html.light .ai-hero-main h2 em { background: var(--brand-grad); -webkit-background-clip: text; background-clip: text; }
.ai-hero-main > p { max-width: 590px; margin: 8px 0 0; font-size: 12.5px; line-height: 1.7; color: rgba(255, 255, 255, 0.55); }
html.light .ai-hero-main > p { color: var(--text-2); }
.ai-hero-actions { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; margin-top: 15px; }
.ai-state-pill, .ai-model-pill, .ai-link-btn {
  display: inline-flex; align-items: center; gap: 5px;
  height: 25px; padding: 0 9px; border-radius: 999px;
  font-size: 10.5px; border: 1px solid transparent;
}
.ai-state-pill.ok { color: #5be7cf; background: rgba(19, 222, 185, 0.12); border-color: rgba(19, 222, 185, 0.2); }
.ai-state-pill.off { color: #ffd27a; background: rgba(255, 174, 31, 0.12); border-color: rgba(255, 174, 31, 0.2); }
.ai-model-pill { color: rgba(255, 255, 255, 0.68); background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.1); font-family: var(--font-mono); }
html.light .ai-model-pill { color: var(--text-2); background: var(--card-2); border-color: var(--border); }
.ai-link-btn {
  cursor: pointer; color: rgba(255, 255, 255, 0.62);
  background: transparent; border-color: rgba(255, 255, 255, 0.1);
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.ai-link-btn:hover { color: #fff; border-color: rgba(255, 255, 255, 0.28); background: rgba(255, 255, 255, 0.06); }
html.light .ai-link-btn { color: var(--text-2); border-color: var(--border); }
html.light .ai-link-btn:hover { color: var(--brand); border-color: var(--brand); background: var(--brand-weak); }
.ai-hero-metrics { position: relative; z-index: 1; display: grid; grid-template-columns: repeat(3, 112px); gap: 8px; }
.ahm-item {
  display: flex; flex-direction: column; gap: 2px;
  padding: 10px 12px; min-width: 0;
  border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 11px;
  background: rgba(255, 255, 255, 0.045);
}
html.light .ahm-item { border-color: var(--border); background: rgba(255, 255, 255, 0.72); }
.ahm-item span { font-size: 9.5px; color: rgba(255, 255, 255, 0.46); white-space: nowrap; }
.ahm-item b { font-size: 18px; font-weight: 700; color: #fff; line-height: 1.25; font-variant-numeric: tabular-nums; }
html.light .ahm-item span { color: var(--text-3); }
html.light .ahm-item b { color: var(--text); }

/* Tabs → 控制台模式卡片 */
.ai-tabs :deep(.el-tabs__header) {
  margin: 0 0 16px;
  padding: 5px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--card-2);
}
.ai-tabs :deep(.el-tabs__nav-wrap::after) { display: none; }
.ai-tabs :deep(.el-tabs__active-bar) { display: none; }
.ai-tabs :deep(.el-tabs__nav) { display: flex; gap: 4px; width: 100%; }
.ai-tabs :deep(.el-tabs__item) {
  height: 54px;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0 13px;
  border-radius: 10px;
  line-height: 1.25;
  transition: background 0.18s, color 0.18s;
}
.ai-tabs :deep(.el-tabs__item:hover) { background: var(--hover); }
.ai-tabs :deep(.el-tabs__item.is-active) { background: var(--brand-weak); color: var(--brand); }
.ai-tab { display: inline-flex; align-items: center; gap: 9px; }
.ai-tab-ic {
  width: 34px; height: 34px; flex-shrink: 0; border-radius: 9px;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--card); color: var(--text-3); font-size: 17px;
  border: 1px solid var(--border);
  transition: background 0.18s, color 0.18s, border-color 0.18s;
}
.ai-tabs :deep(.el-tabs__item.is-active) .ai-tab-ic { background: var(--brand); color: #fff; border-color: var(--brand); }
.ai-tab-copy { display: flex; flex-direction: column; align-items: flex-start; }
.ai-tab-copy b { font-size: 12.5px; font-weight: 600; }
.ai-tab-copy small { margin-top: 1px; font-size: 9.5px; font-weight: 400; color: var(--text-3); }
.ai-tabs :deep(.el-tabs__item.is-active) .ai-tab-copy small { color: color-mix(in srgb, var(--brand) 65%, var(--text-3)); }

/* 权限工具条 */
.perm-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.perm-stats { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.perm-stats span {
  padding: 2px 8px; border-radius: 999px;
  background: var(--card); border: 1px solid var(--border);
  font-size: 10.5px; color: var(--text-3);
}
.perm-stats b { color: var(--text); font-weight: 650; }
.perm-search { width: 230px; }

/* 用量周期 */
.usage-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

@media (max-width: 1200px) {
  .ai-hero { grid-template-columns: 1fr; align-items: start; gap: 16px; }
  .ai-hero-metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 800px) {
  .ai-tabs :deep(.el-tabs__nav) { width: max-content; }
  .ai-tabs :deep(.el-tabs__item) { flex: 0 0 auto; }
  .ai-hero { padding: 20px 18px; border-radius: var(--radius); }
  .ai-hero-main h2 { font-size: 23px; }
  .ai-hero-metrics { gap: 6px; }
  .ahm-item { padding: 9px 10px; }
  .ahm-item b { font-size: 16px; }
  .ai-tabs :deep(.el-tabs__nav) { gap: 2px; }
  .ai-tabs :deep(.el-tabs__item) { height: 46px; padding: 0 9px; }
  .ai-tab-ic { width: 28px; height: 28px; font-size: 15px; border-radius: 8px; }
  .ai-tab-copy small { display: none; }
  .perm-search { width: 100%; }
}
@media (max-width: 540px) {
  .ai-hero-metrics { grid-template-columns: 1fr 1fr; }
  .ahm-item:last-child { grid-column: span 2; }
  .ai-hero-actions { gap: 5px; }
  .ai-state-pill, .ai-model-pill, .ai-link-btn { height: 23px; padding: 0 7px; font-size: 9.5px; }
}

/* ============================================================
   v1.15.2 模型 / 权限 / 技能 三个子页重设计
   ============================================================ */
.ai-panel {
  min-width: 0;
  padding: 17px 18px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--card);
}

/* ---- 模型工作台 ---- */
.model-workspace {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.model-workspace .model-panel { width: 100%; }
.model-side {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  gap: 14px;
  align-items: stretch;
  min-width: 0;
}
.model-workspace .model-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.model-workspace .model-card {
  display: block;
  flex: none;
  padding: 13px 14px;
  border-radius: 12px;
  background: var(--card-2);
  border-color: var(--border);
}
.model-workspace .model-card:hover { transform: translateY(-1px); }
.model-workspace .model-card.active { background: var(--brand-weak); border-color: var(--brand); box-shadow: 0 8px 26px rgba(93, 135, 255, 0.1); }
.mc-top { display: flex; align-items: flex-start; gap: 10px; }
.mc-icon-box {
  width: 34px; height: 34px; flex-shrink: 0; border-radius: 9px;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--card); border: 1px solid var(--border); color: var(--text-3);
}
.model-card.active .mc-icon-box { background: var(--brand); border-color: var(--brand); color: #fff; }
.model-workspace .mc-icon { font-size: 17px; }
.model-workspace .mc-body { flex: 1; min-width: 0; }
.model-workspace .mc-name { font-size: 12.5px; }
.model-workspace .mc-desc { margin-top: 3px; font-size: 11px; line-height: 1.5; }
.model-workspace .mc-check { font-size: 16px; color: var(--brand); margin-top: 2px; }
.mc-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 11px; }
.mc-tags span {
  padding: 1px 6px; border-radius: 5px;
  background: var(--card); border: 1px solid var(--border);
  color: var(--text-3); font-size: 9px;
}
.model-card.active .mc-tags span { background: var(--brand-weak); border-color: var(--brand-weak-2); color: var(--brand); }
.mc-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 6px;
  margin-top: 9px; padding-top: 8px; border-top: 1px dashed var(--border);
  font-size: 9.5px; color: var(--text-3);
}
.mc-latency { display: inline-flex; align-items: center; gap: 3px; }
.mc-latency .iconify { font-size: 11px; }
.mc-active { color: var(--brand); font-weight: 600; }
.model-note {
  display: flex; align-items: flex-start; gap: 5px; margin-top: 12px;
  font-size: 10.5px; line-height: 1.55; color: var(--text-3);
}
.model-note .iconify { color: var(--brand); font-size: 12px; margin-top: 1px; flex-shrink: 0; }
.connection-panel, .param-panel { display: flex; flex-direction: column; background: var(--card-2); }
.connection-panel .settings-section-head, .param-panel .settings-section-head { margin-bottom: 12px; }
.param-panel .settings-hint { margin-top: auto; padding-top: 12px; }
.connection-state {
  display: flex; align-items: center; gap: 5px;
  margin-top: auto; padding: 7px 9px; border-radius: 7px;
  background: var(--warning-weak); color: var(--warning); font-size: 10.5px;
}
.connection-state.ok { background: var(--success-weak); color: var(--success); }
.cs-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.param-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 10px; }
.param-presets { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-top: 2px; }
.param-presets > span { font-size: 10px; color: var(--text-3); margin-right: 1px; }
.param-presets button {
  padding: 1px 7px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--card); color: var(--text-3); font-size: 9.5px; cursor: pointer;
  transition: all 0.15s;
}
.param-presets button:hover, .param-presets button.active { border-color: var(--brand); color: var(--brand); background: var(--brand-weak); }
.model-savebar {
  display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  padding: 10px 13px; border: 1px solid var(--border); border-radius: 11px;
  background: var(--card-2); color: var(--text-3); font-size: 11px;
}
.model-savebar span { display: inline-flex; align-items: center; gap: 5px; }
.model-savebar .iconify { color: var(--brand); font-size: 13px; }

/* ---- 权限控制台 ---- */
.perm-page { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.perm-panel { background: var(--card-2); }

/* 角色切换 */
.role-switch { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
.role-seg {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 11px;
  border: 1px solid var(--border); border-radius: 10px;
  background: var(--card); color: var(--text);
  text-align: left; cursor: pointer;
  transition: border-color 0.16s, background 0.16s, box-shadow 0.16s;
}
.role-seg:hover { border-color: var(--border-2); }
.role-seg.active { border-color: var(--brand); background: var(--brand-weak); box-shadow: inset 0 0 0 1px var(--brand-weak-2); }
.role-seg.custom .rs-copy small { color: var(--warning); }
.rs-icon {
  width: 28px; height: 28px; flex-shrink: 0; border-radius: 8px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 14px;
}
.rs-icon.admin { color: var(--brand); background: var(--brand-weak); }
.rs-icon.staff { color: var(--success); background: var(--success-weak); }
.rs-icon.agent { color: var(--purple); background: var(--purple-weak); }
.rs-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.rs-copy b { font-size: 12px; font-weight: 650; line-height: 1.35; }
.rs-copy small { margin-top: 1px; font-size: 9px; color: var(--text-3); }
.rs-count { font-size: 13px; font-weight: 700; color: var(--text-2); font-variant-numeric: tabular-nums; }
.rs-count em { font-style: normal; font-size: 9.5px; font-weight: 400; color: var(--text-4); }

/* 工具条 */
.perm-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.perm-search { max-width: 260px; }
.perm-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.perm-act {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 10px; border: 1px solid var(--border); border-radius: 7px;
  background: var(--card); color: var(--text-2); font-size: 10.5px; cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.perm-act:hover { color: var(--brand); border-color: var(--brand); background: var(--brand-weak); }
.perm-act .iconify { font-size: 12px; }
.perm-divider { width: 1px; height: 14px; background: var(--border); margin: 0 1px; }

/* 分组列表 */
.perm-list { display: flex; flex-direction: column; gap: 8px; }
.perm-group { border: 1px solid var(--border); border-radius: 10px; overflow: hidden; background: var(--card); }
.perm-group-head {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 11px; border: 0;
  background: var(--card); color: var(--text-2); text-align: left; cursor: pointer;
}
.perm-group.open .perm-group-head { border-bottom: 1px solid var(--border); }
.perm-group-head:hover { background: var(--hover); }
.pg-icon {
  width: 24px; height: 24px; flex-shrink: 0; border-radius: 7px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 13px;
}
.pg-icon.brand, .pr-icon.brand { color: var(--brand); background: var(--brand-weak); }
.pg-icon.info, .pr-icon.info { color: var(--info); background: var(--info-weak); }
.pg-icon.purple, .pr-icon.purple { color: var(--purple); background: var(--purple-weak); }
.pg-icon.success, .pr-icon.success { color: var(--success); background: var(--success-weak); }
.pg-icon.warning, .pr-icon.warning { color: var(--warning); background: var(--warning-weak); }
.pg-icon.danger, .pr-icon.danger { color: var(--danger); background: var(--danger-weak); }
.pg-name { font-size: 11.5px; font-weight: 650; color: var(--text); }
.pg-count { font-size: 10px; color: var(--text-3); font-variant-numeric: tabular-nums; }
.pg-count em { font-style: normal; color: var(--text-4); font-size: 9px; }
.pg-line { flex: 1; height: 1px; background: var(--border); }
.pg-arrow { font-size: 12px; color: var(--text-4); }

.perm-rows { display: flex; flex-direction: column; }
.perm-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
}
.perm-row:last-child { border-bottom: 0; }
.perm-row:hover { background: var(--hover); }
.pr-icon {
  width: 26px; height: 26px; flex-shrink: 0; border-radius: 7px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 13px;
}
.pr-copy { flex: 1; min-width: 0; }
.pr-title { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pr-title b { font-size: 12px; font-weight: 600; color: var(--text); }
.pr-key { font-size: 9px; color: var(--text-4); }
.pr-sens {
  display: inline-flex; align-items: center; gap: 2px;
  padding: 0 5px; border-radius: 999px;
  color: var(--warning); background: var(--warning-weak);
  font-size: 8.5px; line-height: 15px;
}
.pr-sens .iconify { font-size: 9px; }
.pr-desc {
  margin: 2px 0 0; font-size: 10.5px; line-height: 1.45; color: var(--text-3);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pr-control {
  width: 72px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: flex-end;
}
.pr-locked { display: inline-flex; align-items: center; gap: 3px; font-size: 9.5px; color: var(--text-4); }
.pr-locked .iconify { font-size: 10px; }
.perm-row.locked .pr-icon { opacity: 0.55; }
.perm-row.locked .pr-title b { color: var(--text-3); }
.perm-row.locked .pr-desc { color: var(--text-4); }

.perm-footer {
  display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border);
  color: var(--text-3); font-size: 10.5px; line-height: 1.5;
}
.perm-footer span { display: inline-flex; align-items: center; gap: 4px; }
.perm-footer .iconify { color: var(--brand); font-size: 12px; flex-shrink: 0; }

.knowledge-grid { display: grid; grid-template-columns: 1.35fr 0.9fr; gap: 14px; align-items: stretch; }
.knowledge-card, .prompt-card { display: flex; flex-direction: column; background: var(--card-2); }
.knowledge-card .settings-section-head, .prompt-card .settings-section-head { margin-bottom: 10px; }
.knowledge-area :deep(.el-textarea__inner),
.prompt-area :deep(.el-textarea__inner) { min-height: 228px; resize: vertical; }
.kh-status {
  display: inline-flex; align-items: center; margin-left: 5px; padding: 0 6px;
  font-size: 9px; font-weight: 500; line-height: 17px; vertical-align: 1px;
  color: var(--text-3); background: var(--card); border: 1px solid var(--border);
  border-radius: 999px;
}
.kh-status.custom { color: var(--brand); background: var(--brand-weak); border-color: var(--brand-weak-2); }

@media (max-width: 900px) {
  .perm-toolbar { align-items: stretch; }
  .perm-search { max-width: none; width: 100%; }
  .perm-actions { width: 100%; }
}
@media (max-width: 640px) {
  .role-switch { gap: 5px; }
  .role-seg { padding: 8px 7px; gap: 5px; }
  .rs-icon { display: none; }
  .rs-copy b { font-size: 11px; }
  .rs-copy small { font-size: 8px; }
  .rs-count { font-size: 11.5px; }
  .perm-act { flex: 1; justify-content: center; }
  .perm-divider { display: none; }
  .pr-control { width: 64px; }
  .pr-desc { white-space: normal; display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; }
  .perm-footer .el-button { width: 100%; }
}

/* ---- 技能编排 ---- */
.skills-page { min-width: 0; }
.skills-panel { background: var(--card-2); }
.skills-toolbar {
  display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  margin-bottom: 13px; padding-bottom: 12px; border-bottom: 1px solid var(--border);
}
.skills-stats { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.skills-stats span {
  padding: 2px 8px; border-radius: 999px;
  background: var(--card); border: 1px solid var(--border);
  color: var(--text-3); font-size: 10px;
}
.skills-stats b { color: var(--text); font-weight: 650; }
.skills-controls { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.skills-panel .skill-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.skills-panel .skill-card {
  position: relative; overflow: hidden;
  padding: 14px 15px;
  background: var(--card);
  border-radius: 12px;
  gap: 9px;
}
.skills-panel .skill-card.off { opacity: 0.62; }
.sk-accent { position: absolute; left: 0; top: 14px; bottom: 14px; width: 3px; border-radius: 0 3px 3px 0; background: var(--success); opacity: 0.8; }
.skill-card.off .sk-accent { background: var(--text-4); }
.sk-group {
  padding: 0 6px; font-size: 9px; line-height: 16px;
  color: var(--text-3); background: var(--card-2); border: 1px solid var(--border);
  border-radius: 999px;
}
.sk-prompt {
  display: flex; align-items: flex-start; gap: 5px;
  padding: 7px 9px; border-radius: 7px;
  background: var(--card-2); border: 1px dashed var(--border);
  color: var(--text-3); font-size: 10px; line-height: 1.55;
}
.sk-prompt .iconify { flex-shrink: 0; margin-top: 1px; color: var(--brand); font-size: 11px; }
.sk-prompt span { display: -webkit-box; -webkit-line-clamp: 1; line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
.sk-prompt.custom { color: var(--text-2); border-style: solid; border-color: var(--brand-weak-2); background: var(--brand-weak); }
.skills-panel .sk-foot { padding-top: 8px; }

@media (max-width: 1200px) {
  .model-side { grid-template-columns: 1fr; }
  .knowledge-grid { grid-template-columns: 1fr; }
  .knowledge-area :deep(.el-textarea__inner),
  .prompt-area :deep(.el-textarea__inner) { min-height: 190px; }
}
@media (max-width: 900px) {
  .model-workspace .model-cards { grid-template-columns: 1fr; }
  .skills-panel .skill-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .ai-panel { padding: 14px; }
  .param-grid { grid-template-columns: 1fr; }
  .perm-panel .settings-head-actions { width: 100%; }
  .perm-panel .settings-head-actions .el-button { width: 100%; }
  .model-savebar { align-items: flex-start; flex-direction: column; }
  .model-savebar .el-button { width: 100%; }
  .skills-toolbar { align-items: flex-start; flex-direction: column; }
  .skills-controls { width: 100%; }
  .skills-controls .el-radio-group { flex: 1; }
  .skills-controls .el-radio-button { flex: 1; }
  .skills-controls .el-radio-button :deep(.el-radio-button__inner) { width: 100%; }
  .skills-controls .el-button { flex-shrink: 0; }
}
</style>
