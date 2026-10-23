/**
 * 用例管理页（11_用例域.md §3.1 页面总骨架，SectionPageLayout fixedContent + 双视图表格）。
 * 装配：Breadcrumb 工作台/用例管理｜Title「用例管理」｜Actions（+新增用例/导入用例/导出/模板下载）｜
 * Content（视图页签 line → 筛选工具栏 → 分组/平铺表格 → 批量浮条）/ Footer（分页 Portal）。
 * 「导入用例」为单入口（负责人 2026-10-17 口径：只走音频导入页生成，照 V9.7.10 跳 /AudioImport）。
 * 路由 /testcases/$view（by-group/by-tag 白名单在路由层）；mock 态全部弹窗/toast 演示，
 * 接线后替换为 application/testcases mutations + URL 态 useTableUrlState。
 */
import { Link, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { FileDown, FileSpreadsheet, FileUp, Plus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useEvaluationDimensions, useEvaluationCategories } from '@/application/evaluation/use-dimensions'
import { useCaseGroups } from '@/application/testcases/use-case-groups'
import { useCaseTags, useTagCategories } from '@/application/testcases/use-case-tags'
import { useTagMutations } from '@/application/tags/useTags'
import { useCaseBatchActions } from '@/application/testcases/use-case-batch-actions'
import {
  useTestCasesList,
  type TestCaseListFilters,
} from '@/application/testcases/use-testcases-list'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagDraft } from '@/domain/models/testTag'
import {
  TEST_CASES_TABS,
  type TestCasesViewKey,
} from '@/features/testcases/constants'
import { TestCasesFilterToolbar } from '@/features/testcases/components/testcases-filter-toolbar'
import { GroupedCaseList, type GroupActionCallbacks } from '@/features/testcases/components/grouped-case-list'
import { TagCaseList } from '@/features/testcases/components/tag-case-list'
import { CaseBulkActions } from '@/features/testcases/components/case-bulk-actions'
import { CaseBatchActionsHost } from '@/features/testcases/components/case-batch-actions-host'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'
import { CaseMutateDrawer } from '@/features/testcases/modals/case-mutate-drawer'
import { ExportDialog } from '@/features/testcases/modals/export-dialog'
import { GroupMutateDialog } from '@/features/testcases/modals/group-mutate-dialog'
import { AudioPreviewConfigDialog } from '@/features/testcases/modals/audio-preview-config-dialog'
import {
  batchTestcaseAction,
} from '@/infrastructure/api/testcases-batch-api'
import {
  copyTestCase,
  setTestCaseFavorite,
} from '@/infrastructure/api/testcases-api'
import { deleteTag } from '@/infrastructure/api/tags-api'

export function TestCasesPage({ view }: { view: TestCasesViewKey }) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)

  const [filters, setFilters] = useState<TestCaseListFilters>({})
  const [selected, setSelected] = useState<Set<string>>(new Set())

  // 弹窗状态
  const [mutateCase, setMutateCase] = useState<TestCaseListItem | null>(null)
  const [mutateOpen, setMutateOpen] = useState(false)
  const [presetGroupId, setPresetGroupId] = useState<string | null>(null)
  const [exportOpen, setExportOpen] = useState(false)
  const [groupDialog, setGroupDialog] = useState<{ open: boolean; group: TestCaseGroup | null }>({ open: false, group: null })
  const [previewCase, setPreviewCase] = useState<TestCaseListItem | null>(null)

  /** 生效筛选（全局算法联动合并；INT-1284 分组内懒加载按同一筛选取数） */
  const effectiveFilters = useMemo(
    () => ({ ...filters, algorithmType: filters.algorithmType ?? algorithmId }),
    [filters, algorithmId]
  )

  const listQuery = useTestCasesList(view, effectiveFilters)
  const groupsQuery = useCaseGroups()
  const tagsQuery = useCaseTags()
  /** 标签分类（标签操作·编辑标签弹窗所属分类选项；INT-1294 接线） */
  const tagCategoriesQuery = useTagCategories()
  /** 标签增改 mutation（invalidate ['tags'] 前缀，三页联动刷新；删除级联走 deleteTag 直连） */
  const { updateTagMutation } = useTagMutations()
  /** 全量评估维度（含子维度；批量设置评估维度 DimensionPicker 主/子分组云 + 列表筛选
   *  评估维度 facet 分组/主维度/子维度 共用，参考 V9.7.10；INT-1030 全站一致性） */
  const allDimsQuery = useEvaluationDimensions()
  /** 评估维度分类（DimensionPicker 分类分组组头；负责人 2026-10-19 口径） */
  const categoriesQuery = useEvaluationCategories()

  /**
   * 用例列表失败态（INT-1605，与 INT-1560 标签页 / INT-1583 音频页同型）：
   * 失败不得伪装成「没有找到符合条件的测试用例」。
   * React Query 的 placeholderData 只覆盖 pending 态，查询失败后 data 变 undefined，
   * 故留一份「最近一次成功结果」快照——翻页/筛选失败时保留旧列表（行内提示条说明
   * 「当前显示的是上一次加载的数据」），不清空。
   */
  const lastGoodCases = useRef<TestCaseListItem[] | null>(null)
  if (listQuery.data) lastGoodCases.current = listQuery.data.items
  const items = listQuery.data?.items ?? lastGoodCases.current ?? []
  const listError = listQuery.isError
  const groups = groupsQuery.data ?? []
  const tags = tagsQuery.data ?? []
  const allDimensions = allDimsQuery.data ?? []
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

  /** 非回收站筛选（搜索/分组/标签/维度）是否激活——回收站空态区分「真空」与「筛选无匹配」 */
  const hasQueryFilters = useMemo(
    () =>
      Object.entries(filters).some(([key, value]) => {
        if (key === 'algorithmType' || key === 'trash' || key === 'favorite')
          return false
        return value != null && value !== '' && value !== false
      }),
    [filters]
  )

  /** 失败但保留着上次数据（翻页/筛选失败）：toast 一次；首屏失败由列表错误态承担（INT-1605） */
  const lastErrorToastAt = useRef(0)
  useEffect(() => {
    if (!listError) return
    if (listQuery.errorUpdatedAt === lastErrorToastAt.current) return
    lastErrorToastAt.current = listQuery.errorUpdatedAt
    if (items.length === 0) return
    toast.error('用例列表加载失败，已保留上一次加载的数据，请重试')
  }, [listError, listQuery.errorUpdatedAt, items.length])

  const clearSelection = useCallback(() => setSelected(new Set()), [])

  /** 批量弹窗状态机（七件套弹窗 + 两确认；INT-1026 共享 host 双挂） */
  const batch = useCaseBatchActions({ onClearSelection: clearSelection })

  /** 分组新建/编辑弹窗关闭后刷新分组与用例列表（INT-997 接线：提交/取消后均刷新，成本低） */
  useEffect(() => {
    if (!groupDialog.open) return
    return () => {
      void queryClient.invalidateQueries({ queryKey: ['testcase-groups'] })
      void queryClient.invalidateQueries({ queryKey: ['testcases'] })
      // INT-1284：分组内懒加载缓存（独立前缀）同步失效
      void queryClient.invalidateQueries({ queryKey: ['testcase-group-cases'] })
    }
  }, [groupDialog.open, queryClient])

  // ESC 清选（11_用例域.md §3.7「X 清选钮 + ESC 清选 + aria-live 播报照搬」）：
  // 批量浮条可见时页面级 keydown Escape → 清空勾选、浮条消失。
  // 弹窗/抽屉打开时 ESC 归其消费（base-ui dialog 在 document 层 stopPropagation，此处再兜底）；
  // 文本输入/IME 组合输入内 ESC 不清选。
  useEffect(() => {
    if (selected.size === 0) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing)
        return
      if (
        mutateOpen ||
        exportOpen ||
        groupDialog.open ||
        previewCase != null ||
        batch.isBatchOpen
      )
        return
      const target = event.target as HTMLElement | null
      if (
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA' ||
        target?.tagName === 'SELECT' ||
        target?.isContentEditable
      )
        return
      clearSelection()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    selected.size,
    clearSelection,
    mutateOpen,
    exportOpen,
    groupDialog.open,
    previewCase,
    batch.isBatchOpen,
  ])

  const toggleSelect = useCallback((id: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }, [])

  const toggleAll = useCallback((ids: string[], checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (checked) ids.forEach((id) => next.add(id))
      else ids.forEach((id) => next.delete(id))
      return next
    })
  }, [])

  /** 视图页签切换：重置筛选与勾选集（URL 态回归：接线后 page/search/… 进 search） */
  const handleViewChange = (next: string) => {
    setFilters({})
    clearSelection()
    void navigate({
      to: '/testcases/$view',
      params: { view: next as TestCasesViewKey },
    })
  }

  const rowCallbacks = useMemo<CaseCardCallbacks>(
    () => ({
      onPreview: (c) => setPreviewCase(c),
      onCopy: (c) => {
        // INT-997：行复制接 POST /testcases/{id}/copy（深度克隆，新名 {name}_copy）
        void (async () => {
          try {
            await copyTestCase(c.id)
            toast.success('已复制测试用例', {
              description: `已创建副本：${c.name}_copy`,
            })
            await queryClient.invalidateQueries({ queryKey: ['testcases'] })
            // INT-1284：分组内懒加载缓存（独立前缀）同步失效
            await queryClient.invalidateQueries({ queryKey: ['testcase-group-cases'] })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : '复制测试用例失败')
          }
        })()
      },
      onFavorite: (c) => {
        // INT-997：行收藏接 POST/DELETE /testcases/{id}/favorite（INT-141 per-user）
        void (async () => {
          try {
            await setTestCaseFavorite(c.id, !c.isFavorite)
            toast.success(c.isFavorite ? '已取消收藏' : '已加入收藏')
            await queryClient.invalidateQueries({ queryKey: ['testcases'] })
            // INT-1284：分组内懒加载缓存（独立前缀）同步失效
            await queryClient.invalidateQueries({ queryKey: ['testcase-group-cases'] })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : '收藏操作失败')
          }
        })()
      },
      onEdit: (c) => {
        setPresetGroupId(null)
        setMutateCase(c)
        setMutateOpen(true)
      },
      onDelete: (c) => batch.setConfirm({ kind: 'delete', ids: [c.id], name: c.name }),
      onRestore: (c) => batch.setConfirm({ kind: 'restore', ids: [c.id], name: c.name }),
      onPurge: (c) => batch.setConfirm({ kind: 'purge', ids: [c.id], name: c.name }),
    }),
    [queryClient, batch.setConfirm]
  )

  const groupCallbacks = useMemo<GroupActionCallbacks>(
    () => ({
      onCreateInGroup: (group) => {
        setPresetGroupId(group?.id ?? null)
        setMutateCase(null)
        setMutateOpen(true)
      },
      onEditGroup: (group) => setGroupDialog({ open: true, group }),
      onDeleteGroup: (group) =>
        batch.setConfirm({ kind: 'delete-group', ids: [group.id], name: group.name }),
      onCopyGroup: (group) => {
        // INT-997：分组复制接 POST /testcases/batch（copy_by_group → 新分组 {name}_copy）
        void (async () => {
          try {
            await batchTestcaseAction('copy_by_group', [], {
              groupName: group.name,
            })
            toast.success('已复制分组', {
              description: `新分组：${group.name}_copy`,
            })
            await queryClient.invalidateQueries({
              queryKey: ['testcases'],
            })
            await queryClient.invalidateQueries({ queryKey: ['testcase-groups'] })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : '复制分组失败')
          }
        })()
      },
    }),
    [queryClient, batch.setConfirm]
  )

  /** INT-1294 标签操作真实接线：编辑（PUT /tags/{id}）/ 删除（DELETE /tags/{id}?cascade=true 级联）/
   *  复制（POST /testcases/batch copy_by_tag）。成功后刷新用例列表（updateTagMutation 已 invalidate
   *  ['tags']）；改名/删除当前筛选标签时清空标签筛选，避免按旧名查询空列表。 */
  const handleUpdateTag = async (id: number, draft: TagDraft) => {
    await updateTagMutation.mutateAsync({ id, draft })
    await queryClient.invalidateQueries({ queryKey: ['testcases'] })
    const current = tags.find((t) => t.id === id)
    if (current && current.name !== draft.name && filters.tag === current.name) {
      setFilters((prev) => ({ ...prev, tag: null }))
    }
  }

  const handleDeleteTag = async (id: number) => {
    await deleteTag(id, true)
    await queryClient.invalidateQueries({ queryKey: ['tags'] })
    await queryClient.invalidateQueries({ queryKey: ['testcases'] })
    const current = tags.find((t) => t.id === id)
    if (current && filters.tag === current.name) {
      setFilters((prev) => ({ ...prev, tag: null }))
    }
  }

  const handleCopyTag = async (tagName: string, copyToNewGroup: boolean) => {
    await batchTestcaseAction('copy_by_tag', [], { tagName, copyToNewGroup })
    await queryClient.invalidateQueries({ queryKey: ['testcases'] })
    await queryClient.invalidateQueries({ queryKey: ['testcase-groups'] })
  }

  const openCreate = () => {
    setPresetGroupId(null)
    setMutateCase(null)
    setMutateOpen(true)
  }

  const trashCount = useMemo(
    () => (filters.trash ? items.filter((c) => c.deleted).length : 0),
    [filters.trash, items]
  )

  /** 批量设置评估维度透传的 testType（取第一个选中用例；INT-486 用例不分 e2e/api 口径前对齐 Vue） */
  const selectedTestType = useMemo(() => {
    const first = items.find((c) => selected.has(c.id))
    return first?.type ?? null
  }, [items, selected])

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
                用例管理
              </li>
            </ol>
          </nav>
        </SectionPageLayout.Breadcrumb>

        <SectionPageLayout.Title>用例管理</SectionPageLayout.Title>

        <SectionPageLayout.Actions>
          {hasPermission('testcase:create') && (
            <Button size='sm' className='h-7 gap-1.5' onClick={openCreate}>
              <Plus aria-hidden='true' className='size-3.5' />
              新增用例
            </Button>
          )}
          {hasPermission('testcase:import_export') && (
            <Button
              size='sm'
              variant='outline'
              className='h-7 gap-1.5'
              onClick={() => void navigate({ to: '/audio-import' })}
            >
              <FileUp aria-hidden='true' className='size-3.5' />
              导入用例
            </Button>
          )}
          {hasPermission('testcase:import_export') && (
            <Button
              size='sm'
              variant='outline'
              className='h-7 gap-1.5'
              onClick={() => setExportOpen(true)}
            >
              <FileSpreadsheet aria-hidden='true' className='size-3.5' />
              导出
            </Button>
          )}
          {hasPermission('testcase:import_export') && (
            <Button
              size='sm'
              variant='ghost'
              className='h-7 gap-1.5'
              onClick={() => toast.success('模板已下载（演示：testcase-import-template.json）')}
            >
              <FileDown aria-hidden='true' className='size-3.5' />
              模板下载
            </Button>
          )}
        </SectionPageLayout.Actions>

        <SectionPageLayout.Content>
          <div className='flex h-full min-h-0 flex-col gap-3'>
            <Tabs value={view} onValueChange={handleViewChange}>
              <TabsList variant='line' className='max-w-full flex-wrap justify-start'>
                {TEST_CASES_TABS.map((t) => (
                  <TabsTrigger key={t.key} value={t.key} className='px-3'>
                    {t.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            <TestCasesFilterToolbar
              filters={filters}
              onChange={setFilters}
              onReset={() => setFilters({})}
              isFiltered={isFiltered}
              groups={groups}
              tags={tags}
              tagsError={tagsQuery.isError}
              tagsLoading={tagsQuery.isLoading}
              onRetryTags={() => void tagsQuery.refetch()}
              dimensions={allDimensions}
              categories={categories}
              tagCategories={tagCategories}
              onUpdateTag={handleUpdateTag}
              onDeleteTag={handleDeleteTag}
              onCopyTag={handleCopyTag}
              cases={items}
              onRestoreAll={() =>
                batch.setConfirm({
                  kind: 'restore-all',
                  count: trashCount,
                  ids: items.filter((c) => c.deleted).map((c) => c.id),
                })
              }
            />

            <div className='min-h-0 flex-1 overflow-auto'>
              {view === 'by-group' ? (
                <GroupedCaseList
                  groups={groups}
                  cases={items}
                  loading={listQuery.isLoading}
                  groupsLoading={groupsQuery.isLoading}
                  isError={listError}
                  onRetry={() => void listQuery.refetch()}
                  filters={effectiveFilters}
                  trash={filters.trash ?? false}
                  hasQueryFilters={hasQueryFilters}
                  selected={selected}
                  tagRegistry={tags}
                  callbacks={rowCallbacks}
                  onBatchAction={batch.openBatch}
                  actionCallbacks={groupCallbacks}
                  onToggleSelect={toggleSelect}
                  onToggleAll={toggleAll}
                />
              ) : (
                <TagCaseList
                  cases={items}
                  loading={listQuery.isLoading}
                  isError={listError}
                  onRetry={() => void listQuery.refetch()}
                  selected={selected}
                  tagRegistry={tags}
                  callbacks={rowCallbacks}
                  onToggleSelect={toggleSelect}
                  onToggleAll={toggleAll}
                  onCreate={openCreate}
                />
              )}
            </div>
          </div>
        </SectionPageLayout.Content>
      </SectionPageLayout>

      {/* 批量浮条 */}
      <CaseBulkActions
        selectedIds={[...selected]}
        onClear={clearSelection}
        trash={filters.trash ?? false}
        onBatchAction={batch.openBatch}
      />

      {/* 弹窗群（Provider 挂页级，§5） */}
      <CaseMutateDrawer
        open={mutateOpen}
        onOpenChange={setMutateOpen}
        caseItem={mutateCase}
        groups={groups}
        tags={tags}
        presetGroupId={presetGroupId}
      />
      <ExportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        selectedCount={selected.size}
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
      {/* 批量弹窗群（INT-1026 共享 host；/start-test 与用例管理页双挂同一批弹窗） */}
      <CaseBatchActionsHost
        batchDialog={batch.batchDialog}
        setBatchDialog={batch.setBatchDialog}
        confirm={batch.confirm}
        setConfirm={batch.setConfirm}
        handleConfirm={batch.handleConfirm}
        groups={groups}
        tags={tags}
        dimensions={allDimensions}
        categories={categories}
        algorithmType={algorithmId}
        testType={selectedTestType}
      />
    </>
  )
}
