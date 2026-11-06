/**
 * 运维设置域分区常量（interfaces 层，INT-347 §3.2/§4.7）：
 * 日志维护（保留天数/立即清理 + 归档管理小节）；域门槛 log:manage。
 */
export const OPERATIONS_SECTIONS = [
  { id: 'log-maintenance', title: '日志维护' },
] as const

export type OperationsSectionId = (typeof OPERATIONS_SECTIONS)[number]['id']

export const OPERATIONS_SECTION_IDS = OPERATIONS_SECTIONS.map(
  (s) => s.id
) as [OperationsSectionId, ...OperationsSectionId[]]

export const OPERATIONS_DEFAULT_SECTION = 'log-maintenance'
