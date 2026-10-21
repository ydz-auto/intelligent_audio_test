/**
 * 评估维度分组单选下拉（INT-1030 走查实施：参数映射/关联维度选择按 分组→主维度→子维度 展示）。
 * 复用 dimension-picker（round-config/dimension-picker.tsx）的主/子分组云口径：主维度「主」徽章
 * + 子维度数角标、子维度「子」徽章 + 树形分支符 └、孤儿子维度带父名提示；分类分组组头照
 * 负责人 2026-10-19「评估维度已分组/分类」口径（分类名 + 可见维度数）。
 * 以 base-ui Select 下拉单选呈现，适配算法配置参数表行级单选项（评估映射 target、关联维度）。
 */
import { Folder } from 'lucide-react'
import { Fragment, useMemo } from 'react'

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'

const dimId = (d: Dimension) => String(d.id)

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

/** 主/子维度徽章样式（照 dimension-picker chip 徽章） */
const mainBadge =
  'bg-primary/20 text-primary inline-flex size-3.5 items-center justify-center rounded-[3px] text-[9px] font-semibold'
const subBadge =
  'bg-muted text-muted-foreground border-border inline-flex size-3.5 items-center justify-center rounded-[3px] border text-[9px] font-semibold'

/**
 * 构建主/子分组的维度云（dimension-picker buildCloudGroups 平移，无搜索分支）。
 * 主维度在前（带其子维度），父维度不在候选集的子维度作「孤儿子维度」兜底。
 */
function buildCloudGroups(dims: Dimension[]): CloudGroup[] {
  const byId = new Map(dims.map((d) => [dimId(d), d]))
  const mainDims = dims.filter((d) => !d.parentDimensionId)
  const childrenMap = new Map<string, Dimension[]>()
  dims.forEach((d) => {
    if (!d.parentDimensionId) return
    const key = String(d.parentDimensionId)
    childrenMap.set(key, [...(childrenMap.get(key) ?? []), d])
  })

  const groups: CloudGroup[] = []
  const groupedChildIds = new Set<string>()
  mainDims.forEach((main) => {
    const children = childrenMap.get(dimId(main)) ?? []
    groups.push({ main, children, orphanParentName: '' })
    children.forEach((c) => groupedChildIds.add(dimId(c)))
  })
  dims.forEach((d) => {
    const pid = d.parentDimensionId
    if (pid && !groupedChildIds.has(dimId(d))) {
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
 * 按分类聚合主/子分组云（dimension-picker groupByCategory 平移）。
 * 分类顺序照 categories 数组；categoryId 为空 / 未知 →「未分类」；categories 空 → 单节整片分组云。
 */
function groupByCategory(
  groups: CloudGroup[],
  categories: EvaluationCategory[]
): CategorySection[] {
  if (categories.length === 0) return [{ key: 'all', category: null, groups }]
  const byCat = new Map<string, CloudGroup[]>()
  const uncategorized: CloudGroup[] = []
  for (const group of groups) {
    const catId = group.main ? group.main.categoryId : group.children[0]?.categoryId ?? null
    if (catId == null) uncategorized.push(group)
    else {
      const key = String(catId)
      if (!byCat.has(key)) byCat.set(key, [])
      byCat.get(key)!.push(group)
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

export function DimensionSelect(props: {
  dimensions: Dimension[]
  /** 评估维度分类（分类分组组头；不传=整片主/子分组云） */
  categories?: EvaluationCategory[]
  /** 当前选中值（由 valueOf 提取） */
  value: string
  onValueChange: (value: string) => void
  /** 维度 → 选项值的提取器（评估映射 target 用 name，关联维度用 id） */
  valueOf?: (dimension: Dimension) => string
  /** 空值占位；值为空且未选中时显示。未匹配选项的存量值（如已删除维度的映射 target）回退显示「维度(id)」（与分组头/详情 §7.2 同口径，数据保全） */
  placeholder?: string
  triggerClassName?: string
  ariaLabel?: string
  /** 可清除的单选（筛选场景）：下拉顶部「全部」项，选中即清空（value=''） */
  clearLabel?: string
  /** 触发器前缀标签（筛选 chip 形态：如「评估维度」+ 当前值） */
  triggerLabel?: string
}) {
  const {
    dimensions,
    categories = [],
    value,
    onValueChange,
    placeholder = '选择评估维度',
    triggerClassName = 'w-56',
    ariaLabel = '评估维度',
    clearLabel,
    triggerLabel,
  } = props
  // valueOf 是 Object.prototype 的继承属性：调用方缺省该 prop 时解构仍会拿到原生
  // valueOf（而非 undefined），参数默认值因此不生效（JS 解构坑）。用 hasOwnProperty
  // 判断是否真的传入；未传入回退 dimId（INT-1160 返工 P2）。
  const valueOf: (dimension: Dimension) => string = Object.prototype.hasOwnProperty.call(
    props,
    'valueOf'
  )
    ? (props.valueOf as (dimension: Dimension) => string)
    : (dimension: Dimension) => dimId(dimension)
  const sections = useMemo(
    () => groupByCategory(buildCloudGroups(dimensions), categories),
    [dimensions, categories]
  )
  const selected = dimensions.find((d) => valueOf(d) === value)

  return (
    <Select value={value} onValueChange={(next) => onValueChange(next ?? '')}>
      <SelectTrigger size='sm' className={triggerClassName} aria-label={ariaLabel}>
        {triggerLabel && (
          <span className='text-muted-foreground shrink-0'>{triggerLabel}</span>
        )}
        <SelectValue>
          {selected
            ? selected.parentDimensionId
              ? `└ ${selected.name}`
              : selected.name
            : value !== ''
              ? `维度(${value})`
              : placeholder}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {clearLabel && (
          <SelectItem value=''>
            <span className='inline-flex items-center gap-1.5'>
              <span className='text-muted-foreground'>{clearLabel}</span>
            </span>
          </SelectItem>
        )}
        {sections.length === 0 ? (
          <p className='text-muted-foreground px-3 py-4 text-center text-sm'>暂无可用维度</p>
        ) : (
          sections.map((section) => (
            <SelectGroup key={section.key}>
              <SelectLabel className='px-1.5 py-1 text-xs font-medium'>
                <span className='inline-flex items-center gap-1'>
                  <Folder aria-hidden='true' className='size-3.5 shrink-0' />
                  <span className='truncate'>{section.category?.name ?? '未分类'}</span>
                  <span className='bg-muted text-muted-foreground shrink-0 rounded-full px-1.5 text-[10px] tabular-nums'>
                    {sectionCount(section)}
                  </span>
                </span>
              </SelectLabel>
              {section.groups.map((group, groupIndex) => (
                <Fragment key={groupIndex}>
                  {group.main ? (
                    <>
                      <SelectItem value={valueOf(group.main)}>
                        <span className='font-medium'>{group.main.name}</span>
                        <span className={mainBadge}>主</span>
                        {group.children.length > 0 && (
                          <span className='bg-primary/15 text-primary inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold tabular-nums'>
                            {group.children.length}
                          </span>
                        )}
                      </SelectItem>
                      {group.children.map((child) => (
                        <SelectItem key={dimId(child)} value={valueOf(child)}>
                          <span className='text-muted-foreground font-mono text-[10px]'>└</span>
                          <span>{child.name}</span>
                          <span className={subBadge}>子</span>
                        </SelectItem>
                      ))}
                    </>
                  ) : (
                    group.children.map((child) => (
                      <SelectItem key={dimId(child)} value={valueOf(child)}>
                        <span className='text-muted-foreground font-mono text-[10px]'>└</span>
                        <span>{child.name}</span>
                        <span className={subBadge}>子</span>
                        {group.orphanParentName && (
                          <span className='text-muted-foreground/70 text-[11px]'>
                            （{group.orphanParentName}）
                          </span>
                        )}
                      </SelectItem>
                    ))
                  )}
                </Fragment>
              ))}
            </SelectGroup>
          ))
        )}
      </SelectContent>
    </Select>
  )
}
