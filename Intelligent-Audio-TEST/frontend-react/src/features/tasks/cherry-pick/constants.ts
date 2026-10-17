/**
 * 挑选合并功能域常量（features/tasks/cherry-pick，18_挑选合并交互重设计.md §9 中文文案，INT-600）。
 * 文案红线：站内一律「挑选合并/挑选/加入购物车/购物车/复核/下单/挑选集」，不出现 Cherry-Pick。
 */
import type { CheckoutAction, PickLevel } from '@/domain/models/cherryPick'

/** 四步向导（§5.1） */
export const WIZARD_STEPS = [
  { key: 'pick', label: '挑选', subtitle: '多级勾选执行结果' },
  { key: 'cart', label: '购物车', subtitle: '可继续挑选/移除/另存挑选集' },
  { key: 'review', label: '复核', subtitle: '清单核对 + 可编辑' },
  { key: 'checkout', label: '下单', subtitle: '合并/重新执行/重新评估' },
] as const

export type WizardStepKey = (typeof WIZARD_STEPS)[number]['key']

/** 层级图标（PickTree 节点行，lucide） */
export const PICK_LEVEL_ICONS: Record<PickLevel, string> = {
  task: 'ClipboardList',
  case: 'ListChecks',
  device: 'Smartphone',
  resultType: 'Tag',
}

/** 层级中文（汇总条/确认文案） */
export const PICK_LEVEL_LABELS: Record<PickLevel, string> = {
  task: '任务',
  case: '用例',
  device: '设备',
  resultType: '结果类型',
}

/** 挑选筛选：执行状态（仅终态，§3.4） */
export const PICK_EXECUTION_STATUS_OPTIONS = [
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '执行失败' },
  { value: 'stopped', label: '已停止' },
]

/** 挑选筛选：评估状态（evaluated 实测） */
export const PICK_EVALUATION_STATUS_OPTIONS = [
  { value: 'evaluated', label: '已评估' },
  { value: 'unevaluated', label: '未评估' },
]

/** 挑选筛选：时间范围 */
export const PICK_TIME_RANGE_OPTIONS = [
  { value: 'all', label: '全部时间' },
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
]

/** 合并方式 facet（§2.3/§11-1） */
export const MERGE_TYPE_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'whole', label: '整任务合并' },
  { value: 'picked', label: '结果挑选' },
] as const

export const MERGE_TYPE_LABELS: Record<'whole' | 'picked', string> = {
  whole: '整任务合并',
  picked: '结果挑选',
}

/** 三出口（§5.3） */
export const CHECKOUT_ACTIONS: Array<{
  key: CheckoutAction
  label: string
  description: string
}> = [
  {
    key: 'merge',
    label: '合并生成新任务',
    description: '挑选结果合并为新任务与报告，源任务保持原样',
  },
  {
    key: 'reexecute',
    label: '重新执行',
    description: '按所选结果的用例×设备集合创建重执行任务并启动',
  },
  {
    key: 'reevaluate',
    label: '重新评估',
    description: '对所选结果按来源任务逐个发起重新评估（不重跑执行）',
  },
]

export function getCheckoutActionMeta(key: CheckoutAction) {
  return CHECKOUT_ACTIONS.find((a) => a.key === key) ?? CHECKOUT_ACTIONS[0]
}

/** ISO 时间串 → 「YYYY-MM-DD HH:mm」（复用 tasks/constants 同款轻量格式化） */
export function formatPickDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const normalized = value.replace('T', ' ')
  return normalized.length >= 16 ? normalized.slice(0, 16) : normalized
}
