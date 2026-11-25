<template>
  <div class="api-docs page-shell">
    <AppPageHeader
      title="API 对接"
      description="使用代理 / 写手专属 Key 对接外部系统，拉单、交付与回传状态"
      icon="ri:code-s-slash-line"
    >
      <template #badge>
        <span class="base-chip mono">{{ origin }}/api/v1</span>
      </template>
    </AppPageHeader>

    <div class="ad-grid">
      <!-- ===== 左栏：Key + 文档 ===== -->
      <div class="ad-left">
        <!-- 我的 Key -->
        <div v-if="auth.isAgent || auth.isStaffView" class="art-card key-card">
          <div class="key-head">
            <div class="title">
              <h4>我的 API Key</h4>
              <p>请妥善保管，泄露后请立即重置</p>
            </div>
            <div class="key-actions">
              <el-button size="small" @click="copyKey"><Icon icon="ri:file-copy-line" />复制</el-button>
              <el-button size="small" type="danger" @click="resetKey">重置</el-button>
            </div>
          </div>
          <el-input
            v-model="apiKey" class="key-input" type="password" show-password readonly
            placeholder="加载中…"
          />
        </div>
        <el-alert
          v-else type="info" show-icon :closable="false"
          title="代理角色登录本页可查看专属 API Key；以下接口均以代理身份（自己的订单 + 代理价）返回数据。"
        />

        <!-- 接口列表 -->
        <div class="art-card">
          <div class="ep-toolbar">
            <div class="title">
              <h4>接口列表</h4>
              <p>共 {{ endpoints.length }} 个接口，点击展开参数与请求示例</p>
            </div>
            <div class="ep-toolbar-right">
              <span class="text-3 base-url mono">{{ origin }}/api/v1</span>
              <el-button size="small" text @click="expandAll">
                {{ allExpanded ? '收起全部' : '展开全部' }}
              </el-button>
            </div>
          </div>

          <el-collapse v-model="openedKeys" class="ep-collapse">
            <el-collapse-item
              v-for="ep in endpoints" :key="epKey(ep)" :name="epKey(ep)"
            >
              <template #title>
                <span class="method" :class="ep.method.toLowerCase()">{{ ep.method }}</span>
                <code class="ep-path">{{ ep.path }}</code>
                <span class="ep-desc">{{ ep.desc }}</span>
              </template>
              <div class="ep-body">
                <div v-if="ep.params?.length" class="ep-section">
                  <div class="sec-title">参数</div>
                  <div class="tbl-wrap">
                    <table class="param-table">
                      <thead><tr><th>参数</th><th>位置</th><th>必填</th><th>说明</th></tr></thead>
                      <tbody>
                        <tr v-for="p in ep.params" :key="p.name">
                          <td><code>{{ p.name }}</code></td>
                          <td>{{ p.in }}</td>
                          <td>{{ p.required ? '是' : '否' }}</td>
                          <td>{{ p.desc }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
                <div class="ep-section">
                  <div class="sec-title">请求示例</div>
                  <div class="code-wrap">
                    <pre class="code-block">{{ ep.example }}</pre>
                    <el-button class="copy-btn" size="small" text @click.stop="copyExample(ep.example)">
                      <Icon icon="ri:file-copy-line" />复制
                    </el-button>
                  </div>
                </div>
                <el-button size="small" type="primary" plain @click.stop="sendToTester(ep)">
                  <Icon icon="ri:send-plane-line" />在调试器中打开
                </el-button>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!-- 对接说明 + 错误码 -->
        <div class="art-card">
          <div class="title intro-title">
            <h4>对接说明</h4>
          </div>
          <ul class="intro-list">
            <li>所有请求需带请求头 <code>X-API-Key: 你的Key</code>（也支持 <code>Authorization: Bearer 你的Key</code>）。<b>代理与写手角色</b>均可使用。</li>
            <li>基础地址：<code>{{ origin }}/api/v1</code>，所有响应为 JSON（文件下载除外）。</li>
            <li>频率限制：每分钟 120 次，超限返回 <code>429</code>。</li>
            <li>价格字段统一为 <code>agent_price</code>（代理价），不包含真实价字段。</li>
            <li><b>代理</b>：只见自己名下的订单，可建单、下载需求书/交付物；<b>写手</b>：可拉取全部订单、回传制作状态、上传演示视频与交付包（<code>POST /orders/{id}/files</code>，multipart 字段 file/category，category 可选 video/package/doc/other；演示视频、程序包每单各一份，重复上传即替换旧文件，传 replace=0 可保留）。</li>
            <li>订单状态值：<code>pending</code> 待开始 / <code>in_progress</code> 制作中 / <code>completed</code> 已完成 / <code>closed</code> 已结单 / <code>after_sale</code> 售后中 / <code>cancelled</code> 已取消。</li>
            <li>项目类型（project_type）：<code>program</code> 纯程序设计 / <code>thesis</code> 纯论文 / <code>thesis_program</code> 论文+设计；旧参数 category（code/design/thesis）仍兼容并自动映射。管理员可为代理账号勾选 API 可拉取的项目类型，未勾选类型的订单将不可见（写手不受此限制）。</li>
            <li>写手可通过 <code>POST /orders/{id}/status</code> 回传制作状态，系统自动同步、通知代理并记录日志。</li>
          </ul>
          <div class="err-divider"></div>
          <div class="title intro-title">
            <h4>错误码</h4>
          </div>
          <div class="tbl-wrap">
            <table class="param-table">
              <thead><tr><th>状态码</th><th>含义</th></tr></thead>
              <tbody>
                <tr><td><code>401</code></td><td>缺少 / 无效 API Key</td></tr>
                <tr><td><code>403</code></td><td>访问了不属于你的订单</td></tr>
                <tr><td><code>404</code></td><td>订单或资源不存在（如需求书尚未生成）</td></tr>
                <tr><td><code>429</code></td><td>请求过于频繁</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ===== 右栏：常驻调试器 ===== -->
      <div class="ad-right">
        <div class="art-card tester-card">
          <div class="tester-head">
            <div class="title">
              <h4>API 调试</h4>
              <p>用你的 Key 现场验证接口</p>
            </div>
            <span class="ts-badge"><Icon icon="ri:flashlight-line" />Live</span>
          </div>
          <div class="ts-row">
            <el-select v-model="test.method" style="width: 92px">
              <el-option label="GET" value="GET" />
              <el-option label="POST" value="POST" />
            </el-select>
            <el-input v-model="test.path" placeholder="/orders?page_size=5" style="flex: 1" @keyup.enter="runTest" />
          </div>
          <div class="ts-row">
            <el-input v-model="test.body" placeholder="POST 请求体 JSON（GET 留空）" style="flex: 1" />
          </div>
          <el-button class="ts-send" type="primary" :loading="testLoading" @click="runTest">
            <Icon icon="ri:send-plane-line" />发送请求
          </el-button>
          <div class="ts-presets">
            <button
              v-for="p in presets" :key="p.label" class="ts-preset"
              :disabled="p.disabled" :title="p.disabled ? '当前账号暂无可见订单' : p.path"
              @click="applyPreset(p)"
            >{{ p.label }}</button>
          </div>
          <div class="ts-res-head">
            <span :class="['ts-status', testStatus >= 200 && testStatus < 300 ? 'ok' : (testStatus ? 'err' : '')]">{{ testStatus || '—' }}</span>
            <span class="text-3 ts-time" v-if="testTime">{{ testTime }}ms</span>
            <el-button v-if="testResult" size="small" text style="margin-left: auto" @click="copyResult">复制结果</el-button>
          </div>
          <div class="ts-error" v-if="testError">
            <Icon icon="ri:error-warning-line" /><span>{{ testError }}</span>
          </div>
          <div class="ts-result-wrap" :aria-busy="testLoading">
            <div v-if="testLoading" class="ts-loading">
              <Icon icon="ri:loader-4-line" class="spin" /><span>请求中…</span>
            </div>
            <pre class="ts-result">{{ testResult || '点击「发送请求」查看响应…' }}</pre>
          </div>
          <!-- 请求历史 -->
          <div v-if="history.length" class="ts-history">
            <div class="tsh-head">
              <span class="tsh-title"><Icon icon="ri:time-line" /> 最近请求</span>
              <button class="tsh-clear" @click="clearHistory"><Icon icon="ri:delete-bin-line" />清空</button>
            </div>
            <button v-for="(h, i) in history" :key="i" class="tsh-item" @click="replayHistory(h)">
              <span class="tsh-method" :class="h.method.toLowerCase()">{{ h.method }}</span>
              <span class="tsh-path mono">{{ h.path }}</span>
              <span class="tsh-status" :class="h.status >= 200 && h.status < 300 ? 'ok' : 'err'">{{ h.status }}</span>
              <span class="tsh-at">{{ h.at }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { Icon } from '@iconify/vue'
import http from '../api'
import { sensitiveConfirm, withConfirm } from '../utils/sensitive'
import { useAuthStore } from '../stores/auth'
import AppPageHeader from '../components/ui/AppPageHeader.vue'

const auth = useAuthStore()
const apiKey = ref('')
const origin = computed(() => window.location.origin)

// ===== 接口折叠状态（el-collapse） =====
const openedKeys = ref([])
function epKey(ep) {
  return ep.path + ep.method
}
const allExpanded = computed(() => openedKeys.value.length === endpoints.value.length)
function expandAll() {
  openedKeys.value = allExpanded.value
    ? []
    : endpoints.value.map((e) => epKey(e))
}
function sendToTester(ep) {
  test.method = ep.method
  // 文档路径 → 实际调试路径：{id} 等占位符填入真实示例
  test.path = ep.path.replace('/api/v1', '')
  if (test.path.includes('{')) {
    test.path = test.path
      .replace('{id}', sampleOrderId.value || '261018-001')
      .replace('{file_id}', sampleFileId.value || '1')
    ElMessage.info('已填入示例参数，可自行修改')
  }
  const sample = (ep.params || []).find((p) => p.in === 'body')
  test.body = sample ? '{}' : ''
}

const endpoints = computed(() => [
  {
    method: 'GET', path: '/api/v1/qualities', desc: '品质列表（含代理价）',
    example: `curl "${origin.value}/api/v1/qualities" -H "X-API-Key: $你的KEY"`,
  },
  {
    method: 'GET', path: '/api/v1/orders', desc: '我的订单列表（分页）',
    params: [
      { name: 'status', in: 'query', required: false, desc: '按状态过滤：pending / in_progress / completed / closed / after_sale / cancelled' },
      { name: 'keyword', in: 'query', required: false, desc: '按单号或题目模糊搜索' },
      { name: 'page / page_size', in: 'query', required: false, desc: '分页，默认 page=1，page_size=20（最大 100）' },
    ],
    example: `curl "${origin.value}/api/v1/orders?status=in_progress&page=1" -H "X-API-Key: $你的KEY"`,
  },
  {
    method: 'POST', path: '/api/v1/orders', desc: '创建订单（返回单号与代理价）',
    params: [
      { name: 'title', in: 'body', required: true, desc: '论文题目，2~255 字' },
      { name: 'quality_code', in: 'body', required: true, desc: '品质：white / green / blue / purple / orange / red' },
      { name: 'deadline', in: 'body', required: false, desc: '交付期限，格式 YYYY-MM-DD' },
      { name: 'tech_stack', in: 'body', required: false, desc: '技术栈偏好，如 SpringBoot+Vue3' },
      { name: 'remark', in: 'body', required: false, desc: '备注' },
    ],
    example: `curl -X POST "${origin.value}/api/v1/orders" \\
  -H "X-API-Key: $你的KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"title":"基于SpringBoot的图书管理系统设计与实现","quality_code":"green","deadline":"2026-12-20"}'`,
  },
  {
    method: 'GET', path: '/api/v1/orders/{id}', desc: '订单详情',
    params: [{ name: 'id', in: 'path', required: true, desc: '单号，如 261018-001' }],
    example: `curl "${origin.value}/api/v1/orders/261018-001" -H "X-API-Key: $你的KEY"`,
  },
  {
    method: 'GET', path: '/api/v1/orders/{id}/requirement.docx', desc: '下载需求书 Word（未生成时返回 404）',
    params: [{ name: 'id', in: 'path', required: true, desc: '单号' }],
    example: `curl -o 需求书.docx "${origin.value}/api/v1/orders/261018-001/requirement.docx" -H "X-API-Key: $你的KEY"`,
  },
  {
    method: 'GET', path: '/api/v1/orders/{id}/requirement', desc: '获取需求书结构化 JSON（九章，可读取后分段写回）',
    params: [{ name: 'id', in: 'path', required: true, desc: '单号' }],
    example: `curl "${origin.value}/api/v1/orders/261018-001/requirement" -H "X-API-Key: $你的KEY"`,
  },
  {
    method: 'PATCH', path: '/api/v1/orders/{id}/requirement', desc: '分段修改需求书：按章节覆盖，未提交的章节保持原样（免去本地改完再整体上传；修改前自动存历史版本）',
    params: [
      { name: 'id', in: 'path', required: true, desc: '单号' },
      { name: 'chapters', in: 'body', required: true, desc: '要修改的章节对象，键为 goal/scope/roles/scenarios/functions/rules/data_scope/tech/database，值与 GET 返回的结构一致' },
      { name: 'remark', in: 'body', required: false, desc: '版本备注（可选，≤200 字）' },
    ],
    example: `curl -X PATCH "${origin.value}/api/v1/orders/261018-001/requirement" \\
  -H "X-API-Key: $你的KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"chapters":{"goal":{"heading":"一、项目目标","paragraphs":["新的目标描述…"]}},"remark":"调整项目目标"}'`,
  },
  {
    method: 'POST', path: '/api/v1/orders/{id}/requirement/upload', desc: '上传需求书整体替换（大改后回传 / 不走 AI 自行撰写；支持九章 JSON、docx、txt/md）',
    params: [
      { name: 'id', in: 'path', required: true, desc: '单号' },
      { name: 'file', in: 'formData', required: true, desc: 'multipart 文件字段：.json（九章结构，建议先 GET 修改再传）/ .docx / .txt / .md' },
    ],
    example: `curl -X POST "${origin.value}/api/v1/orders/261018-001/requirement/upload" \\
  -H "X-API-Key: $你的KEY" \\
  -F "file=@我的需求书.docx"`,
  },
  {
    method: 'POST', path: '/api/v1/orders/{id}/status', desc: '回传状态（写手同步用）',
    params: [
      { name: 'id', in: 'path', required: true, desc: '单号' },
      { name: 'status', in: 'body', required: true, desc: 'in_progress 开始制作 / completed 已完成' },
      { name: 'note', in: 'body', required: false, desc: '说明（如"代码已写完待测试"），记入日志' },
    ],
    example: `curl -X POST "${origin.value}/api/v1/orders/261018-001/status" \\
  -H "X-API-Key: $你的KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"status":"completed","note":"代码+论文均已完成"}'`,
  },
  {
    method: 'GET', path: '/api/v1/orders/{id}/files', desc: '订单附件列表',
    params: [
      { name: 'id', in: 'path', required: true, desc: '单号' },
      { name: 'category', in: 'query', required: false, desc: 'package 程序包 / video 演示视频 / doc 文档 / other 其他' },
    ],
    example: `curl "${origin.value}/api/v1/orders/261018-001/files?category=video" -H "X-API-Key: $你的KEY"`,
  },
  {
    method: 'GET', path: '/api/v1/files/{file_id}/download', desc: '下载附件（视频支持断点/拖动）',
    params: [{ name: 'file_id', in: 'path', required: true, desc: '附件 ID（来自附件列表）' }],
    example: `curl -o 演示视频.mp4 "${origin.value}/api/v1/files/12/download" -H "X-API-Key: $你的KEY"`,
  },
  {
    method: 'POST', path: '/api/v1/orders/{id}/files', desc: '上传交付物（写手上传演示视频 / 程序包）。演示视频、程序包每单各保留 1 份：再次上传自动替换旧文件，响应 replaced 列出被替换的文件',
    params: [
      { name: 'id', in: 'path', required: true, desc: '单号' },
      { name: 'file', in: 'formData', required: true, desc: 'multipart 文件字段' },
      { name: 'category', in: 'formData', required: false, desc: 'video 演示视频 / package 程序包 / doc 文档 / other 其他' },
      { name: 'replace', in: 'formData', required: false, desc: '可选，仅对 video / package 生效：不传或传 1 = 替换旧文件；传 0 = 保留旧文件，追加为新文件' },
    ],
    example: `curl -X POST "${origin.value}/api/v1/orders/261018-001/files" \\
  -H "X-API-Key: $你的KEY" \\
  -F "file=@演示视频.mp4" -F "category=video"`,
  },
].filter((x) => {
  // 写接口按角色过滤：建单（管理员 / 代理）、回传需求书（所有持 Key 的角色）、其余（管理员 / 写手）
  if (x.method !== 'POST') return true
  if (x.path === '/api/v1/orders') return auth.isAdmin || auth.isAgent
  if (x.path === '/api/v1/orders/{id}/requirement/upload') return true
  return auth.isAdmin || auth.isStaffView
}))

async function copyText(text, tip) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    ElMessage.success(tip)
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}

function copyKey() {
  if (!apiKey.value) return
  copyText(apiKey.value, '已复制到剪贴板')
}

function copyExample(text) {
  copyText(text, '已复制 curl 命令')
}

// ===== API 调试测试器 =====
const test = reactive({ method: 'GET', path: '/orders?page_size=3', body: '' })
const testLoading = ref(false)
const testResult = ref('')
const testStatus = ref(0)
const testTime = ref(0)
const testError = ref('')

// 真实示例 ID（从当前账号可见订单/附件里取，避免"订单不存在"）
const sampleOrderId = ref('')
const sampleFileId = ref('')

// 请求历史（localStorage，最多 8 条）
const HISTORY_KEY = 'api-test-history'
const history = ref([])
try { history.value = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]') } catch { history.value = [] }

function pushHistory(method, path, status) {
  history.value = [{ method, path, status, at: new Date().toLocaleTimeString('zh-CN', { hour12: false }) }, ...history.value].slice(0, 8)
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value)) } catch { /* 忽略 */ }
}
function clearHistory() {
  history.value = []
  try { localStorage.removeItem(HISTORY_KEY) } catch { /* 忽略 */ }
}
function replayHistory(h) {
  test.method = h.method
  test.path = h.path
  test.body = ''
  runTest()
}

const presets = computed(() => [
  { label: '拉取订单', method: 'GET', path: '/orders?page_size=3' },
  { label: '品质列表', method: 'GET', path: '/qualities' },
  { label: '订单详情', method: 'GET', path: `/orders/${sampleOrderId.value || '261018-001'}`, disabled: !sampleOrderId.value },
  { label: '需求书下载', method: 'GET', path: `/orders/${sampleOrderId.value || '261018-001'}/requirement.docx`, disabled: !sampleOrderId.value },
  { label: '附件列表', method: 'GET', path: `/orders/${sampleOrderId.value || '261018-001'}/files`, disabled: !sampleOrderId.value },
  { label: '创建订单', method: 'POST', path: '/orders', body: JSON.stringify({ title: '测试订单-API创建', quality_code: 'white', project_type: 'thesis_program' }, null, 2) },
  // 「回传完成」只给写手看；建单预设对写手隐藏
  auth.isStaffView && !auth.isAgent && {
    label: '回传完成',
    method: 'POST',
    path: `/orders/${sampleOrderId.value || '261018-001'}/status`,
    body: JSON.stringify({ status: 'completed', note: 'API 回传：制作完成' }, null, 2),
  },
].filter((p) => p && !(p.method === 'POST' && p.path === '/orders' && !auth.isAdmin && !auth.isAgent)))

function applyPreset(p) {
  test.method = p.method
  test.path = p.path
  test.body = p.body || ''
}

async function runTest() {
  if (!test.path) return
  if (!apiKey.value) return ElMessage.warning('请先获取 API Key')
  testLoading.value = true
  testResult.value = ''
  testStatus.value = 0
  testTime.value = 0
  testError.value = ''
  const start = Date.now()
  try {
    const url = `/api/v1${test.path.startsWith('/') ? test.path : '/' + test.path}`
    const opts = {
      method: test.method,
      headers: { 'X-API-Key': apiKey.value },
    }
    if (test.method === 'POST' && test.body.trim()) {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = test.body
    }
    const resp = await fetch(url, opts)
    testStatus.value = resp.status
    const contentType = resp.headers.get('content-type') || ''
    if (contentType.includes('json')) {
      const data = await resp.json()
      testResult.value = JSON.stringify(data, null, 2)
    } else if (contentType.includes('document') || contentType.includes('octet-stream')) {
      testResult.value = `（二进制文件，${contentType}）\n状态码: ${resp.status}\n请用浏览器直接访问下载。`
    } else {
      testResult.value = await resp.text()
    }
    if (!resp.ok) testError.value = `请求返回 ${resp.status}${resp.statusText ? ' ' + resp.statusText : ''}`
    pushHistory(test.method, test.path, resp.status)
  } catch (err) {
    testResult.value = `请求失败: ${err.message}`
    testError.value = `网络或请求错误：${err.message}`
    testStatus.value = 0
  } finally {
    testTime.value = Date.now() - start
    testLoading.value = false
  }
}

function copyResult() {
  if (testResult.value) copyText(testResult.value, '已复制响应')
}

async function resetKey() {
  try {
    await ElMessageBox.confirm('重置后旧 Key 立即失效，已对接的系统需要更新 Key，确定？', '重置 API Key', {
      confirmButtonText: '重置',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
    })
  } catch { /* 取消 */ return }
  const pwd = await sensitiveConfirm({ title: '重置 API Key 确认', content: '重置 Key 需要密码二次确认' })
  if (pwd == null) return
  const data = await http.post('/me/api-key/reset', {}, withConfirm(pwd))
  apiKey.value = data.api_key
  ElMessage.success('已重置，请更新到你的对接系统')
}

onMounted(async () => {
  // 示例 ID：取当前账号可见的第一个订单及其附件（避免预设"订单不存在"）
  try {
    const o = await http.get('/orders', { params: { page_size: 1 } })
    const first = o.items?.[0]
    if (first?.id) {
      sampleOrderId.value = first.id
      const d = await http.get(`/orders/${first.id}`)
      const fid = d.order?.files?.[0]?.id
      if (fid) sampleFileId.value = String(fid)
    }
  } catch { /* 忽略 */ }
  if (auth.isAgent || auth.isStaffView) {
    const data = await http.get('/me/api-key')
    apiKey.value = data.api_key
  }
})
</script>

<style scoped>
.api-docs { min-width: 0; }
.base-chip {
  display: inline-flex; align-items: center; height: 24px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--card-2); color: var(--text-3);
  font-size: 11.5px; white-space: nowrap;
}

.ad-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  gap: 14px;
  align-items: start;
  max-width: 100%;
}
.ad-left { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.ad-right { position: sticky; top: 76px; min-width: 0; }

.title h4 { margin: 0; font-size: 15px; font-weight: 600; color: var(--text); }
.title p { margin: 3px 0 0; font-size: 12px; color: var(--text-3); }

.key-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.key-actions { display: flex; gap: 8px; }
.key-input { margin-top: 12px; }
.key-input :deep(.el-input__inner) {
  font-family: var(--font-mono);
  font-size: 13px; letter-spacing: 0.5px; word-break: break-all;
}

/* 接口列表 */
.ep-toolbar { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.ep-toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.base-url { font-size: 11.5px; }
.ep-collapse { border: none; }
.ep-collapse :deep(.el-collapse-item__header) {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  height: auto; min-height: 42px; line-height: 1.5;
  padding: 9px 12px; margin-bottom: 6px;
  background: transparent; color: var(--text);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  transition: border-color 0.15s, background 0.15s;
}
.ep-collapse :deep(.el-collapse-item__header:hover) { border-color: var(--border-3); }
.ep-collapse :deep(.el-collapse-item__header.is-active) {
  border-color: var(--brand); background: var(--brand-weak);
}
.ep-collapse :deep(.el-collapse-item__title) {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  min-width: 0; flex: 1;
}
.ep-collapse :deep(.el-collapse-item__arrow) { color: var(--text-3); }
.ep-collapse :deep(.el-collapse-item__wrap) { background: transparent; border: none; }
.ep-collapse :deep(.el-collapse-item__content) { padding: 2px 12px 14px; color: var(--text); }
.ep-body { min-width: 0; }
.ep-section { margin-bottom: 10px; }

.method {
  padding: 2px 10px; border-radius: var(--radius-xs);
  font-size: 11.5px; font-weight: 700; width: 52px; text-align: center; flex-shrink: 0;
}
.method.get { background: var(--success-weak); color: var(--success); border: 1px solid color-mix(in srgb, var(--success) 30%, transparent); }
.method.post { background: var(--warning-weak); color: var(--warning); border: 1px solid color-mix(in srgb, var(--warning) 30%, transparent); }
.ep-path { font-weight: 600; font-size: 13px; word-break: break-all; color: var(--text); }
.ep-desc { color: var(--text-2); font-size: 12.5px; flex: 1; min-width: 140px; }

.intro-title { margin-bottom: 10px; }
.intro-list { margin: 0; padding-left: 18px; line-height: 2; color: var(--text-2); font-size: 13px; }
.err-divider { height: 1px; background: var(--border); margin: 18px 0; }

code {
  background: var(--brand-weak); color: var(--brand); padding: 1px 6px; border-radius: 5px; font-size: 12px; word-break: break-all;
  font-family: var(--font-mono);
}
.sec-title { font-size: 12.5px; font-weight: 600; color: var(--text-2); margin-bottom: 6px; }
.tbl-wrap { overflow-x: auto; }
.param-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.param-table th, .param-table td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
.param-table th { background: var(--card-2); color: var(--text-2); font-weight: 600; }
.code-wrap { position: relative; }
.copy-btn { position: absolute; top: 8px; right: 8px; color: var(--text-3); }
.copy-btn:hover { color: var(--text); }
.code-block {
  background: var(--code-bg); border: 1px solid var(--code-border); color: var(--text); border-radius: var(--radius); 
  padding: 12px 14px; font-size: 12px; line-height: 1.7;
  overflow-x: auto; margin: 0; white-space: pre;
  font-family: var(--font-mono);
}

/* ===== 右栏调试器 ===== */
.tester-card { display: flex; flex-direction: column; gap: 10px; }
.tester-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.ts-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: var(--success);
  background: var(--success-weak); border: 1px solid color-mix(in srgb, var(--success) 28%, transparent);
  border-radius: var(--radius-pill); padding: 2px 10px;
}
.ts-row { display: flex; gap: 8px; align-items: center; }
.ts-send { width: 100%; }
.ts-presets { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.ts-preset {
  padding: 4px 10px; border-radius: var(--radius-xs); border: 1px solid var(--border);
  background: var(--card-2); color: var(--text-2); font-size: 12px; cursor: pointer;
  transition: all 0.15s;
}
.ts-preset:hover { border-color: var(--brand); color: var(--brand); background: var(--brand-weak); }
.ts-res-head { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.ts-status { font-size: 13px; font-weight: 700; padding: 2px 10px; border-radius: var(--radius-xs); min-width: 40px; text-align: center; }
.ts-status.ok { background: var(--success-weak); color: var(--success); }
.ts-status.err { background: var(--danger-weak); color: var(--danger); }
.ts-time { font-size: 12px; }
.ts-error {
  display: flex; align-items: flex-start; gap: 6px;
  padding: 8px 10px; border-radius: var(--radius-sm);
  background: var(--danger-weak); border: 1px solid color-mix(in srgb, var(--danger) 28%, transparent);
  color: var(--danger); font-size: 12px; line-height: 1.5;
}
.ts-error .iconify { font-size: 15px; flex-shrink: 0; margin-top: 1px; }
.ts-result-wrap { position: relative; }
.ts-loading {
  position: absolute; inset: 0; z-index: 1;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--code-bg) 82%, transparent);
  color: var(--text-2); font-size: 12.5px;
  backdrop-filter: blur(2px);
}
.ts-result {
  margin: 0; padding: 12px;
  background: var(--code-bg); border: 1px solid var(--code-border); border-radius: var(--radius-sm);
  font-size: 11.5px; line-height: 1.6; overflow: auto; min-height: 160px; max-height: 40vh;
  font-family: var(--font-mono); color: var(--text);
  white-space: pre-wrap; word-break: break-all;
}

/* 请求历史 */
.ts-history { display: flex; flex-direction: column; gap: 4px; }
.tsh-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; }
.tsh-title { font-size: 12px; color: var(--text-2); display: inline-flex; align-items: center; gap: 5px; }
.tsh-clear {
  border: none; background: transparent; color: var(--text-3); font-size: 11.5px;
  cursor: pointer; display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; border-radius: 5px;
}
.tsh-clear:hover { color: var(--danger); background: var(--danger-weak); }
.tsh-item {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 8px; border-radius: var(--radius-xs); border: 1px solid var(--border);
  background: var(--card-2); cursor: pointer; transition: border-color 0.15s;
  font-size: 11.5px; color: var(--text-2); text-align: left;
}
.tsh-item:hover { border-color: var(--brand); color: var(--text); }
.tsh-method { font-size: 10px; font-weight: 700; padding: 0 6px; border-radius: 4px; flex-shrink: 0; }
.tsh-method.get { background: var(--success-weak); color: var(--success); }
.tsh-method.post { background: var(--warning-weak); color: var(--warning); }
.tsh-path { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tsh-status { font-weight: 600; flex-shrink: 0; }
.tsh-status.ok { color: var(--success); }
.tsh-status.err { color: var(--danger); }
.tsh-at { color: var(--text-3); font-size: 10.5px; flex-shrink: 0; }
.ts-preset:disabled { opacity: 0.4; cursor: not-allowed; }
.ts-preset:disabled:hover { border-color: var(--border); color: var(--text-2); background: var(--card-2); }

.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 1100px) {
  .ad-grid { grid-template-columns: 1fr; }
  .ad-right { position: static; }
  .ts-result { max-height: 280px; }
}
@media (max-width: 640px) {
  .ep-collapse :deep(.el-collapse-item__header) { gap: 6px; padding: 9px 10px; }
  .ep-collapse :deep(.el-collapse-item__content) { padding: 2px 6px 12px; }
  .ep-desc { flex-basis: 100%; min-width: 0; }
  .ts-row { flex-wrap: wrap; }
  .ts-row :deep(.el-select) { width: 100% !important; }
  .ts-result { max-height: 240px; }
}
</style>
