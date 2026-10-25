/**
 * 块三：执行结果（15_报告域.md §3.5.3，TestCaseReportDetail 块三~七对位）。
 * 多轮场景顶部轮次 Tab（共享 useCaseRoundTabs）→ 参考数据（currentRoundReferenceTextFields）
 * + 用例参数（块四，按轮次）+ 评估结果（块五，维度 tab 切换 + 对比按设备列块）
 * + 设备/API 执行结果（块六，每设备结果文本 + 播放音频）+ 时间轴对比 + 音频时间轴（块七）+ 结果音频（按设备分组）。
 */
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import type {
  ReportCaseItem,
  ReportDetailData,
  ReportReferenceParam,
} from '@/domain/models/report'
import { extractCaseResourceMetrics } from '@/application/report-view/case-matrix'
import {
  isExecutionChildVisible,
  type CaseDisplaySettings,
} from '@/application/report-view/use-case-display-settings'
import { cn } from '@/lib/utils'

import {
  fieldHasRoundTag,
  filterByRound,
  formatCaseParamValue,
  getDeviceName,
  getReferenceTextValue,
  getResultTextValue,
  normalizeAlgorithmResult,
  parseFieldRoundTag,
  type RoundTab,
} from './case-report-utils'
import { ResultField } from './result-field'
import { TimelineComparison } from './timeline-comparison'
import { AudioTimeline } from './audio-timeline'
import { AudioPlayerModal, type AudioItemMeta } from './audio-player-modal'
import { hasTimelineData } from '@/application/report-view/use-timeline-comparison'

const META_CODES = new Set([
  'test_type',
  'testType',
  'algorithm_type',
  'algorithmType',
  'total_rounds',
  'totalRounds',
  'aggregated',
  'multi_round',
  'multiRound',
  'multi_round_result',
  'session_id',
  'sessionId',
  'context_mode',
  'contextMode',
  'error',
])
const DISPLAY_TYPES = new Set(['text', 'timestamp', 'number', 'boolean', 'json', 'audio_file'])

/** 音频外链 scheme 白名单（P3：拒绝 javascript:/data: 等危险 scheme 作 href） */
function isSafeHttpUrl(url?: string): url is string {
  if (!url) return false
  return /^https?:\/\//i.test(url)
}

interface ResultTextField {
  paramCode: string
  label: string
  paramType?: string
  roundNumber?: number
  dimensionName?: string
  getValue: (device?: string) => string
}

interface ExecutionResultsProps {
  caseItem: ReportCaseItem
  report: ReportDetailData
  roundTabs: RoundTab[]
  activeRoundTab: string
  setActiveRoundTab: (label: string) => void
  activeRoundTag: string | null
  /** §3.5.10 显示设置（不传 = 全显）；控制执行结果子项与资源 / 维度裁剪 */
  display?: CaseDisplaySettings
}

export function ExecutionResults({
  caseItem,
  report,
  roundTabs,
  activeRoundTab,
  setActiveRoundTab,
  activeRoundTag,
  display,
}: ExecutionResultsProps) {
  const [playingAudio, setPlayingAudio] = useState<AudioItemMeta>()
  const [activeDimTab, setActiveDimTab] = useState(0)

  const fieldMapping = report.summary.field_mappings?.[0]?.algorithmType
  const headers = report.summary.resource_headers ?? []
  const resourceMetrics = useMemo(() => extractCaseResourceMetrics(caseItem), [caseItem])
  const allResources = Object.keys(resourceMetrics)
  const hiddenResources = display?.hiddenResources ?? []
  const resources = allResources.filter((r) => !hiddenResources.includes(r))
  const isComparison = allResources.length > 1
  const hiddenMetrics = display?.hiddenMetrics ?? []
  const hiddenRounds = display?.hiddenRounds ?? []
  const show = (key: Parameters<typeof isExecutionChildVisible>[1]) =>
    display ? isExecutionChildVisible(display, key) : true

  // ---- 参考数据字段（referenceParams text + fieldMapping.reference 补充，按轮次排序） ----
  const referenceFields = useMemo(() => {
    const refParams = caseItem.referenceParams ?? {}
    const result: ResultTextField[] = []
    const seenCodes = new Set<string>()
    for (const [code, data] of Object.entries(refParams)) {
      if (!data || typeof data !== 'object') continue
      if (data.type !== 'text') continue
      const text = (data.text ?? data.value ?? '') as string
      if (typeof text !== 'string' || !text.trim()) continue
      seenCodes.add(code)
      const roundMatch = code.match(/^(.*)@round:(\d+)$/i)
      const roundNumber = (data as ReportReferenceParam & { round_number?: number }).round_number
      result.push({
        paramCode: code,
        label: (data as ReportReferenceParam & { label?: string }).label || (roundMatch ? `${roundMatch[1]} (第${roundMatch[2]}轮)` : code),
        paramType: 'text',
        roundNumber,
        getValue: () => text,
      })
    }
    // 补充 fieldMapping.reference 里定义但 referenceParams 未覆盖的 text 字段（reference 为 param_code 数组）
    const refCodes = fieldMapping?.reference ?? []
    for (const code of refCodes) {
      if (seenCodes.has(code)) continue
      const text = getReferenceTextValue(code, refParams)
      if (text && text.trim() && text !== '无数据') {
        seenCodes.add(code)
        const roundMatch = code.match(/^(.*)@round:(\d+)$/i)
        result.push({
          paramCode: code,
          label: roundMatch ? `${roundMatch[1]} (第${roundMatch[2]}轮)` : code,
          paramType: 'text',
          getValue: () => text,
        })
      }
    }
    result.sort((a, b) => (a.roundNumber ?? 0) - (b.roundNumber ?? 0) || a.paramCode.localeCompare(b.paramCode))
    return result
  }, [caseItem.referenceParams, fieldMapping])

  // ---- 结果文本字段（algorithmResults 扁平项 + fieldMapping.result 补充） ----
  const resultFields = useMemo(() => {
    const algoResults = (caseItem.algorithmResults ?? []).map(normalizeAlgorithmResult)
    const result: ResultTextField[] = []
    const seenCodes = new Set<string>()
    for (const item of algoResults) {
      const code = item.param_code
      if (!code || META_CODES.has(code) || code.startsWith('rounds')) continue
      if (!DISPLAY_TYPES.has(item.param_type ?? 'text')) continue
      if (seenCodes.has(code)) continue
      seenCodes.add(code)
      result.push({
        paramCode: code,
        label: item.label || code,
        paramType: item.param_type,
        roundNumber: item.round_number,
        dimensionName: item.dimension_name,
        getValue: (device?: string) => getResultTextValue(device, code, caseItem.algorithmResults ?? [], isComparison),
      })
    }
    // 补充 fieldMapping.result 里定义、algorithmResults 中有对应值的字段（result 为 param_code 数组）
    const fmCodes = (fieldMapping?.result ?? []).filter(
      (code) => code && !META_CODES.has(code) && !code.startsWith('rounds')
    )
    const allResultCodes = new Set(algoResults.map((i) => i.param_code))
    for (const code of fmCodes) {
      if (seenCodes.has(code) || !allResultCodes.has(code)) continue
      seenCodes.add(code)
      result.push({
        paramCode: code,
        label: code,
        getValue: (device?: string) => getResultTextValue(device, code, caseItem.algorithmResults ?? [], isComparison),
      })
    }
    result.sort((a, b) => (a.roundNumber ?? 0) - (b.roundNumber ?? 0) || a.paramCode.localeCompare(b.paramCode))
    return result
  }, [caseItem.algorithmResults, fieldMapping, isComparison])

  // ---- 用例参数字段（块四，按轮次排序） ----
  const caseParamFields = useMemo(() => {
    const fields: (ResultTextField & { value: string })[] = []
    for (const [code, p] of Object.entries(caseItem.caseParams ?? {})) {
      if (!p || typeof p !== 'object') continue
      const roundNumber =
        (p as ReportReferenceParam & { round_number?: number }).round_number ??
        (code.match(/@round:(\d+)$/i)?.[1] ? Number(code.match(/@round:(\d+)$/i)?.[1]) : undefined)
      fields.push({
        paramCode: code,
        label: (p as ReportReferenceParam & { label?: string }).label || (roundNumber !== undefined ? `${code.replace(/@round:\d+$/i, '')} (第${roundNumber}轮)` : code),
        paramType: p.type,
        roundNumber,
        value: formatCaseParamValue(p.value),
        getValue: () => '',
      })
    }
    fields.sort((a, b) => (a.roundNumber ?? 0) - (b.roundNumber ?? 0) || a.paramCode.localeCompare(b.paramCode))
    return fields
  }, [caseItem.caseParams])

  // ---- 多轮场景判定 + 当前轮次过滤 ----
  const isMultiRoundFields = useMemo(
    () =>
      resultFields.some(fieldHasRoundTag) ||
      referenceFields.some(fieldHasRoundTag) ||
      caseParamFields.some(fieldHasRoundTag),
    [resultFields, referenceFields, caseParamFields]
  )

  const currentRefFields = useMemo(
    () => (isMultiRoundFields ? filterByRound(referenceFields, activeRoundTag) : referenceFields),
    [referenceFields, isMultiRoundFields, activeRoundTag]
  )
  const currentCaseParamFields = useMemo(
    () => (isMultiRoundFields ? filterByRound(caseParamFields, activeRoundTag) : caseParamFields),
    [caseParamFields, isMultiRoundFields, activeRoundTag]
  )
  const currentResultFields = useMemo(() => {
    if (!isMultiRoundFields) return resultFields
    if (activeRoundTag === 'overall') {
      // 无维度归属（设备/API）显示所有轮次；有维度归属（评估结果）只显示 @overall
      return resultFields.filter((f) => {
        if (!f.dimensionName) return true
        const tag = parseFieldRoundTag(f.paramCode, f.roundNumber)
        return tag === 'overall'
      })
    }
    return filterByRound(resultFields, activeRoundTag)
  }, [resultFields, isMultiRoundFields, activeRoundTag])

  // ---- 按维度分组（子维度归父维度组；无维度 → 设备/API 执行结果） ----
  const groupedFields = useMemo(() => {
    const groups = new Map<string | null, ResultTextField[]>()
    const order: (string | null)[] = []
    for (const field of currentResultFields) {
      let dimName: string | null = field.dimensionName || null
      if (dimName) {
        const config = report.summary.all_metrics.find((m) => m.name === dimName)
        if (config?.dimension_type === 'sub' && config.parent_dimension_name) {
          dimName = config.parent_dimension_name
        }
      }
      if (!groups.has(dimName)) {
        groups.set(dimName, [])
        order.push(dimName)
      }
      groups.get(dimName)?.push(field)
    }
    const result: { key: string; label: string; fields: ResultTextField[] }[] = []
    for (const key of order) {
      if (key !== null) {
        result.push({ key, label: key, fields: groups.get(key) ?? [] })
      }
    }
    const general = groups.get(null)
    if (general && general.length > 0) {
      result.push({ key: '_general', label: '设备/API 执行结果', fields: general })
    }
    return result
  }, [currentResultFields, report.summary.all_metrics])

  const evalGroups = useMemo(
    () => groupedFields.filter((g) => g.key !== '_general' && !hiddenMetrics.includes(g.key)),
    [groupedFields, hiddenMetrics]
  )
  /** 可见轮次 Tab（显示设置「轮次」） */
  const visibleRoundTabs = roundTabs.filter((t) => !t.roundTag || !hiddenRounds.includes(t.roundTag))
  const generalGroup = useMemo(
    () => groupedFields.find((g) => g.key === '_general') ?? { key: '_general', label: '设备/API 执行结果', fields: [] as ResultTextField[] },
    [groupedFields]
  )
  const safeDimTab = Math.min(activeDimTab, Math.max(0, evalGroups.length - 1))

  const hasTimeline = useMemo(() => {
    // fieldMapping.result/reference 显式声明的 rttm/stm 时间轴字段码
    const fm = fieldMapping
    const hasResultTimeline = (fm?.result ?? []).some((code) => /rttm|stm/i.test(code))
    const hasRefTimeline = (fm?.reference ?? []).some((code) => /rttm|stm/i.test(code))
    if (hasResultTimeline || hasRefTimeline) return true
    // 结果字段：rttm/stm 直接算时间轴；json 需值结构校验（rounds 等多轮结果数组不算，INT-951）
    if (
      (caseItem.algorithmResults ?? []).some((r) => {
        const pt = r.paramType ?? ''
        if (pt === 'rttm' || pt === 'stm') return true
        if (pt === 'json') return hasTimelineData(r.value)
        return false
      })
    )
      return true
    // 参考字段：key 含 rttm/stm 直接算；json 类 key 需值结构校验
    for (const [key, value] of Object.entries(caseItem.referenceParams ?? {})) {
      if (/rttm|stm/i.test(key) && value) return true
      if (/json/i.test(key) && value && hasTimelineData((value as ReportReferenceParam).json ?? (value as ReportReferenceParam).value)) return true
    }
    return false
  }, [fieldMapping, caseItem.algorithmResults, caseItem.referenceParams])

  const hasAudio = (caseItem.audios?.length ?? 0) > 0

  // 结果音频按设备分组（device_name 兜底 '默认'）
  const resultAudioGroups = useMemo(() => {
    const map = new Map<string, typeof caseItem.audios>()
    for (const audio of caseItem.audios ?? []) {
      const key = audio.device_name || '默认'
      const list = map.get(key) ?? []
      list.push(audio)
      map.set(key, list)
    }
    return [...map.entries()]
  }, [caseItem.audios])

  const openPlayer = (value: unknown, label: string) => {
    setPlayingAudio({
      audio_id: String(value),
      audio_name: label,
      audio_type: 'result',
    })
  }

  return (
    <div className='space-y-3'>
      <p className='text-sm font-semibold'>执行结果</p>

      {/* 多轮场景：轮次 Tab 控制执行结果与参考数据显示（§3.5.3） */}
      {isMultiRoundFields && visibleRoundTabs.length > 1 && (
        <div className='flex flex-wrap gap-1' role='tablist' aria-label='轮次切换'>
          {visibleRoundTabs.map((tab) => (
            <button
              key={tab.key}
              type='button'
              role='tab'
              aria-selected={activeRoundTab === tab.label}
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

      {/* 参考数据 */}
      {show('reference') && currentRefFields.length > 0 && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>参考数据</p>
          <div className='rounded-lg border'>
            {currentRefFields.map((field) => (
              <ResultField key={`ref_${field.paramCode}`} label={field.label} value={field.getValue()} type={field.paramType} />
            ))}
          </div>
        </div>
      )}

      {/* 用例参数（块四） */}
      {show('caseParams') && currentCaseParamFields.length > 0 && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>用例参数</p>
          <div className='rounded-lg border'>
            {currentCaseParamFields.map((field) => (
              <ResultField key={`case_${field.paramCode}`} label={field.label} value={field.value} type={field.paramType} />
            ))}
          </div>
        </div>
      )}

      {/* 评估结果（块五，维度 tab 切换） */}
      {show('evaluation') && evalGroups.length > 0 && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>评估结果</p>
          <div className='rounded-lg border p-2'>
            <div className='flex flex-wrap gap-1' role='tablist' aria-label='评估维度切换'>
              {evalGroups.map((group, idx) => (
                <button
                  key={group.key}
                  type='button'
                  role='tab'
                  aria-selected={safeDimTab === idx}
                  className={cn(
                    'rounded-md px-2 py-0.5 text-xs transition-colors',
                    safeDimTab === idx ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
                  )}
                  onClick={() => setActiveDimTab(idx)}
                >
                  {group.label}
                </button>
              ))}
            </div>
            <div className='mt-2 space-y-2'>
              {isComparison ? (
                // 对比模式：每设备一个 device-block（标题 = 资源 label）
                resources.map((device) => (
                  <div key={device}>
                    <p className='text-muted-foreground text-xs font-medium'>{getDeviceName(device, headers)}</p>
                    <div className='mt-1 rounded-lg border'>
                      {evalGroups[safeDimTab]?.fields.map((field, i) => (
                        <ResultField
                          key={`${device}_${field.paramCode}_${i}`}
                          label={field.label}
                          value={field.getValue(device)}
                          type={field.paramType}
                          onPlayAudio={(v) => openPlayer(v, field.label)}
                        />
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className='rounded-lg border'>
                  {evalGroups[safeDimTab]?.fields.map((field, i) => (
                    <ResultField
                      key={`res_${field.paramCode}_${i}`}
                      label={field.label}
                      value={field.getValue(undefined)}
                      type={field.paramType}
                      onPlayAudio={(v) => openPlayer(v, field.label)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 设备/API 执行结果（块六：结果文本 + 音频播放 + 执行状态） */}
      {show('deviceResults') && (generalGroup.fields.length > 0 || caseItem.results.length > 0) && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>设备/API 执行结果</p>
          {isComparison ? (
            <div className='space-y-2'>
              {resources.map((device) => (
                <div key={device}>
                  <p className='text-muted-foreground text-xs font-medium'>{getDeviceName(device, headers)}</p>
                  <div className='mt-1 rounded-lg border'>
                    {generalGroup.fields.length === 0 ? (
                      <p className='text-muted-foreground px-3 py-2 text-xs'>无结果字段</p>
                    ) : (
                      generalGroup.fields.map((field, i) => (
                        <ResultField
                          key={`${device}_${field.paramCode}_${i}`}
                          label={field.label}
                          value={field.getValue(device)}
                          type={field.paramType}
                          onPlayAudio={(v) => openPlayer(v, field.label)}
                        />
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className='rounded-lg border'>
              {generalGroup.fields.length === 0 ? (
                <p className='text-muted-foreground px-3 py-2 text-xs'>无结果字段</p>
              ) : (
                generalGroup.fields.map((field, i) => (
                  <ResultField
                    key={`res_${field.paramCode}_${i}`}
                    label={field.label}
                    value={field.getValue(undefined)}
                    type={field.paramType}
                    onPlayAudio={(v) => openPlayer(v, field.label)}
                  />
                ))
              )}
            </div>
          )}
          {/* 执行状态行（caseItem.results：每资源友好名 + 结果类型徽标 + 状态 + 时间） */}
          {caseItem.results.length > 0 && (
            <div className='mt-1 rounded-lg border'>
              {caseItem.results.map((r) => (
                <div key={r.resource} className='flex items-center justify-between gap-2 border-b px-3 py-1.5 text-xs last:border-0'>
                  <span className='flex min-w-0 items-center gap-1.5'>
                    <span className='truncate font-medium'>{getDeviceName(r.resource, headers)}</span>
                    {r.result_type && (
                      <Badge variant='outline' className='font-mono text-[10px]'>{resultTypeLabel(r.result_type)}</Badge>
                    )}
                  </span>
                  <span className='text-muted-foreground shrink-0'>
                    {statusLabel(r.status)}
                    {r.startTime && <span className='ms-2 font-mono'>{r.startTime}</span>}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 时间轴对比（§3.3.9） */}
      {show('timeline') && hasTimeline && <TimelineComparison caseItem={caseItem} report={report} />}

      {/* 音频时间轴（块七 §3.5.7） */}
      {show('audio') && hasAudio && <AudioTimeline audioList={caseItem.audios ?? []} />}

      {/* 结果音频（块七：按设备分组 + 播放外链/播放器） */}
      {show('audio') && resultAudioGroups.length > 0 && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>结果音频</p>
          <div className='space-y-2'>
            {resultAudioGroups.map(([device, audios]) => (
              <div key={device}>
                <p className='text-muted-foreground text-xs font-medium'>{device}</p>
                <div className='mt-1 flex flex-wrap gap-1.5'>
                  {audios.map((audio, idx) => (
                    <Badge key={String(audio.audio_id)} variant='outline' className='gap-1'>
                      {audio.audio_name ?? `音频 ${idx + 1}`}
                      {isSafeHttpUrl(audio.url) ? (
                        <a href={audio.url} target='_blank' rel='noreferrer' className='text-primary underline-offset-2 hover:underline'>
                          播放
                        </a>
                      ) : (
                        <button
                          type='button'
                          className='text-primary underline-offset-2 hover:underline'
                          onClick={() =>
                            setPlayingAudio({
                              audio_id: audio.audio_id,
                              audio_name: audio.audio_name ?? `音频 ${idx + 1}`,
                              audio_type: audio.audio_type,
                              spl: audio.spl,
                              play_order: audio.play_order,
                              noise_spl: audio.noise_spl,
                              device_name: audio.device_name,
                              // INT-1547 P2-2：透传真实地址/时长（相对路径由 Modal 经
                              // GET /audios/{id}/stream 换预签名地址后播放）
                              url: audio.url,
                              duration: audio.duration,
                            })
                          }
                        >
                          播放
                        </button>
                      )}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <AudioPlayerModal
        open={playingAudio !== undefined}
        onOpenChange={(open) => {
          if (!open) setPlayingAudio(undefined)
        }}
        audio={playingAudio}
      />
    </div>
  )
}

function statusLabel(status?: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    成功: '成功',
    success: '成功',
    failed: '执行失败',
    失败: '失败',
    skipped: '已跳过',
    跳过: '已跳过',
    pending: '排队中',
    'in-progress': '执行中',
    warning: '警告',
    警告: '警告',
  }
  return map[status ?? ''] ?? status ?? '—'
}

/** 结果类型中文（V9.7.10 result_type 后缀：realtime→实时/final→最终，缺省原样） */
function resultTypeLabel(resultType?: string) {
  const map: Record<string, string> = {
    realtime: '实时',
    final: '最终',
    recording: '录音',
    default: '默认',
  }
  return map[resultType ?? ''] ?? resultType ?? ''
}
