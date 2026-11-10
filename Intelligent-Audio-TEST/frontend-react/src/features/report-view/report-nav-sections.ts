/**
 * 报告「本页目录」分区定义（INT-2434）：报告详情页右导航与 HTML 快照导出共用一份。
 *
 * 页面上由 `ReportReadingNav` 渲染；导出产物按同一份 id → 文案映射重建右栏目录，
 * 避免从分区标题反推文案（标题里带「设备 2 · API 0」「共 793 条结果」这类统计），
 * 也避免两处顺序/措辞各写一套。
 */
import type { ReadingNavSection } from './components/report-reading-nav'

/** 动态区块：仅当 summary.tables 非空时 TaskReportPanel 才渲染（§3.3.4），目录须同条件 */
export const COMPARISON_TABLES_SECTION_ID = 'report-comparison-tables'

export const REPORT_READING_NAV: Record<'task' | 'comparison' | 'benchmark', ReadingNavSection[]> = {
  task: [
    { id: 'report-overview', label: '总览' },
    { id: 'report-resource-stats', label: '设备与API' },
    { id: 'report-conclusion', label: '分析结论' },
    { id: COMPARISON_TABLES_SECTION_ID, label: '对比表格' },
    { id: 'report-case-category', label: '用例分组' },
    { id: 'report-case-tag', label: '用例标签' },
    { id: 'report-specific-cases', label: '具体用例' },
    { id: 'report-documents', label: '报告文档' },
  ],
  benchmark: [
    { id: 'report-benchmark-ranking', label: 'Benchmark 排行' },
    { id: 'report-overview', label: '总览' },
    { id: 'report-resource-stats', label: '设备与API' },
    { id: 'report-conclusion', label: '分析结论' },
    { id: COMPARISON_TABLES_SECTION_ID, label: '对比表格' },
    { id: 'report-case-category', label: '用例分组' },
    { id: 'report-case-tag', label: '用例标签' },
    { id: 'report-specific-cases', label: '具体用例' },
    { id: 'report-documents', label: '报告文档' },
  ],
  comparison: [
    { id: 'report-resource-stats', label: '设备与API' },
    { id: 'report-conclusion', label: '分析结论' },
    { id: 'report-case-category', label: '用例分组' },
    { id: 'report-case-tag', label: '用例标签' },
    { id: 'report-specific-cases', label: '具体用例' },
    { id: 'report-documents', label: '报告文档' },
  ],
}

/** 分区 id → 目录文案（三种报告类型合并；同名 id 文案一致） */
const SECTION_LABELS: Record<string, string> = (() => {
  const labels: Record<string, string> = {}
  for (const sections of Object.values(REPORT_READING_NAV)) {
    for (const section of sections) labels[section.id] = section.label
  }
  return labels
})()

/** 目录文案：优先用页面同一份分区定义，未登记的分区返回 undefined（调用方回退到标题） */
export function readingNavLabel(sectionId: string): string | undefined {
  return SECTION_LABELS[sectionId]
}
