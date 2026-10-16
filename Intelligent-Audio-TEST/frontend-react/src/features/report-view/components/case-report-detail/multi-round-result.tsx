/**
 * 块二：多轮对话结果（15_报告域.md §3.5.2，parseMultiRoundResult 对位）。
 * 判定：algorithmResults 中首个含 rounds 数组的对象；聚合卡（平均 WER/LLM 评分/延迟/打断次数）
 * + 每轮展开（输入音频/ASR 输出/参考文本/延迟/打断/维度评分/LLM 评语）。
 */
import { ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import type { ReportAlgorithmResult, ReportCaseItem } from '@/domain/models/report'
import { cn } from '@/lib/utils'

interface RoundData {
  round: number
  input?: { audio_name?: string }
  output?: { asr_text?: string }
  evaluation?: { wer?: number; llm_judge?: number; latency?: number; reasoning?: string }
  interruption?: { detected?: boolean; timestamp?: number }
}

export function MultiRoundResult({ caseItem }: { caseItem: ReportCaseItem }) {
  const rounds = useMemo(() => {
    const first = (caseItem.algorithmResults ?? []).find((r) => Array.isArray((r as ReportAlgorithmResult & { rounds?: unknown[] }).rounds))
    const arr = (first as { rounds?: unknown } | undefined)?.rounds
    if (!Array.isArray(arr)) return null
    return arr as RoundData[]
  }, [caseItem.algorithmResults])

  if (!rounds || rounds.length === 0) return null

  const totalRounds = rounds.length
  const avg = (key: (r: RoundData) => number | undefined) => {
    const vals = rounds.map(key).filter((v): v is number => v !== undefined)
    if (vals.length === 0) return undefined
    return vals.reduce((s, v) => s + v, 0) / vals.length
  }
  const avgWER = avg((r) => r.evaluation?.wer)
  const avgJudge = avg((r) => r.evaluation?.llm_judge)
  const avgLatency = avg((r) => r.evaluation?.latency)
  const interruptions = rounds.filter((r) => r.interruption?.detected).length

  const [expanded, setExpanded] = useState<number>()

  return (
    <div className='space-y-2'>
      <p className='text-sm font-semibold'>多轮对话结果 ({totalRounds} 轮)</p>

      {/* 聚合卡 */}
      <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
        <AggregateStat label='平均 WER' value={avgWER === undefined ? '—' : `${avgWER.toFixed(2)}%`} />
        <AggregateStat label='平均 LLM 评分' value={avgJudge === undefined ? '—' : avgJudge.toFixed(1)} />
        <AggregateStat label='平均延迟' value={avgLatency === undefined ? '—' : `${avgLatency.toFixed(0)}s`} />
        <AggregateStat label='打断次数' value={String(interruptions)} />
      </div>

      {/* 每轮展开 */}
      <div className='space-y-1.5'>
        {rounds.map((round, index) => {
          const roundNum = index + 1
          const open = expanded === index
          const det = round.interruption?.detected
          return (
            <div key={index} className='rounded-lg border'>
              <button
                type='button'
                className='flex w-full items-center gap-2 px-3 py-2 text-start text-sm'
                onClick={() => setExpanded(open ? undefined : index)}
              >
                <span className='font-medium'>第 {roundNum} 轮</span>
                {round.evaluation?.latency !== undefined && (
                  <span className='text-muted-foreground text-xs'>
                    延迟 {round.evaluation.latency.toFixed(0)}ms
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
                  <InfoRow label='参考文本' value={caseItem.referenceParams?.[`answer@round:${roundNum}`]?.value ?? '—'} />
                  <InfoRow label='延迟' value={round.evaluation?.latency !== undefined ? `${round.evaluation.latency}ms` : '—'} />
                  <InfoRow label='打断' value={det ? (round.interruption?.timestamp !== undefined ? `${round.interruption.timestamp}s` : '检测到打断') : '未检测到'} />
                  <div className='flex flex-wrap gap-1.5'>
                    <span className='text-muted-foreground'>维度评分：</span>
                    {round.evaluation?.wer !== undefined && <Badge variant='outline'>WER {round.evaluation.wer.toFixed(2)}%</Badge>}
                    {round.evaluation?.llm_judge !== undefined && <Badge variant='outline'>LLM 评分 {round.evaluation.llm_judge.toFixed(1)}</Badge>}
                  </div>
                  <InfoRow label='LLM 评语' value={round.evaluation?.reasoning ?? '—'} full />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
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
