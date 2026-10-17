/**
 * 报告展示页 URL 搜索态类型（validateSearch 产物形态；15_报告域.md §2.1 INT-441 双入口拆分）。
 * 类型定义上提 domain（INT-596 P2-5：adapter 不 type-import 特性层），本文件仅 re-export。
 * 展示页仅已发布报告（published），行操作仅「查看/复制链接」；无 tab/收藏/回收站态。
 */
export type { ShowcaseSearch } from '@/domain/models/report-search'
