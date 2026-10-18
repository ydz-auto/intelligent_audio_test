/**
 * 日志查看页常量（interfaces 层；17_配置运维.md §10 文案源 + Vue LogView
 * logView.ts LOGCategoryOptions/LOGModuleOptions/LOGMarkOptions 实测值平移）。
 * 级别 tag 取值大写（后端 LogItem.level 原值）；分类/模块/标记选值 = 后端查询
 * 参数原值（category/module/mark），'all' 表示不过滤。
 */
import type { StatusVariant } from '@/features/dashboard/components/ui/status-badge'

/** 日志级别 tag 选项（大写原值；后端按逗号串过滤） */
export const LOG_LEVEL_OPTIONS = [
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'CRITICAL', label: 'CRITICAL' },
] as const

/** 级别 → StatusBadge 色（§4.4：DEBUG=neutral/INFO=info/WARNING=warning/ERROR·CRITICAL=destructive） */
export const LOG_LEVEL_BADGE_VARIANT: Record<string, StatusVariant> = {
  DEBUG: 'neutral',
  INFO: 'info',
  WARNING: 'warning',
  ERROR: 'danger',
  CRITICAL: 'danger',
}

/** 级别 → 行染浅色 tint（§4.4：ERROR/CRITICAL 行染 rose；照 usage-logs renderRow） */
export const LOG_LEVEL_ROW_TINT: Record<string, string> = {
  ERROR: 'bg-rose-50/40 dark:bg-rose-950/20',
  CRITICAL: 'bg-rose-50/40 dark:bg-rose-950/20',
}

/** 分类选项（后端 category 原值；Vue LogView logView.ts:119） */
export const LOG_CATEGORY_OPTIONS = [
  { value: 'all', label: '所有分类' },
  { value: 'system', label: '系统日志' },
  { value: 'test', label: '测试日志' },
  { value: 'error', label: '错误日志' },
] as const

/** 模块选项（后端 module 原值；Vue logView.ts:120 TestType.API='api'/E2E='e2e'/device） */
export const LOG_MODULE_OPTIONS = [
  { value: 'all', label: '所有模块' },
  { value: 'api', label: 'API模块' },
  { value: 'e2e', label: 'E2E测试' },
  { value: 'device', label: '设备管理' },
] as const

/** 标记筛选选项（后端 mark 原值；Vue logView.ts:121） */
export const LOG_MARK_FILTER_OPTIONS = [
  { value: 'all', label: '所有标记' },
  { value: 'yellow', label: '黄色标记' },
  { value: 'red', label: '红色标记' },
  { value: 'green', label: '绿色标记' },
  { value: 'blue', label: '蓝色标记' },
] as const

/** 视图范围 Tabs（§4.1「全部/仅自己」，log:manage 显；仅自己=请求附 user_id） */
export const LOG_SCOPE_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'mine', label: '仅自己' },
] as const

export type LogScope = (typeof LOG_SCOPE_OPTIONS)[number]['value']

/** 标记颜色选项（§4.5 批量浮条「标记颜色」；mark 值同 LOG_MARK_FILTER_OPTIONS 非 all） */
export const LOG_MARK_COLORS = [
  { value: 'yellow', label: '黄色', swatch: 'bg-yellow-400' },
  { value: 'red', label: '红色', swatch: 'bg-red-500' },
  { value: 'green', label: '绿色', swatch: 'bg-green-500' },
  { value: 'blue', label: '蓝色', swatch: 'bg-blue-500' },
] as const

export const LOG_PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const
export const LOG_DEFAULT_PAGE_SIZE = 20

/** 搜索防抖（§4.2 Enter 应用；300ms 与算法页 ALGORITHM_SEARCH_DEBOUNCE_MS 同档） */
export const LOG_SEARCH_DEBOUNCE_MS = 300
