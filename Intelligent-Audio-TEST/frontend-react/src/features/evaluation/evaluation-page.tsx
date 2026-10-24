/**
 * 评估维度页（features/evaluation；11_用例域.md §4.1 页面装配）。
 * 工作台壳（AppHeader+AppSidebar）由 AuthenticatedLayout 提供，本组件只出内容。
 * 列表视图=平铺层级表格；分组视图=按分类聚合卡（组内嵌同款表格）。
 * 交互：筛选（搜索/状态/分类/关联算法 + 全局算法联动 chip）→ 本地派生；权重滑杆
 * onValueCommitted 提交 + toast；行操作（上移/下移/编辑/复制/启停/添加子维度/测试 API/
 * 规则试算/删除）；批量操作浮条；导入导出接真实接口。
 * RBAC：写权限缺失时写钮禁用 + Tooltip「无 {code} 权限」（基座 §9.2 规则 3）。
 */
import { Link } from '@tanstack/react-router'
import { Info, ListChecks } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import {
  useCalculateScore,
  useEvaluationCategories,
  useEvaluationCategoryMutations,
  useEvaluationDimensions,
  useEvaluationImportExport,
  useEvaluationMutations,
  useAlgorithmOptions,
  useTestHealth,
} from '@/application/evaluation/use-dimensions'
import { ApiError } from '@/infrastructure/api/api-error'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { PageFooterPortal } from '@/components/layout/components/page-footer'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import {
  AUTO_MERGE_HINT,
  EVALUATION_VIEW_TABS,
  WEIGHT_UPDATE_SUCCESS,
  WEIGHT_UPDATE_FAILURE,
  getAlgorithmLabel,
} from '@/features/evaluation/constants'
import { EvaluationHeaderActions } from '@/features/evaluation/components/evaluation-header-actions'
import { EvaluationToolbar } from '@/features/evaluation/components/evaluation-toolbar'
import {
  DimensionTable,
  type HierarchicalDimension,
} from '@/features/evaluation/components/dimension-table'
import {
  GroupedDimensionList,
  type DimensionGroup,
} from '@/features/evaluation/components/grouped-dimension-list'
import { DimensionMutateDrawer } from '@/features/evaluation/modals/dimension-mutate-drawer'
import { CategoryMutateDialog } from '@/features/evaluation/modals/category-mutate-dialog'
import { RuleCalcDialog } from '@/features/evaluation/modals/dimension-rule-calc-dialog'
import { HealthTestDialog } from '@/features/evaluation/modals/health-test-dialog'
import { EvaluationConfirmDialog } from '@/features/evaluation/modals/evaluation-confirms'
import { downloadBlob } from '@/lib/download-blob'
import type {
  CategoryDialogState,
  EvaluationConfirmState,
  HealthTestDialogState,
  MutateDrawerState,
  RuleCalcDialogState,
} from '@/features/evaluation/types'

/** 300ms 防抖搜索（§4.1 搜索提交；提交值驱动派生；reset 同步清空输入与提交值） */
function useDebouncedSearch(initial = '') {
  const [value, setValue] = useState(initial)
  const [committed, setCommitted] = useState(initial)
  const timerRef = useRef<number | null>(null)

  const handleChange = useCallback((next: string) => {
    setValue(next)
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(
      () => setCommitted(next.trim().toLowerCase()),
      300
    )
  }, [])

  const reset = useCallback(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    setValue('')
    setCommitted('')
  }, [])

  return [value, handleChange, committed, reset] as const
}

export function EvaluationPage() {
  const { hasPermission } = usePermissions()
  const canManage = hasPermission('evaluation:dim_manage')
  const canCategoryManage = hasPermission('evaluation:category_manage')
  const canImportExport = hasPermission('evaluation:import_export')
  const canRead = hasPermission('evaluation:read')

  // 数据源
  const dimensionsQuery = useEvaluationDimensions()
  const categoriesQuery = useEvaluationCategories()
  const algorithmOptionsQuery = useAlgorithmOptions()
  const { save, remove, batch, weight, reorder, duplicate } =
    useEvaluationMutations()
  const categoryMutations = useEvaluationCategoryMutations()
  const calculate = useCalculateScore()
  const healthTest = useTestHealth()
  const importExport = useEvaluationImportExport()

  const globalAlgorithmId = useAlgorithmStore((s) => s.algorithmId)
  const setGlobalAlgorithmId = useAlgorithmStore((s) => s.setAlgorithmId)

  // 本地状态列表（mock 阶段行级操作就地回写，不依赖重拉；query 变化时同步）
  const [dimensions, setDimensions] = useState<Dimension[]>([])
  useEffect(() => {
    if (dimensionsQuery.data) setDimensions(dimensionsQuery.data)
  }, [dimensionsQuery.data])

  // 筛选状态
  const [searchInput, handleSearch, searchKeyword, resetSearch] =
    useDebouncedSearch()
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [algorithmFilter, setAlgorithmFilter] = useState('all')

  // 视图 / 选择 / 分页
  const [viewMode, setViewMode] = useState<'list' | 'group'>('list')
  const [selectedIds, setSelectedIds] = useState<Set<number | string>>(new Set())
  const [weightPendingIds, setWeightPendingIds] = useState<Set<number | string>>(new Set())
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  // 弹窗群
  const [mutateDrawer, setMutateDrawer] = useState<MutateDrawerState>({
    open: false,
    mode: 'create',
    dimension: null,
  })
  const [categoryDialog, setCategoryDialog] = useState<CategoryDialogState>({
    open: false,
    category: null,
  })
  const [ruleCalc, setRuleCalc] = useState<RuleCalcDialogState>({
    open: false,
    dimension: null,
  })
  const [healthDialog, setHealthDialog] = useState<HealthTestDialogState>({
    open: false,
    dimension: null,
  })
  const [confirm, setConfirm] = useState<EvaluationConfirmState | null>(null)

  const categories = categoriesQuery.data ?? []
  const algorithmOptions = algorithmOptionsQuery.data ?? []
  // 算法类型码 → 中文名（真实 /algorithm/options 的 value→label；关联算法徽章/导出列用）
  const algorithmLabels = useMemo(
    () =>
      Object.fromEntries(
        algorithmOptions.map((o) => [o.value, o.label])
      ) as Record<string, string>,
    [algorithmOptions]
  )
  // 全局算法联动（§4.1）：页内 facet 未显式选择时，过滤口径/默认值继承全局算法；
  // 但全局算法不在真实 /algorithm/options 选项内时视为无效——不继承、按「全部」展示
  // （INT-646 返修：避免把真实维度筛成空态；用户在 facet 显式选择即脱离全局）。
  const globalAlgorithmValid = Boolean(
    globalAlgorithmId && algorithmOptions.some((o) => o.value === globalAlgorithmId)
  )
  // 全局算法中文名：优先取真实 /algorithm/options 的 label（照 Vue getAlgorithmLabel
  // 从 algorithms 列表解析口径）；真实列表未含时回退 constants 登记表/原值，避免裸 type 码
  const globalAlgorithmLabel = globalAlgorithmValid
    ? algorithmOptions.find((o) => o.value === globalAlgorithmId)?.label ??
      getAlgorithmLabel(globalAlgorithmId)
    : null
  const effectiveAlgorithmId =
    algorithmFilter !== 'all'
      ? algorithmFilter
      : globalAlgorithmValid
        ? globalAlgorithmId
        : ''
  const algorithmFacetValue =
    algorithmFilter !== 'all'
      ? algorithmFilter
      : globalAlgorithmValid
        ? globalAlgorithmId || 'all'
        : 'all'

  /* ───────── 派生：筛选 → 层级 → 分组 ───────── */

  const filteredDimensions = useMemo(() => {
    const keyword = searchKeyword
    const matches = (dim: Dimension): boolean => {
      const searchHit =
        !keyword ||
        dim.name.toLowerCase().includes(keyword) ||
        (dim.description ?? '').toLowerCase().includes(keyword) ||
        (dim.keywords ?? '').toLowerCase().includes(keyword)
      const statusHit =
        statusFilter === 'all' ||
        (statusFilter === 'active' && !!dim.status) ||
        (statusFilter === 'inactive' && !dim.status)
      const categoryHit =
        categoryFilter === 'all' ||
        String(dim.categoryId ?? '') === categoryFilter
      const algorithmHit =
        !effectiveAlgorithmId ||
        (dim.associatedAlgorithms ?? []).some(
          (a) => a.algorithmType === effectiveAlgorithmId
        )
      return searchHit && statusHit && categoryHit && algorithmHit
    }

    // 主/子联动：子维度命中时带上父维度上下文；主维度命中整组展示（避免孤儿子维度）
    const byParentId = new Map<number | string, Dimension[]>()
    for (const dim of dimensions) {
      const pid = dim.parentDimensionId ?? ''
      if (!byParentId.has(pid)) byParentId.set(pid, [])
      byParentId.get(pid)!.push(dim)
    }
    const included = new Set<number | string>()
    for (const dim of dimensions) {
      if (!dim.parentDimensionId) {
        if (matches(dim)) {
          included.add(dim.id)
          for (const child of byParentId.get(dim.id) ?? []) {
            if (keyword || !!effectiveAlgorithmId || matches(child))
              included.add(child.id)
          }
        }
      } else if (matches(dim)) {
        included.add(dim.id)
        if (dim.parentDimensionId != null) included.add(dim.parentDimensionId)
      }
    }
    return dimensions.filter((dim) => included.has(dim.id))
  }, [dimensions, searchKeyword, statusFilter, categoryFilter, effectiveAlgorithmId])

  const hierarchicalDimensions = useMemo<HierarchicalDimension[]>(() => {
    const mains = filteredDimensions.filter(
      (d) => !d.parentDimensionId
    )
    const subs = filteredDimensions.filter((d) => !!d.parentDimensionId)
    const result: HierarchicalDimension[] = []
    const placed = new Set<number | string>()
    for (const main of mains) {
      result.push({ ...main, _level: 0, _isMain: true, _parentName: '' })
      placed.add(main.id)
      for (const child of subs.filter((s) => s.parentDimensionId === main.id)) {
        result.push({
          ...child,
          _level: 1,
          _isMain: false,
          _parentName: main.name,
        })
        placed.add(child.id)
      }
    }
    // 孤儿子维度（父维度不在当前筛选结果中）
    for (const sub of subs) {
      if (!placed.has(sub.id)) {
        const parent = dimensions.find((d) => d.id === sub.parentDimensionId)
        result.push({
          ...sub,
          _level: 1,
          _isMain: false,
          _parentName: parent?.name ?? '',
        })
        placed.add(sub.id)
      }
    }
    return result
  }, [filteredDimensions, dimensions])

  // 分类 → 维度总数（不受筛选影响）：空分类分组渲染与删除钮可用性判定用（INT-1550）
  const dimensionCountByCategory = useMemo(() => {
    const counts = new Map<string, number>()
    for (const dim of dimensions) {
      if (dim.categoryId == null) continue
      const key = String(dim.categoryId)
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    return counts
  }, [dimensions])

  const groupedDimensions = useMemo<DimensionGroup[]>(() => {
    const byCategory = new Map<string, HierarchicalDimension[]>()
    const uncategorized: HierarchicalDimension[] = []
    for (const dim of hierarchicalDimensions) {
      const catId = dim.categoryId
      if (catId == null) uncategorized.push(dim)
      else {
        const key = String(catId)
        if (!byCategory.has(key)) byCategory.set(key, [])
        byCategory.get(key)!.push(dim)
      }
    }
    const groups: DimensionGroup[] = []
    // 分类全量渲染（含 0 维度的空分类）——分组由维度派生时空分类会连同删除入口
    // 一起消失，分类永远删不掉（INT-1550）
    for (const cat of categories) {
      const key = String(cat.id)
      groups.push({
        key,
        category: cat,
        items: byCategory.get(key) ?? [],
        totalCount: dimensionCountByCategory.get(key) ?? 0,
      })
    }
    for (const [key, items] of byCategory.entries()) {
      if (!groups.some((g) => g.key === key))
        groups.push({ key, category: null, items, totalCount: items.length })
    }
    if (uncategorized.length > 0)
      groups.push({
        key: 'uncategorized',
        category: null,
        items: uncategorized,
        totalCount: uncategorized.length,
      })
    return groups
  }, [hierarchicalDimensions, categories, dimensionCountByCategory])

  const sorted = useMemo(() => [...filteredDimensions], [filteredDimensions])
  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const pageRows = useMemo<HierarchicalDimension[]>(() => {
    const start = (safePage - 1) * pageSize
    return hierarchicalDimensions.slice(start, start + pageSize)
  }, [hierarchicalDimensions, safePage, pageSize])

  const toggleSelection = (id: number | string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      if (pageRows.length > 0 && prev.size === pageRows.length) return new Set()
      return new Set(pageRows.map((r) => r.id))
    })
  }

  /* ───────── 上移/下移边界（现 canMoveUp/canMoveDown 语义平移） ───────── */

  const moveListFor = (dimension: HierarchicalDimension) => {
    if (viewMode === 'group') {
      const group = groupedDimensions.find((g) =>
        g.items.some((i) => i.id === dimension.id)
      )
      return group?.items ?? []
    }
    return pageRows
  }

  const canMoveUp = (dimension: HierarchicalDimension) => {
    const list = moveListFor(dimension)
    const index = list.findIndex((d) => d.id === dimension.id)
    if (index <= 0) return false
    // 子维度：上方必须是同一父维度的同级子维度，否则会跑到父维度上面
    if (dimension._level === 1) {
      const prev = list[index - 1]
      return (
        prev._level === 1 && prev.parentDimensionId === dimension.parentDimensionId
      )
    }
    return true
  }

  const canMoveDown = (dimension: HierarchicalDimension) => {
    const list = moveListFor(dimension)
    const index = list.findIndex((d) => d.id === dimension.id)
    if (index < 0 || index >= list.length - 1) return false
    // 子维度：下方必须是同一父维度的同级子维度，否则会跑到其它主维度的组里
    if (dimension._level === 1) {
      const next = list[index + 1]
      return (
        next._level === 1 && next.parentDimensionId === dimension.parentDimensionId
      )
    }
    return true
  }

  const moveDimension = (dimension: Dimension, direction: -1 | 1) => {
    // 主维度连同其子维度整块移动；子维度仅同组内移动（现语义平移）
    const list = moveListFor(dimension as HierarchicalDimension)
    const index = list.findIndex((d) => d.id === dimension.id)
    if (index < 0) return
    if (
      direction === -1
        ? !canMoveUp(list[index])
        : !canMoveDown(list[index])
    )
      return

    const isMain = list[index]._level === 0
    let blockStart = index
    let blockEnd = index
    if (isMain) {
      while (
        blockEnd < list.length - 1 &&
        list[blockEnd + 1]._level === 1
      )
        blockEnd++
    } else {
      const parentId = list[index].parentDimensionId
      while (
        blockStart > 0 &&
        list[blockStart - 1].parentDimensionId === parentId
      )
        blockStart--
      while (
        blockEnd < list.length - 1 &&
        list[blockEnd + 1].parentDimensionId === parentId
      )
        blockEnd++
    }

    const ids = list.map((d) => d.id)
    const block = ids.splice(blockStart, blockEnd - blockStart + 1)
    if (direction === -1) ids.splice(blockStart - 1, 0, ...block)
    else ids.splice(blockStart + 1, 0, ...block)

    // 按新 id 序重排本地 dimensions（仅调整展示序，字段不变）
    const order = new Map(ids.map((id, i) => [id, i]))
    setDimensions((prev) =>
      [...prev].sort(
        (a, b) =>
          (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0)
      )
    )
    void reorder
      .mutateAsync(ids)
      .then(() => toast.success(direction === -1 ? '已上移' : '已下移'))
      .catch(() => toast.error('排序失败，请重试'))
  }

  /* ───────── 行操作 ───────── */

  const commitWeight = (dimension: Dimension, next: number) => {
    setWeightPendingIds((prev) => new Set(prev).add(dimension.id))
    setDimensions((prev) =>
      prev.map((d) => (d.id === dimension.id ? { ...d, weight: next } : d))
    )
    void weight
      .mutateAsync({ id: dimension.id, weight: next })
      .then(() => {
        toast.success(WEIGHT_UPDATE_SUCCESS)
      })
      .catch(() => toast.error(WEIGHT_UPDATE_FAILURE))
      .finally(() => {
        setWeightPendingIds((prev) => {
          const nextSet = new Set(prev)
          nextSet.delete(dimension.id)
          return nextSet
        })
      })
  }

  const toggleStatus = (dimension: Dimension) => {
    const nextStatus = !dimension.status
    setDimensions((prev) =>
      prev.map((d) =>
        d.id === dimension.id ? { ...d, status: nextStatus } : d
      )
    )
    void save
      .mutateAsync({ ...dimension, status: nextStatus } as Dimension)
      .then(() =>
        toast.success(nextStatus ? '维度已启用' : '维度已禁用')
      )
  }

  const handleConfirm = async () => {
    if (!confirm) return
    if (confirm.kind === 'delete-dimension') {
      const { dimension } = confirm
      setDimensions((prev) => prev.filter((d) => d.id !== dimension.id))
      setSelectedIds((prev) => {
        const next = new Set(prev)
        next.delete(dimension.id)
        return next
      })
      void remove
        .mutateAsync(dimension.id)
        .then(() => toast.success('维度已删除'))
        .catch(() => toast.error('删除维度失败'))
    } else if (confirm.kind === 'batch-action') {
      const ids = [...selectedIds]
      if (confirm.action === 'delete') {
        setDimensions((prev) => prev.filter((d) => !ids.includes(d.id)))
      } else {
        const enabled = confirm.action === 'enable'
        setDimensions((prev) =>
          prev.map((d) =>
            ids.includes(d.id) ? { ...d, status: enabled } : d
          )
        )
      }
      setSelectedIds(new Set())
      void batch
        .mutateAsync({ ids, action: confirm.action })
        .then(() => toast.success('批量操作执行成功'))
        .catch(() => toast.error('批量操作失败'))
    } else if (confirm.kind === 'delete-category') {
      setDimensions((prev) =>
        prev.map((d) =>
          d.categoryId === confirm.category.id ? { ...d, categoryId: null } : d
        )
      )
      void categoryMutations.remove
        .mutateAsync(confirm.category.id)
        .then(() => toast.success('分类删除成功'))
        .catch(() => toast.error('分类删除失败'))
    } else if (confirm.kind === 'duplicate-dimension') {
      const { dimension } = confirm
      const copy: Dimension = {
        ...dimension,
        id: `copy-${Date.now()}`,
        name: `${dimension.name}（副本）`,
      }
      setDimensions((prev) => [...prev, copy])
      void duplicate
        .mutateAsync(dimension)
        .then(() => toast.success('维度复制成功'))
        .catch(() => toast.error('维度复制失败'))
    }
    setConfirm(null)
  }

  /* ───────── 分类 / 导入导出 ───────── */

  // 编辑分类必须把当前分类 id 并入 input（saveEvaluationCategory 以 id 判定 PUT，
  // 缺失即走 POST 新建 → 出现改名后的重复分类）；失败抛回弹窗，由弹窗保留内容并提示。
  const handleSaveCategory = async (
    input: Partial<EvaluationCategory>,
    isNew: boolean
  ) => {
    const editingId = categoryDialog.category?.id
    try {
      await categoryMutations.save.mutateAsync(
        editingId != null ? { ...input, id: editingId } : input
      )
      toast.success(isNew ? '分类添加成功' : '分类更新成功')
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.userMessage
          : isNew
            ? '分类添加失败'
            : '分类更新失败'
      )
      throw error
    }
  }

  const handleExport = (format: 'json' | 'excel') => {
    // §4.1 导出维度（JSON/Excel 二选一下拉项）；GET /evaluation/dimensions/export?format= 真实数据
    // excel：后端返回二进制 XLSX 直接落盘（对照旧 Vue blob 口径）；json：行数组由前端序列化
    const date = new Date().toISOString().slice(0, 10)
    const extension = format === 'excel' ? 'xlsx' : 'json'
    const filename = `evaluation-dimensions-${date}.${extension}`
    void importExport.export
      .mutateAsync(format)
      .then((result) => {
        if (result.format === 'excel') {
          downloadBlob(
            result.blob,
            filename,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          )
        } else {
          downloadBlob(JSON.stringify(result.rows, null, 2), filename, 'application/json')
        }
        toast.success('维度导出成功')
      })
      .catch(() => toast.error('导出维度失败'))
  }

  const handleImport = () => {
    // §4.1 导入维度；POST /evaluation/dimensions/import multipart（file + updateExisting=true）
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.json'
    input.style.display = 'none'
    input.addEventListener('change', (event) => {
      const file = (event.target as HTMLInputElement).files?.[0]
      input.remove()
      if (!file) return
      void importExport.import
        .mutateAsync({ file, updateExisting: true })
        .then((result) =>
          toast.success(
            `导入完成: 新增 ${result.imported} 条, 更新 ${result.updated} 条`
          )
        )
        .catch(() => toast.error('导入维度失败'))
    })
    document.body.appendChild(input)
    input.click()
  }

  const openAddSub = (dimension: Dimension) => {
    setMutateDrawer({
      open: true,
      mode: 'create',
      dimension: null,
      presetParentId:
        typeof dimension.id === 'number' ? dimension.id : null,
      presetCategoryId: dimension.categoryId,
    })
  }

  const openAddInCategory = (category: EvaluationCategory | null) => {
    setMutateDrawer({
      open: true,
      mode: 'create',
      dimension: null,
      presetCategoryId: category?.id ?? null,
    })
  }

  /* ───────── 页面装配 ───────── */

  return (
    <>
      <SectionPageLayout fixedContent>
        <SectionPageLayout.Breadcrumb>
          <nav aria-label='面包屑' className='text-sm'>
            <ol className='flex flex-wrap items-center gap-1.5'>
              <li>
                <Link
                  to='/dashboard'
                  className='text-muted-foreground hover:text-foreground transition-colors'
                >
                  工作台
                </Link>
              </li>
              <li aria-hidden='true' className='text-muted-foreground/50'>
                /
              </li>
              <li aria-current='page' className='text-foreground font-medium'>
                评估维度
              </li>
            </ol>
          </nav>
        </SectionPageLayout.Breadcrumb>

        <SectionPageLayout.Title>评估维度</SectionPageLayout.Title>
        <SectionPageLayout.Actions>
          <div className='flex flex-wrap items-center gap-2'>
            <p className='text-muted-foreground mr-auto text-sm'>
              管理语音测试的评估维度和权重
            </p>
            <EvaluationHeaderActions
              canManage={canManage}
              canCategoryManage={canCategoryManage}
              canImportExport={canImportExport}
              selectedCount={selectedIds.size}
              onAddDimension={() =>
                setMutateDrawer({ open: true, mode: 'create', dimension: null })
              }
              onAddCategory={() =>
                setCategoryDialog({ open: true, category: null })
              }
              onBatchAction={(action) =>
                setConfirm({ kind: 'batch-action', action, count: selectedIds.size })
              }
              onImport={handleImport}
              onExport={handleExport}
            />
          </div>
        </SectionPageLayout.Actions>

        <SectionPageLayout.Content>
          <div className='flex h-full min-h-0 flex-col gap-3'>
            {/* 自动合并提示条（§4.1 现 auto-merge-hint 文案逐字保留） */}
            <Alert className='items-start gap-2'>
              <Info aria-hidden='true' className='mt-0.5 size-4 shrink-0' />
              <AlertTitle>自动合并提示</AlertTitle>
              <AlertDescription>{AUTO_MERGE_HINT}</AlertDescription>
            </Alert>

            {/* 双视图页签（default 胶囊） */}
            <Tabs
              value={viewMode}
              onValueChange={(value) =>
                setViewMode((value ?? 'list') as 'list' | 'group')
              }
            >
              <TabsList className='h-8'>
                {EVALUATION_VIEW_TABS.map((tab) => (
                  <TabsTrigger key={tab.key} value={tab.key}>
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            {/* 筛选工具栏 */}
            <EvaluationToolbar
              searchValue={searchInput}
              onSearch={handleSearch}
              statusFilter={statusFilter}
              onStatusFilter={(value) => {
                setStatusFilter(value)
                setPage(1)
              }}
              categoryFilter={categoryFilter}
              onCategoryFilter={(value) => {
                setCategoryFilter(value)
                setPage(1)
              }}
              categories={categories}
              algorithmFilter={algorithmFilter}
              onAlgorithmFilter={(value) => {
                setAlgorithmFilter(value)
                setPage(1)
              }}
              algorithmOptions={algorithmOptions}
              algorithmFacetValue={algorithmFacetValue}
              globalAlgorithmLabel={globalAlgorithmLabel}
              onClearGlobalAlgorithm={() => {
                setGlobalAlgorithmId('')
                toast.success('已清除全局算法，显示全部算法的维度')
              }}
              canFilter={canRead}
              onReset={() => {
                resetSearch()
                setStatusFilter('all')
                setCategoryFilter('all')
                setAlgorithmFilter('all')
                setPage(1)
              }}
            />

            {/* 内容区（列表/分组双视图） */}
            <div className='min-h-0 flex-1 overflow-y-auto'>
              {dimensionsQuery.isLoading ? (
                <div className='space-y-2'>
                  <Skeleton className='h-11 w-full rounded-xl' />
                  <Skeleton className='h-11 w-full rounded-xl' />
                  <Skeleton className='h-11 w-full rounded-xl' />
                </div>
              ) : dimensionsQuery.isError ? (
                <div className='bg-card ring-foreground/10 rounded-xl ring-1'>
                  <Empty className='h-72'>
                    <EmptyMedia variant='icon'>
                      <ListChecks aria-hidden='true' className='size-4' />
                    </EmptyMedia>
                    <EmptyHeader>
                      <EmptyTitle>加载失败</EmptyTitle>
                      <EmptyDescription>评估维度加载失败，请重试</EmptyDescription>
                    </EmptyHeader>
                    <EmptyContent>
                      <Button
                        variant='outline'
                        size='sm'
                        onClick={() => void dimensionsQuery.refetch()}
                      >
                        请重试
                      </Button>
                    </EmptyContent>
                  </Empty>
                </div>
              ) : (viewMode === 'list'
                  ? hierarchicalDimensions.length === 0
                  : groupedDimensions.length === 0) ? (
                <div className='bg-card ring-foreground/10 rounded-xl ring-1'>
                  <Empty className='h-72'>
                    <EmptyMedia variant='icon'>
                      <ListChecks aria-hidden='true' className='size-4' />
                    </EmptyMedia>
                    <EmptyHeader>
                      <EmptyTitle>暂无评估维度</EmptyTitle>
                      <EmptyDescription>
                        点击右上角「新增维度」创建第一个评估维度
                      </EmptyDescription>
                    </EmptyHeader>
                    {canManage && (
                      <EmptyContent>
                        <Button
                          variant='outline'
                          size='sm'
                          onClick={() =>
                            setMutateDrawer({
                              open: true,
                              mode: 'create',
                              dimension: null,
                            })
                          }
                        >
                          新增维度
                        </Button>
                      </EmptyContent>
                    )}
                  </Empty>
                </div>
              ) : viewMode === 'list' ? (
                <DimensionTable
                  items={pageRows}
                  selectedIds={selectedIds}
                  onToggleSelection={toggleSelection}
                  onToggleSelectAll={toggleSelectAll}
                  categories={categories}
                  canManage={canManage}
                  canRead={canRead}
                  canMoveUp={canMoveUp}
                  canMoveDown={canMoveDown}
                  weightPendingIds={weightPendingIds}
                  algorithmLabels={algorithmLabels}
                  onEdit={(dimension) =>
                    setMutateDrawer({
                      open: true,
                      mode: 'edit',
                      dimension,
                    })
                  }
                  onDelete={(dimension) =>
                    setConfirm({ kind: 'delete-dimension', dimension })
                  }
                  onDuplicate={(dimension) =>
                    setConfirm({ kind: 'duplicate-dimension', dimension })
                  }
                  onAddSub={openAddSub}
                  onTestApi={(dimension) =>
                    setHealthDialog({ open: true, dimension })
                  }
                  onRuleCalc={(dimension) =>
                    setRuleCalc({ open: true, dimension })
                  }
                  onToggleStatus={toggleStatus}
                  onMove={moveDimension}
                  onWeightCommit={commitWeight}
                />
              ) : (
                <GroupedDimensionList
                  groups={groupedDimensions}
                  selectedIds={selectedIds}
                  onToggleSelection={toggleSelection}
                  canManage={canManage}
                  canRead={canRead}
                  canMoveUp={canMoveUp}
                  canMoveDown={canMoveDown}
                  weightPendingIds={weightPendingIds}
                  algorithmLabels={algorithmLabels}
                  onEdit={(dimension) =>
                    setMutateDrawer({
                      open: true,
                      mode: 'edit',
                      dimension,
                    })
                  }
                  onDelete={(dimension) =>
                    setConfirm({ kind: 'delete-dimension', dimension })
                  }
                  onDuplicate={(dimension) =>
                    setConfirm({ kind: 'duplicate-dimension', dimension })
                  }
                  onAddSub={openAddSub}
                  onTestApi={(dimension) =>
                    setHealthDialog({ open: true, dimension })
                  }
                  onRuleCalc={(dimension) =>
                    setRuleCalc({ open: true, dimension })
                  }
                  onToggleStatus={toggleStatus}
                  onMove={moveDimension}
                  onWeightCommit={commitWeight}
                  onAddDimension={openAddInCategory}
                  onEditCategory={(category) =>
                    setCategoryDialog({ open: true, category })
                  }
                  onDeleteCategory={(category) =>
                    setConfirm({ kind: 'delete-category', category })
                  }
                />
              )}
            </div>

            {/* 批量浮条（§4.1 勾选 ≥1 后走浮条或页头下拉） */}
            {selectedIds.size > 0 && canManage && (
              <div className='shadow-xl flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-background/95 p-2 backdrop-blur-lg'>
                <span className='text-muted-foreground px-1 text-sm tabular-nums'>
                  已选择 {selectedIds.size} 个维度
                </span>
                <div className='flex items-center gap-1'>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() =>
                      setConfirm({
                        kind: 'batch-action',
                        action: 'enable',
                        count: selectedIds.size,
                      })
                    }
                  >
                    批量启用
                  </Button>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() =>
                      setConfirm({
                        kind: 'batch-action',
                        action: 'disable',
                        count: selectedIds.size,
                      })
                    }
                  >
                    批量禁用
                  </Button>
                  <Button
                    variant='destructive'
                    size='sm'
                    onClick={() =>
                      setConfirm({
                        kind: 'batch-action',
                        action: 'delete',
                        count: selectedIds.size,
                      })
                    }
                  >
                    批量删除
                  </Button>
                </div>
              </div>
            )}

            {/* 分页 Portal（§4.1 DataTablePagination 页脚） */}
            <PageFooterPortal>
              <div className='flex flex-wrap items-center justify-end gap-2 text-sm'>
                <span className='text-muted-foreground tabular-nums'>
                  共 {sorted.length} 条
                </span>
                <Select
                  value={String(pageSize)}
                  onValueChange={(value) => {
                    setPageSize(Number(value ?? 10))
                    setPage(1)
                  }}
                >
                  <SelectTrigger size='sm' className='w-24'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[10, 20, 30, 40, 50, 100].map((size) => (
                      <SelectItem key={size} value={String(size)}>
                        {size} 条/页
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className='flex items-center gap-1'>
                  <Button
                    variant='outline'
                    size='sm'
                    disabled={safePage <= 1}
                    onClick={() => setPage(safePage - 1)}
                  >
                    上一页
                  </Button>
                  <span className='text-muted-foreground px-1 tabular-nums'>
                    {safePage} / {pageCount}
                  </span>
                  <Button
                    variant='outline'
                    size='sm'
                    disabled={safePage >= pageCount}
                    onClick={() => setPage(safePage + 1)}
                  >
                    下一页
                  </Button>
                </div>
              </div>
            </PageFooterPortal>
          </div>
        </SectionPageLayout.Content>
      </SectionPageLayout>

      {/* 弹窗群（§5.5 + §4.1 确认族） */}
      <DimensionMutateDrawer
        open={mutateDrawer.open}
        onOpenChange={(open) =>
          setMutateDrawer((prev) => ({
            ...prev,
            open,
            dimension: open ? prev.dimension : null,
          }))
        }
        mode={mutateDrawer.mode}
        dimension={mutateDrawer.dimension}
        presetParentId={mutateDrawer.presetParentId}
        presetCategoryId={mutateDrawer.presetCategoryId}
        categories={categories}
        mainDimensions={dimensions.filter((d) => !d.parentDimensionId)}
        algorithmOptions={algorithmOptions}
        canManage={canManage}
      />
      <CategoryMutateDialog
        open={categoryDialog.open}
        onOpenChange={(open) =>
          setCategoryDialog((prev) => ({
            ...prev,
            open,
            category: open ? prev.category : null,
          }))
        }
        category={categoryDialog.category}
        onSave={handleSaveCategory}
      />
      <RuleCalcDialog
        open={ruleCalc.open}
        onOpenChange={(open) =>
          setRuleCalc((prev) => ({
            ...prev,
            open,
            dimension: open ? prev.dimension : null,
          }))
        }
        dimension={ruleCalc.dimension}
        calculate={calculate}
      />
      <HealthTestDialog
        open={healthDialog.open}
        onOpenChange={(open) =>
          setHealthDialog((prev) => ({
            ...prev,
            open,
            dimension: open ? prev.dimension : null,
          }))
        }
        dimension={healthDialog.dimension}
        healthTest={healthTest}
      />
      <EvaluationConfirmDialog
        open={confirm != null}
        onOpenChange={(open) => !open && setConfirm(null)}
        state={confirm}
        onConfirm={handleConfirm}
      />
    </>
  )
}
