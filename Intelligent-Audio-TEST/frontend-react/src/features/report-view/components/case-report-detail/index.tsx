/**
 * 用例级报告卡片（15_报告域.md §3.5，TestCaseReportDetail 对位——七块复杂结构）。
 * 块一评分指标 / 块二多轮对话结果 / 块三执行结果（含参考数据、用例参数、评估结果、
 * 设备·API 执行结果、时间轴对比、音频时间轴、结果音频）+ 用例描述 + 详细日志。
 * 块一/块三共享轮次 Tab 状态（useCaseRoundTabs）。
 *
 * **INT-1738 §3.5.10 显示设置裁剪**：传入 `display`（区级一份状态）时按「卡片内容」一级开关 +
 * 「评估维度 / 轮次 / 资源」二级选择裁剪；不传（详情 Dialog §4.7）→ 全显七块。
 */
import { FileText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'
import {
  isBlockVisible,
  type CaseDisplaySettings,
} from '@/application/report-view/use-case-display-settings'

import { getDeviceName } from './case-report-utils'
import { MetricTable } from './metric-table'
import { MultiRoundResult } from './multi-round-result'
import { ExecutionResults } from './execution-results'
import { useCaseRoundTabs } from './use-case-round-tabs'

interface CaseReportDetailProps {
  caseItem: ReportCaseItem
  report: ReportDetailData
  /** 区级显示设置（不传 = 全显，详情 Dialog 口径） */
  display?: CaseDisplaySettings
  /** 隐藏全部内容时的「恢复默认」回调（§3.5.10 兜底） */
  onRestoreDisplay?: () => void
}

export function CaseReportDetail({
  caseItem,
  report,
  display,
  onRestoreDisplay,
}: CaseReportDetailProps) {
  const roundState = useCaseRoundTabs(caseItem)
  const settings = display
  const visible = (key: Parameters<typeof isBlockVisible>[1]) =>
    settings ? isBlockVisible(settings, key) : true

  const showMetric = visible('metricTable')
  const showMultiRound = visible('multiRound')
  const showExecution = visible('execution')
  const showDescription = visible('description')
  const showLogs = visible('logs')

  const nothingVisible =
    settings !== undefined &&
    !showMetric &&
    !showMultiRound &&
    !showExecution &&
    !showDescription &&
    !showLogs

  if (nothingVisible) {
    return (
      <div className='bg-muted/40 text-muted-foreground flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2 text-xs'>
        <span>已按显示设置隐藏全部内容</span>
        {onRestoreDisplay && (
          <Button
            variant='outline'
            size='sm'
            className='h-7 px-2 text-xs'
            onClick={onRestoreDisplay}
          >
            恢复默认
          </Button>
        )}
      </div>
    )
  }

  const resourceLogs = (caseItem as ReportCaseItem & { resourceLogs?: Record<string, string> })
    .resourceLogs

  return (
    <div className='space-y-4'>
      {/* 块一：评分指标 */}
      {showMetric && (
        <section className='space-y-1.5'>
          <p className='text-sm font-semibold'>评分指标</p>
          <MetricTable
            caseItem={caseItem}
            report={report}
            roundTabs={roundState.roundTabs}
            activeRoundTab={roundState.activeRoundTab}
            setActiveRoundTab={roundState.setActiveRoundTab}
            currentRoundMetricKeys={roundState.currentRoundMetricKeys}
            display={settings}
          />
        </section>
      )}

      {/* 块二：多轮对话结果 */}
      {showMultiRound && <MultiRoundResult caseItem={caseItem} />}

      {/* 块三：执行结果（子项受「卡片内容 · 执行结果」子开关控制） */}
      {showExecution && (
        <ExecutionResults
          caseItem={caseItem}
          report={report}
          roundTabs={roundState.roundTabs}
          activeRoundTab={roundState.activeRoundTab}
          setActiveRoundTab={roundState.setActiveRoundTab}
          activeRoundTag={roundState.activeRoundTag}
          display={settings}
        />
      )}

      {/* 用例描述 */}
      {showDescription && caseItem.description && (
        <section className='space-y-1.5'>
          <p className='text-sm font-semibold'>用例描述</p>
          <p className='text-muted-foreground text-sm leading-relaxed'>{caseItem.description}</p>
        </section>
      )}

      {/* 详细日志（多资源日志不同时按资源分节，§3.3.7 合并口径） */}
      {showLogs && (
        <section className='space-y-1.5'>
          <p className='flex items-center gap-1.5 text-sm font-semibold'>
            <FileText aria-hidden='true' className='text-muted-foreground size-4' />
            详细日志
          </p>
          {resourceLogs ? (
            <div className='space-y-2'>
              {Object.entries(resourceLogs).map(([resource, logs]) => (
                <div key={resource} className='space-y-1'>
                  <p className='text-muted-foreground text-xs font-medium'>
                    {getDeviceName(resource, report.summary.resource_headers)}
                  </p>
                  <pre className='bg-muted/40 overflow-x-auto rounded-lg border p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap'>
                    {logs || '暂无日志信息'}
                  </pre>
                </div>
              ))}
            </div>
          ) : (
            <pre className='bg-muted/40 overflow-x-auto rounded-lg border p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap'>
              {caseItem.logs ?? '暂无日志信息'}
            </pre>
          )}
        </section>
      )}
    </div>
  )
}
