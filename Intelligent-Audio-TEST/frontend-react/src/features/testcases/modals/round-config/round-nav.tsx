/**
 * 轮次导航（11_用例域.md §5.1 RoundConfigEditor 结构平移，左 180px）。
 * 轮次列表项「第 {n} 轮 + {x}音频·{y}维度」摘要；空轮次（0 音频 0 维度）标 destructive 色；
 * 底部「添加轮次/复制当前轮次」；行内删除钮（仅 1 轮禁用，删除前确认）。
 * RoundDraft 携带 evaluation（enabled + selectedIds + params，§5.1「启用本轮评估」）——
 * ⚠️ 实施注意②：addRound 已有轮次时复制上一轮 evaluation（V9.7.10 RoundConfigEditor.vue:252-254
 * 语义），「新轮次默认关闭」严格仅首轮成立，不额外重置 enabled。
 */
import { Copy, Plus, X } from 'lucide-react'
import { useState } from 'react'

import { ConfirmDialog } from '@/components/confirm-dialog'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** 单轮评估草稿（§5.1 评估维度步骤；params 按维度 id 存权重/阈值/LLM 配置） */
export interface RoundEvaluationDraft {
  /** 启用本轮评估（首轮默认开；addRound 复制上一轮 enabled） */
  enabled: boolean
  selectedIds: number[]
  params: Record<
    number,
    { weight: number; threshold: number; model?: string; promptTemplate?: string }
  >
}

/** 默认新轮评估草稿（enabled=false：新轮次默认关闭，首轮由调用方置 true） */
export const newRoundEvaluation = (): RoundEvaluationDraft => ({
  enabled: false,
  selectedIds: [],
  params: {},
})

/** 算法参数项（后端 AlgorithmParamItem：{field_code, field_value}；INT-996 独立列 params 数组元素） */
export interface RoundAlgorithmParamItem {
  field_code: string
  field_value: unknown
}

/** 轮次级背景噪声草稿（INT-996；保存写入 config.rounds[].audios[].background_noise） */
export interface RoundBackgroundNoiseDraft {
  audioId: number | string | null
  audioName?: string | null
  /** 冗余音频简报（音频选择弹窗回填 name/duration/tags；保存侧序列化时剔除） */
  audio?: {
    id: number | string
    name: string
    duration?: number | null
    tags?: string[]
  } | null
  /** 声压级（dB；§5.3.4 建议值 94） */
  spl: number
  /** 播放设备 id 列表（真实 /playback-devices） */
  deviceIds: Array<number | string>
  /** 循环播放 */
  loop: boolean
}

/** 轮次声纹注册草稿（INT-996；保存写入 algorithm_params 独立列 field_code='voiceprint'） */
export interface RoundVoiceprintDraft {
  enabled: boolean
  audioId: number | string | null
  audioName?: string | null
  playbackDeviceId: number | string | null
  /** 播放声压级（dB） */
  spl: number
  /** 注册后等待秒数（0-60） */
  waitSec: number
}

/** 单个干扰人草稿（INT-996；保存写入 config.rounds[].audios[].interferers） */
export interface RoundInterfererDraft {
  /** 本地行 id（仅渲染 key/删除定位用；保存序列化时剔除） */
  id: string
  audioId: number | string | null
  audioName?: string | null
  playbackDeviceId: number | string | null
  /** 声压级（dB） */
  spl: number
  /** 开始延迟秒 */
  startDelay: number
  /** 循环播放 */
  loop: boolean
}

/** 轮次噪声与干扰草稿（INT-996；算法参数步骤排除的 voiceprint/interferers/背景噪声集中在此） */
export interface RoundNoiseDraft {
  backgroundNoise: RoundBackgroundNoiseDraft | null
  voiceprint: RoundVoiceprintDraft
  interferers: RoundInterfererDraft[]
}

/** 默认空声纹草稿（§5.1 声纹注册配置节：播放声压级默认 75、等待 5s） */
export const emptyVoiceprint = (): RoundVoiceprintDraft => ({
  enabled: false,
  audioId: null,
  audioName: null,
  playbackDeviceId: null,
  spl: 75,
  waitSec: 5,
})

/** 默认空噪声与干扰草稿（背景噪声未配置 + 声纹关闭 + 无干扰人） */
export const emptyRoundNoise = (): RoundNoiseDraft => ({
  backgroundNoise: null,
  voiceprint: emptyVoiceprint(),
  interferers: [],
})

export interface RoundDraft {
  number: number
  audioCount: number
  dimensionCount: number
  evaluation: RoundEvaluationDraft
  /** INT-996 算法参数独立列 params（[{field_code, field_value}]；DynamicForm 排除声纹/干扰人/音频选择类字段） */
  algorithmParams: RoundAlgorithmParamItem[]
  /** INT-996 噪声与干扰草稿（背景噪声/声纹/干扰人） */
  noise: RoundNoiseDraft
}

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
