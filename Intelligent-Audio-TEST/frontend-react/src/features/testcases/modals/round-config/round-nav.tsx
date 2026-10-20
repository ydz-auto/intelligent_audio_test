/**
 * 轮次导航（11_用例域.md §5.1 RoundConfigEditor 结构平移，左 180px）。
 * 轮次列表项「第 {n} 轮 + {x}音频·{y}维度」摘要；空轮次（0 音频 0 维度）标 destructive 色；
 * 底部「添加轮次/复制当前轮次」；行内删除钮（仅 1 轮禁用，删除前确认）。
 * RoundDraft 携带 evaluation（enabled + selectedIds + params，§5.1「启用本轮评估」）+
 * audios（INT-877 音频草稿）+ algorithmParams/noise（INT-996 算法参数/噪声草稿）——
 * ⚠️ 实施注意②：addRound 已有轮次时复制上一轮 evaluation（V9.7.10 RoundConfigEditor.vue:252-254
 * 语义），「新轮次默认关闭」严格仅首轮成立，不额外重置 enabled。
 * 草稿类型定义收敛在 domain/models/testCaseRound（编辑抽屉/音频列表步骤/评估步骤共用），
 * 本组件 re-export 保持既有导入路径不变。
 */
import { Copy, Plus, X } from 'lucide-react'
import { useState } from 'react'

import { ConfirmDialog } from '@/components/confirm-dialog'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  emptyRoundNoise,
  emptyVoiceprint,
  newRoundEvaluation,
  type RoundAlgorithmParamItem,
  type RoundAudioDraft,
  type RoundBackgroundNoiseDraft,
  type RoundDraft,
  type RoundEvaluationDraft,
  type RoundInterfererDraft,
  type RoundNoiseDraft,
  type RoundVoiceprintDraft,
} from '@/domain/models/testCaseRound'

export type {
  RoundAlgorithmParamItem,
  RoundAudioDraft,
  RoundBackgroundNoiseDraft,
  RoundDraft,
  RoundEvaluationDraft,
  RoundInterfererDraft,
  RoundNoiseDraft,
  RoundVoiceprintDraft,
}
export { newRoundEvaluation, emptyRoundNoise, emptyVoiceprint }

export function RoundNav({
  rounds,
  activeRound,
  onSelect,
  onAdd,
  onCopy,
  onDelete,
}: {
  rounds: RoundDraft[]
  activeRound: number
  onSelect: (number: number) => void
  onAdd: () => void
  onCopy: () => void
  onDelete: (number: number) => void
}) {
  const [confirmRound, setConfirmRound] = useState<number | null>(null)

  return (
    <div className='border-border/60 flex shrink-0 flex-col border-b p-2 sm:w-44 sm:border-r sm:border-b-0'>
      <div className='space-y-1.5'>
        {rounds.map((round) => {
          const empty = round.audioCount === 0 && round.dimensionCount === 0
          const active = round.number === activeRound
          return (
            <div
              key={round.number}
              className={cn(
                'hover:bg-accent group flex items-center justify-between rounded-md transition-colors',
                active && 'bg-accent'
              )}
            >
              <button
                type='button'
                className='flex min-w-0 flex-1 items-center justify-between gap-1 rounded-md px-2 py-1.5 text-start text-sm'
                onClick={() => onSelect(round.number)}
              >
                <span className={cn('font-medium', empty && 'text-destructive')}>
                  第 {round.number} 轮
                </span>
                <span
                  className={cn(
                    'text-muted-foreground text-xs tabular-nums',
                    empty && 'text-destructive/70'
                  )}
                >
                  {empty ? '未配置' : `${round.audioCount} 音频·${round.dimensionCount} 维度`}
                </span>
              </button>
              <button
                type='button'
                aria-label={`删除第 ${round.number} 轮`}
                disabled={rounds.length <= 1}
                className='text-muted-foreground hover:text-destructive invisible group-hover:visible rounded p-1 disabled:opacity-30'
                onClick={() => {
                  if (rounds.length > 1) setConfirmRound(round.number)
                }}
              >
                <X aria-hidden='true' className='size-3.5' />
              </button>
            </div>
          )
        })}
      </div>
      <div className='mt-2 flex flex-col gap-1.5 border-t pt-2'>
        <Button type='button' variant='ghost' size='sm' className='h-7 gap-1' onClick={onAdd}>
          <Plus aria-hidden='true' className='size-3.5' />
          添加轮次
        </Button>
        <Button type='button' variant='ghost' size='sm' className='h-7 gap-1' onClick={onCopy}>
          <Copy aria-hidden='true' className='size-3.5' />
          复制当前轮次
        </Button>
      </div>
      <ConfirmDialog
        open={confirmRound != null}
        onOpenChange={(open) => !open && setConfirmRound(null)}
        title='删除轮次'
        desc={`确定要删除第 ${confirmRound ?? ''} 轮吗？该操作不可撤销。`}
        confirmText='删除'
        destructive
        handleConfirm={() => {
          if (confirmRound != null) onDelete(confirmRound)
          setConfirmRound(null)
        }}
      />
    </div>
  )
}
