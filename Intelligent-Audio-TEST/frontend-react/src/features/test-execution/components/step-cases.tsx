/**
 * 步骤二：选择测试用例（10_测试执行.md §3.5；INT-710 与用例管理页「一模一样」）。
 * 负责人 2026-10-18 口径：开始测试的用例选择直接复用用例管理页的列表、筛选（分组/标签分类/
 * 搜索）、视图切换组件，不再单独实现一套——按分组/按标签页签 + TestCasesFilterToolbar +
 * GroupedCaseList/TagCaseList（真实接口）。向导专用选择操作（全选结果/反选/重置）与已选汇总行
 * 保留（§3.5 本页不启用批量浮条，汇总行承担全部选择态操作）。
 * 选择态经 useCaseSelectionStore（manual/filter-all）适配为管理组件消费的 Set + checked 回调。
 *
 * INT-1138 行内/分组操作全功能对齐（负责人 2026-10-21 反馈「开始测试页面能做用例管理页能做的
 * 所有功能」）：收藏/编辑/复制/删除/预览、分组 CRUD 全部真实接线——收藏经 setTestCaseFavorite
 * 就地回写缓存（不整表重拉）、复制走 POST /testcases/{id}/copy、删除/恢复/彻底删除/删除分组走
 * CaseConfirmDialog 确认后真实调用、分组复制走 POST /testcases/batch copy_by_group。readOnly
 * 观察态（§3.1.1）动作钮/勾选/收藏回收站切换全部隐藏，选中态静态展示。
 * INT-1026 组头「批量修改」九项弹窗（CaseBatchActionsHost）与行内/分组操作并存（集成合流保留）。
 */
import { ListChecks, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { useAlgorithmChannel } from '@/application/test-execution/useAlgorithmChannel'
import { useCaseSelection } from '@/application/test-execution/useCaseSelection'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useAlgorithmLabels } from '@/application/hooks/use-algorithm-options'
import { CaseRoundsProvider } from '@/application/testcases/case-rounds-registry'
import { useTestCasesList, type TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import { useCaseGroups } from '@/application/testcases/use-case-groups'
import { useCaseTags, useTagCategories } from '@/application/testcases/use-case-tags'
import { useTagMutations } from '@/application/tags/useTags'
import { useEvaluationDimensions, useEvaluationCategories } from '@/application/evaluation/use-dimensions'
import { useCaseBatchActions } from '@/application/testcases/use-case-batch-actions'
import { useCaseSelectionStore } from '@/infrastructure/stores/case-selection-store'
import { fetchCaseIdsByFilter } from '@/infrastructure/api/testcases-ids-api'
import {
  copyTestCase,
  deleteTestCase,
  purgeTestCases,
  restoreTestCases,
  setTestCaseFavorite,
  type TestCaseListResult,
} from '@/infrastructure/api/testcases-api'
import { deleteGroup } from '@/infrastructure/api/groups-api'
import { deleteTag } from '@/infrastructure/api/tags-api'
import { batchTestcaseAction } from '@/infrastructure/api/testcases-batch-api'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/confirm-dialog'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagDraft } from '@/domain/models/testTag'

import {
  TEST_CASES_TABS,
  type TestCasesViewKey,
} from '@/features/testcases/constants'
import { TestCasesFilterToolbar } from '@/features/testcases/components/testcases-filter-toolbar'
import { GroupedCaseList, type GroupActionCallbacks } from '@/features/testcases/components/grouped-case-list'
import { CaseBatchActionsHost } from '@/features/testcases/components/case-batch-actions-host'
import { TagCaseList } from '@/features/testcases/components/tag-case-list'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'
import { CaseMutateDrawer } from '@/features/testcases/modals/case-mutate-drawer'
import { GroupMutateDialog } from '@/features/testcases/modals/group-mutate-dialog'
import { AudioPreviewConfigDialog } from '@/features/testcases/modals/audio-preview-config-dialog'
import {
  CaseConfirmDialog,
  type CaseConfirmState,
} from '@/features/testcases/modals/case-confirms'
import { SelectionSummary } from '@/features/test-execution/components/selection-summary'

interface StepCasesProps {
  readOnly: boolean
  /** 保留父级 URL view 契约（表格/卡片→按分组/按标签映射为初始值）；不再独立实现表格/卡片 */
  view: 'table' | 'card'
  onViewChange: (view: 'table' | 'card') => void
  /** 全量圈定/过滤空态用（步骤一算法联动 chip 由 toolBar 内嵌） */
  onGoStep0?: () => void
}

export function StepCases({ readOnly, view }: StepCasesProps) {
  const { hasPermission } = usePermissions()
  const { algorithmType } = useAlgorithmChannel()
  /** 算法类型码 → 中文名（真实 /algorithm/options；卡片算法徽章，INT-1687） */
  const algorithmLabels = useAlgorithmLabels()
  const selection = useCaseSelection([])
  const store = useCaseSelectionStore
  const queryClient = useQueryClient()

  const [caseView, setCaseView] = useState<TestCasesViewKey>(
    view === 'card' ? 'by-tag' : 'by-group'
  )
  const [filters, setFilters] = useState<TestCaseListFilters>({})
  const [pendingSelectAll, setPendingSelectAll] = useState(false)

  // 弹窗/确认状态（行内/分组操作装配，11_用例域.md §5）
  const [mutateCase, setMutateCase] = useState<TestCaseListItem | null>(null)
  const [mutateOpen, setMutateOpen] = useState(false)
  const [presetGroupId, setPresetGroupId] = useState<string | null>(null)
  const [groupDialog, setGroupDialog] = useState<{
    open: boolean
    group: TestCaseGroup | null
  }>({ open: false, group: null })
  const [previewCase, setPreviewCase] = useState<TestCaseListItem | null>(null)
  const [confirm, setConfirm] = useState<CaseConfirmState | null>(null)
  /** 确认弹窗目标对象（case/group/restore-all 的 ids），随 confirm 打开写入、关闭清空 */
  const [confirmTarget, setConfirmTarget] = useState<{
    caseItem?: TestCaseListItem
    group?: TestCaseGroup
    deletedIds?: string[]
  } | null>(null)
  /** 复制分组确认（§3.5 ConfirmDialog「复制后将成为新分组：{名}_copy」） */
  const [copyGroup, setCopyGroup] = useState<TestCaseGroup | null>(null)

  const canSelect = hasPermission('testcase:read') && !readOnly

  /** 生效筛选（全局算法联动合并；INT-1284 分组内懒加载按同一筛选取数） */
  const effectiveFilters = useMemo(
    () => ({ ...filters, algorithmType: filters.algorithmType ?? algorithmType }),
    [filters, algorithmType]
  )

  const listQuery = useTestCasesList(caseView, effectiveFilters)
  const groupsQuery = useCaseGroups()
  const tagsQuery = useCaseTags()
  /** 标签分类（标签操作·编辑标签弹窗所属分类选项；INT-1294 接线） */
  const tagCategoriesQuery = useTagCategories()
  /** 标签增改 mutation（invalidate ['tags'] 前缀，三页联动刷新；删除级联走 deleteTag 直连） */
  const { updateTagMutation } = useTagMutations()
  /** 全量评估维度（含子维度）+ 分类：与用例管理页同源（INT-1030 走查打回 P2-2——不再用
   *  /evaluation/dimensions/options 旧 facet 子集，保证 开始测试 筛选 facet 与用例管理分组一致） */
  const allDimsQuery = useEvaluationDimensions()
  const categoriesQuery = useEvaluationCategories()

  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? items.length
  const groups = groupsQuery.data ?? []
  const tags = tagsQuery.data ?? []
  const dimensions = allDimsQuery.data ?? []
  const categories = categoriesQuery.data ?? []
  const tagCategories = tagCategoriesQuery.data ?? []

  const isFiltered = useMemo(
    () =>
      Object.entries(filters).some(([key, value]) => {
        if (key === 'algorithmType') return false
        return value != null && value !== '' && value !== false
      }),
    [filters]
  )

  /** 非回收站筛选是否激活（搜索/分组/标签/维度）——回收站空态区分「真空」与「筛选无匹配」 */
  const hasQueryFilters = useMemo(
    () =>
      Object.entries(filters).some(([key, value]) => {
        if (key === 'algorithmType' || key === 'trash' || key === 'favorite')
          return false
        return value != null && value !== '' && value !== false
      }),
    [filters]
  )

  /** 选择态适配（store manualCaseIds → 管理组件消费的 Set<string>） */
  const selectedSet = useMemo(
    () => new Set(selection.manualCaseIds),
    [selection.manualCaseIds]
  )

  /** 批量弹窗状态机（七件套弹窗 + 两确认；INT-1026 与用例管理页共享 host 双挂） */
  const batch = useCaseBatchActions({ onClearSelection: selection.clearSelection })

  /** 批量设置评估维度透传的 testType（取第一个选中用例；INT-486 口径对齐 /testcases） */
  const selectedTestType = useMemo(
    () => items.find((c) => selectedSet.has(c.id))?.type ?? null,
    [items, selectedSet]
  )

  /** 工具栏分组筛选对应的分组名（POST /testcases/ids 契约只认 group 名；__ungrouped__ 无 /groups 映射） */
  const groupName = useMemo(
    () => groups.find((g) => g.id === filters.groupId)?.name,
    [groups, filters.groupId]
  )

  /**
   * INT-1544：页面筛选持续同步进 case-selection store（缺陷根因——此前 store.filter 恒为 {}，
   * filter-all 圈定忽略筛选条件，界面「全部 1 条」却按全部用例建任务）。
   * 本组件在离开步骤一时卸载，筛选态必须落到 store 才能随启动流程传入 createTask；
   * 键与 POST /testcases/ids 契约一致（search / group 名 / tag / dimension_id / algorithm_type，
   * 与「全选结果」同一口径）。收藏/回收站是列表视图开关，不进圈定条件。
   */
  useEffect(() => {
    store.getState().setFilter(
      {
        search: filters.search?.trim() || undefined,
        group: groupName ?? null,
        tag: filters.tag ?? null,
        dimensionId: filters.dimensionId ?? null,
        algorithmType: filters.algorithmType ?? algorithmType ?? null,
      },
      total
    )
  }, [
    store,
    filters.search,
    filters.tag,
    filters.dimensionId,
    filters.algorithmType,
    groupName,
    algorithmType,
    total,
  ])

  const handleToggleSelect = (id: string, checked: boolean) => {
    if (canSelect && checked !== selectedSet.has(id)) store.getState().toggleCase(id)
  }

  const handleToggleAll = (ids: string[], checked: boolean) => {
    if (!canSelect) return
    if (checked) store.getState().selectMany(ids)
    else store.getState().removeMany(ids)
  }

  /** 全选结果（真实 POST /testcases/ids 按当前筛选圈定；分组筛选传分组名，INT-1267 契约对齐） */
  const handleSelectAllFiltered = async () => {
    setPendingSelectAll(true)
    try {
      const { ids, total: count } = await fetchCaseIdsByFilter({
        search: filters.search,
        group: groupName,
        tag: filters.tag,
        dimensionId: filters.dimensionId,
        algorithmType: filters.algorithmType ?? algorithmType,
      })
      store.getState().selectMany(ids)
      toast.success(`已全选 ${count} 条用例`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '全选用例失败，请重试')
    } finally {
      setPendingSelectAll(false)
    }
  }

  /** 反选（对称差；分组筛选传分组名，INT-1267 契约对齐） */
  const handleInvert = async () => {
    try {
      const { ids } = await fetchCaseIdsByFilter({
        search: filters.search,
        group: groupName,
        tag: filters.tag,
        dimensionId: filters.dimensionId,
        algorithmType: filters.algorithmType ?? algorithmType,
      })
      store.getState().invertWith(ids)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '反选用例失败，请重试')
    }
  }

  const handleReset = () => setFilters({})

  /** 列表/分组缓存刷新（删/改/复制后重拉；收藏除外——收藏走就地回写） */
  const refreshCases = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['testcases'] })
    // INT-1284：分组内懒加载缓存（独立前缀，避免误命中列表就地回写/透明度判定）
    void queryClient.invalidateQueries({ queryKey: ['testcase-group-cases'] })
  }, [queryClient])
  const refreshGroups = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['testcase-groups'] })
  }, [queryClient])

  /** INT-1294 标签操作真实接线（与用例管理页同款：编辑 PUT /tags/{id}、删除 DELETE /tags/{id}
   *  ?cascade=true 级联、复制 POST /testcases/batch copy_by_tag）；改名/删除当前筛选标签时清空标签筛选 */
  const handleUpdateTag = async (id: number, draft: TagDraft) => {
    await updateTagMutation.mutateAsync({ id, draft })
    refreshCases()
    const current = tags.find((t) => t.id === id)
    if (current && current.name !== draft.name && filters.tag === current.name) {
      setFilters((prev) => ({ ...prev, tag: null }))
    }
  }

  const handleDeleteTag = async (id: number) => {
    await deleteTag(id, true)
    await queryClient.invalidateQueries({ queryKey: ['tags'] })
    refreshCases()
    const current = tags.find((t) => t.id === id)
    if (current && filters.tag === current.name) {
      setFilters((prev) => ({ ...prev, tag: null }))
    }
  }

  const handleCopyTag = async (tagName: string, copyToNewGroup: boolean) => {
    await batchTestcaseAction('copy_by_tag', [], { tagName, copyToNewGroup })
    refreshCases()
    refreshGroups()
  }

  /** 收藏/取消收藏（POST/DELETE /testcases/{id}/favorite，就地回写缓存，不整表重拉） */
  const handleFavorite = useCallback(
    async (c: TestCaseListItem) => {
      const next = c.isFavorite !== true
      try {
        await setTestCaseFavorite(c.id, next)
        queryClient.setQueriesData<TestCaseListResult>(
          { queryKey: ['testcases'] },
          (prev) => {
            if (!prev) return prev
            return {
              ...prev,
              items: prev.items.map((item) =>
                item.id === c.id ? { ...item, isFavorite: next } : item
              ),
            }
          }
        )
        toast.success(next ? '已收藏' : '已取消收藏')
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '收藏操作失败，请重试')
      }
    },
    [queryClient]
  )

  /** 复制用例（POST /testcases/{id}/copy → Toast「已复制测试用例」+ 描述「已创建副本」） */
  const handleCopy = useCallback(
    async (c: TestCaseListItem) => {
      try {
        await copyTestCase(c.id)
        toast.success('已复制测试用例', { description: `已创建副本：${c.name}_copy` })
        refreshCases()
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '复制用例失败，请重试')
      }
    },
    [refreshCases]
  )

  /** 确认弹窗打开（delete/restore/purge/delete-group/restore-all 统一入口） */
  const openConfirm = (
    state: CaseConfirmState,
    target?: { caseItem?: TestCaseListItem; group?: TestCaseGroup; deletedIds?: string[] }
  ) => {
    setConfirmTarget(target ?? null)
    setConfirm(state)
  }

  /** 确认执行（CaseConfirmDialog onConfirm；真实 API + 勾选集同步 + 列表刷新） */
  const handleConfirm = (state: CaseConfirmState) => {
    const target = confirmTarget
    setConfirm(null)
    setConfirmTarget(null)
    switch (state.kind) {
      case 'delete': {
        const c = target?.caseItem
        if (!c) return
        void deleteTestCase(c.id)
          .then(() => {
            store.getState().removeSelected([c.id])
            toast.success('已移入回收站')
            refreshCases()
          })
          .catch((error) =>
            toast.error(error instanceof Error ? error.message : '删除用例失败，请重试')
          )
        break
      }
      case 'restore': {
        const c = target?.caseItem
        if (!c) return
        void restoreTestCases([c.id])
          .then((restored) => {
            if (restored > 0) {
              store.getState().removeSelected([c.id])
              toast.success(`用例「${c.name}」已恢复`)
            } else {
              toast.info('无可恢复项（用例可能已被恢复）')
            }
            refreshCases()
          })
          .catch((error) =>
            toast.error(error instanceof Error ? error.message : '恢复用例失败，请重试')
          )
        break
      }
      case 'purge': {
        const c = target?.caseItem
        if (!c) return
        void purgeTestCases([c.id])
          .then((purged) => {
            if (purged > 0) {
              store.getState().removeSelected([c.id])
              toast.success(`用例「${c.name}」已彻底删除`)
            } else {
              toast.info('无可删除项（用例可能已被删除或不满足权限）')
            }
            refreshCases()
          })
          .catch((error) =>
            toast.error(error instanceof Error ? error.message : '彻底删除用例失败，请重试')
          )
        break
      }
      case 'delete-group': {
        const g = target?.group
        if (!g) return
        void deleteGroup(g.id, true)
          .then(() => {
            // 删除当前筛选分组后清分组筛选（§3.5）
            setFilters((prev) =>
              prev.groupId === g.id ? { ...prev, groupId: null } : prev
            )
            // 已选中的该组用例同步移出勾选集
            const groupIds = items
              .filter((c) => c.groupId === g.id)
              .map((c) => c.id)
            store.getState().removeSelected(groupIds)
            toast.success('删除分组成功')
            refreshCases()
            refreshGroups()
          })
          .catch((error) =>
            toast.error(error instanceof Error ? error.message : '删除分组失败，请重试')
          )
        break
      }
      case 'restore-all': {
        const deletedIds = target?.deletedIds
        if (!deletedIds || deletedIds.length === 0) return
        void restoreTestCases(deletedIds)
          .then((restored) => {
            store.getState().removeSelected(deletedIds)
            toast.success(`已恢复 ${restored} 个用例`)
            refreshCases()
          })
          .catch((error) =>
            toast.error(error instanceof Error ? error.message : '恢复失败，请重试')
          )
        break
      }
      default:
        break
    }
  }

  /** 复制分组（POST /testcases/batch copy_by_group；ConfirmDialog 文案照 §3.5） */
  const handleCopyGroup = useCallback(
    (g: TestCaseGroup) => {
      void batchTestcaseAction('copy_by_group', [], { groupName: g.name })
        .then(() => {
          toast.success('已复制分组', { description: `新分组：${g.name}_copy` })
          refreshCases()
          refreshGroups()
        })
        .catch((error) =>
          toast.error(error instanceof Error ? error.message : '复制分组失败，请重试')
        )
    },
    [refreshCases, refreshGroups]
  )

  const openCreateCase = (group: TestCaseGroup | null) => {
    setPresetGroupId(group?.id ?? null)
    setMutateCase(null)
    setMutateOpen(true)
  }

  const openEditCase = (c: TestCaseListItem) => {
    setPresetGroupId(null)
    setMutateCase(c)
    setMutateOpen(true)
  }

  /** 向导语境行内操作（INT-1138 去 stub：真实接线，与用例管理页同组件/同确认文案） */
  const rowCallbacks = useMemo<CaseCardCallbacks>(
    () => ({
      onPreview: (c) => setPreviewCase(c),
      onCopy: (c) => void handleCopy(c),
      onFavorite: (c) => void handleFavorite(c),
      onEdit: (c) => openEditCase(c),
      onDelete: (c) => openConfirm({ kind: 'delete', name: c.name }, { caseItem: c }),
      onRestore: (c) => openConfirm({ kind: 'restore', name: c.name }, { caseItem: c }),
      onPurge: (c) => openConfirm({ kind: 'purge', name: c.name }, { caseItem: c }),
    }),
    [handleCopy, handleFavorite]
  )

  /** 分组操作（§3.5：新增用例预填 group_id / 编辑 GroupMutateDialog / 复制/删除确认） */
  const groupCallbacks = useMemo<GroupActionCallbacks>(
    () => ({
      onCreateInGroup: (group) => openCreateCase(group),
      onEditGroup: (group) => setGroupDialog({ open: true, group }),
      onDeleteGroup: (group) =>
        openConfirm({ kind: 'delete-group', name: group.name }, { group }),
      onCopyGroup: (group) => setCopyGroup(group),
    }),
    []
  )

  /** 回收站「全部恢复」：确认后真实恢复当前已加载的回收站用例 */
  const handleRestoreAll = () => {
    const deletedIds = items.filter((c) => c.deleted).map((c) => c.id)
    if (deletedIds.length === 0) {
      toast.info('回收站为空')
      return
    }
    openConfirm({ kind: 'restore-all', count: deletedIds.length }, { deletedIds })
  }

  const canManage = !readOnly

  return (
    <CaseRoundsProvider cases={items}>
      <div className='flex flex-col gap-3'>
        {/* 视图页签：按分组/按标签（用例管理页同款） */}
        <Tabs value={caseView} onValueChange={(v) => setCaseView(v as TestCasesViewKey)}>
          <TabsList variant='line' className='max-w-full flex-wrap justify-start'>
            {TEST_CASES_TABS.map((t) => (
              <TabsTrigger key={t.key} value={t.key} className='px-3'>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {/* 筛选工具栏（用例管理页同款：搜索/分组/标签分类/评估维度）；readOnly 隐藏收藏回收站/重置 */}
        <TestCasesFilterToolbar
          filters={filters}
          onChange={setFilters}
          onReset={handleReset}
          isFiltered={isFiltered}
          groups={groups}
          tags={tags}
          tagsError={tagsQuery.isError}
          tagsLoading={tagsQuery.isLoading}
          onRetryTags={() => void tagsQuery.refetch()}
          dimensions={dimensions}
          categories={categories}
          tagCategories={tagCategories}
          onUpdateTag={handleUpdateTag}
          onDeleteTag={handleDeleteTag}
          onCopyTag={handleCopyTag}
          cases={items}
          onRestoreAll={handleRestoreAll}
          readOnly={readOnly}
        />

        {/* 向导专用选择操作（§3.5：本页不启用批量浮条，汇总行承担选择态操作） */}
        {canManage && canSelect && (
          <div className='flex flex-wrap items-center gap-2'>
            <Button
              variant='outline'
              size='sm'
              className='h-8 gap-1.5 text-xs'
              disabled={pendingSelectAll}
              onClick={() => void handleSelectAllFiltered()}
            >
              <ListChecks aria-hidden='true' className='size-3.5' />
              全选结果
            </Button>
            <Button variant='outline' size='sm' className='h-8 gap-1.5 text-xs' onClick={() => void handleInvert()}>
              反选
            </Button>
            {isFiltered && (
              <Button variant='ghost' size='sm' className='h-8 gap-1.5 text-xs' onClick={handleReset}>
                <X aria-hidden='true' className='size-3.5' />
                重置
              </Button>
            )}
          </div>
        )}

        {/* 内容区（分组/标签卡片流，与用例管理页同一组件）；readOnly 不传动作回调 → 动作钮隐藏 */}
        <div className='min-h-0 flex-1 overflow-auto'>
          {caseView === 'by-group' ? (
            <GroupedCaseList
              groups={groups}
              cases={items}
              loading={listQuery.isLoading}
              groupsLoading={groupsQuery.isLoading}
              filters={effectiveFilters}
              trash={filters.trash ?? false}
              hasQueryFilters={hasQueryFilters}
              selected={selectedSet}
              tagRegistry={tags}
              algorithmLabels={algorithmLabels}
              callbacks={canManage ? rowCallbacks : undefined}
              onBatchAction={batch.openBatch}
              actionCallbacks={canManage ? groupCallbacks : undefined}
              onToggleSelect={canManage ? handleToggleSelect : undefined}
              onToggleAll={canManage ? handleToggleAll : undefined}
            />
          ) : (
            <TagCaseList
              cases={items}
              loading={listQuery.isLoading}
              selected={selectedSet}
              tagRegistry={tags}
              algorithmLabels={algorithmLabels}
              callbacks={canManage ? rowCallbacks : undefined}
              onToggleSelect={canManage ? handleToggleSelect : undefined}
              onToggleAll={canManage ? handleToggleAll : undefined}
              onCreate={canManage ? () => openCreateCase(null) : undefined}
            />
          )}
        </div>

        {/* 已选汇总行（常驻） */}
        {canManage && (
          <SelectionSummary
            mode='case'
            count={selection.selectedCount}
            manual={selection.summary.manual}
            invertAdded={selection.summary.invertAdded}
            total={total}
            onClear={selection.clearSelection}
          />
        )}

        {/* 弹窗群（复用用例管理页组件，§5：行内/分组操作） */}
        <CaseMutateDrawer
          open={mutateOpen}
          onOpenChange={setMutateOpen}
          caseItem={mutateCase}
          groups={groups}
          presetGroupId={presetGroupId}
        />
        <GroupMutateDialog
          open={groupDialog.open}
          onOpenChange={(open) => setGroupDialog((prev) => ({ ...prev, open }))}
          group={groupDialog.group}
        />
        <AudioPreviewConfigDialog
          open={previewCase != null}
          onOpenChange={(open) => !open && setPreviewCase(null)}
          caseItem={previewCase}
        />
        <CaseConfirmDialog
          open={confirm != null}
          onOpenChange={(open) => !open && setConfirm(null)}
          state={confirm}
          onConfirm={handleConfirm}
        />
        <ConfirmDialog
          open={copyGroup != null}
          onOpenChange={(open) => !open && setCopyGroup(null)}
          title='复制分组'
          desc={`确定要复制分组「${copyGroup?.name ?? ''}」下的 ${copyGroup?.testCaseCount ?? 0} 个用例吗？复制后将成为新分组：${copyGroup?.name ?? ''}_copy`}
          confirmText='复制'
          handleConfirm={() => {
            if (copyGroup) handleCopyGroup(copyGroup)
            setCopyGroup(null)
          }}
        />

        {/* 批量弹窗群（INT-1026：组头「批量修改」九项与 /testcases 同款弹窗，共享 host） */}
        <CaseBatchActionsHost
          batchDialog={batch.batchDialog}
          setBatchDialog={batch.setBatchDialog}
          confirm={batch.confirm}
          setConfirm={batch.setConfirm}
          handleConfirm={batch.handleConfirm}
          groups={groups}
          tags={tags}
          dimensions={dimensions}
          categories={categories}
          algorithmType={algorithmType}
          testType={selectedTestType}
        />
      </div>
    </CaseRoundsProvider>
  )
}
