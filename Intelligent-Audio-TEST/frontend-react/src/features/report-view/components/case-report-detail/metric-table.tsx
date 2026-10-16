/**
 * 块一：评分指标（15_报告域.md §3.5.1，TestCaseReportDetail 块一对位）。
 * 单设备模式：四列（指标名称/指标数值/得分/详情·错误）+ score 五档徽章 + 长错误可折叠（>50 字）；
 * 对比模式：轮次横向 Tab（@round:N/@overall 提取）+ 主/子维度层级分组表格（每设备一列）。
 * P1-2：轮次 Tab 为真实交互——resourceMetrics 按 @round:N/@overall 分轮次装配，metricValue 读 activeRound。
 * P2-7：得分/错误走数据契约真实字段（ReportMetricValue.score/error + caseItem.metricScore/metricError），不再臆造公式。
 */
import { ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type {
  ReportCaseItem,
  ReportDetailData,
  ReportMetricConfig,
} from '@/domain/models/report'
import { extractCaseResourceMetrics } from '@/application/report-view/case-matrix'
import { cn } from '@/lib/utils'

export function ScoreBadge({ score }: { score?: number }) {
  if (score === undefined) {
    return (
      <Badge variant='secondary' className='font-mono tabular-nums'>
        —
      </Badge>
    )
  }
  const variant =
    score >= 5
      ? 'success'
      : score >= 3
        ? 'warning'
        : score >= 1
          ? 'destructive'
          : 'secondary'
  return (
    <Badge variant={variant as never} className='font-mono tabular-nums'>
      {score}
    </Badge>
  )
}

/** 轮次 Tab 文案 → @round:N 数字（「第1轮」→ '1'；「整体」→ null） */
function roundNumberFromTab(tab: string): string | null {
  const m = tab.match(/^第(\d+)轮$/)
  return m ? m[1] : null
}

export function MetricTable({
  caseItem,
  report,
}: {
  caseItem: ReportCaseItem
  report: ReportDetailData
}) {
  const allMetrics: ReportMetricConfig[] = report.summary.all_metrics
  const resourceMetrics = useMemo(() => extractCaseResourceMetrics(caseItem), [caseItem])
  const resources = Object.keys(resourceMetrics)
  const isComparison = resources.length > 1

  // 轮次 Tab：从指标 key @round:N/@overall 与 algorithmResults roundNumber/paramCode 提取
  const roundTabs = useMemo(() => {
    const rounds = new Set<string>()
    for (const resource of Object.keys(resourceMetrics)) {
      for (const key of Object.keys(resourceMetrics[resource])) {
        const m = key.match(/@round:(\d+)/)
        if (m) rounds.add(`第${m[1]}轮`)
        if (key.includes('@overall')) rounds.add('整体')
      }
    }
    for (const result of caseItem.algorithmResults ?? []) {
      if (result.roundNumber !== undefined) rounds.add(`第${result.roundNumber}轮`)
      if (result.paramCode?.includes('@round:')) {
        rounds.add(`第${result.paramCode.split('@round:')[1]}轮`)
      }
    }
    // 有轮次数据时始终提供「整体」（整体/未标注轮次值）
    if (rounds.size === 0) rounds.add('整体')
    else rounds.add('整体')
    return [...rounds]
  }, [caseItem.algorithmResults, resourceMetrics])

  const [activeRound, setActiveRound] = useState(roundTabs[0] ?? '整体')

  // 按 activeRound 过滤后的资源指标（P1-2：真实轮次切换）
  const roundScopedMetrics = useMemo(() => {
    if (!isComparison) return resourceMetrics
    const roundNum = roundNumberFromTab(activeRound)
    const result: Record<string, Record<string, number>> = {}
    for (const [resource, metrics] of Object.entries(resourceMetrics)) {
      const out: Record<string, number> = {}
      for (const [key, value] of Object.entries(metrics)) {
        const rm = key.match(/@round:(\d+)/)
        if (activeRound === '整体') {
          if (!rm) out[key.replace('@overall', '')] = value
        } else if (rm && roundNum && rm[1] === roundNum) {
          out[key.replace(/@round:\d+/, '')] = value
        }
      }
      if (Object.keys(out).length > 0) result[resource] = out
    }
    return result
  }, [resourceMetrics, activeRound, isComparison])

  // 主/子维度分组（isGroupHeader 加粗 + isSubDim 缩进）
  const dimensionRows = useMemo(() => {
    const main = allMetrics.filter((m) => m.dimension_type !== 'sub')
    const sub = allMetrics.filter((m) => m.dimension_type === 'sub')
    const rows: { key: string; name: string; metricName: string; isGroupHeader: boolean; isSubDim: boolean }[] = []
    for (const m of main) {
      const children = sub.filter(
        (s) => s.parent_dimension_name === m.name || s.parent_dimension_id === m.id
      )
      rows.push({ key: `m-${m.id ?? m.name}`, name: m.name, metricName: m.name, isGroupHeader: false, isSubDim: false })
      if (children.length > 0 && !children.some((c) => c.parent_dimension_name === m.name)) {
        rows.push({ key: `g-${m.id ?? m.name}`, name: m.name, metricName: '', isGroupHeader: true, isSubDim: false })
      }
      for (const c of children) {
        rows.push({ key: `s-${c.id ?? c.name}`, name: c.name, metricName: c.name, isGroupHeader: false, isSubDim: true })
      }
    }
    for (const m of sub) {
      if (!main.some((x) => x.name === m.parent_dimension_name)) {
        rows.push({ key: `s-${m.id ?? m.name}`, name: m.name, metricName: m.name, isGroupHeader: false, isSubDim: true })
      }
    }
    return rows
  }, [allMetrics])

  const decimalPlaces = (metricName: string) =>
    allMetrics.find((m) => m.name === metricName)?.decimal_places ?? 2

  // 真实得分/错误字段读取（数组格式 ReportMetricValue.score/error；dict 格式 caseItem.metricScore/metricError）
  const getScore = (metricName: string): number | undefined => {
    if (Array.isArray(caseItem.metrics)) {
      return caseItem.metrics[0]?.metrics?.find((m) => m.metric === metricName)?.score
    }
    return caseItem.metricScore?.[metricName]
  }
  const getError = (metricName: string): string | undefined => {
    if (Array.isArray(caseItem.metrics)) {
      return caseItem.metrics[0]?.metrics?.find((m) => m.metric === metricName)?.error
    }
    return caseItem.metricError?.[metricName]
  }

  const metricValue = (metricName: string, resource?: string) => {
    const source = isComparison ? roundScopedMetrics : resourceMetrics
    if (resource) return source[resource]?.[metricName]
    const first = Object.keys(source)[0]
    return first ? source[first]?.[metricName] : undefined
  }

  return (
    <div className='space-y-2'>
      {isComparison && roundTabs.length > 1 && (
        <div className='flex flex-wrap gap-1' role='tablist' aria-label='轮次切换'>
          {roundTabs.map((tab) => (
            <button
              key={tab}
              type='button'
              role='tab'
              aria-selected={activeRound === tab}
              className={activeRound === tab ? 'bg-primary text-primary-foreground rounded-md px-2.5 py-1 text-xs' : 'text-muted-foreground hover:bg-muted rounded-md px-2.5 py-1 text-xs'}
              onClick={() => setActiveRound(tab)}
            >
              {tab}
            </button>
          ))}
        </div>
      )}

      {isComparison ? (
        <div className='overflow-x-auto rounded-lg border'>
          <table className='w-full min-w-[480px] text-sm'>
            <thead>
              <tr className='text-muted-foreground border-b bg-muted/30'>
                <th className='px-3 py-2 text-left font-medium'>指标名称</th>
                {resources.map((r) => (
                  <th key={r} className='px-3 py-2 text-left font-medium'>{r}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dimensionRows.map((row) => (
                <tr key={row.key} className={row.isGroupHeader ? 'bg-muted/40 border-b font-semibold' : 'hover:bg-muted/30 border-b'}>
                  <td className={row.isSubDim ? 'text-muted-foreground px-3 py-2 ps-8 text-sm' : 'px-3 py-2 text-sm'}>
                    {row.name}
                  </td>
                  {resources.map((r) => {
                    if (row.isGroupHeader) return <td key={r} />
                    const v = metricValue(row.metricName, r)
                    return (
                      <td key={r} className='px-3 py-2 font-mono text-xs tabular-nums'>
                        {v === undefined ? '—' : v.toFixed(decimalPlaces(row.metricName))}
                      </td>
                    )
                  })}
                </tr>
              ))}
              {dimensionRows.length === 0 && (
                <tr>
                  <td colSpan={resources.length + 1} className='text-muted-foreground p-4 text-center text-sm'>
                    暂无指标数据
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className='overflow-hidden rounded-lg border'>
          <table className='w-full text-sm'>
            <thead>
              <tr className='text-muted-foreground border-b bg-muted/30'>
                <th className='px-3 py-2 text-left font-medium'>指标名称</th>
                <th className='px-3 py-2 text-left font-medium'>指标数值</th>
                <th className='px-3 py-2 text-left font-medium'>得分</th>
                <th className='px-3 py-2 text-left font-medium'>详情·错误</th>
              </tr>
            </thead>
            <tbody>
              {allMetrics.map((m) => {
                const v = metricValue(m.name)
                if (v === undefined) return null
                const score = getScore(m.name)
                const error = getError(m.name)
                return (
                  <tr key={m.id ?? m.name} className='hover:bg-muted/30 border-b last:border-0'>
                    <td className='px-3 py-2 text-sm font-medium'>{m.name}</td>
                    <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                      {v.toFixed(decimalPlaces(m.name))}
                    </td>
                    <td className='px-3 py-2'>
                      <ScoreBadge score={score} />
                    </td>
                    <td className='text-muted-foreground px-3 py-2 text-xs'>
                      <ErrorText text={error} />
                    </td>
                  </tr>
                )
              })}
              {allMetrics.length === 0 && (
                <tr>
                  <td colSpan={4} className='text-muted-foreground p-4 text-center text-sm'>暂无指标数据</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/** 详情·错误文本（>50 字可折叠展开/收起，§3.5.1） */
function ErrorText({ text }: { text?: string }) {
  const [open, setOpen] = useState(false)
  if (!text) return <span>—</span>
  if (text.length <= 50) return <span>{text}</span>
  return (
    <div className='min-w-0 max-w-[320px]'>
      <p className={cn('text-xs leading-relaxed break-words', !open && 'line-clamp-2')}>
        {text}
      </p>
      <Button
        variant='ghost'
        size='sm'
        className='text-muted-foreground h-5 gap-1 px-1 text-xs'
        onClick={() => setOpen((v) => !v)}
      >
        {open ? '收起' : '展开'}
        <ChevronDown aria-hidden='true' className={cn('size-3 transition-transform', open && 'rotate-180')} />
      </Button>
    </div>
  )
}
