/**
 * 日志查看页筛选状态类型（features/logs；17_配置运维.md §4.2）。
 * 页面本地态（与 algorithm-config 同款口径，URL 化留待接线）；'all' = 不过滤。
 */

/** 主筛选（日期/分类/模块/标记/算法） */
export type LogFilterState = {
  startTime: string
  endTime: string
  /** 'all' | 'system' | 'test' | 'error' */
  category: string
  /** 'all' | 'api' | 'e2e' | 'device' */
  module: string
  /** 'all' | 'yellow' | 'red' | 'green' | 'blue' */
  mark: string
  /** 'all' | 算法 type（与全局切换器联动 §2.2） */
  algorithmType: string
}

/** 高级过滤（折叠区） */
export type LogAdvancedState = {
  deviceId: string
  taskId: string
  evaluationId: string
  userId: string
  threadId: string
  contentInclude: string
  contentExclude: string
}

export const EMPTY_FILTER_STATE: LogFilterState = {
  startTime: '',
  endTime: '',
  category: 'all',
  module: 'all',
  mark: 'all',
  algorithmType: 'all',
}

export const EMPTY_ADVANCED_STATE: LogAdvancedState = {
  deviceId: '',
  taskId: '',
  evaluationId: '',
  userId: '',
  threadId: '',
  contentInclude: '',
  contentExclude: '',
}

/** 主筛选是否有非默认值（重置钮可用性） */
export function hasActiveFilters(filter: LogFilterState, advanced: LogAdvancedState): boolean {
  return (
    filter.startTime !== '' ||
    filter.endTime !== '' ||
    filter.category !== 'all' ||
    filter.module !== 'all' ||
    filter.mark !== 'all' ||
    filter.algorithmType !== 'all' ||
    advanced.deviceId !== '' ||
    advanced.taskId !== '' ||
    advanced.evaluationId !== '' ||
    advanced.threadId !== '' ||
    advanced.contentInclude !== '' ||
    advanced.contentExclude !== ''
  )
}
