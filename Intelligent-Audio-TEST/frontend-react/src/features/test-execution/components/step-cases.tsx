/**
 * 步骤二：选择测试用例（10_测试执行.md §3.5；INT-710 与用例管理页「一模一样」）。
 * 负责人 2026-10-18 口径：开始测试的用例选择直接复用用例管理页的列表、筛选（分组/标签分类/
 * 搜索）、视图切换组件，不再单独实现一套——按分组/按标签页签 + TestCasesFilterToolbar +
 * GroupedCaseList/TagCaseList（真实接口）。向导专用选择操作（全选结果/反选/重置）与已选汇总行
 * 保留（§3.5 本页不启用批量浮条，汇总行承担全部选择态操作）。
 * 选择态经 useCaseSelectionStore（manual/filter-all）适配为管理组件消费的 Set + checked 回调。
 */
import { ListChecks, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { useAlgorithmChannel } from '@/application/test-execution/useAlgorithmChannel'
import { useCaseSelection } from '@/application/test-execution/useCaseSelection'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useTestCasesList, type TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import { useCaseGroups } from '@/application/testcases/use-case-groups'
import { useCaseTags } from '@/application/testcases/use-case-tags'
import { useDimensionOptions } from '@/application/testcases/use-evaluation-dimensions'
import { useCaseSelectionStore } from '@/infrastructure/stores/case-selection-store'
import { fetchCaseIdsByFilter } from '@/infrastructure/api/testcases-ids-api'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

import {
  TEST_CASES_TABS,
  type TestCasesViewKey,
} from '@/features/testcases/constants'
import { TestCasesFilterToolbar } from '@/features/testcases/components/testcases-filter-toolbar'
import { GroupedCaseList, type GroupActionCallbacks } from '@/features/testcases/components/grouped-case-list'
import { TagCaseList } from '@/features/testcases/components/tag-case-list'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'
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
  const selection = useCaseSelection([])
  const store = useCaseSelectionStore

  const [caseView, setCaseView] = useState<TestCasesViewKey>(
    view === 'card' ? 'by-tag' : 'by-group'
  )
  const [filters, setFilters] = useState<TestCaseListFilters>({})
  const [pendingSelectAll, setPendingSelectAll] = useState(false)

  const canSelect = hasPermission('testcase:read') && !readOnly

  const listQuery = useTestCasesList(caseView, {
    ...filters,
    algorithmType: filters.algorithmType ?? algorithmType,
  })
  const groupsQuery = useCaseGroups()
  const tagsQuery = useCaseTags()
  const dimsQuery = useDimensionOptions(algorithmType)

  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? items.length
  const groups = groupsQuery.data ?? []
  const tags = tagsQuery.data ?? []
  const dimensions = dimsQuery.data ?? []

  const isFiltered = useMemo(
    () =>
      Object.entries(filters).some(([key, value]) => {
        if (key === 'algorithmType') return false
        return value != null && value !== '' && value !== false
      }),
    [filters]
  )

  /** 选择态适配（store manualCaseIds → 管理组件消费的 Set<string>） */
  const selectedSet = useMemo(
    () => new Set(selection.manualCaseIds),
    [selection.manualCaseIds]
  )

  const handleToggleSelect = (id: string, checked: boolean) => {
    if (canSelect && checked !== selectedSet.has(id)) store.getState().toggleCase(id)
  }

  const handleToggleAll = (ids: string[], checked: boolean) => {
    if (!canSelect) return
    if (checked) store.getState().selectMany(ids)
    else store.getState().removeMany(ids)
  }

  /** 全选结果（真实 POST /testcases/ids 按当前筛选圈定） */
  const handleSelectAllFiltered = async () => {
    setPendingSelectAll(true)
    try {
      const { ids, total: count } = await fetchCaseIdsByFilter({
        search: filters.search,
        groupId: filters.groupId,
        tag: filters.tag,
        dimensionId: filters.dimensionId,
        algorithmType: filters.algorithmType ?? algorithmType,
      })
      store.getState().selectMany(ids)
      toast.success(`已全选 ${count} 条用例`)
    } finally {
      setPendingSelectAll(false)
    }
  }

  /** 反选（对称差） */
  const handleInvert = async () => {
    const { ids } = await fetchCaseIdsByFilter({
      search: filters.search,
      groupId: filters.groupId,
      tag: filters.tag,
      dimensionId: filters.dimensionId,
      algorithmType: filters.algorithmType ?? algorithmType,
    })
    store.getState().invertWith(ids)
  }

  const handleReset = () => setFilters({})

  /** 向导语境行内操作（编辑/复制/收藏/删除归用例管理页；试听入口归预览弹窗） */
  const rowCallbacks = useMemo<CaseCardCallbacks>(
    () => ({
      onPreview: () => toast.info('音频试听请前往用例管理页'),
      onCopy: () => toast.info('复制用例请前往用例管理页'),
      onFavorite: () => toast.info('收藏请在用例管理页操作'),
      onEdit: () => toast.info('编辑用例请前往用例管理页'),
      onDelete: () => toast.info('删除用例请前往用例管理页'),
      onRestore: () => {},
      onPurge: () => {},
    }),
    []
  )

  const groupCallbacks = useMemo<GroupActionCallbacks>(
    () => ({
      onCreateInGroup: () => toast.info('新增用例请前往用例管理页'),
      onEditGroup: () => toast.info('分组编辑请前往用例管理页'),
      onDeleteGroup: () => toast.info('分组删除请前往用例管理页'),
      onCopyGroup: () => toast.info('分组复制请前往用例管理页'),
    }),
    []
  )

  return (
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

      {/* 筛选工具栏（用例管理页同款：搜索/分组/标签分类/评估维度） */}
      <TestCasesFilterToolbar
        filters={filters}
        onChange={setFilters}
        onReset={handleReset}
        isFiltered={isFiltered}
        groups={groups}
        tags={tags}
        dimensions={dimensions}
        onRestoreAll={() => {}}
      />

      {/* 向导专用选择操作（§3.5：本页不启用批量浮条，汇总行承担选择态操作） */}
      {!readOnly && canSelect && (
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

      {/* 内容区（分组/标签卡片流，与用例管理页同一组件） */}
      <div className='min-h-0 flex-1 overflow-auto'>
        {caseView === 'by-group' ? (
          <GroupedCaseList
            groups={groups}
            cases={items}
            loading={listQuery.isLoading}
            trash={false}
            hasQueryFilters={isFiltered}
            selected={selectedSet}
            tagRegistry={tags}
            callbacks={rowCallbacks}
            onBatchAction={() => {}}
            actionCallbacks={groupCallbacks}
            onToggleSelect={handleToggleSelect}
            onToggleAll={handleToggleAll}
          />
        ) : (
          <TagCaseList
            cases={items}
            loading={listQuery.isLoading}
            selected={selectedSet}
            tagRegistry={tags}
            callbacks={rowCallbacks}
            onToggleSelect={handleToggleSelect}
            onToggleAll={handleToggleAll}
            onCreate={() => toast.info('新增用例请前往用例管理页')}
          />
        )}
      </div>

      {/* 已选汇总行（常驻） */}
      {!readOnly && (
        <SelectionSummary
          mode='case'
          count={selection.selectedCount}
          manual={selection.summary.manual}
          invertAdded={selection.summary.invertAdded}
          total={total}
          onClear={selection.clearSelection}
        />
      )}
    </div>
  )
}
