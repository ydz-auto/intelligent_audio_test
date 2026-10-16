/**
 * 用例级报告卡片（15_报告域.md §3.5，TestCaseReportDetail 对位——七块复杂结构）。
 * 块一评分指标 / 块二多轮对话结果 / 块三执行结果（含参考数据、用例参数、评估结果、
 * 设备·API 执行结果、时间轴对比、音频时间轴、结果音频）+ 用例描述 + 详细日志。
 */
import { FileText } from 'lucide-react'

import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'

import { MetricTable } from './metric-table'
import { MultiRoundResult } from './multi-round-result'
import { ExecutionResults } from './execution-results'

interface CaseReportDetailProps {
  caseItem: ReportCaseItem
  report: ReportDetailData
}

export function CaseReportDetail({ caseItem, report }: CaseReportDetailProps) {
  return (
    <div className='space-y-4'>
      {/* 块一：评分指标 */}
      <section className='space-y-1.5'>
        <p className='text-sm font-semibold'>评分指标</p>
        <MetricTable caseItem={caseItem} report={report} />
      </section>

      {/* 块二：多轮对话结果 */}
      <MultiRoundResult caseItem={caseItem} />

      {/* 块三：执行结果 */}
      <ExecutionResults caseItem={caseItem} report={report} />

      {/* 用例描述 */}
      {caseItem.description && (
        <section className='space-y-1.5'>
          <p className='text-sm font-semibold'>用例描述</p>
          <p className='text-muted-foreground text-sm leading-relaxed'>{caseItem.description}</p>
        </section>
      )}

      {/* 详细日志 */}
      <section className='space-y-1.5'>
        <p className='flex items-center gap-1.5 text-sm font-semibold'>
          <FileText aria-hidden='true' className='text-muted-foreground size-4' />
          详细日志
        </p>
        <pre className='bg-muted/40 overflow-x-auto rounded-lg border p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap'>
          {caseItem.logs ?? '暂无日志信息'}
        </pre>
      </section>
    </div>
  )
}
