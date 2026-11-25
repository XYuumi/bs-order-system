/** 订单元数据唯一出口：状态/项目类型/部署状态的颜色与文案。 */
export const STATUS_META = {
  pending: { label: '待开始', color: 'var(--status-pending)', hex: '#9a9aad' },
  in_progress: { label: '制作中', color: 'var(--status-in_progress)', hex: '#ffae1f' },
  completed: { label: '已完成', color: 'var(--status-completed)', hex: '#13deb9' },
  closed: { label: '已结单', color: 'var(--status-closed)', hex: '#5d87ff' },
  after_sale: { label: '售后中', color: 'var(--status-after_sale)', hex: '#ff4d4f' },
  cancelled: { label: '已取消', color: 'var(--status-cancelled)', hex: '#73738c' },
}

export const STATUS_ORDER = ['pending', 'in_progress', 'completed', 'closed', 'after_sale', 'cancelled']

/** 项目类型（唯一分类维度）：纯程序设计 / 纯论文 / 论文+设计；含论文的类型启用论文进度留档。 */
export const PROJECT_TYPE_META = {
  program: { label: '纯程序设计', short: '纯设计', icon: '⌨️', hex: '#5d87ff', hasPaper: false },
  thesis: { label: '纯论文', short: '纯论文', icon: '📑', hex: '#13deb9', hasPaper: true },
  thesis_program: { label: '论文+设计', short: '论文+设计', icon: '📘', hex: '#b48df3', hasPaper: true },
}

export const DEPLOY_META = {
  // hex 供 StatusTag 渲染色块与小圆点；color 供少数直接用 CSS 变量的场景
  undeployed: { label: '未部署', color: 'var(--warning)', hex: '#ffae1f' },
  deployed: { label: '已部署', color: 'var(--success)', hex: '#13deb9' },
  not_required: { label: '无需部署', color: 'var(--text-2)', hex: '#73738c' },
}

export const QUALITY_FALLBACK = { name: '白色', color: '#9ca3af' }

export function statusMeta(status) {
  return STATUS_META[status] || { label: status || '-', color: 'var(--text-3)', hex: '#8f8fa3' }
}

export function projectTypeMeta(projectType) {
  return PROJECT_TYPE_META[projectType]
    || { label: projectType || '未设置', short: '未设置', icon: '📁', hex: '#8f8fa3', hasPaper: false }
}

/** 订单是否启用论文进度（任务书/开题/初稿/终稿留档）。 */
export function hasPaperWorkflow(projectType) {
  return PROJECT_TYPE_META[projectType]?.hasPaper === true
}

export function deployMeta(status) {
  return DEPLOY_META[status] || { label: status || '-', color: 'var(--text-3)', hex: '#8f8fa3' }
}

/** 生产看板的列顺序（只展示生产主链路，已取消单不进看板）。 */
export const BOARD_COLUMNS = ['pending', 'in_progress', 'completed', 'closed', 'after_sale']

/** 订单交付期限的紧迫度：overdue 已逾期 / today 今天到期 / soon 3 天内 / normal。
 *  口径与后端一致：overdue 仅指早于今天（后端提醒用 deadline < today），今天到期不算逾期。 */
export function deadlineState(deadline) {
  if (!deadline) return { key: 'none', label: '', days: null }
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const due = new Date(String(deadline) + 'T00:00:00')
  if (Number.isNaN(due.getTime())) return { key: 'none', label: '', days: null }
  const days = Math.round((due.getTime() - today.getTime()) / 86400000)
  if (days < 0) return { key: 'overdue', label: `逾期 ${-days} 天`, days }
  if (days === 0) return { key: 'today', label: '今天到期', days }
  if (days <= 3) return { key: 'soon', label: `${days} 天后到期`, days }
  return { key: 'normal', label: `${days} 天后到期`, days }
}

