/**
 * 评估维度多选区（用例编辑抽屉 §5.1 轮次评估步骤 / §5.1.3.1 整体评估 / 批量设置评估维度
 * / 音频导入上传选项共用）。照 V9.7.10 DimensionConfigPanel.buildCloudGroups + DimensionCloud
 * 的**主/子分组云**形态（负责人 2026-10-18 裁定：三个评估维度模态窗不能平铺，照 V9.7.10
 * 组织主维度/子维度，可加分组）：
 * 搜索框「搜索评估维度」+「已选 {n} 项」计数 + 主维度 chip（「主」徽章 + 子维度数角标，
 * 勾选联动全部子维度）+ 子维度 chip（「子」徽章 + 树形分支符「└」，点击只勾选自身）。
 * - **分类分组（负责人 2026-10-19「选A 得把 评估维度分组/分类也加上，咱们评估维度已经
 *   分组/分类了」）**：传入 categories 时按维度 categoryId 聚合分类组头（分类名 + 该分类
 *   可见维度数），组内再按主/子分组云；未传入 categories 时保持整片主/子分组云。
 * - 搜索命中子维度时带出父维度作为上下文（整组只展示命中的子维度）；
 * - 搜索命中主维度时整组展示（非搜索时展示全部子维度）；
 * - 父维度不在候选集（如被算法关联过滤）的子维度作「孤儿子维度」兜底（附父名提示）。
 * requiresAudio 维度带音乐图标（title「该维度需要音频文件，将随多轮音频一起上传」）。
 * 空态三态：「没有匹配的评估维度」/「暂无可用维度（当前算法类型无关联维度）」/「暂无可用维度」。
 * 注：Dimension.id 为 number|string，mock 全为 number——组件内部统一 Number() 归一。
 */
import { Check, Folder, Music4, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'

/**
 * requiresAudio 维度（mock 侧：随多轮音频一起上传，音乐图标 + title 提示）。
 * 注：当前按维度 id 硬编码（审计 P4-1，mock 阶段可接受）；接线后改随维度模型数据驱动——
 * 建议 Dimension 增 requiresAudio 布尔字段，由 d.requiresAudio 判断，不再维护 id 集合。
 */
const REQUIRES_AUDIO_DIMENSION_IDS = new Set<number>([11])

const dimId = (d: Dimension) => Number(d.id)

/** 维度云分组：主维度 + 其子维度；main 为 null 表示父维度不在候选集（孤儿子维度） */
interface CloudGroup {
  main: Dimension | null
  children: Dimension[]
  /** 孤儿子维度时展示的父维度名 */
  orphanParentName: string
}

/** 分类分组节：分类（未知/未分类为 null）+ 该分类下的主/子分组云 */
interface CategorySection {
  key: string
  category: EvaluationCategory | null
  groups: CloudGroup[]
}

/** chip 基础样式（主/子同款，选中填充色反相） */
const chipBase =
  'flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition-colors'
const chipSelected = 'bg-primary/10 border-primary/40 text-primary font-medium'
const chipIdle = 'hover:bg-accent border-border text-muted-foreground'

/**
 * 构建主/子分组的维度云（V9.7.10 DimensionConfigPanel.buildCloudGroups 平移）。
 * - 主维度命中：整组展示（非搜索时全部子维度；搜索时仅命中的子维度）；
 * - 子维度命中：带出父维度上下文；
 * - 父维度不在候选集（被算法过滤等）的子维度作为「孤儿子维度」。
 */
function buildCloudGroups(dims: Dimension[], keyword: string): CloudGroup[] {
  const kw = keyword.trim().toLowerCase()
  const byId = new Map<string, Dimension>()
  dims.forEach((d) => byId.set(String(dimId(d)), d))

  const matches = (d: Dimension): boolean => {
    if (!kw) return true
    return [d.name, d.description ?? '', d.keywords ?? ''].some((v) =>
      String(v).toLowerCase().includes(kw)
    )
  }

  const matchedIds = new Set<string>()
  dims.forEach((d) => {
    if (matches(d)) matchedIds.add(String(dimId(d)))
  })

  // 父子聚合：子维度命中带父；主维度命中整组展示（非搜索时仅展示全部子维度）
  const visibleIds = new Set<string>()
  dims.forEach((d) => {
    const pid = d.parentDimensionId
    if (!pid) {
      if (matchedIds.has(String(dimId(d)))) {
        visibleIds.add(String(dimId(d)))
        dims.forEach((c) => {
          if (
            String(c.parentDimensionId) === String(dimId(d)) &&
            (kw === '' || matchedIds.has(String(dimId(c))))
          ) {
            visibleIds.add(String(dimId(c)))
          }
        })
      }
    } else if (matchedIds.has(String(dimId(d)))) {
      visibleIds.add(String(dimId(d)))
      visibleIds.add(String(pid))
    }
  })

  const visible = dims.filter((d) => visibleIds.has(String(dimId(d))))
  const mainDims = visible.filter((d) => !d.parentDimensionId)
  const childrenMap = new Map<string, Dimension[]>()
  visible.forEach((d) => {
    if (!d.parentDimensionId) return
    const key = String(d.parentDimensionId)
    if (!childrenMap.has(key)) childrenMap.set(key, [])
    childrenMap.get(key)!.push(d)
  })

  const groups: CloudGroup[] = []
  const groupedChildIds = new Set<string>()
  mainDims.forEach((m) => {
    const children = childrenMap.get(String(dimId(m))) || []
    groups.push({ main: m, children, orphanParentName: '' })
    children.forEach((c) => groupedChildIds.add(String(dimId(c))))
  })
  // 孤儿子维度：父维度不在候选集（如被算法关联过滤）
  visible.forEach((d) => {
    const pid = d.parentDimensionId
    if (pid && !groupedChildIds.has(String(dimId(d)))) {
      groups.push({
        main: null,
        children: [d],
        orphanParentName: byId.get(String(pid))?.name ?? '',
      })
    }
  })
  return groups
}

/**
 * 按分类聚合主/子分组云（负责人 2026-10-19 口径：评估维度已分组/分类）。
 * - 主分组取主维度 categoryId；孤儿子维度取自身 categoryId；
 * - 分类顺序照 categories 数组，未知分类 →「未分类」，categoryId 为空 →「未分类」；
 * - categories 为空时返回单节「all」（整片分组云，兼容未接线/无分类态）。
 */
function groupByCategory(
  groups: CloudGroup[],
  categories: EvaluationCategory[]
): CategorySection[] {
  if (categories.length === 0) return [{ key: 'all', category: null, groups }]
  const byCat = new Map<string, CloudGroup[]>()
  const uncategorized: CloudGroup[] = []
  for (const g of groups) {
    const catId = g.main ? g.main.categoryId : g.children[0]?.categoryId ?? null
    if (catId == null) uncategorized.push(g)
    else {
      const key = String(catId)
      if (!byCat.has(key)) byCat.set(key, [])
      byCat.get(key)!.push(g)
    }
  }
  const result: CategorySection[] = []
  for (const cat of categories) {
    const items = byCat.get(String(cat.id))
    if (items && items.length > 0)
      result.push({ key: String(cat.id), category: cat, groups: items })
  }
  for (const [key, items] of byCat.entries()) {
    if (!result.some((r) => r.key === key))
      result.push({ key, category: null, groups: items })
  }
  if (uncategorized.length > 0)
    result.push({ key: 'uncategorized', category: null, groups: uncategorized })
  return result
}

/** 分类节可见维度数（主维度 + 子维度） */
const sectionCount = (section: CategorySection) =>
  section.groups.reduce((sum, g) => sum + g.children.length + (g.main ? 1 : 0), 0)

/** 渲染一组主/子分组云（主维度 chip + 归属子维度 chips / 孤儿子维度） */
function CloudGroupList({
  groups,
  selected,
  onToggle,
  childrenOf,
}: {
  groups: CloudGroup[]
  selected: number[]
  onToggle: (ids: number[], checked: boolean) => void
  childrenOf: (main: Dimension) => Dimension[]
}) {
  return (
    <div className='flex flex-wrap gap-1.5'>
      {groups.map((group, gi) =>
        group.main ? (
          <div key={gi} className='flex w-full flex-wrap items-center gap-1.5'>
            {/* 主维度 chip：勾选联动全部子维度 */}
            {(() => {
              const main = group.main
              const id = dimId(main)
              const checked = selected.includes(id)
              const childIds = childrenOf(main).map(dimId)
              return (
                <button
                  type='button'
                  onClick={() => onToggle([id, ...childIds], !checked)}
                  aria-pressed={checked}
                  className={cn(chipBase, 'font-medium', checked ? chipSelected : chipIdle)}
                >
                  {checked ? (
                    <Check aria-hidden='true' className='size-3' />
                  ) : (
                    <Plus aria-hidden='true' className='size-3' />
                  )}
                  <span className='truncate'>{main.name}</span>
                  <span className='bg-primary/20 text-primary inline-flex size-3.5 items-center justify-center rounded-[3px] text-[9px] font-semibold'>
                    主
                  </span>
                  {group.children.length > 0 && (
                    <span className='bg-primary/15 text-primary inline-flex min-w-4 h-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold tabular-nums'>
                      {group.children.length}
                    </span>
                  )}
                </button>
              )
            })()}
            {/* 子维度 chips（归属当前主维度，缩进展示） */}
            {group.children.length > 0 && (
              <div className='flex flex-wrap items-center gap-1.5 ps-1'>
                {group.children.map((child) => {
                  const id = dimId(child)
                  const checked = selected.includes(id)
                  const requiresAudio = REQUIRES_AUDIO_DIMENSION_IDS.has(id)
                  return (
                    <button
                      key={id}
                      type='button'
                      onClick={() => onToggle([id], !checked)}
                      aria-pressed={checked}
                      className={cn(chipBase, checked ? chipSelected : chipIdle)}
                    >
                      <span aria-hidden='true' className='text-muted-foreground font-mono text-[10px]'>
                        └
                      </span>
                      {checked ? (
                        <Check aria-hidden='true' className='size-3' />
                      ) : (
                        <Plus aria-hidden='true' className='size-3' />
                      )}
                      <span className='truncate'>{child.name}</span>
                      <span className='bg-muted text-muted-foreground border-border inline-flex size-3.5 items-center justify-center rounded-[3px] border text-[9px] font-semibold'>
                        子
                      </span>
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
        ) : (
          /* 孤儿子维度：父维度不在候选集，附带父维度名提示 */
          <div key={gi} className='flex w-full flex-wrap items-center gap-1.5'>
            {group.children.map((child) => {
              const id = dimId(child)
              const checked = selected.includes(id)
              const requiresAudio = REQUIRES_AUDIO_DIMENSION_IDS.has(id)
              return (
                <button
                  key={id}
                  type='button'
                  onClick={() => onToggle([id], !checked)}
                  aria-pressed={checked}
                  className={cn(chipBase, checked ? chipSelected : chipIdle)}
                >
                  <span aria-hidden='true' className='text-muted-foreground font-mono text-[10px]'>
                    └
                  </span>
                  {checked ? (
                    <Check aria-hidden='true' className='size-3' />
                  ) : (
                    <Plus aria-hidden='true' className='size-3' />
                  )}
                  <span className='truncate'>{child.name}</span>
                  <span className='bg-muted text-muted-foreground border-border inline-flex size-3.5 items-center justify-center rounded-[3px] border text-[9px] font-semibold'>
                    子
                  </span>
                  {group.orphanParentName && (
                    <span className='text-muted-foreground/70 text-[11px]'>
                      （{group.orphanParentName}）
                    </span>
                  )}
                  {requiresAudio && (
                    <span title='该维度需要音频文件，将随多轮音频一起上传'>
                      <Music4 aria-hidden='true' className='size-3.5 shrink-0' />
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        )
      )}
    </div>
  )
}

export function DimensionPicker({
  dimensions,
  categories = [],
  algorithmType,
  selected,
  onToggle,
  showSearch = true,
}: {
  dimensions: Dimension[]
  /** 评估维度分类（分类分组组头；负责人 2026-10-19 口径。不传=整片主/子分组云不分分类） */
  categories?: EvaluationCategory[]
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

  /** 主/子分组云（搜索命中子维度带父、命中主维度整组；孤儿子维度兜底） */
  const groups = useMemo(
    () => buildCloudGroups(algoFiltered, keyword),
    [algoFiltered, keyword]
  )
  /** 可见维度总数（分组云中的主维度 + 子维度） */
  const visibleCount = useMemo(
    () =>
      groups.reduce(
        (sum, g) => sum + g.children.length + (g.main ? 1 : 0),
        0
      ),
    [groups]
  )
  /** 分类分组节（分类组头 + 节内主/子分组云） */
  const sections = useMemo(
    () => groupByCategory(groups, categories),
    [groups, categories]
  )

  /** 主维度全部子维度（算法过滤后；勾选联动口径，V9.7.10 applyLinkageToggle） */
  const childrenOf = (main: Dimension) =>
    algoFiltered.filter((d) => String(d.parentDimensionId) === String(dimId(main)))

  // 空态三态（V9.7.10 口径）：搜索无结果 → 算法无关联 → 全量无维度
  let empty: string | null = null
  if (keyword && visibleCount === 0) empty = '没有匹配的评估维度'
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
        <div className='space-y-2'>
          {sections.map((section) => (
            <div key={section.key} className='space-y-1.5'>
              {categories.length > 0 && (
                <div className='text-muted-foreground flex items-center gap-1.5 px-0.5 pt-1 text-xs font-medium'>
                  <Folder aria-hidden='true' className='size-3.5 shrink-0' />
                  <span className='truncate'>{section.category?.name ?? '未分类'}</span>
                  <span className='bg-muted text-muted-foreground shrink-0 rounded-full px-1.5 text-[10px] tabular-nums'>
                    {sectionCount(section)} 项
                  </span>
                </div>
              )}
              <CloudGroupList
                groups={section.groups}
                selected={selected}
                onToggle={onToggle}
                childrenOf={childrenOf}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
