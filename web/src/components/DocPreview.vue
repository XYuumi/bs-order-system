<template>
  <div class="doc-preview">
    <!-- 原文直用：按行渲染上传原文，疑似标题的行加标题样式，内容不改 -->
    <template v-if="document?.mode === 'raw'">
      <div class="raw-banner">
        <Icon icon="ri:file-check-line" />
        <span>原文直用 · 未做修改</span>
      </div>
      <template v-for="(block, i) in rawBlocks" :key="i">
        <!-- 原文里的 Markdown 表格按表格渲染，其余行按「疑似标题 / 段落」处理 -->
        <table v-if="block.t === 2" :key="'tb' + i" class="raw-md-table">
          <thead>
            <tr><th v-for="(cell, j) in block.h" :key="j">{{ cell }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, j) in block.r" :key="j"><td v-for="(cell, k) in row" :key="k">{{ cell }}</td></tr>
          </tbody>
        </table>
        <h4 v-else-if="isRawHeading(block.s)" class="dp-h2">{{ block.s }}</h4>
        <p v-else-if="block.s && block.s.trim()" class="dp-p raw-line">{{ block.s }}</p>
      </template>
    </template>

    <div v-for="key in CHAPTER_ORDER" v-else :key="key">
      <template v-if="['goal', 'scope', 'data_scope'].includes(key)">
        <h4 class="dp-h2">{{ headingOf(key) }}</h4>
        <p v-for="(p, i) in c(key).paragraphs || c(key).items" :key="i" class="dp-p">{{ p }}</p>
      </template>

      <template v-else-if="key === 'roles'">
        <h4 class="dp-h2">{{ c(key).heading }}</h4>
        <div v-for="(r, i) in c(key).roles" :key="i">
          <h5 class="dp-h3">3.{{ i + 1 }} {{ r.name }}</h5>
          <p v-for="(pt, j) in r.points" :key="j" class="dp-li">• {{ pt }}</p>
        </div>
      </template>

      <template v-else-if="key === 'scenarios' || key === 'rules'">
        <h4 class="dp-h2">{{ c(key).heading }}</h4>
        <p v-for="(it, i) in c(key).items" :key="i" class="dp-li">{{ i + 1 }}. {{ it }}</p>
      </template>

      <template v-else-if="key === 'functions'">
        <h4 class="dp-h2">{{ c(key).heading }}</h4>
        <div v-for="(g, gi) in c(key).groups" :key="gi">
          <h5 class="dp-h3">5.{{ gi + 1 }} {{ g.name }}</h5>
          <div v-for="(m, mi) in g.modules" :key="mi">
            <h6 class="dp-h4">5.{{ gi + 1 }}.{{ mi + 1 }} {{ m.name }}</h6>
            <p v-for="(pt, j) in m.points" :key="j" class="dp-li">• {{ pt }}</p>
            <p v-if="m.note" class="dp-note">说明：{{ m.note }}</p>
          </div>
        </div>
      </template>

      <template v-else-if="key === 'tech'">
        <h4 class="dp-h2">{{ c(key).heading }}</h4>
        <p class="dp-p" v-if="c(key).intro">{{ c(key).intro }}</p>
        <h5 class="dp-h3">8.1 技术选型</h5>
        <div class="tbl-wrap">
          <table class="dp-table">
            <thead><tr><th>层级</th><th>技术选型</th><th>版本说明</th></tr></thead>
            <tbody><tr v-for="(r, i) in c(key).stack_table" :key="i"><td v-for="(cell, j) in r" :key="j">{{ cell }}</td></tr></tbody>
          </table>
        </div>
        <h5 class="dp-h3">8.2 项目结构</h5>
        <p v-for="(s, i) in c(key).structure" :key="i" class="dp-p mono-struct">{{ s.dir }}：{{ s.desc }}</p>
      </template>

      <template v-else-if="key === 'database'">
        <h4 class="dp-h2">{{ c(key).heading }}</h4>
        <p class="dp-p" v-if="c(key).intro">{{ c(key).intro }}</p>
        <div v-for="(t, i) in c(key).tables" :key="i">
          <h5 class="dp-h3">9.{{ i + 1 }} {{ t.name }}</h5>
          <div class="tbl-wrap">
            <table class="dp-table">
              <thead><tr><th>字段名</th><th>类型</th><th>说明</th></tr></thead>
              <tbody><tr v-for="(r, j) in t.columns" :key="j"><td v-for="(cell, k) in r" :key="k">{{ cell }}</td></tr></tbody>
            </table>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  document: { type: Object, required: true },
})

const CHAPTER_ORDER = ['goal', 'scope', 'roles', 'scenarios', 'functions', 'rules', 'data_scope', 'tech', 'database']
const FALLBACK = {
  goal: '一、项目目标', scope: '二、建设范围', roles: '三、角色定义',
  scenarios: '四、核心业务场景', functions: '五、功能需求', rules: '六、业务规则',
  data_scope: '七、数据范围', tech: '八、技术架构', database: '九、数据库设计（MySQL 8.0）',
}

// 原文直用：与后端 renderer 的标题识别同一套规则，保证预览与导出观感一致
const CN_HEADING = /^(?:[一二三四五六七八九十百]+、|第[一二三四五六七八九十百\d]+[章节部分]|[一二三四五六七八九十]+\s*[、.．])/
const NUM_HEADING = /^\d+(?:\.\d+)*[、.．\s]/

/**
 * 把原文切成「文本行 / 表格」两种块：表头行的下一行是 |---|---| 分隔线即视为表格，
 * 之后连续以竖线开头的行都是表格行；单元格按未被反斜杠转义的竖线切分。
 */
const splitRawBlocks = (text) => {
  const lines = String(text || '').split('\n')
  const blocks = []
  let i = 0
  const cells = (line) => {
    let s = line.trim()
    if (s.startsWith('|')) s = s.slice(1)
    if (s.endsWith('|')) s = s.slice(0, -1)
    const cols = []
    let buf = ''
    let esc = false
    for (const ch of s) {
      if (esc) {
        buf += ch
        esc = false
      } else if (ch === '\\') {
        esc = true
      } else if (ch === '|') {
        cols.push(buf)
        buf = ''
      } else {
        buf += ch
      }
    }
    cols.push(buf)
    return cols.map((col) => col.trim())
  }
  while (i < lines.length) {
    const cur = lines[i].trim()
    if (cur.startsWith('|') && i + 1 < lines.length && /^\|(\s*:?-{2,}:?\s*\|)+$/.test(lines[i + 1].trim())) {
      const header = cells(lines[i])
      i += 2
      const rows = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        const row = cells(lines[i])
        if (row.length > 1 || row[0] !== '') rows.push(row)
        i++
      }
      blocks.push({ t: 2, h: header, r: rows })
    } else {
      blocks.push({ t: 1, s: lines[i] })
      i++
    }
  }
  return blocks
}

const rawBlocks = computed(() => splitRawBlocks(props.document?.raw_text || ''))

function isRawHeading(line) {
  const text = (line || '').trim()
  if (!text || text.length > 40) return false
  if (CN_HEADING.test(text)) return true
  return NUM_HEADING.test(text) && !/[。！？；，,]$/.test(text)
}

function c(key) {
  return props.document?.chapters?.[key] || {}
}
function headingOf(key) {
  return c(key).heading || FALLBACK[key]
}
</script>

<style scoped>
.doc-preview {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 24px;
  margin-top: 14px;
  background: var(--preview-bg);
}
.dp-h2 { font-size: 14.5px; color: var(--preview-accent); margin: 18px 0 8px; }
.dp-h2:first-child { margin-top: 0; }
.dp-h3 { font-size: 13.5px; color: var(--preview-accent); margin: 12px 0 6px; }
.dp-h4 { font-size: 12.8px; color: var(--preview-accent); margin: 10px 0 4px; }
.dp-p { margin: 0 0 8px; line-height: 1.75; color: var(--text); }
.dp-li { margin: 0 0 5px 2px; line-height: 1.7; color: var(--text); }
.dp-note { color: var(--text-3); font-size: 12.5px; margin: 2px 0 8px; }
.raw-banner {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 10px; margin-bottom: 6px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--success) 12%, transparent);
  color: var(--success); font-size: 11.5px; font-weight: 600;
}
.raw-line { white-space: pre-wrap; }
.tbl-wrap { overflow-x: auto; }
.dp-table { border-collapse: collapse; width: 100%; margin: 6px 0 12px; background: var(--card); font-size: 12.5px; }
.dp-table th, .dp-table td { border: 1px solid var(--border-2); padding: 5px 10px; text-align: left; }
.dp-table th { background: #1c1c1f; color: var(--preview-accent); font-weight: 600; }
</style>
