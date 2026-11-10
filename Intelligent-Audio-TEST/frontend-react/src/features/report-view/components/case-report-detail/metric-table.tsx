/**
 * 块一：评分指标（15_报告域.md §3.5.1，TestCaseReportDetail 块一对位）。
 *
 * 报告域**恒走对比模式**（INT-2120，照 V9.7.10 报告用例卡 / 报告详情弹窗 / 任务用例弹窗
 * 一律 `:isComparison="true"`）：轮次 Tab 与叶表 / 执行结果共用同一 `activeRoundTab`，
 * 行集 = 当前轮 `currentRoundMetricKeys`；主/子维度层级分组 + 资源列保留。
 * 单轮用例无轮次后缀 → 无 Tab、行集不变（不回归）。
 * 指标 key 友好化（(第N轮)/(整体)）；数值按 metricConfigs[].decimal_places（默认 2）精度显示。
 */
import { useCallback, useMemo } from 'react'

import type {
  ReportCaseItem,
  ReportDetailData,
  ReportMetricConfig,
} from '@/domain/models/report'
import { extractCaseResourceMetrics } from '@/application/report-view/case-matrix'
import type { CaseDisplaySettings } from '@/application/report-view/use-case-display-settings'
import { cn } from '@/lib/utils'

import {
  parseMetricKey,
  getDeviceName,
  roundTagLabel,
  type RoundTab,
} from './case-report-utils'

/** 指标 key 是否保留（显示设置：隐藏的评估维度 / 轮次；无轮次标记的 key 恒保留） */
function keepMetricKey(key: string, hiddenMetrics: string[], hiddenRounds: string[]): boolean {
  const { base, roundTag } = parseMetricKey(key)
  if (hiddenMetrics.includes(base)) return false
  if (roundTag && hiddenRounds.includes(roundTag)) return false
  return true
}

interface MetricTableProps {
  caseItem: ReportCaseItem
  report: ReportDetailData
  roundTabs: RoundTab[]
  activeRoundTab: string
  setActiveRoundTab: (tab: string) => void
  currentRoundMetricKeys: string[]
  /** 显示设置「轮次」chips 全清（§3.5.10 兜底「未选择轮次」） */
  noRoundSelected?: boolean
  /** §3.5.10 显示设置（不传 = 全显）；裁评估维度 / 轮次 / 资源 */
  display?: CaseDisplaySettings
  /** 导出态（INT-2434）：轮次 Tab 保留并由导出脚本纯 DOM 切换；行集按轮次拆成多个 tbody */
  isExporting?: boolean
  /** 导出 Tab 组前缀（与执行结果块共用同一轮次轴 → 同一组名） */
  exportGroup?: string
}

export function MetricTable({
  caseItem,
  report,
  roundTabs,
  activeRoundTab,
  setActiveRoundTab,
  currentRoundMetricKeys,
  noRoundSelected = false,
  display,
  isExporting = false,
  exportGroup,
}: MetricTableProps) {
  const roundGroup = exportGroup ? `${exportGroup}-round` : ''
  const allMetrics: ReportMetricConfig[] = report.summary.all_metrics
  const resourceMetrics = useMemo(() => extractCaseResourceMetrics(caseItem), [caseItem])
  const headers = report.summary.resource_headers ?? []
  const hiddenMetrics = display?.hiddenMetrics ?? []
  const hiddenRounds = display?.hiddenRounds ?? []
  const hiddenResources = display?.hiddenResources ?? []

  const resources = useMemo(
    () => Object.keys(resourceMetrics).filter((r) => !hiddenResources.includes(r)),
    [resourceMetrics, hiddenResources]
  )

  const allMetricKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const metrics of Object.values(resourceMetrics)) {
      for (const key of Object.keys(metrics)) keys.add(key)
    }
    return [...keys]
  }, [resourceMetrics])

  /** 显示设置裁剪：评估维度按基础维度名、轮次按 `overall` / `round:N`（无轮次标记的 key 恒显示） */
  const visibleMetricKeys = useMemo(
    () => allMetricKeys.filter((k) => keepMetricKey(k, hiddenMetrics, hiddenRounds)),
    [allMetricKeys, hiddenMetrics, hiddenRounds]
  )
  /** 可见轮次 Tab（显示设置「轮次」全清 → 展示提示，不空表） */
  const visibleRoundTabs = roundTabs.filter(
    (t) => !t.roundTag || !hiddenRounds.includes(t.roundTag)
  )
  const allRoundsHidden =
    roundTabs.length > 0 && visibleRoundTabs.length === 0 && hiddenRounds.length > 0
  const allMetricsHidden = allMetricKeys.length > 0 && visibleMetricKeys.length === 0 && hiddenMetrics.length > 0

  const decimalPlaces = (metricName: string) => {
    const base = metricName.replace(/@round:\d+$|@overall$/i, '')
    return (
      allMetrics.find((m) => m.name === base)?.decimal_places ??
      allMetrics.find((m) => m.name === metricName)?.decimal_places ??
      2
    )
  }
  const metricUnit = (metricName: string) => {
    const base = metricName.replace(/@round:\d+$|@overall$/i, '')
    return allMetrics.find((m) => m.name === base)?.unit
  }

  const metricValue = (metricKey: string, resource?: string) => {
    if (resource) return resourceMetrics[resource]?.[metricKey]
    const first = resources[0]
    return first ? resourceMetrics[first]?.[metricKey] : undefined
  }

  // 当前轮次 key → 主/子维度层级分组行（照 V9.7.10 groupedMetricsForCurrentRound + currentRoundTableData）
  const buildDimensionRows = useCallback((keys: string[]) => {
    type Group = {
      groupLabel: string
      mainItem: { metricKey: string; base: string } | null
      subItems: { metricKey: string; base: string }[]
    }
    const groupMap = new Map<string, Group>()
    const getDimInfo = (base: string) => {
      const config = allMetrics.find((m) => m.name === base)
      if (!config) return { dimType: 'main' as const, parentName: '' }
      if (config.dimension_type === 'sub' && config.parent_dimension_name) {
        return { dimType: 'sub' as const, parentName: config.parent_dimension_name }
      }
      return { dimType: 'main' as const, parentName: '' }
    }
    for (const key of keys) {
      const { base } = parseMetricKey(key)
      const { dimType, parentName } = getDimInfo(base)
      let groupKey: string
      let effectiveType = dimType
      if (dimType === 'sub' && parentName) {
        groupKey = parentName
      } else {
        effectiveType = 'main'
        groupKey = base
      }
      let group = groupMap.get(groupKey)
      if (!group) {
        group = { groupLabel: groupKey, mainItem: null, subItems: [] }
        groupMap.set(groupKey, group)
      }
      const item = { metricKey: key, base }
      if (effectiveType === 'main') {
        if (group.mainItem) group.subItems.push(item)
        else group.mainItem = item
      } else {
        group.subItems.push(item)
      }
    }
    const rows: {
      key: string
      name: string
      isGroupHeader: boolean
      isSubDim: boolean
      metricKey: string
    }[] = []
    let seq = 0
    for (const group of groupMap.values()) {
      const mainIsHeader = group.mainItem !== null && group.mainItem.base === group.groupLabel
      if (group.subItems.length > 0 && !mainIsHeader) {
        rows.push({ key: `hdr-${seq++}`, name: group.groupLabel, isGroupHeader: true, isSubDim: false, metricKey: '' })
      }
      if (group.mainItem) {
        rows.push({
          key: `main-${seq++}`,
          name: group.mainItem.base,
          isGroupHeader: mainIsHeader,
          isSubDim: false,
          metricKey: group.mainItem.metricKey,
        })
      }
      for (const sub of group.subItems) {
        rows.push({ key: `sub-${seq++}`, name: sub.base, isGroupHeader: false, isSubDim: true, metricKey: sub.metricKey })
      }
    }
    return rows
  }, [allMetrics])

  const currentRowKeys = useMemo(
    () => currentRoundMetricKeys.filter((k) => keepMetricKey(k, hiddenMetrics, hiddenRounds)),
    [currentRoundMetricKeys, hiddenMetrics, hiddenRounds]
  )
  const dimensionRows = useMemo(() => buildDimensionRows(currentRowKeys), [buildDimensionRows, currentRowKeys])

  /**
   * 导出态轮次行组（INT-2434）：每个轮次一组行，渲染成多个 `<tbody>`，
   * 由导出脚本按轮次 Tab 显示 / 隐藏（产物里没有 React 状态）。
   * 规则与页面一致：无轮次标记的指标在所有轮次下都显示。
   */
  const exportRoundSheets = useMemo(() => {
    if (!isExporting) return []
    return visibleRoundTabs.map((tab) => ({
      tag: tab.roundTag ?? '',
      rows: buildDimensionRows(
        allMetricKeys.filter((key) => {
          if (!keepMetricKey(key, hiddenMetrics, hiddenRounds)) return false
          const { roundTag } = parseMetricKey(key)
          return roundTag === null || roundTag === tab.roundTag
        })
      ),
    }))
  }, [isExporting, visibleRoundTabs, allMetricKeys, buildDimensionRows, hiddenMetrics, hiddenRounds])

  const renderMetricRow = (row: (typeof dimensionRows)[number]) => (
    <tr
      key={row.key}
      className={row.isGroupHeader ? 'bg-muted/40 border-b font-semibold' : 'hover:bg-muted/30 border-b'}
    >
      <td className={row.isSubDim ? 'text-muted-foreground px-3 py-2 ps-8 text-sm' : 'px-3 py-2 text-sm'}>
        {row.name}
        {row.metricKey && row.metricKey !== row.name && (
          <span className='text-muted-foreground ms-1 text-xs'>({roundTagLabel(parseMetricKey(row.metricKey).roundTag ?? '')})</span>
        )}
      </td>
      {resources.map((r) => {
        // 独立分组标题行（metricKey 为空）无值；主维度兼分组标题行照常渲染数值
        if (!row.metricKey) return <td key={r} />
        const v = metricValue(row.metricKey, r)
        const unit = metricUnit(row.metricKey)
        return (
          <td key={r} className='px-3 py-2 font-mono text-xs tabular-nums'>
            {typeof v === 'number' && Number.isFinite(v) ? v.toFixed(decimalPlaces(row.metricKey)) : '—'}
            {typeof v === 'number' && unit && <span className='text-muted-foreground ms-0.5'>{unit}</span>}
          </td>
        )
      })}
    </tr>
  )

  const renderEmptyRow = (keyPrefix: string) => (
    <tr key={`${keyPrefix}-empty`}>
      <td colSpan={resources.length + 1} className='text-muted-foreground p-4 text-center text-sm'>
        {allMetricsHidden ? '未选择评估维度' : allRoundsHidden || noRoundSelected ? '未选择轮次' : '暂无指标数据'}
      </td>
    </tr>
  )

  return (
    <div className='space-y-2'>
      {visibleRoundTabs.length > 1 && (
        <div className='flex flex-wrap gap-1' role='tablist' aria-label='轮次切换'>
          {visibleRoundTabs.map((tab) => (
            <button
              key={tab.key}
              type='button'
              role='tab'
              aria-selected={activeRoundTab === tab.label}
              data-export-tab={roundGroup ? `${roundGroup}:${tab.roundTag ?? ''}` : undefined}
              className={cn(
                'rounded-md px-2.5 py-1 text-xs transition-colors',
                activeRoundTab === tab.label
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted'
              )}
              onClick={() => setActiveRoundTab(tab.label)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      <div className='overflow-x-auto rounded-lg border'>
        <table className='w-full min-w-[480px] text-sm'>
          <thead>
            <tr className='text-muted-foreground border-b bg-muted/30'>
              <th className='px-3 py-2 text-left font-medium'>指标名称</th>
              {resources.map((r) => (
                <th key={r} className='px-3 py-2 text-left font-medium'>
                  {getDeviceName(r, headers)}
                </th>
              ))}
            </tr>
          </thead>
          {isExporting && exportRoundSheets.length > 0 ? (
            // 导出态：每轮一组行（多个 tbody，脚本按轮次 Tab 显示 / 隐藏）
            exportRoundSheets.map((sheet, sheetIndex) => (
              <tbody
                // 导出态轮次行组按「轮次标记 + 顺序」取 key：无轮次标记的 Tab 可能不止一个
                // （`roundTag` 为空），只用 tag 会撞 key（React duplicate key 警告）
                key={`${sheet.tag}-${sheetIndex}`}
                data-export-round={roundGroup ? `${roundGroup}|${sheet.tag}|m` : undefined}
              >
                {sheet.rows.map(renderMetricRow)}
                {sheet.rows.length === 0 && renderEmptyRow(sheet.tag)}
              </tbody>
            ))
          ) : (
            <tbody>
              {dimensionRows.map(renderMetricRow)}
              {dimensionRows.length === 0 && renderEmptyRow('current')}
            </tbody>
          )}
        </table>
      </div>
    </div>
  )
}
