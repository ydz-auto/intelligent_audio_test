/**
 * 叶表「结果对比」（15_报告域.md §3.3.7，INT-1738）。
 *
 * 三视图共用一张组件，仅行列维度不同：
 * - 行集：用例视图 = 设备/API × result_type（设备名只在首行显示，result_type 作次级 mono 徽章）；
 *   设备视图 = 当前资源的 result_type；结果类型视图 = 当前 result_type 下的设备/API。
 * - 列（依次）：资源（设备视图改「结果类型」、结果类型视图改「设备/API」）｜执行状态｜执行时间｜
 *   每个已选评估维度一列（值按 `all_metrics[].decimal_places`，默认 2；缺值「—」）。
 * - 排序：按资源名升序稳定；「失败」不置顶，以状态徽章区分（§3.3.7）。
 * - 兜底：无结果「该用例暂无执行结果」；有结果无指标「暂无可对比指标」；资源为空「未知设备/未知 API」。
 */
import { ArrowLeftRight, Smartphone } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { ReportMetricConfig, ReportResourceHeader } from '@/domain/models/report'
import type {
  LeafMetricColumn,
  MergedReportCase,
  ReportCaseView,
} from '@/application/report-view/report-case-view-model'
import {
  DEFAULT_RESULT_TYPE,
  buildResultComparisonRows,
  formatMetricCell,
  metricDecimalPlaces,
  resultTypeText,
} from '@/application/report-view/report-case-view-model'
import { getDeviceName } from '../../case-report-detail/case-report-utils'
import { cn } from '@/lib/utils'

export interface ResultComparisonTableProps {
  caseItem: MergedReportCase
  view: ReportCaseView
  /** 设备视图：第 1 层节点资源键 */
  resourceKey?: string
  /** 结果类型视图：第 1 层节点结果类型 */
  resultType?: string
  headers: ReportResourceHeader[]
  allMetrics: ReportMetricConfig[]
  /** 叶表指标列（主维度 × 轮次，由显示设置决定） */
  columns: LeafMetricColumn[]
  /** 显示设置已选资源 / 结果类型（已解析的最终集合；空数组 = 全部取消，见口径 A） */
  selectedResources: string[]
  selectedResultTypes: string[]
  className?: string
}

/**
 * 执行状态 → 中文 + 徽章样式。
 * 后端真实枚举未归一（§10-11）：既有 `completed/failed/…`，也有中文 `成功/失败/警告/…`（报告 395 实测），
 * 两种都按同一语义映射，避免出现原始枚举 / 破折号。
 */
function statusMeta(status?: string): {
  label: string
  variant: 'secondary' | 'destructive' | 'warning'
  className?: string
} {
  switch (status) {
    case 'completed':
    case 'success':
    case '成功':
    case '已完成':
      // Badge 无 success 变体：用语义 token 覆盖 secondary 底色（与 StatusDot 的 bg-success 同源）
      return {
        label: '成功',
        variant: 'secondary',
        className: 'border-success/40 bg-success/10 text-success',
      }
    case 'failed':
    case 'failure':
    case '失败':
    case '执行失败':
      return { label: '失败', variant: 'destructive' }
    case 'warning':
    case '警告':
      return { label: '警告', variant: 'warning' }
    case 'running':
    case 'in-progress':
    case '执行中':
      return { label: '执行中', variant: 'secondary' }
    case 'pending':
    case '排队中':
      return { label: '排队中', variant: 'secondary' }
    case 'skipped':
    case '跳过':
    case '已跳过':
      return { label: '已跳过', variant: 'secondary' }
    default:
      return { label: status || '—', variant: 'secondary' }
  }
}

/** 执行时间（mono YYYY-MM-DD HH:mm；非 ISO 原样） */
function formatStartTime(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function resourceLabel(key: string, headers: ReportResourceHeader[]): string {
  const name = getDeviceName(key, headers)
  if (name && name !== 'default') return name
  const header = headers.find((h) => String(h.key) === key)
  return header?.type === 'api' ? '未知 API' : '未知设备'
}

export function ResultComparisonTable({
  caseItem,
  view,
  resourceKey,
  resultType,
  headers,
  allMetrics,
  columns,
  selectedResources,
  selectedResultTypes,
  className,
}: ResultComparisonTableProps) {
  const rows = buildResultComparisonRows(caseItem, {
    view,
    resourceKey,
    resultType,
    // 当维由视图决定（口径 A）：设备视图行恒为本节点、结果类型视图行恒为本类型，不受显示设置影响
    selectedResources: view === 'case' || view === 'resultType' ? selectedResources : undefined,
    selectedResultTypes: view === 'case' || view === 'resource' ? selectedResultTypes : undefined,
    headers,
  }).sort((a, b) =>
    resourceLabel(String(a.resource ?? ''), headers).localeCompare(
      resourceLabel(String(b.resource ?? ''), headers),
      'zh-CN'
    )
  )

  const firstColumnLabel =
    view === 'resource' ? '结果类型' : view === 'resultType' ? '设备/API' : '资源'
  /** 行区全清（资源 / 结果类型全不选）时给专门兜底文案（§3.5.10 兜底） */
  const noSelection =
    (view === 'resultType' && selectedResources.length === 0) ||
    (view === 'resource' && selectedResultTypes.length === 0)

  return (
    <div className={cn('space-y-1.5', className)}>
      <div className='flex flex-wrap items-center gap-2'>
        <p className='text-sm font-semibold'>结果对比</p>
        {view === 'resource' && resourceKey && (
          <span className='text-muted-foreground text-xs'>{resourceLabel(resourceKey, headers)}</span>
        )}
        {view === 'resultType' && (
          <Badge variant='outline' className='font-mono text-[10px]'>
            {resultTypeText(resultType ?? DEFAULT_RESULT_TYPE)}
          </Badge>
        )}
        {columns.length > 12 && (
          <span className='text-warning text-[11px]'>列较多（{columns.length}），可在显示设置中收窄维度</span>
        )}
      </div>

      {rows.length === 0 ? (
        <div className='text-muted-foreground flex h-16 items-center justify-center rounded-lg border text-xs'>
          {noSelection ? '未选择资源 / 结果类型' : '该用例暂无执行结果'}
        </div>
      ) : (
        <>
          <div className='overflow-x-auto rounded-lg border'>
            <table className='w-full text-sm'>
              <thead>
                <tr className='text-muted-foreground border-b bg-muted/30'>
                  <th className='px-3 py-2 text-left font-medium'>{firstColumnLabel}</th>
                  <th className='px-3 py-2 text-left font-medium'>执行状态</th>
                  <th className='px-3 py-2 text-left font-medium'>执行时间</th>
                  {columns.map((column) => (
                    <th key={column.key} className='px-3 py-2 text-left font-medium whitespace-nowrap'>
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const status = statusMeta(row.status)
                  const showResource =
                    index === 0 || rows[index - 1].resource !== row.resource
                  return (
                    <tr key={row.key} className='hover:bg-muted/30 border-b last:border-0'>
                      <td className='px-3 py-2 text-sm'>
                        <div className='flex items-center gap-1.5'>
                          {view === 'resource' ? (
                            <Badge variant='outline' className='font-mono text-[10px]'>
                              {resultTypeText(row.resultType ?? DEFAULT_RESULT_TYPE)}
                            </Badge>
                          ) : (
                            <>
                              {showResource && (
                                <>
                                  {resourceKind(row.resource, headers) === 'api' ? (
                                    <ArrowLeftRight aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
                                  ) : (
                                    <Smartphone aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
                                  )}
                                  <span className='truncate'>
                                    {resourceLabel(String(row.resource ?? ''), headers)}
                                  </span>
                                </>
                              )}
                              {view === 'case' && row.resultType !== DEFAULT_RESULT_TYPE && (
                                <span className='text-muted-foreground font-mono text-[10px]'>
                                  {resultTypeText(row.resultType)}
                                </span>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                      <td className='px-3 py-2'>
                        <Badge variant={status.variant} className={cn('text-[11px]', status.className)}>
                          {status.label}
                        </Badge>
                      </td>
                      <td className='text-muted-foreground px-3 py-2 font-mono text-xs tabular-nums'>
                        {formatStartTime(row.startTime)}
                      </td>
                      {columns.map((column) => {
                        // 该资源无当前轮次键时回退基础维度名（单轮键无 @overall 后缀，§3.3.7 叶表）
                        const value = column.metricKey
                          ? (row.metrics[column.metricKey] ?? row.metrics[column.base])
                          : undefined
                        return (
                          <td key={column.key} className='px-3 py-2 font-mono text-xs tabular-nums'>
                            {formatMetricCell(
                              value,
                              column.metricKey ? metricDecimalPlaces(column.metricKey, allMetrics) : 2
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {columns.length === 0 && (
            <p className='text-muted-foreground text-xs'>暂无可对比指标</p>
          )}
        </>
      )}
    </div>
  )
}

function resourceKind(key: string | undefined, headers: ReportResourceHeader[]): 'device' | 'api' {
  const header = headers.find((h) => String(h.key) === String(key ?? ''))
  if (header?.type === 'api') return 'api'
  return 'device'
}
