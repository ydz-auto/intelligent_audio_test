/**
 * 块二：多轮对话结果（15_报告域.md §3.5.2，parseMultiRoundResult 对位）。
 * 判定：algorithmResults 中首个含 rounds 数组的对象（兼容 round 0 基 / roundNumber 1 基）；
 * 聚合卡优先后端 aggregated（avg_wer/avg_llm_judge/avg_latency/interruption_count），兜底前端自算；
 * 每轮展开：输入音频/ASR 输出/参考文本/延迟/打断/维度评分徽章/LLM 评语（reasoning → raw_response 解析）。
 */
import { ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import type { ReportAlgorithmResult, ReportCaseItem } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { extractLlmReasoning, getReferenceTextValue } from './case-report-utils'

interface RoundEvaluation {
  wer?: number
  llm_judge?: number
  latency?: number
  reasoning?: string
  raw_response?: unknown
  [key: string]: unknown
}

interface RoundData {
  round?: number
  roundNumber?: number
  input?: { audio_name?: string }
  output?: { asr_text?: string }
  evaluation?: RoundEvaluation
  round_evaluation?: RoundEvaluation
  latency?: number
  interruption?: { detected?: boolean; timestamp?: number }
}

interface MultiRoundResultData {
  isMultiRound: boolean
  rounds: RoundData[]
  aggregated?: Record<string, number>
  totalRounds: number
}

const metricLabel = (key: string): string => {
  const labels: Record<string, string> = {
    avg_wer: '平均 WER',
    avg_latency: '平均延迟',
    avg_llm_judge: '平均 LLM 评分',
    interruption_count: '打断次数',
    total_latency: '总延迟',
    wer: 'WER',
    llm_judge: 'LLM 评分',
    latency: '延迟',
  }
  return labels[key] ?? key
}

export function MultiRoundResult({ caseItem }: { caseItem: ReportCaseItem }) {
  const multiRound = useMemo<MultiRoundResultData | null>(() => {
    const algoResults = caseItem.algorithmResults ?? []
    if (algoResults.length === 0) return null
    type Holder = { rounds?: unknown; aggregated?: Record<string, number> }
    // 直接挂在 item.rounds（mock 形态）或 item.value.rounds（快照嵌套形态）
    const holder = (algoResults as (ReportAlgorithmResult & Holder)[]).find((item) => {
      if (Array.isArray(item.rounds)) return true
      const v = item.value as { rounds?: unknown } | undefined
      return v && typeof v === 'object' && Array.isArray(v.rounds)
    })
    if (!holder) return null
    const source = Array.isArray(holder.rounds)
      ? holder
      : ((holder.value as Holder) ?? {})
    const rounds = (source.rounds ?? []) as RoundData[]
    if (!Array.isArray(rounds) || rounds.length === 0) return null
    return {
      isMultiRound: true,
      rounds,
      aggregated: source.aggregated,
      totalRounds: rounds.length,
    }
  }, [caseItem.algorithmResults])

  if (!multiRound || multiRound.rounds.length === 0) return null

  const rounds = multiRound.rounds
  const totalRounds = rounds.length

  // 聚合卡：优先后端 aggregated，兜底前端自算
  const aggregated = useAggregated(multiRound)
  const [expanded, setExpanded] = useState<number>()

  return (
    <div className='space-y-2'>
      <p className='text-sm font-semibold'>多轮对话结果 ({totalRounds} 轮)</p>

      {/* 聚合卡 */}
      <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
        <AggregateStat label='平均 WER' value={aggregated.avg_wer === undefined ? '—' : `${aggregated.avg_wer.toFixed(2)}%`} />
        <AggregateStat label='平均 LLM 评分' value={aggregated.avg_llm_judge === undefined ? '—' : aggregated.avg_llm_judge.toFixed(1)} />
        <AggregateStat label='平均延迟' value={aggregated.avg_latency === undefined ? '—' : `${aggregated.avg_latency.toFixed(0)}ms`} />
        <AggregateStat label='打断次数' value={String(aggregated.interruption_count ?? 0)} />
      </div>

      {/* 每轮展开 */}
      <div className='space-y-1.5'>
        {rounds.map((round, index) => {
          const roundNum = index + 1
          const open = expanded === index
          const evalData = round.evaluation || round.round_evaluation || null
          const latency = evalData?.latency ?? round.latency
          const det = round.interruption?.detected
          const refText = getRoundReferenceText(caseItem, roundNum)
          const reasoning = extractLlmReasoning(evalData as Record<string, unknown> | undefined)
          return (
            <div key={index} className='rounded-lg border'>
              <button
                type='button'
                className='flex w-full items-center gap-2 px-3 py-2 text-start text-sm'
                onClick={() => setExpanded(open ? undefined : index)}
              >
                <span className='font-medium'>第 {roundNum} 轮</span>
                {latency !== undefined && (
                  <span className='text-muted-foreground text-xs'>
                    延迟 {latency.toFixed(0)}ms
                  </span>
                )}
                {det && <Badge className='bg-destructive text-destructive-foreground'>打断</Badge>}
                <span className='flex-1' />
                <ChevronDown aria-hidden='true' className={cn('text-muted-foreground size-4 transition-transform', open && 'rotate-180')} />
              </button>
              {open && (
                <div className='grid gap-x-4 gap-y-1 border-t p-3 text-xs sm:grid-cols-2'>
                  <InfoRow label='输入音频' value={round.input?.audio_name ?? '—'} />
                  <InfoRow label='ASR 输出' value={round.output?.asr_text ?? '—'} mono />
                  <InfoRow label='参考文本' value={refText} />
                  <InfoRow label='延迟' value={latency !== undefined ? `${latency}ms` : '—'} />
                  <InfoRow
                    label='打断'
                    value={det ? (round.interruption?.timestamp !== undefined ? `${round.interruption.timestamp}s` : '检测到打断') : '未检测到'}
                  />
                  <div className='flex flex-wrap items-start gap-1.5'>
                    <span className='text-muted-foreground shrink-0'>维度评分：</span>
                    {evalData && Object.keys(evalData).length > 0 ? (
                      <div className='flex flex-wrap gap-1'>
                        {Object.entries(evalData)
                          .filter(([key]) => ['wer', 'llm_judge', 'latency'].includes(key))
                          .map(([key, value]) => {
                            if (typeof value !== 'number') return null
                            const label = metricLabel(key)
                            const text =
                              key === 'wer'
                                ? `${value.toFixed(2)}%`
                                : key === 'latency'
                                  ? `${value.toFixed(0)}ms`
                                  : value.toFixed(1)
                            return (
                              <Badge key={key} variant='outline'>
                                {label} {text}
                              </Badge>
                            )
                          })}
                      </div>
                    ) : (
                      <span>—</span>
                    )}
                  </div>
                  <InfoRow label='LLM 评语' value={reasoning || '—'} full />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** 参考文本按轮读取（referenceParams.answer@round:N → 参考文本字段兜底） */
function getRoundReferenceText(caseItem: ReportCaseItem, roundNum: number): string {
  const refs = caseItem.referenceParams ?? {}
  const direct = getReferenceTextValue(`answer@round:${roundNum}`, refs)
  if (direct) return direct
  for (const [code, p] of Object.entries(refs)) {
    if (code.match(/@round:(\d+)$/i)) {
      const rn = Number(code.match(/@round:(\d+)$/i)?.[1])
      if (rn === roundNum) {
        const text = (p.text ?? p.value ?? '') as string
        if (text) return text
      }
    }
  }
  // 兜底：参考文本首条（照 V9.7.10 getReferenceTextForRound）
  const first = Object.values(refs).find((p) => p.type === 'text')
  return ((first?.text ?? first?.value ?? '') as string) || '—'
}

/** 聚合卡计算（优先后端 aggregated；兜底由各轮 evaluation/latency/interruption 自算） */
function useAggregated(data: { aggregated?: Record<string, number>; rounds: RoundData[] }) {
  return useMemo(() => {
    if (data.aggregated && Object.keys(data.aggregated).length > 0) {
      return {
        avg_wer: data.aggregated.avg_wer,
        avg_llm_judge: data.aggregated.avg_llm_judge,
        avg_latency: data.aggregated.avg_latency,
        interruption_count: data.aggregated.interruption_count,
      }
    }
    const rounds = data.rounds ?? []
    const evals = rounds
      .map((r) => r.evaluation || r.round_evaluation)
      .filter((e): e is RoundEvaluation => Boolean(e))
    const avg = (key: (e: RoundEvaluation) => number | undefined) => {
      const vals = evals.map(key).filter((v): v is number => v !== undefined && v > 0)
      if (vals.length === 0) return undefined
      return vals.reduce((s, v) => s + v, 0) / vals.length
    }
    const avgWER = avg((e) => e.wer)
    const llmVals = evals.map((e) => e.llm_judge).filter((v): v is number => v !== undefined && v > 0)
    const latencies = rounds.map((r) => r.evaluation?.latency ?? r.latency).filter((v): v is number => v !== undefined)
    const interruptions = rounds.filter((r) => r.interruption?.detected).length
    return {
      avg_wer: avgWER,
      avg_llm_judge: llmVals.length > 0 ? llmVals.reduce((s, v) => s + v, 0) / llmVals.length : undefined,
      avg_latency: latencies.length > 0 ? latencies.reduce((s, v) => s + v, 0) / latencies.length : undefined,
      interruption_count: interruptions > 0 ? interruptions : undefined,
    }
  }, [data])
}

function AggregateStat({ label, value }: { label: string; value: string }) {
  return (
    <div className='bg-muted/40 rounded-lg border px-2.5 py-2'>
      <div className='text-muted-foreground text-[11px]'>{label}</div>
      <div className='text-foreground mt-0.5 font-mono text-sm font-semibold tabular-nums'>{value}</div>
    </div>
  )
}

function InfoRow({ label, value, mono, full }: { label: string; value: string; mono?: boolean; full?: boolean }) {
  return (
    <div className={cn('flex items-start justify-between gap-2', full && 'sm:col-span-2')}>
      <span className='text-muted-foreground shrink-0'>{label}</span>
      <span className={cn('min-w-0 flex-1 break-all text-right', mono && 'font-mono')}>{value}</span>
    </div>
  )
}
