/**
 * 批量弹窗共享片段（11_用例域.md §5.3 九件套统一口径）。
 * 轮次范围（RadioGroup「所有轮次/指定轮次」→ 指定轮次展开轮次号 Checkbox 组「第{n}轮」）
 * + 应用层级多选（目标人音频/case级背景噪声/segment级背景噪声/干扰人/声纹，§5.3.2~5.3.4 同口径）。
 * 内部受控状态随弹窗重新挂载即重置；数据契约 roundMode/rounds/appliedLayers 留接线批次。
 */
import { useState } from 'react'

import { Checkbox } from '@/components/ui/checkbox'

export type RoundScopeMode = 'all' | 'specific'

export function RoundScopeField({
  name,
  roundCount = 4,
}: {
  /** radio name（同页多弹窗实例隔离，防表单串扰） */
  name: string
  /** mock 轮次数（§5.3.1~5.3.4 演示第 1~N 轮，接线后按选中用例实际轮次） */
  roundCount?: number
}) {
  const [mode, setMode] = useState<RoundScopeMode>('all')
  const [selected, setSelected] = useState<number[]>([])

  const toggleRound = (round: number) => {
    setSelected((prev) =>
      prev.includes(round) ? prev.filter((r) => r !== round) : [...prev, round]
    )
  }

  return (
    <div className='space-y-2'>
      <span className='text-sm font-medium'>轮次范围</span>
      <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
        <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
          <input
            type='radio'
            name={name}
            checked={mode === 'all'}
            onChange={() => setMode('all')}
          />
          所有轮次
        </label>
        <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
          <input
            type='radio'
            name={name}
            checked={mode === 'specific'}
            onChange={() => setMode('specific')}
          />
          指定轮次
        </label>
      </div>
      {mode === 'specific' && (
        <div className='border-border/60 flex flex-wrap gap-1.5 rounded-lg border p-2'>
          {Array.from({ length: roundCount }, (_, i) => i + 1).map((round) => (
            <label
              key={round}
              className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'
            >
              <Checkbox
                checked={selected.includes(round)}
                onCheckedChange={() => toggleRound(round)}
              />
              第{round}轮
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

/** 应用层级五项（§5.3.2~5.3.4；noise 弹窗默认勾选 case级/segment级背景噪声） */
export const APPLY_LAYERS = [
  { id: 'target', label: '目标人音频' },
  { id: 'case-bg', label: 'case级背景噪声' },
  { id: 'segment-bg', label: 'segment级背景噪声' },
  { id: 'interferer', label: '干扰人' },
  { id: 'voiceprint', label: '声纹' },
] as const

export type ApplyLayerId = (typeof APPLY_LAYERS)[number]['id']

export function ApplyLayerField({
  defaultChecked = [],
}: {
  /** 默认勾选的层级 id（§5.3.4 默认 case级/segment级背景噪声） */
  defaultChecked?: ApplyLayerId[]
}) {
  const [checked, setChecked] = useState<Set<string>>(() => new Set(defaultChecked))

  const toggle = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className='space-y-2'>
      <span className='text-sm font-medium'>应用层级</span>
      <div className='flex flex-wrap gap-1.5'>
        {APPLY_LAYERS.map((layer) => (
          <label
            key={layer.id}
            className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'
          >
            <Checkbox
              checked={checked.has(layer.id)}
              onCheckedChange={() => toggle(layer.id)}
            />
            {layer.label}
          </label>
        ))}
      </div>
      <p className='text-muted-foreground/70 text-xs'>
        可多选；留空表示不应用任何层级
      </p>
    </div>
  )
}
