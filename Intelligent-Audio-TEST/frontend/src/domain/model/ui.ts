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
