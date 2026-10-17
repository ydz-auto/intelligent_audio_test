/**
 * 用例管理页（11_用例域.md §3.1 页面总骨架，SectionPageLayout fixedContent + 双视图表格）。
 * 装配：Breadcrumb 工作台/用例管理｜Title「用例管理」｜Actions（+新增用例/导入/导出/模板下载）｜
 * Content（视图页签 line → 筛选工具栏 → 分组/平铺表格 → 批量浮条）/ Footer（分页 Portal）。
 * 路由 /testcases/$view（by-group/by-tag 白名单在路由层）；mock 态全部弹窗/toast 演示，
 * 接线后替换为 application/testcases mutations + URL 态 useTableUrlState。
 */
import { Link, useNavigate } from '@tanstack/react-router'
import { FileDown, FileSpreadsheet, FileUp, Plus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useEvaluationDimensions } from '@/application/evaluation/use-dimensions'
import { useDimensionOptions } from '@/application/testcases/use-evaluation-dimensions'
import { useCaseGroups } from '@/application/testcases/use-case-groups'
import { useCaseTags } from '@/application/testcases/use-case-tags'
import {
  useTestCasesList,
  type TestCaseListFilters,
} from '@/application/testcases/use-testcases-list'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import {
  TEST_CASES_TABS,
  type TestCasesViewKey,
} from '@/features/testcases/constants'
import { TestCasesFilterToolbar } from '@/features/testcases/components/testcases-filter-toolbar'
import { GroupedCaseList, type GroupActionCallbacks } from '@/features/testcases/components/grouped-case-list'
import { TagCaseList } from '@/features/testcases/components/tag-case-list'
import { CaseBulkActions, type BatchActionKey } from '@/features/testcases/components/case-bulk-actions'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'
import { CaseMutateDrawer } from '@/features/testcases/modals/case-mutate-drawer'
import { ImportExportDialog } from '@/features/testcases/modals/import-export-dialog'
import { GroupMutateDialog } from '@/features/testcases/modals/group-mutate-dialog'
import { BatchDimensionsDialog } from '@/features/testcases/modals/batch-dimensions-dialog'
import { BatchAdjustGroupDialog } from '@/features/testcases/modals/batch-adjust-group-dialog'
import { BatchManageTagsDialog } from '@/features/testcases/modals/batch-manage-tags-dialog'
import { BatchAlgoParamsDialog } from '@/features/testcases/modals/batch-algo-params-dialog'
import { BatchDeviceDialog } from '@/features/testcases/modals/batch-device-dialog'
import { BatchSplDialog } from '@/features/testcases/modals/batch-spl-dialog'
import { BatchNoiseDialog } from '@/features/testcases/modals/batch-noise-dialog'
import { AudioPreviewConfigDialog } from '@/features/testcases/modals/audio-preview-config-dialog'
import {
  CaseConfirmDialog,
  type CaseConfirmState,
} from '@/features/testcases/modals/case-confirms'

export function TestCasesPage({ view }: { view: TestCasesViewKey }) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)

  const [filters, setFilters] = useState<TestCaseListFilters>({})
  const [selected, setSelected] = useState<Set<string>>(new Set())

  // 弹窗状态
  const [mutateCase, setMutateCase] = useState<TestCaseListItem | null>(null)
  const [mutateOpen, setMutateOpen] = useState(false)
  const [presetGroupId, setPresetGroupId] = useState<string | null>(null)
  const [importExport, setImportExport] = useState<{ open: boolean; mode: 'import' | 'export' }>({ open: false, mode: 'import' })
  const [groupDialog, setGroupDialog] = useState<{ open: boolean; group: TestCaseGroup | null }>({ open: false, group: null })
  const [previewCase, setPreviewCase] = useState<TestCaseListItem | null>(null)
  const [batchDialog, setBatchDialog] = useState<{
    kind: 'dimensions' | 'group' | 'tags' | 'params' | 'device' | 'spl' | 'noise'
    count: number
  } | null>(null)
  const [confirm, setConfirm] = useState<CaseConfirmState | null>(null)

  const listQuery = useTestCasesList(view, {
    ...filters,
    algorithmType: filters.algorithmType ?? algorithmId,
  })
  const groupsQuery = useCaseGroups()
  const tagsQuery = useCaseTags()
  const dimsQuery = useDimensionOptions(algorithmId)
  /** 全量评估维度（含子维度；批量设置评估维度 DimensionPicker 主/子层级用，参考 V9.7.10） */
  const allDimsQuery = useEvaluationDimensions()

  const items = listQuery.data?.items ?? []
  const groups = groupsQuery.data ?? []
  const tags = tagsQuery.data ?? []
  const dimensions = dimsQuery.data ?? []
  const allDimensions = allDimsQuery.data ?? []

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

  const clearSelection = useCallback(() => setSelected(new Set()), [])

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
        importExport.open ||
        groupDialog.open ||
        previewCase != null ||
        batchDialog != null ||
        confirm != null
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
    importExport.open,
    groupDialog.open,
    previewCase,
    batchDialog,
    confirm,
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
      onCopy: (c) =>
        toast.success('已复制测试用例', { description: `已创建副本：${c.name}_copy` }),
      onFavorite: (c) => toast.success(c.isFavorite ? '已取消收藏' : '已加入收藏'),
      onEdit: (c) => {
        setPresetGroupId(null)
        setMutateCase(c)
        setMutateOpen(true)
      },
      onDelete: (c) => setConfirm({ kind: 'delete', name: c.name }),
      onRestore: (c) => setConfirm({ kind: 'restore', name: c.name }),
      onPurge: (c) => setConfirm({ kind: 'purge', name: c.name }),
    }),
    []
  )

  const groupCallbacks = useMemo<GroupActionCallbacks>(
    () => ({
      onCreateInGroup: (group) => {
        setPresetGroupId(group?.id ?? null)
        setMutateCase(null)
        setMutateOpen(true)
      },
      onEditGroup: (group) => setGroupDialog({ open: true, group }),
      onDeleteGroup: (group) => setConfirm({ kind: 'delete-group', name: group.name }),
      onCopyGroup: (group) => {
        toast.success('已复制分组', { description: `新分组：${group.name}_copy` })
      },
    }),
    []
  )

  const handleBatchAction = (action: BatchActionKey, ids: string[]) => {
    const count = ids.length
    switch (action) {
      case 'dimensions':
      case 'group':
      case 'tags':
      case 'params':
      case 'device':
      case 'spl':
      case 'noise':
        setBatchDialog({ kind: action, count })
        break
      case 'copy':
        setConfirm({ kind: 'batch-copy', count })
        break
      case 'delete':
        setConfirm({ kind: 'batch-delete', count })
        break
      case 'restore':
        setConfirm({ kind: 'batch-restore', count })
        break
      case 'purge':
        setConfirm({ kind: 'batch-purge', count })
        break
      case 'name':
        setConfirm({ kind: 'auto-name', count })
        break
      case 'refresh':
        setConfirm({ kind: 'refresh', count })
        break
      default:
        toast.success('批量操作执行成功（演示：完整弹窗随接线批次落地）')
    }
  }

  const handleConfirm = (state: CaseConfirmState) => {
    switch (state.kind) {
      case 'delete':
        toast.success('已移入回收站')
        break
      case 'purge':
        toast.success('已彻底删除')
        break
      case 'restore':
        toast.success(`用例「${state.name}」已恢复`)
        break
      case 'delete-group':
        toast.success('删除分组成功')
        break
      case 'restore-all':
        toast.success(`已恢复 ${state.count ?? 0} 个用例`)
        break
      case 'batch-copy':
        toast.success('批量复制成功')
        break
      case 'batch-delete':
        toast.success('已批量移入回收站')
        break
      case 'batch-restore':
        toast.success('已批量恢复')
        break
      case 'batch-purge':
        toast.success('已批量彻底删除')
        break
      case 'auto-name':
        toast.success('自动生成名称完成')
        break
      case 'refresh':
        toast.success('已提交刷新任务')
        break
    }
    clearSelection()
    setConfirm(null)
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
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button size='sm' variant='outline' className='h-7 gap-1.5' />
                }
              >
                <FileUp aria-hidden='true' className='size-3.5' />
                导入
              </DropdownMenuTrigger>
              <DropdownMenuContent align='end' className='w-44'>
                <DropdownMenuItem
                  onSelect={() => setImportExport({ open: true, mode: 'import' })}
                >
                  导入用例文件
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => void navigate({ to: '/audio-import' })}
                >
                  去音频导入页生成
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          {hasPermission('testcase:import_export') && (
            <Button
              size='sm'
              variant='outline'
              className='h-7 gap-1.5'
              onClick={() => setImportExport({ open: true, mode: 'export' })}
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
              dimensions={dimensions}
              onRestoreAll={() =>
                setConfirm({ kind: 'restore-all', count: trashCount })
              }
            />

            <div className='min-h-0 flex-1 overflow-auto'>
              {view === 'by-group' ? (
                <GroupedCaseList
                  groups={groups}
                  cases={items}
                  loading={listQuery.isLoading}
                  trash={filters.trash ?? false}
                  hasQueryFilters={hasQueryFilters}
                  selected={selected}
                  tagRegistry={tags}
                  callbacks={rowCallbacks}
                  onBatchAction={handleBatchAction}
                  actionCallbacks={groupCallbacks}
                  onToggleSelect={toggleSelect}
                  onToggleAll={toggleAll}
                />
              ) : (
                <TagCaseList
                  cases={items}
                  loading={listQuery.isLoading}
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
        onBatchAction={handleBatchAction}
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
      <ImportExportDialog
        open={importExport.open}
        onOpenChange={(open) => setImportExport((prev) => ({ ...prev, open }))}
        mode={importExport.mode}
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
      {batchDialog?.kind === 'dimensions' && (
        <BatchDimensionsDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          dimensions={allDimensions}
          algorithmType={algorithmId}
        />
      )}
      {batchDialog?.kind === 'group' && (
        <BatchAdjustGroupDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          groups={groups}
        />
      )}
      {batchDialog?.kind === 'tags' && (
        <BatchManageTagsDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          tags={tags}
        />
      )}
      {batchDialog?.kind === 'params' && (
        <BatchAlgoParamsDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
        />
      )}
      {batchDialog?.kind === 'device' && (
        <BatchDeviceDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
        />
      )}
      {batchDialog?.kind === 'spl' && (
        <BatchSplDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
        />
      )}
      {batchDialog?.kind === 'noise' && (
        <BatchNoiseDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
        />
      )}
      <CaseConfirmDialog
        open={confirm != null}
        onOpenChange={(open) => !open && setConfirm(null)}
        state={confirm}
        onConfirm={handleConfirm}
      />
    </>
  )
}
