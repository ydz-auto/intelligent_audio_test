/**
 * 报告筛选分类归属（application 层，15_报告域.md §3.3.7 / §3.5.10，INT-1738 / INT-2101）。
 *
 * 「整份报告的筛选都得」按「分类 → 主维度 → 子维度」三级、「分类 → 标签」两级展示：
 * - **评估维度**：① 报告快照 `summary.all_metrics[]` 的主/子层级（`dimension_type` /
 *   `parent_dimension_name`）→ ② 用户持有 `evaluation:read` 时用维度字典（`id → categoryId`）+
 *   分类字典（`categoryId → 名称`）补分类 → ③ 仍无 → 「未分类」单组。
 * - **用例标签**：① 报告快照 `all_case_tags[].category_id / category_name`（真实快照多数只存
 *   `{id,name}`）→ ② 用户持有 `tag:read` 时用 `GET /tags/by-category`（INT-487 口径，INT-2101
 *   落地）按标签名补分类 → ③ 仍无 → 「未分类」单组。
 *
 * **只产出展示树，不改报告数据、不改筛选请求**（请求仍传维度名 / 标签名数组）。
 */
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import {
  fetchEvaluationCategories,
  fetchEvaluationDimensions,
} from '@/infrastructure/api/evaluation-api'
import { fetchTagsByCategory } from '@/infrastructure/api/tags-api'
import type { ReportMetricConfig, ReportTag } from '@/domain/models/report'

export const UNCATEGORIZED_SECTION_KEY = '__uncategorized__'
export const UNCATEGORIZED_SECTION_NAME = '未分类'

/** 评估维度三级树：分类 → 主维度（可含子维度） */
export interface DimensionTreeGroup {
  main: string
  subs: string[]
}

export interface DimensionTreeSection {
  key: string
  name: string
  groups: DimensionTreeGroup[]
}

/** 标签两级树：分类 → 标签 */
export interface TagTreeSection {
  key: string
  name: string
  tags: string[]
}

/** 标签分类归属（从 all_case_tags / all_tags 快照取，缺省「未分类」；阶梯② by-category 兜底） */
export function buildTagSections(
  tagNames: string[],
  tags: ReportTag[],
  categoryByName: ReadonlyMap<string, string> = new Map()
): TagTreeSection[] {
  const byName = new Map<string, ReportTag>()
  for (const tag of tags) if (tag.tag_name) byName.set(tag.tag_name, tag)
  const buckets = new Map<string, { name: string; tags: string[] }>()
  for (const name of tagNames) {
    const tag = byName.get(name)
    // 阶梯① 快照分类优先；缺失时阶梯② 用 by-category 按标签名兜底
    let categoryName = tag?.category_name?.trim() ?? ''
    if (!categoryName) categoryName = categoryByName.get(name)?.trim() ?? ''
    const key = categoryName || UNCATEGORIZED_SECTION_KEY
    if (!buckets.has(key)) {
      buckets.set(key, { name: categoryName || UNCATEGORIZED_SECTION_NAME, tags: [] })
    }
    buckets.get(key)!.tags.push(name)
  }
  const sections = [...buckets.entries()]
    .filter(([key]) => key !== UNCATEGORIZED_SECTION_KEY)
    .map(([key, v]) => ({ key, name: v.name, tags: v.tags }))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
  const uncategorized = buckets.get(UNCATEGORIZED_SECTION_KEY)
  if (uncategorized) {
    sections.push({
      key: UNCATEGORIZED_SECTION_KEY,
      name: UNCATEGORIZED_SECTION_NAME,
      tags: uncategorized.tags,
    })
  }
  return sections
}

interface DictionaryMaps {
  /** 维度名 → 分类名 */
  dimensionCategory: Map<string, string>
  /** 维度名 → 父维度名（字典比快照更全时用于补层级） */
  dimensionParent: Map<string, string>
}

/** 字典补齐（无权限 / 请求失败 → 空映射，全部归「未分类」） */
function buildDictionaryMaps(
  dimensions: { name: string; parentDimensionName?: string | null; categoryId?: number | null }[],
  categories: { id: number; name: string }[]
): DictionaryMaps {
  const categoryNameById = new Map(categories.map((c) => [String(c.id), c.name]))
  const dimensionCategory = new Map<string, string>()
  const dimensionParent = new Map<string, string>()
  for (const dim of dimensions) {
    if (!dim?.name) continue
    const categoryName = dim.categoryId != null ? categoryNameById.get(String(dim.categoryId)) : undefined
    if (categoryName) dimensionCategory.set(dim.name, categoryName)
    if (dim.parentDimensionName) dimensionParent.set(dim.name, dim.parentDimensionName)
  }
  return { dimensionCategory, dimensionParent }
}

/** 维度三级树（快照层级 + 字典分类；孤儿子维度挂「未分类」末尾） */
export function buildDimensionSections(
  baseDimensions: string[],
  configs: ReportMetricConfig[],
  dictionary: DictionaryMaps
): DimensionTreeSection[] {
  const configByName = new Map(configs.map((c) => [c.name, c]))
  const categoryOf = (name: string): string => {
    const config = configByName.get(name)
    const declared = (config as ReportMetricConfig & { category_name?: string })?.category_name
    if (declared?.trim()) return declared.trim()
    return dictionary.dimensionCategory.get(name) ?? ''
  }
  const parentOf = (name: string): string | null => {
    const config = configByName.get(name)
    if (config?.dimension_type === 'sub') {
      return config.parent_dimension_name ?? dictionary.dimensionParent.get(name) ?? null
    }
    return dictionary.dimensionParent.get(name) ?? null
  }

  const available = new Set(baseDimensions)
  const groupsByCategory = new Map<string, Map<string, DimensionTreeGroup>>()

  // 主维度先落组（分类按主维度归属）
  for (const name of baseDimensions) {
    const parent = parentOf(name)
    if (parent && available.has(parent)) continue
    const category = categoryOf(name)
    if (!groupsByCategory.has(category)) groupsByCategory.set(category, new Map())
    groupsByCategory.get(category)!.set(name, { main: name, subs: [] })
  }

  // 子维度挂父组；父不在本报告 → 孤儿子维度，挂「未分类」末尾作独立项
  for (const name of baseDimensions) {
    const parent = parentOf(name)
    if (!parent) continue
    const parentGroup = [...groupsByCategory.values()]
      .map((g) => g.get(parent))
      .find(Boolean)
    if (parentGroup) {
      parentGroup.subs.push(name)
      continue
    }
    const category = UNCATEGORIZED_SECTION_KEY
    if (!groupsByCategory.has(category)) groupsByCategory.set(category, new Map())
    groupsByCategory.get(category)!.set(`${name}__orphan`, { main: name, subs: [] })
  }

  const sections: DimensionTreeSection[] = []
  for (const [category, groups] of groupsByCategory.entries()) {
    if (!groups.size) continue
    sections.push({
      key: category || UNCATEGORIZED_SECTION_KEY,
      name: category || UNCATEGORIZED_SECTION_NAME,
      groups: [...groups.values()],
    })
  }
  sections.sort((a, b) => {
    if (a.key === UNCATEGORIZED_SECTION_KEY) return 1
    if (b.key === UNCATEGORIZED_SECTION_KEY) return -1
    return a.name.localeCompare(b.name, 'zh-CN')
  })
  return sections
}

export interface ReportFilterTaxonomy {
  dimensionSections: DimensionTreeSection[]
  tagSections: TagTreeSection[]
  /** 主维度名集合（叶表默认列 / 子维度判定） */
  mainDimensions: string[]
  /** 子维度名集合 */
  subDimensions: string[]
}

/**
 * 分类归属 hook（展示层归类；无权限不发字典请求）。
 * @param baseDimensions 当前报告出现的基础维度名（去轮次后缀）
 * @param configs `summary.all_metrics`
 * @param tags `summary.all_case_tags ∪ summary.all_tags`
 * @param tagNames 当前可选标签（快照标签池 ∪ 用例自带标签）
 */
export function useReportFilterTaxonomy(
  baseDimensions: string[],
  configs: ReportMetricConfig[],
  tags: ReportTag[],
  tagNames: string[]
): ReportFilterTaxonomy {
  const { hasPermission } = usePermissions()
  const canReadEvaluation = hasPermission('evaluation:read')
  const canReadTag = hasPermission('tag:read')

  const dictionaryQuery = useQuery({
    queryKey: ['reports', 'filter-taxonomy', 'evaluation'],
    queryFn: async () => {
      const [dimensions, categories] = await Promise.all([
        fetchEvaluationDimensions(),
        fetchEvaluationCategories(),
      ])
      return buildDictionaryMaps(
        dimensions.map((d) => ({
          name: d.name,
          parentDimensionName: null,
          categoryId: d.categoryId ?? null,
        })),
        categories.map((c) => ({ id: Number(c.id), name: c.name }))
      )
    },
    enabled: canReadEvaluation,
    staleTime: 5 * 60_000,
    retry: false,
  })

  const dictionary = dictionaryQuery.data ?? { dimensionCategory: new Map(), dimensionParent: new Map() }

  const dimensionSections = useMemo(
    () => buildDimensionSections(baseDimensions, configs, dictionary),
    [baseDimensions, configs, dictionary]
  )

  /** 阶梯① 快照分类（all_case_tags/all_tags 自带 category_name 时优先） */
  const snapshotTagCategory = useMemo(() => {
    const m = new Map<string, string>()
    for (const tag of tags) {
      if (!tag.tag_name) continue
      const cat = tag.category_name?.trim()
      if (cat) m.set(tag.tag_name, cat)
    }
    return m
  }, [tags])

  /** 任一可用标签在快照里缺分类 → 才需要阶梯② by-category 兜底 */
  const needsTagByCategory = useMemo(
    () => tagNames.some((name) => !snapshotTagCategory.get(name)),
    [tagNames, snapshotTagCategory]
  )

  /**
   * 阶梯② by-category 兜底：`GET /tags/by-category` 分组数据 → 标签名→分类名映射。
   * 快照分类优先，仅补缺；无 `tag:read` 权限或快照已全分类时不发请求。
   */
  const tagByCategoryQuery = useQuery({
    queryKey: ['reports', 'filter-taxonomy', 'tags-by-category'],
    queryFn: async () => {
      const groups = await fetchTagsByCategory()
      const m = new Map<string, string>()
      for (const group of groups) {
        const categoryName = group.category?.name?.trim()
        if (!categoryName) continue
        for (const tag of group.tags) {
          if (tag.name) m.set(tag.name, categoryName)
        }
      }
      return m
    },
    enabled: canReadTag && needsTagByCategory,
    staleTime: 5 * 60_000,
    retry: false,
  })

  const tagSections = useMemo(
    () => buildTagSections(tagNames, tags, tagByCategoryQuery.data ?? new Map()),
    [tagNames, tags, tagByCategoryQuery.data]
  )

  const { mainDimensions, subDimensions } = useMemo(() => {
    const subs = new Set<string>()
    const mains: string[] = []
    for (const section of dimensionSections) {
      for (const group of section.groups) {
        mains.push(group.main)
        for (const s of group.subs) subs.add(s)
      }
    }
    return { mainDimensions: mains, subDimensions: [...subs] }
  }, [dimensionSections])

  return { dimensionSections, tagSections, mainDimensions, subDimensions }
}
