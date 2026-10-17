/**
 * 评估维度多选区（用例编辑抽屉 §5.1 轮次评估步骤 / §5.1.2 整体评估维度共用）。
 * 维度 chips 按主/子层级分组：主维度=描边 chip +「主」徽章 + 子维度数角标 + 展开/收起钮；
 * 子维度=「子」徽章；勾选主维度联动勾选/取消全部子维度；requiresAudio 维度带音乐图标。
 * 空态三态：「没有匹配的评估维度」/「暂无可用维度（当前算法类型无关联维度）」/「暂无可用维度」。
 * 搜索命中主维度带出整组、命中子维度带出父维度并自动展开（§5.1.2 交互）。
 * 注：Dimension.id 为 number|string，mock 全为 number——组件内部统一 Number() 归一。
 */
import { ChevronDown, Music4 } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  /** 按当前算法过滤可用维度（associated_algorithms 口径；无算法=全量） */
  const algoFiltered = useMemo(() => {
    if (!algorithmType) return dimensions
    return dimensions.filter((d) =>
      d.associatedAlgorithms?.some((a) => a.algorithmType === algorithmType)
    )
  }, [dimensions, algorithmType])

  const keyword = search.trim().toLowerCase()

  /** 原始搜索命中（主/子维度都算；渲染集合见 mainDims「带出整组」逻辑） */
  const searched = useMemo(() => {
    if (!keyword) return algoFiltered
    return algoFiltered.filter((d) => {
      const hay = [d.name, d.description ?? '', d.keywords ?? '']
        .join(' ')
        .toLowerCase()
      return hay.includes(keyword)
    })
  }, [algoFiltered, keyword])

  /** 全部子维度按父维度索引（搜索「带出整组」取完整子维度集，非仅命中项） */
  const allSubsByParent = useMemo(() => {
    const map = new Map<number, Dimension[]>()
    for (const d of algoFiltered) {
      if (d.dimensionType === 'sub' && d.parentDimensionId != null) {
        const p = Number(d.parentDimensionId)
        map.set(p, [...(map.get(p) ?? []), d])
      }
    }
    return map
  }, [algoFiltered])

  /** 渲染主维度集（§5.1.2 搜索交互：命中主维度带出整组、命中子维度带出父维度） */
  const mainDims = useMemo(() => {
    if (!keyword) return algoFiltered.filter((d) => d.dimensionType !== 'sub')
    const kept = new Map<number, Dimension>()
    for (const d of searched) {
      if (d.dimensionType !== 'sub') {
        kept.set(dimId(d), d)
      } else if (d.parentDimensionId != null) {
        const pid = Number(d.parentDimensionId)
        if (!kept.has(pid)) {
          const parent = algoFiltered.find((dd) => dimId(dd) === pid)
          if (parent) kept.set(pid, parent)
        }
      }
    }
    return [...kept.values()]
  }, [algoFiltered, searched, keyword])

  /** 渲染子维度集：搜索态=已渲染主维度的整组子维度；非搜索态=全量子维度索引 */
  const subsByParent = useMemo(() => {
    if (!keyword) return allSubsByParent
    const map = new Map<number, Dimension[]>()
    for (const m of mainDims) {
      const subs = allSubsByParent.get(dimId(m))
      if (subs) map.set(dimId(m), subs)
    }
    return map
  }, [allSubsByParent, mainDims, keyword])

  /** 搜索态自动展开全部已渲染主组（先并入渲染集合再展开：带出整组/父维度可见） */
  const effectiveExpanded = useMemo(() => {
    if (!keyword) return expanded
    const next = new Set(expanded)
    for (const m of mainDims) next.add(dimId(m))
    return next
  }, [expanded, mainDims, keyword])

  const toggleSubs = (mainId: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(mainId)) next.delete(mainId)
      else next.add(mainId)
      return next
    })
  }

  const isMainChecked = (mainId: number) => {
    const subs = subsByParent.get(mainId) ?? []
    return subs.length > 0
      ? subs.every((s) => selected.includes(dimId(s)))
      : selected.includes(mainId)
  }

  const handleMainToggle = (mainId: number, checked: boolean) => {
    const subs = subsByParent.get(mainId) ?? []
    onToggle([mainId, ...subs.map((s) => dimId(s))], checked)
  }

  // 空态三态（§5.1.2）：搜索无结果（以渲染主维度集为准）→ 算法无关联 → 全量无维度
  let empty: string | null = null
  if (keyword && mainDims.length === 0) empty = '没有匹配的评估维度'
  else if (algoFiltered.length === 0 && algorithmType) empty = '暂无可用维度（当前算法类型无关联维度）'
  else if (dimensions.length === 0) empty = '暂无可用维度'

  return (
    <div className='space-y-2'>
      {showSearch && (
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder='搜索评估维度'
          className='h-8'
          aria-label='搜索评估维度'
        />
      )}
      {empty ? (
        <p className='text-muted-foreground py-3 text-center text-sm'>{empty}</p>
      ) : (
        <div className='space-y-1.5'>
          {mainDims.map((dim) => {
            const mainId = dimId(dim)
            const subs = subsByParent.get(mainId) ?? []
            const isExpanded = effectiveExpanded.has(mainId)
            const checked = isMainChecked(mainId)
            const requiresAudio = REQUIRES_AUDIO_DIMENSION_IDS.has(mainId)
            return (
              <div key={mainId} className='space-y-1'>
                <div
                  className={cn(
                    'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                    checked
                      ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                      : 'hover:bg-accent border-border'
                  )}
                >
                  <button
                    type='button'
                    className='flex min-w-0 items-center gap-1.5'
                    aria-pressed={checked}
                    onClick={() => handleMainToggle(mainId, !checked)}
                  >
                    <span className='truncate'>{dim.name}</span>
                    <Badge variant='secondary' className='rounded-sm px-1 text-[10px]'>
                      主
                    </Badge>
                    {requiresAudio && (
                      <span title='该维度需要音频文件，将随多轮音频一起上传'>
                        <Music4 aria-hidden='true' className='size-3.5 shrink-0' />
                      </span>
                    )}
                  </button>
                  {subs.length > 0 && (
                    <>
                      <Badge className='rounded-sm px-1 font-mono text-[10px] tabular-nums'>
                        {subs.length}
                      </Badge>
                      <Button
                        type='button'
                        variant='ghost'
                        size='icon-sm'
                        className='size-5 rounded-full p-0'
                        aria-label={`展开/收起 ${dim.name} 子维度`}
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleSubs(mainId)
                        }}
                      >
                        <ChevronDown
                          aria-hidden='true'
                          className={cn('size-3.5 transition-transform', !isExpanded && '-rotate-90')}
                        />
                      </Button>
                    </>
                  )}
                </div>
                {isExpanded && subs.length > 0 && (
                  <div className='flex flex-wrap gap-1.5 ps-4'>
                    {subs.map((sub) => {
                      const subId = dimId(sub)
                      const subChecked = selected.includes(subId)
                      return (
                        <button
                          key={subId}
                          type='button'
                          onClick={() => onToggle([subId], !subChecked)}
                          aria-pressed={subChecked}
                          className={cn(
                            'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                            subChecked
                              ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                              : 'hover:bg-accent border-border'
                          )}
                        >
                          <span className='truncate'>{sub.name}</span>
                          <Badge variant='outline' className='rounded-sm px-1 text-[10px]'>
                            子
                          </Badge>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
