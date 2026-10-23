/**
 * UI 展示领域模型 —— camelCase
 *
 * Presentation 层视图间复用的展示结构，零依赖。
 */

import type { Log } from './log'

/** Toast 提示消息 */
export interface ToastMessage {
  type: 'success' | 'error' | 'warning' | 'info'
  message: string
}

/** 日志行视图模型：Log + 格式化时间/选中态/展开态（LogView/TaskLogs 共用，消除两处重复定义） */
export interface LogRow extends Log {
  time: string
  /** 列表选中（批量标记/导出用） */
  selected?: boolean
  /** 详情行展开态 */
  isExpanded?: boolean
}

/**
 * 导入导出弹窗导出范围选项（INT-1628）。
 * resource 侧按自身数据口径给出可用范围：disabled 表示当前不可选（如未勾选任何记录），
 * hint 为不可选原因提示，避免弹窗给出无法真实执行的导出范围。
 */
export interface ExportRangeOption {
  value: string
  label: string
  disabled?: boolean
  hint?: string
}
