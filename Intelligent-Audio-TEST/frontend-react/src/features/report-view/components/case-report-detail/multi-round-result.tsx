/**
 * 块二：多轮对话结果（15_报告域.md §3.5.2，TestCaseReportDetail 块二对位）。
 *
 * **判定（INT-2120，对齐 V9.7.10 `parseMultiRoundResult`）**：只认真正的 rounds 源
 * （项自身 `rounds` 数组 / `value` 对象内含 `rounds` 数组 / `param_code` 以 `rounds`
 * 开头且 value 即数组）。`round_details@round:N` 这类按轮展开的 json 数组**不是**
 * rounds 源 → 整块不渲染（含标题），不再出现「多轮对话结果 (1 轮)」假块。
 *
 * **字段渲染（对齐 V9.7.10 模板 `v-if` 语义）**：聚合卡只渲染有值字段；每轮展开的
 * 输入音频 / ASR 输出 / 参考文本 / 延迟 / 打断 / 维度评分 / LLM 评语都按「有值才渲染」，
 * 不再出现「—」占位卡片与占位行。
 */
import { ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import type { ReportCaseItem } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import {
  extractLlmReasoning,
  findMultiRoundSource,
  getReferenceTextValue,
  type MultiRoundAggregated,
  type MultiRoundSource,
} from './case-report-utils'

interface RoundEvaluation {
  wer?: number
  llm_judge?: number
  latency?: number
  reasoning?: string
  raw_response?: unknown
  [key: string]: unknown
}

interface RoundData {
  latency?: number
  interruption?: { detected?: boolean; timestamp?: number }
  input?: { audio_name?: string }
  output?: { asr_text?: string }
  evaluation?: RoundEvaluation
  round_evaluation?: RoundEvaluation
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

const asNumber = (v: unknown): number | undefined =>
  typeof v === 'number' && Number.isFinite(v) ? v : undefined

export function MultiRoundResult({ caseItem }: { caseItem: ReportCaseItem }) {
  const multiRound = useMemo<MultiRoundSource | null>(
    () => findMultiRoundSource(caseItem.algorithmResults),
    [caseItem.algorithmResults]
  )
  const aggregated = useAggregated(multiRound)
  const [expanded, setExpanded] = useState<number>()

  // hooks 已全部调用完毕：无真实 rounds 源 → 整块不渲染
  if (!multiRound || multiRound.rounds.length === 0) return null

  const rounds = multiRound.rounds as unknown as RoundData[]
  const aggregateCards = [
    {
      label: '平均 WER',
      value: aggregated.avg_wer == null ? '' : `${aggregated.avg_wer.toFixed(2)}%`,
    },
    {
      label: '平均 LLM 评分',
      value: aggregated.avg_llm_judge == null ? '' : aggregated.avg_llm_judge.toFixed(1),
    },
    {
      label: '平均延迟',
      value: aggregated.avg_latency == null ? '' : `${aggregated.avg_latency.toFixed(0)}ms`,
    },
    {
      label: '打断次数',
      value: aggregated.interruption_count == null ? '' : String(aggregated.interruption_count),
    },
  ].filter((card) => card.value !== '')

  return (
    <div className='space-y-2'>
      <p className='text-sm font-semibold'>多轮对话结果 ({rounds.length} 轮)</p>

      {/* 聚合卡：只渲染有值字段（V9.7.10 `v-if="aggregatedMetrics.xxx != null"`） */}
      {aggregateCards.length > 0 && (
        <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
          {aggregateCards.map((card) => (
            <AggregateStat key={card.label} label={card.label} value={card.value} />
          ))}
        </div>
      )}

      {/* 每轮展开 */}
      <div className='space-y-1.5'>
        {rounds.map((round, index) => {
          const roundNum = index + 1
          const open = expanded === index
          const evalData = round.evaluation || round.round_evaluation || null
          const latency = asNumber(evalData?.latency) ?? asNumber(round.latency)
          const det = round.interruption?.detected === true
          const refText = getRoundReferenceText(caseItem, roundNum)
          const reasoning = extractLlmReasoning(evalData as Record<string, unknown> | undefined)
          const evalBadges: { key: 'wer' | 'llm_judge' | 'latency'; value: number }[] = evalData
            ? (['wer', 'llm_judge', 'latency'] as const)
                .map((key) => ({ key, value: asNumber(evalData[key]) }))
                .filter((entry): entry is { key: 'wer' | 'llm_judge' | 'latency'; value: number } => entry.value !== undefined)
            : []
          return (
            <div key={index} className='rounded-lg border'>
              <button
                type='button'
                className='flex w-full items-center gap-2 px-3 py-2 text-start text-sm'
                onClick={() => setExpanded(open ? undefined : index)}
              >
                <span className='font-medium'>第 {roundNum} 轮</span>
                {latency != null && (
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
                  {round.input?.audio_name && <InfoRow label='输入音频' value={round.input.audio_name} />}
                  {round.output?.asr_text && <InfoRow label='ASR 输出' value={round.output.asr_text} mono />}
                  {refText && <InfoRow label='参考文本' value={refText} />}
                  {latency != null && <InfoRow label='延迟' value={`${latency}ms`} />}
                  {det && (
                    <InfoRow
                      label='打断'
                      value={round.interruption?.timestamp !== undefined ? `${round.interruption.timestamp}s` : '检测到打断'}
                    />
                  )}
                  {evalBadges.length > 0 && (
                    <div className='flex flex-wrap items-start gap-1.5'>
                      <span className='text-muted-foreground shrink-0'>维度评分：</span>
                      <div className='flex flex-wrap gap-1'>
                        {evalBadges.map(({ key, value }) => (
                          <Badge key={key} variant='outline'>
                            {metricLabel(key)}{' '}
                            {key === 'wer'
                              ? `${value.toFixed(2)}%`
                              : key === 'latency'
                                ? `${value.toFixed(0)}ms`
                                : value.toFixed(1)}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {reasoning && <InfoRow label='LLM 评语' value={reasoning} full />}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** 参考文本按轮读取（referenceParams.answer@round:N → 参考文本字段兜底；无值返回空串） */
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
  // 兜底：参考文本首条（照 V9.7.10 getReferenceTextForRound；无值不渲染该行）
  const first = Object.values(refs).find((p) => p.type === 'text')
  return ((first?.text ?? first?.value ?? '') as string) || ''
}

/**
 * 聚合卡计算（照 V9.7.10 `aggregatedMetrics`）：
 * 优先后端 aggregated；兜底由各轮 evaluation / latency / interruption 自算。
 * 无值字段保持 undefined（模板侧不渲染，不出现「—」占位）。
 */
function useAggregated(data: MultiRoundSource | null): MultiRoundAggregated {
  return useMemo(() => {
    if (!data) return {}
    if (data.aggregated && Object.keys(data.aggregated).length > 0) {
      return {
        avg_wer: data.aggregated.avg_wer,
        avg_llm_judge: data.aggregated.avg_llm_judge,
        avg_latency: data.aggregated.avg_latency,
        interruption_count: data.aggregated.interruption_count,
      }
    }
    const rounds = data.rounds as unknown as RoundData[]
    if (rounds.length === 0) return {}
    const result: MultiRoundAggregated = {}
    const evals = rounds
      .map((r) => r.evaluation || r.round_evaluation)
      .filter((e): e is RoundEvaluation => Boolean(e))
    // 只统计**真有数值**的轮次：空 evaluation（{}）不算 0 分，避免凭空出现 0.00% 聚合卡
    const werValues = evals.map((e) => asNumber(e.wer)).filter((v): v is number => v !== undefined)
    if (werValues.length > 0) {
      result.avg_wer = werValues.reduce((sum, v) => sum + v, 0) / werValues.length
    }
    const llmVals = evals.map((e) => asNumber(e.llm_judge)).filter((v): v is number => v !== undefined)
    const llmSum = llmVals.reduce((sum, v) => sum + v, 0)
    if (llmVals.length > 0 && llmSum > 0) {
      result.avg_llm_judge = llmSum / llmVals.length
    }
    const latencies = rounds
      .map((r) => asNumber((r.evaluation || r.round_evaluation)?.latency) ?? asNumber(r.latency))
      .filter((v): v is number => v !== undefined)
    if (latencies.length > 0) {
      result.avg_latency = latencies.reduce((sum, v) => sum + v, 0) / latencies.length
    }
    const interruptionCount = rounds.filter((r) => r.interruption?.detected === true).length
    if (interruptionCount > 0) result.interruption_count = interruptionCount
    return result
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
