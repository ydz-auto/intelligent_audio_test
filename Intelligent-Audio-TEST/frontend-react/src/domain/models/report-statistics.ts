/**
 * 报告统计分析领域类型（domain 层；15_报告域.md §2.2）。
 * 统计维度枚举由 application/features 共享，避免 application→interfaces 反向依赖。
 */
export type StatisticDimension = 'time' | 'task_type' | 'device_type' | 'metric'
