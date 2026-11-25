<template>
  <el-config-provider :locale="zhCn">
    <router-view v-slot="{ Component }">
      <transition name="page" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </el-config-provider>
</template>

<script setup>
// 组件按需引入后，Element Plus 中文语言包由 config-provider 全局提供
import zhCn from 'element-plus/es/locale/lang/zh-cn'
// 主题由 html.dark/html.light 类 + styles/tokens.css 的语义变量驱动
</script>

<style>
/* 弹层统一约束（过渡动画在 base.css 中） */
.el-dialog { max-width: calc(100vw - 24px); }
.el-drawer { max-width: calc(100vw - 8px); }
.el-dialog .el-dialog__body { max-height: min(72vh, 720px); overflow-y: auto; }

/* 需求书原文直用模式：Markdown 表格渲染样式（深浅色自适应） */
.raw-md-table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
  table-layout: fixed;
  word-break: break-word
}

.raw-md-table th,
.raw-md-table td {
  border: 1px solid var(--el-border-color,#d4d4d8);
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
  line-height: 1.5
}

.raw-md-table th {
  background: var(--el-fill-color-light,#f4f4f5);
  font-weight: 600
}

/* 订单编辑弹窗：原始需求文档 上传替换/清空 小按钮 */
.bs-mini-btn {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  font-size: 12px;
  border: 1px solid var(--el-border-color,#d4d4d8);
  border-radius: 4px;
  background: var(--el-fill-color-blank,#fff);
  color: var(--el-text-color-regular,#444);
  cursor: pointer
}

.bs-mini-btn:hover {
  border-color: var(--el-color-primary,#4361ee);
  color: var(--el-color-primary,#4361ee)
}

/* 创建订单表单：校验错误文字改为占位布局，避免与下方字段标签重叠 */
.oc-main .el-form-item__error {
  position: static;
  padding-top: 2px
}

/* AI 聊天输入区：强制单框（内层输入框永远透明无边框，含旧缓存样式兜底） */
.ci-composer .el-textarea__inner {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 5px 0 !important
}

/* AI 聊天：清空对话按钮 */
.ch-clear {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-3,#9a9aa5);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 16px;
  flex-shrink: 0;
  transition: all .15s
}

.ch-clear:hover {
  color: var(--el-color-primary,#4361ee);
  background: var(--el-fill-color-light,rgba(125,125,150,.12))
}

/* 订单编辑弹窗：原始需求文档工具条（低调文字链样式） */
.bs-req-tools {
  display: flex;
  justify-content: flex-end;
  gap: 14px;
  margin-top: 2px
}

.bs-req-link {
  background: none;
  border: none;
  padding: 0;
  font-size: 12px;
  color: var(--text-3,#8f8f9a);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 3px
}

.bs-req-link:hover {
  color: var(--el-color-primary,#4361ee)
}

/* 原始需求全文文本框：限高滚动，避免撑爆弹窗 */
.el-dialog .el-textarea__inner[maxlength="20000"] {
  height: 104px !important;
  max-height: 104px !important;
  overflow-y: auto;
  resize: vertical
}

/* 工作台所有卡片：内容纵向弹性铺满，消除卡内底部空白 */
.grid-stack-item:not([gs-id="trend"]):not([gs-id="radar"]):not([gs-id="heat"]) .grid-stack-item-content {
  display: flex
}

.grid-stack-item:not([gs-id="trend"]):not([gs-id="radar"]):not([gs-id="heat"]) .dash-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column
}

.grid-stack-item .ov-body,
.grid-stack-item .row-list,
.grid-stack-item .cat-body,
.grid-stack-item .rank-list,
.grid-stack-item .empty-state {
  flex: 1;
  min-height: 0
}

.grid-stack-item .ov-body {
  justify-content: space-between
}

.grid-stack-item .row-list,
.grid-stack-item .rank-list {
  justify-content: space-evenly
}

/* 本月概览紧凑化：适配矮卡（行1 374px） */
.grid-stack-item[gs-id="overview"] .ov-hero {
  margin: 0
}

.grid-stack-item[gs-id="overview"] .ov-number {
  font-size: 30px
}

.grid-stack-item[gs-id="overview"] .ov-mini {
  padding: 6px 8px
}

.grid-stack-item[gs-id="overview"] .ov-mini .mini-value {
  font-size: 17px
}

.grid-stack-item[gs-id="overview"] .ov-gross {
  margin-top: 2px
}

.grid-stack-item[gs-id="overview"] .ov-body {
  gap: 4px
}

.grid-stack-item[gs-id="overview"] .ov-mini-grid {
  gap: 4px
}

.grid-stack-item[gs-id="overview"] .ov-label {
  margin-bottom: 1px
}

.grid-stack-item[gs-id="overview"] .dc-head {
  margin-bottom: 6px
}

/* 本月概览：统计块 2x2 → 1x4 单排，适配矮卡 */
.grid-stack-item[gs-id="overview"] .ov-mini-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px
}

.grid-stack-item[gs-id="overview"] .ov-mini {
  padding: 4px 2px;
  text-align: center
}

.grid-stack-item[gs-id="overview"] .ov-mini .mini-label {
  font-size: 10px
}

.grid-stack-item[gs-id="overview"] .ov-mini .mini-value {
  font-size: 15px
}

/* 订单列表：价格脱敏眼睛按钮（正圆） */
.bs-eye-btn {
  width: 28px !important;
  height: 28px !important;
  padding: 0 !important;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50% !important
}

/* 订单详情：代理确认开工按钮区 */
.sa-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap
}

/* 需求书预览：所有段落允许长单词（路径/代码）换行 */
.dp-p {
  overflow-wrap: anywhere !important;
  word-break: break-word !important
}

.dp-p.mono-struct {
  word-break: break-all !important
}

/* 需求书预览：统一行距（段落/结构/列表视觉一致） */
.dp-p,
.dp-p.mono-struct,
.dp-li {
  line-height: 1.75;
  margin-bottom: 6px
}

.dp-p.mono-struct {
  padding: 0;
  font-size: 12.5px
}

/* 返回顶部按钮 */
.bs-backtop {
  position: fixed;
  right: 24px;
  bottom: 32px;
  z-index: 999;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--el-color-primary,#4361ee);
  color: #fff;
  border: none;
  cursor: pointer;
  display: none;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, .25);
  transition: opacity .2s, transform .2s;
  opacity: 0;
  transform: translateY(8px)
}

.bs-backtop.show {
  display: flex;
  opacity: 1;
  transform: translateY(0)
}

.bs-backtop:hover {
  filter: brightness(1.15)
}

/* 订单列表：来源列按代理稳定着色（按用户名哈希取色），自接单灰色 */
.src-tag {
  display: inline-block;
  max-width: 100%;
  box-sizing: border-box;
  font-weight: 600;
  font-size: 12px;
  line-height: 20px;
  padding: 0 8px;
  border-radius: 10px;
  border: 1px solid;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle
}

.src-tag.agc0 {
  color: #4361ee;
  background: rgba(67, 97, 238, .09);
  border-color: rgba(67, 97, 238, .35)
}

.src-tag.agc1 {
  color: #7c5cff;
  background: rgba(124, 92, 255, .09);
  border-color: rgba(124, 92, 255, .35)
}

.src-tag.agc2 {
  color: #0e9f8e;
  background: rgba(14, 159, 142, .09);
  border-color: rgba(14, 159, 142, .35)
}

.src-tag.agc3 {
  color: #d97706;
  background: rgba(217, 119, 6, .10);
  border-color: rgba(217, 119, 6, .35)
}

.src-tag.agc4 {
  color: #db2777;
  background: rgba(219, 39, 119, .09);
  border-color: rgba(219, 39, 119, .35)
}

.src-tag.agc5 {
  color: #16a34a;
  background: rgba(22, 163, 74, .09);
  border-color: rgba(22, 163, 74, .35)
}

.src-tag.agc6 {
  color: #dc2626;
  background: rgba(220, 38, 38, .08);
  border-color: rgba(220, 38, 38, .35)
}

.src-tag.agc7 {
  color: #0891b2;
  background: rgba(8, 145, 178, .09);
  border-color: rgba(8, 145, 178, .35)
}

.src-tag.self {
  color: #8a919f;
  background: rgba(138, 145, 159, .10);
  border-color: rgba(138, 145, 159, .32)
}
</style>
