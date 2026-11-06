/**
 * 报告中心 URL 搜索态类型（validateSearch 产物形态，供页面/子组件消费；
 * 类型定义上提 domain（INT-596 P2-5：adapter 不 type-import 特性层），本文件仅 re-export。
 * 避免 routes → features 循环引用，类型独立于此文件）。
 * 口径修正 2026-10-16：取消双页签，单一列表视图；类型/状态均为筛选条件而非页面层级。
 */
export type { ReportsSearch } from '@/domain/models/report-search'
