/**
 * 评估维度多选区（用例编辑抽屉 §5.1 轮次评估步骤 / §5.1.3.1 整体评估 / 批量设置评估维度
 * / 音频导入上传选项共用）。照 V9.7.10 DimensionConfigPanel/RoundEvaluationEditor 的
 * **平铺 chips 云**形态：搜索框「搜索评估维度」+「已选 {n} 项」计数 + 平铺维度 chip
 * （未选 Plus / 已选 Check 图标），点击单个维度即勾选/取消（主/子维度同屏平铺，各自独立勾选，
 * 不做主/子联动分组——V9.7.10 实测口径）。
 * requiresAudio 维度带音乐图标（title「该维度需要音频文件，将随多轮音频一起上传」）。
 * 空态三态：「没有匹配的评估维度」/「暂无可用维度（当前算法类型无关联维度）」/「暂无可用维度」。
 * 注：Dimension.id 为 number|string，mock 全为 number——组件内部统一 Number() 归一。
 */
import { Check, Music4, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { Dimension } from '@/domain/models/evaluationDimension'

/**
 * requiresAudio 维度（mock 侧：随多轮音频一起上传，音乐图标 + title 提示）。
 * 注：当前按维度 id 硬编码（审计 P4-1，mock 阶段可接受）；接线后改随维度模型数据驱动——
 * 建议 Dimension 增 requiresAudio 布尔字段，由 d.requiresAudio 判断，不再维护 id 集合。
 */
const REQUIRES_AUDIO_DIMENSION_IDS = new Set<number>([11])

const dimId = (d: Dimension) => Number(d.id)

export function DimensionPicker({
  dimensions,
  algorithmType,
  selected,
  onToggle,
  showSearch = true,
}: {
  dimensions: Dimension[]
  algorithmType?: string | null
  selected: number[]
  onToggle: (ids: number[], checked: boolean) => void
  showSearch?: boolean
}) {
  const [search, setSearch] = useState('')

  /** 按当前算法过滤可用维度（associated_algorithms 口径；无算法=全量） */
  const algoFiltered = useMemo(() => {
    if (!algorithmType) return dimensions
    return dimensions.filter((d) =>
      d.associatedAlgorithms?.some((a) => a.algorithmType === algorithmType)
    )
  }, [dimensions, algorithmType])

  const keyword = search.trim().toLowerCase()

  /** 搜索命中（名称/描述/keywords，与 §5.1.3.1 搜索口径一致） */
  const searched = useMemo(() => {
    if (!keyword) return algoFiltered
    return algoFiltered.filter((d) => {
      const hay = [d.name, d.description ?? '', d.keywords ?? '']
        .join(' ')
        .toLowerCase()
      return hay.includes(keyword)
    })
  }, [algoFiltered, keyword])

  // 空态三态（V9.7.10 口径）：搜索无结果 → 算法无关联 → 全量无维度
  let empty: string | null = null
  if (keyword && searched.length === 0) empty = '没有匹配的评估维度'
  else if (algoFiltered.length === 0 && algorithmType) empty = '暂无可用维度（当前算法类型无关联维度）'
  else if (dimensions.length === 0) empty = '暂无可用维度'

  return (
    <div className='space-y-2'>
      {showSearch && (
        <div className='flex items-center gap-2'>
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder='搜索评估维度'
            className='h-8'
            aria-label='搜索评估维度'
          />
          <span className='text-muted-foreground shrink-0 text-xs tabular-nums'>
            已选 {selected.length} 项
          </span>
        </div>
      )}
      {empty ? (
        <p className='text-muted-foreground py-3 text-center text-sm'>{empty}</p>
      ) : (
        <div className='flex flex-wrap gap-1.5'>
          {searched.map((dim) => {
            const id = dimId(dim)
            const checked = selected.includes(id)
            const requiresAudio = REQUIRES_AUDIO_DIMENSION_IDS.has(id)
            return (
              <button
                key={id}
                type='button'
                onClick={() => onToggle([id], !checked)}
                aria-pressed={checked}
                className={cn(
                  'flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition-colors',
                  checked
                    ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                    : 'hover:bg-accent border-border text-muted-foreground'
                )}
              >
                {checked ? (
                  <Check aria-hidden='true' className='size-3' />
                ) : (
                  <Plus aria-hidden='true' className='size-3' />
                )}
                <span className='truncate'>{dim.name}</span>
                {requiresAudio && (
                  <span title='该维度需要音频文件，将随多轮音频一起上传'>
                    <Music4 aria-hidden='true' className='size-3.5 shrink-0' />
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
