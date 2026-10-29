/**
 * 任务用例执行详情·执行结果与指标全块（10_测试执行.md §5.2 + 15_报告域.md §3.5，INT-2088）。
 * 在弹窗分节①内按 V9.7.10 TestCaseReportDetail 全块补齐：
 * - 评分指标（主/子维度层级分组表，复用弹窗既有轮次 Tab 轴；后端 metric_configs 现不下发
 *   dimension_type → 按主维度平铺，V9.7.10 comparisonData `dimension_type ?? 'main'` 同口径）；
 * - 多轮对话结果（MultiRoundResult，algorithmResults.rounds 检测；无则整体不渲染）；
 * - 执行结果：参考数据（referenceParams text kv）、用例参数（后端无 case_params 数据源 →
 *   「暂无数据」空态）、评估结果（维度 tab 切换 + 每设备 kv）、设备·API 执行结果
 *   （无维度归属结果字段 + /results 状态行）、时间轴对比（§3.3.9）、音频时间轴（§3.5.7）。
 * 轮次轴与弹窗 Tab 同源（detail.roundTabs / currentTab），跨组件同轴切换（INT-1861 不回归）。
 *
 * report 域块组件（ExecutionResults/MultiRoundResult）消费 report 领域模型——在组合点把
 * test-execution 数据桥接成 report 用例卡形态（仅本模态窗内使用，不进 domain/infrastructure）。
 */
import { Minus, Plus, RotateCcw } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type {
  CaseDeviceResult,
  CaseExecutionDetail,
  CaseMetricConfig,
  CaseMetricRow,
  CaseRoundTab,
} from '@/domain/models/testExecution'
import { executionStatusLabel } from '@/domain/models/review'
import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'
import type { CaseDisplaySettings } from '@/application/report-view/use-case-display-settings'
import { useTimelineComparison, hasTimelineData } from '@/application/report-view/use-timeline-comparison'
import { MultiRoundResult } from '@/features/report-view/components/case-report-detail/multi-round-result'
import { ExecutionResults } from '@/features/report-view/components/case-report-detail/execution-results'
import { AudioTimeline } from '@/features/report-view/components/case-report-detail/audio-timeline'
import type { RoundTab } from '@/features/report-view/components/case-report-detail/case-report-utils'
import { cn } from '@/lib/utils'

/** ExecutionResults 子项裁剪：音频时间轴/结果音频与时间轴对比由本弹窗自行渲染
 *  （report 块内置 TimelineComparison/AudioTimeline 不重复渲染）；轮次 Tab 也由弹窗层
 *  RoundTabBar 单一轴驱动（ExecutionResults 内部轮次 Tab 条隐藏，避免双 Tab 条） */
const HIDE_AUDIO_DISPLAY: CaseDisplaySettings = {
  hiddenBlocks: [],
  hiddenExecution: ['audio', 'timeline'],
  hiddenMetrics: [],
  hiddenRounds: [],
  hiddenResources: [],
  hiddenResultTypes: [],
  includeSubDimensions: false,
}

interface CaseDetailExecutionResultsProps {
  detail: CaseExecutionDetail
  /**
   * 目标切换后的作用域（被测设备/API）：只作用于「评分指标以下」的模块
   * （多轮结果 / 执行结果 / 时间轴 / 音频），评分指标恒按全量目标列对比。
   * 不传 = 全量（现状）。
   */
  targetDetail?: CaseExecutionDetail
  /** 设备/API 一级 Tab（透传给执行结果块，渲染在「执行结果」之上） */
  targetTab?: {
    names: string[]
    active: string
    onSelect: (target: string) => void
  }
  /** 当前轮次 Tab（弹窗既有状态；null = 数据未就绪） */
  currentTab: CaseRoundTab | null
  /** 轮次 Tab 选择（label → 弹窗 tabChoice 更新；INT-1861 复位语义在弹窗层） */
  onRoundTabLabelSelect: (label: string) => void
}

/**
 * 评分指标层级分组行（V9.7.10 groupedMetricsForCurrentRound + currentRoundTableData 同口径）：
 * 子维度归父维度组；组内无主维度行（或主维度名≠组名）时插入分组标题行。
 */
function buildHierarchyRows(
  rows: CaseMetricRow[],
  configs: CaseMetricConfig[]
): { key: string; name: string; isGroupHeader: boolean; isSubDim: boolean; metric: CaseMetricRow | null }[] {
  type Group = { groupLabel: string; mainItem: CaseMetricRow | null; subItems: CaseMetricRow[] }
  const groupMap = new Map<string, Group>()
  for (const row of rows) {
    const config = configs.find((c) => c.name === row.dimension)
    const isSub = config?.dimensionType === 'sub' && config.parentDimensionName != null
    const groupKey = isSub ? (config!.parentDimensionName as string) : row.dimension
    let group = groupMap.get(groupKey)
    if (!group) {
      group = { groupLabel: groupKey, mainItem: null, subItems: [] }
      groupMap.set(groupKey, group)
    }
    if (isSub) group.subItems.push(row)
    else if (group.mainItem) group.subItems.push(row)
    else group.mainItem = row
  }
  const out: { key: string; name: string; isGroupHeader: boolean; isSubDim: boolean; metric: CaseMetricRow | null }[] = []
  let seq = 0
  for (const group of groupMap.values()) {
    const mainIsHeader = group.mainItem !== null && group.mainItem.dimension === group.groupLabel
    if (group.subItems.length > 0 && !mainIsHeader) {
      out.push({ key: `hdr-${seq++}`, name: group.groupLabel, isGroupHeader: true, isSubDim: false, metric: null })
    }
    if (group.mainItem) {
      out.push({ key: `main-${seq++}`, name: group.mainItem.dimension, isGroupHeader: mainIsHeader, isSubDim: false, metric: group.mainItem })
    }
    for (const sub of group.subItems) {
      out.push({ key: `sub-${seq++}`, name: sub.dimension, isGroupHeader: false, isSubDim: true, metric: sub })
    }
  }
  return out
}

/** 评分指标表（行=指标名称、列=设备；V9.7.10 指标名称列头 + 每设备执行状态徽章保留） */
function ScoreMetricTable({
  tab,
  devices,
  metricConfigs,
}: {
  tab: CaseRoundTab | null
  devices: CaseDeviceResult[]
  metricConfigs: CaseMetricConfig[]
}) {
  const rows = useMemo(() => buildHierarchyRows(tab?.rows ?? [], metricConfigs), [tab, metricConfigs])
  return (
    <div className='overflow-x-auto rounded-lg border'>
      <table className='w-full text-left text-sm'>
        <thead className='bg-muted/50 border-b'>
          <tr className='text-muted-foreground text-xs'>
            <th className='px-3 py-2 font-medium whitespace-nowrap'>指标名称</th>
            {devices.map((device) => (
              <th key={device.deviceName} className='px-3 py-2 font-medium whitespace-nowrap'>
                <span className='flex items-center gap-1.5'>
                  {device.deviceName}
                  <StatusBadge
                    label={device.executionStatus ? executionStatusLabel(device.executionStatus) : '—'}
                    variant={
                      device.executionStatus === 'completed'
                        ? 'success'
                        : device.executionStatus === 'failed'
                          ? 'danger'
                          : device.executionStatus
                            ? 'warning'
                            : 'neutral'
                    }
                  />
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.key}
              className={row.isGroupHeader ? 'bg-muted/40 border-b font-semibold' : 'border-b last:border-0 hover:bg-muted/30'}
            >
              <td className={row.isSubDim ? 'text-muted-foreground px-3 py-2 ps-8 text-sm' : 'px-3 py-2 text-sm'}>
                {row.name}
              </td>
              {devices.map((device) => (
                <td key={device.deviceName} className='px-3 py-2 font-mono text-xs tabular-nums'>
                  {row.metric?.values[device.deviceName] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={devices.length + 1} className='text-muted-foreground p-4 text-center text-sm'>
                暂无指标数据
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

/** 时间轴参考值提取：referenceParams 值对象（{text|value|json}）→ 可解析文本（rttm/stm/json） */
function extractTimelineValue(v: unknown): unknown {
  if (v && typeof v === 'object') {
    const rec = v as { json?: unknown; text?: unknown; value?: unknown }
    return rec.json ?? rec.text ?? rec.value ?? v
  }
  return v
}

/** 时间轴对比（§3.3.9；useTimelineComparison.build 平移，参考段经 extractTimelineValue 预处理） */
function TimelineCompare({ detail }: { detail: CaseExecutionDetail }) {
  const { scale, zoom, resetZoom, selectedSpeaker, setSelectedSpeaker, build } = useTimelineComparison()
  const [resource, setResource] = useState('全部')

  const timeline = useMemo(() => {
    const refCodes = detail.fieldMapping?.reference ?? []
    const refParams: Record<string, unknown> = {}
    for (const code of refCodes) {
      const v = detail.referenceParams?.[code]
      if (v == null) continue
      refParams[code] = extractTimelineValue(v)
    }
    return build(detail.algorithmResults, refParams, refCodes)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail])

  if (!timeline) {
    return (
      <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
        暂无时间轴数据
      </div>
    )
  }

  const speakers = timeline.speakers.filter(
    (s) => s === '全部' || selectedSpeaker === '全部' || s === selectedSpeaker
  )
  const resources = [
    '全部',
    ...new Set([
      ...(detail.results ?? []).map((r) => r.deviceName ?? r.apiName ?? '').filter(Boolean),
      ...timeline.resultSegments.map((s) => s.resource ?? '').filter(Boolean),
    ]),
  ]
  const maxDuration = timeline.effectiveDuration * scale

  return (
    <div className='space-y-2'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <p className='text-sm font-semibold'>时间轴对比</p>
        <div className='flex items-center gap-1'>
          <Button variant='ghost' size='sm' className='h-7 px-1.5' aria-label='缩小' onClick={() => zoom(0.8)}>
            <Minus aria-hidden='true' className='size-3.5' />
          </Button>
          <span className='text-muted-foreground w-10 text-center text-xs tabular-nums'>{scale.toFixed(1)}x</span>
          <Button variant='ghost' size='sm' className='h-7 px-1.5' aria-label='放大' onClick={() => zoom(1.25)}>
            <Plus aria-hidden='true' className='size-3.5' />
          </Button>
          <Button variant='ghost' size='sm' className='h-7 px-1.5' aria-label='重置' onClick={resetZoom}>
            <RotateCcw aria-hidden='true' className='size-3.5' />
          </Button>
        </div>
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        <Select value={resource} onValueChange={(v) => setResource(v ?? '')}>
          <SelectTrigger className='h-8 w-44 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {resources.map((r) => (
              <SelectItem key={r} value={r}>{r === '全部' ? '全部资源' : r}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={selectedSpeaker} onValueChange={(v) => setSelectedSpeaker(v ?? '全部')}>
          <SelectTrigger className='h-8 w-32 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {timeline.speakers.map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className='overflow-hidden rounded-lg border'>
        <div className='overflow-x-auto'>
          <div className='min-w-[560px] p-3'>
            {speakers.map((speaker) => {
              if (speaker === '全部') return null
              const refs = timeline.referenceSegments.filter((s) => s.speaker === speaker)
              const results = timeline.resultSegments.filter(
                (s) => s.speaker === speaker && (resource === '全部' || s.resource === resource)
              )
              return (
                <div key={speaker} className='space-y-1'>
                  <p className='text-muted-foreground text-xs font-medium'>{speaker}</p>
                  <div className='space-y-1'>
                    <SegmentRow label='参考' segments={refs} maxDuration={maxDuration} tone='bg-muted' />
                    <SegmentRow
                      label='结果'
                      segments={results}
                      maxDuration={maxDuration}
                      tone='bg-primary/40'
                      matchTone='bg-primary/70'
                    />
                  </div>
                </div>
              )
            })}
            <div className='text-muted-foreground mt-2 flex justify-between text-[10px] font-mono tabular-nums'>
              <span>0s</span>
              <span>{maxDuration.toFixed(1)}s</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function SegmentRow({
  label,
  segments,
  maxDuration,
  tone,
  matchTone,
}: {
  label: string
  segments: { start: number; end: number; text: string; isMatch?: boolean }[]
  maxDuration: number
  tone: string
  matchTone?: string
}) {
  return (
    <div className='flex items-center gap-2 text-xs'>
      <span className='text-muted-foreground w-8 shrink-0'>{label}</span>
      <div className='relative h-6 flex-1 overflow-hidden rounded bg-muted/30'>
        {segments.length === 0 && <span className='text-muted-foreground px-2 text-[10px]'>无数据</span>}
        {segments.map((seg, i) => (
          <div
            key={i}
            className={(seg.isMatch ? (matchTone ?? tone) : tone) + ' absolute top-1 h-4 overflow-hidden rounded-sm px-1.5 text-[10px] leading-4'}
            style={{
              left: `${(seg.start / maxDuration) * 100}%`,
              width: `${((seg.end - seg.start) / maxDuration) * 100}%`,
            }}
            title={seg.text}
          >
            <span className='truncate'>{seg.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * 时间轴数据是否存在（§3.3.9 判据；report ExecutionResults.hasTimeline 同口径）：
 * fieldMapping.result/reference 显式声明的 rttm/stm 码、algorithmResults rttm/stm/json 项、
 * referenceParams rttm/stm 键与 json 类键。
 */
function hasTimelineEvidence(detail: CaseExecutionDetail): boolean {
  const fm = detail.fieldMapping ?? { result: [], reference: [] }
  if ((fm.result ?? []).some((code) => /rttm|stm/i.test(code))) return true
  if ((fm.reference ?? []).some((code) => /rttm|stm/i.test(code))) return true
  if (
    (detail.algorithmResults ?? []).some((r) => {
      const pt = r.paramType ?? ''
      if (pt === 'rttm' || pt === 'stm') return true
      if (pt === 'json') return hasTimelineData(r.value)
      return false
    })
  ) {
    return true
  }
  for (const [key, value] of Object.entries(detail.referenceParams ?? {})) {
    if (/rttm|stm/i.test(key) && value) return true
    if (/json/i.test(key) && value && hasTimelineData(extractTimelineValue(value))) return true
  }
  return false
}

/** test-execution 用例详情 → report 用例卡形态（组合点桥接；仅 ExecutionResults/MultiRoundResult 消费） */
function toReportCaseItem(detail: CaseExecutionDetail): ReportCaseItem {
  const isMultiRound = (detail.roundTabs ?? []).some((t) => t.kind === 'round')
  const metrics: Record<string, Record<string, number>> = {}
  for (const device of detail.devices) {
    const deviceMetrics: Record<string, number> = {}
    for (const point of device.metrics) {
      const key = isMultiRound
        ? point.round == null
          ? `${point.dimension}@overall`
          : `${point.dimension}@round:${point.round}`
        : point.dimension
      const num = Number(point.value)
      if (Number.isFinite(num)) deviceMetrics[key] = num
    }
    metrics[device.deviceName] = deviceMetrics
  }
  return {
    id: detail.caseId,
    name: detail.name,
    description: undefined,
    tags: [],
    metrics,
    caseParams: detail.caseParams as ReportCaseItem['caseParams'],
    results: (detail.results ?? []).map((r) => ({
      resource: r.deviceName ?? r.apiName ?? `结果 ${r.id}`,
      status: r.executionStatus ?? undefined,
    })),
    audios: (detail.resultAudios ?? []).map((a) => ({
      audio_id: a.audioName ?? '',
      audio_name: a.audioName,
      url: a.url ?? undefined,
    })),
    referenceParams: detail.referenceParams as ReportCaseItem['referenceParams'],
    algorithmResults: detail.algorithmResults as ReportCaseItem['algorithmResults'],
    algorithmType: detail.algorithmType ?? undefined,
  }
}

/** report 域块组件所需的报告摘要最小形态（all_metrics / resource_headers / field_mappings） */
function toReportDetailData(detail: CaseExecutionDetail): ReportDetailData {
  const devices = detail.devices ?? []
  const fieldMapping = detail.fieldMapping ?? { result: [], reference: [] }
  return {
    id: detail.taskId,
    name: detail.name,
    type: 'task',
    task_name: detail.name,
    status: 'published',
    created_at: '',
    summary: {
      total_cases: 0,
      completed_cases: 0,
      failed_cases: 0,
      resources: devices.map((d) => d.deviceName),
      resource_headers: devices.map((d) => ({ key: d.deviceName, label: d.deviceName })),
      raw_data: [],
      metric_data: [],
      tag_metric_data: [],
      case_categories: [],
      all_case_tags: [],
      all_tags: [],
      all_metrics: (detail.metricConfigs ?? []).map((c) => ({
        name: c.name,
        dimension_type: c.dimensionType,
        parent_dimension_name: c.parentDimensionName,
        decimal_places: c.decimalPlaces,
        unit: c.unit,
      })),
      case_type_stats: [],
      device_stats: [],
      api_stats: [],
      devices: [],
      apis: [],
      field_mappings: [
        {
          algorithmType: {
            result: fieldMapping.result ?? [],
            reference: fieldMapping.reference ?? [],
          },
        },
      ],
    },
  }
}

/** 音频时间轴输入（用例输入音频 audio_list；V9.7.10 音频时间轴 §3.5.7 同源） */
function toTimelineAudioItems(detail: CaseExecutionDetail) {
  return (detail.referenceAudios ?? []).map((a) => ({
    audio_id: a.audioName ?? '',
    audio_name: a.audioName,
    url: a.url ?? undefined,
  }))
}

export function CaseDetailExecutionResults({
  detail,
  targetDetail,
  targetTab,
  currentTab,
  onRoundTabLabelSelect,
}: CaseDetailExecutionResultsProps) {
  /** 评分指标以下模块的取数作用域（目标切换）；评分指标本身恒用全量 detail */
  const scoped = targetDetail ?? detail
  const reportCaseItem = useMemo(() => toReportCaseItem(scoped), [scoped])
  const reportDetail = useMemo(() => toReportDetailData(scoped), [scoped])

  /** 弹窗既有轮次 Tab → report 域 RoundTab（key/label/roundTag/order） */
  const reportRoundTabs = useMemo<RoundTab[]>(
    () =>
      (detail.roundTabs ?? []).map((t) => ({
        key: t.key,
        label: t.label,
        roundTag: t.kind === 'overall' ? 'overall' : t.kind === 'round' ? `round:${t.round}` : null,
        order: t.kind === 'overall' ? 9999 : t.kind === 'round' ? (t.round ?? 0) : 0,
      })),
    [detail.roundTabs]
  )
  const activeRoundTab = currentTab?.label ?? ''
  const activeRoundTag =
    currentTab == null
      ? null
      : currentTab.kind === 'overall'
        ? 'overall'
        : currentTab.kind === 'round'
          ? `round:${currentTab.round}`
          : null

  /** 弹窗层 RoundTabBar 是唯一轮次轴 → ExecutionResults 内部轮次 Tab 条隐藏
   *  （hiddenRounds 覆盖全部 roundTag，visibleRoundTabs 为空；轮次过滤仍走 activeRoundTag） */
  const display = useMemo(() => {
    const hiddenRounds = reportRoundTabs
      .map((t) => t.roundTag)
      .filter((t): t is string => t != null)
    return { ...HIDE_AUDIO_DISPLAY, hiddenRounds }
  }, [reportRoundTabs])

  const hasTimeline = useMemo(() => hasTimelineEvidence(scoped), [scoped])
  const hasInputAudio = (scoped.referenceAudios ?? []).length > 0

  return (
    <div className='space-y-3'>
      {/* 评分指标（主/子维度层级分组表；轮次 Tab 在弹窗层渲染）。无设备列（API/voice_llm 用例
          devices 空）时隐藏——V9.7.10 comparisonData 无资源列不渲染 hasMetrics 块 */}
      {detail.devices.length > 0 && (
        <div className='space-y-2'>
          <p className='text-sm font-semibold'>评分指标</p>
          <ScoreMetricTable
            tab={currentTab}
            devices={detail.devices}
            metricConfigs={detail.metricConfigs ?? []}
          />
        </div>
      )}

      {/* 多轮对话结果（algorithmResults.rounds 检测；无多轮数据返回 null 不渲染） */}
      <MultiRoundResult caseItem={reportCaseItem} />

      {/* 执行结果（参考数据 / 用例参数 / 评估结果 / 设备·API 执行结果 / 时间轴对比）；
          ExecutionResults 自身带「执行结果」块标题（report 域同口径，不再重复渲染） */}
      <div className='space-y-2'>
        <ExecutionResults
          caseItem={reportCaseItem}
          report={reportDetail}
          roundTabs={reportRoundTabs}
          activeRoundTab={activeRoundTab}
          setActiveRoundTab={onRoundTabLabelSelect}
          activeRoundTag={activeRoundTag}
          display={display}
          targetTab={targetTab}
        />

        {/* 用例参数块由上方 ExecutionResults 独占渲染（含无数据时的块内「暂无数据」空态，
            INT-2089）；弹窗侧不再补一份兜底空态，V9.7.10 该弹窗只有一处「用例参数」。 */}

        {/* 时间轴对比（§3.3.9；随目标切换收窄） */}
        {hasTimeline && <TimelineCompare detail={scoped} />}

        {/* 音频时间轴（§3.5.7；用例输入音频；随目标切换收窄） */}
        {hasInputAudio && <AudioTimeline audioList={toTimelineAudioItems(scoped)} />}
      </div>
    </div>
  )
}

/** 弹窗分节①轮次 Tab 条（V9.7.10 round-tab-bar 同口径；单轮不渲染） */
export function RoundTabBar({
  roundTabs,
  activeTabKey,
  onTabKeySelect,
}: {
  roundTabs: CaseRoundTab[]
  activeTabKey: string | null
  onTabKeySelect: (tabKey: string) => void
}) {
  if (roundTabs.length <= 1) return null
  return (
    <div className='flex flex-wrap gap-1' role='tablist' aria-label='轮次切换'>
      {roundTabs.map((tab) => (
        <button
          key={tab.key}
          type='button'
          role='tab'
          aria-selected={activeTabKey === tab.key}
          className={cn(
            'rounded-md px-2.5 py-1 text-xs transition-colors',
            activeTabKey === tab.key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
          )}
          onClick={() => onTabKeySelect(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

/** 目标切换「全部对比」哨兵值（与弹窗层约定一致） */
export { ALL_TARGETS, TargetTabBar } from '@/features/report-view/components/case-report-detail/target-tab-bar'
