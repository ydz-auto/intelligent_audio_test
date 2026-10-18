/**
 * 步骤二：选择测试用例（interfaces/features/test-execution/components；10_测试执行.md §3.5）。
 * 表格/卡片双模式（view 进 URL）+ 正选/反选（POST /testcases/ids 全量圈定 + 对称差）+
 * 已选汇总行常驻 + 全量圈定显性提示；readOnly（§3.1.1）：表格/卡片只读可见，
 * 勾选/正选/反选/清空隐藏。
 */
import { Check, ListChecks, Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import { useAlgorithmChannel } from '@/application/test-execution/useAlgorithmChannel'
import { useCaseSelection } from '@/application/test-execution/useCaseSelection'
import { usePermissions } from '@/application/hooks/use-permissions'
import { fetchTestCases, type TestCaseFilter } from '@/infrastructure/api/test-execution-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'

import { SelectionSummary } from '@/features/test-execution/components/selection-summary'
import { fetchCaseGroups, fetchCaseTags, fetchEvaluationDimensions } from '@/infrastructure/api/test-execution-api'

interface StepCasesProps {
  readOnly: boolean
  view: 'table' | 'card'
  onViewChange: (view: 'table' | 'card') => void
  /** 全量圈定/过滤空态用（步骤一算法联动 chip 由 toolBar 内嵌） */
  onGoStep0?: () => void
}

export function StepCases({ readOnly, view, onViewChange }: StepCasesProps) {
  const { hasPermission } = usePermissions()
  const { algorithmType, current: currentAlgorithm } = useAlgorithmChannel()
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [groupId, setGroupId] = useState<string | null>(null)
  const [tags, setTags] = useState<string[]>([])
  const [dimensionId, setDimensionId] = useState<number | null>(null)
  const [pendingSelectAll, setPendingSelectAll] = useState(false)

  const canSelect = hasPermission('testcase:read') && !readOnly

  const groupsQuery = useQuery({ queryKey: ['test-execution', 'groups'], queryFn: fetchCaseGroups })
  const tagsQuery = useQuery({ queryKey: ['test-execution', 'tags'], queryFn: fetchCaseTags })
  const dimensionsQuery = useQuery({
    queryKey: ['test-execution', 'dimensions'],
    queryFn: fetchEvaluationDimensions,
  })

  const filter = useMemo<TestCaseFilter>(
    () => ({
      keyword: debouncedKeyword || undefined,
      groupId: groupId ?? null,
      tags: tags.length ? tags : undefined,
      dimensionId: dimensionId ?? null,
      algorithmType,
    }),
    [debouncedKeyword, groupId, tags, dimensionId, algorithmType]
  )

  const listQuery = useQuery({
    queryKey: ['test-execution', 'cases', JSON.stringify(filter)],
    queryFn: () => fetchTestCases(filter),
    staleTime: 15_000,
  })
  const cases = listQuery.data ?? []
  const total = cases.length

  const selection = useCaseSelection(cases)

  const isFiltered = Boolean(debouncedKeyword || groupId || tags.length || dimensionId)

  const handleSearch = (value: string) => {
    setKeyword(value)
    // debounce 500ms
    window.setTimeout(() => setDebouncedKeyword(value), 500)
  }

  const handleSelectAllFiltered = async () => {
    setPendingSelectAll(true)
    try {
      await selection.selectAllFiltered(filter)
    } finally {
      setPendingSelectAll(false)
    }
  }

  const handleInvert = async () => {
    await selection.invertSelection(filter)
  }

  const handleReset = () => {
    setKeyword('')
    setDebouncedKeyword('')
    setGroupId(null)
    setTags([])
    setDimensionId(null)
  }

  const groups = groupsQuery.data ?? []
  const allTags = tagsQuery.data ?? []
  const dimensions = dimensionsQuery.data ?? []

  return (
    <div className='flex flex-col gap-4'>
      {/* 工具栏 */}
      <div className='flex flex-wrap items-center gap-2'>
        {/* 算法联动 chip（§3.3；本页 chip 无 ×，点击回步骤0 换算法） */}
        <Badge variant='secondary' className='gap-1 rounded-md px-2 py-1 text-xs'>
          <span className='text-muted-foreground'>算法：</span>
          <span className='font-medium'>{currentAlgorithm?.name ?? '未选择'}</span>
        </Badge>

        <div className='relative'>
          <Search
            aria-hidden='true'
            className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2'
          />
          <Input
            value={keyword}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder='搜索用例名称或描述'
            className='h-8 w-[200px] ps-7 sm:w-[240px]'
          />
        </div>

        {/* 分组 facet（单选，Command 搜索） */}
        <Popover>
          <PopoverTrigger
            render={
              <Button variant='outline' size='sm' className='h-8 gap-1.5 text-xs' />
            }
          >
            {groupId ? groups.find((g) => g.value === groupId)?.label ?? '分组' : '分组'}
            {groupId && <X aria-hidden='true' className='size-3' onClick={() => setGroupId(null)} />}
          </PopoverTrigger>
          <PopoverContent align='start' className='w-44 p-1'>
            <button
              type='button'
              className={cn(
                'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm',
                groupId === null && 'bg-accent'
              )}
              onClick={() => setGroupId(null)}
            >
              全部分组
            </button>
            {groups.map((group) => (
              <button
                key={group.value}
                type='button'
                className={cn(
                  'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm',
                  groupId === group.value && 'bg-accent'
                )}
                onClick={() => setGroupId(groupId === group.value ? null : group.value)}
              >
                <span className='flex-1'>{group.label}</span>
                {groupId === group.value && <Check aria-hidden='true' className='size-3.5' />}
              </button>
            ))}
          </PopoverContent>
        </Popover>

        {/* 标签 facet（多选+计数） */}
        <Popover>
          <PopoverTrigger render={<Button variant='outline' size='sm' className='h-8 gap-1.5 text-xs' />}>
            标签
            {tags.length > 0 && (
              <span className='bg-primary text-primary-foreground rounded-full px-1.5 text-[10px] font-semibold'>
                {tags.length}
              </span>
            )}
          </PopoverTrigger>
          <PopoverContent align='start' className='w-56 p-1'>
            {allTags.length === 0 ? (
              <p className='text-muted-foreground px-3 py-6 text-center text-sm'>暂无标签</p>
            ) : (
              <div className='max-h-60 overflow-auto'>
                {allTags.map((tag) => {
                  const selected = tags.includes(tag)
                  return (
                    <button
                      key={tag}
                      type='button'
                      className={cn(
                        'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm',
                        selected && 'bg-accent'
                      )}
                      onClick={() =>
                        setTags((prev) => (selected ? prev.filter((t) => t !== tag) : [...prev, tag]))
                      }
                    >
                      <Checkbox checked={selected} className='size-3.5' readOnly />
                      <span className='flex-1'>{tag}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </PopoverContent>
        </Popover>

        {/* 评估维度 facet（单选，Popover 内滚动） */}
        <Popover>
          <PopoverTrigger render={<Button variant='outline' size='sm' className='h-8 gap-1.5 text-xs' />}>
            评估维度
          </PopoverTrigger>
          <PopoverContent align='start' className='w-52 p-1'>
            <div className='max-h-60 overflow-auto'>
              <button
                type='button'
                className={cn(
                  'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm',
                  dimensionId === null && 'bg-accent'
                )}
                onClick={() => setDimensionId(null)}
              >
                全部维度
              </button>
              {dimensions.map((dimension) => (
                <button
                  key={dimension.id}
                  type='button'
                  className={cn(
                    'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm',
                    dimensionId === dimension.id && 'bg-accent'
                  )}
                  onClick={() =>
                    setDimensionId(dimensionId === dimension.id ? null : dimension.id)
                  }
                >
                  <span className='flex-1'>{dimension.name}</span>
                  {dimensionId === dimension.id && (
                    <Check aria-hidden='true' className='size-3.5' />
                  )}
                </button>
              ))}
            </div>
          </PopoverContent>
        </Popover>

        {/* 右端：正选/反选 + 重置 */}
        {!readOnly && canSelect && (
          <div className='ml-auto flex items-center gap-2'>
            <Button variant='outline' size='sm' disabled={pendingSelectAll} onClick={() => void handleSelectAllFiltered()}>
              <ListChecks aria-hidden='true' className='size-3.5' />
              全选结果
            </Button>
            <Button variant='outline' size='sm' onClick={() => void handleInvert()}>
              反选
            </Button>
            {isFiltered && (
              <Button variant='ghost' size='sm' onClick={handleReset}>
                <X aria-hidden='true' className='size-3.5' />
                重置
              </Button>
            )}
          </div>
        )}

        {/* 视图切换 */}
        <Tabs value={view} onValueChange={(v) => onViewChange(v as 'table' | 'card')}>
          <TabsList className='h-8'>
            <TabsTrigger value='table' className='text-xs'>
              表格
            </TabsTrigger>
            <TabsTrigger value='card' className='text-xs'>
              卡片
            </TabsTrigger>
          </TabsList>
        </Tabs>
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

      {/* 内容区 */}
      {listQuery.isPending ? (
        <div aria-busy='true' className='overflow-hidden rounded-lg border'>
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className='flex gap-4 border-b p-4 last:border-0'>
              <Skeleton className='h-4 w-4' />
              <Skeleton className='h-5 w-48 max-w-full' />
              <Skeleton className='h-5 flex-1' />
              <Skeleton className='h-5 w-20' />
            </div>
          ))}
        </div>
      ) : cases.length === 0 ? (
        <Empty className='min-h-[280px] border-dashed'>
          <EmptyHeader>
            <EmptyMedia variant='icon'>
              <ListChecks className='size-4' />
            </EmptyMedia>
            <EmptyTitle>暂无匹配的测试用例</EmptyTitle>
            <EmptyDescription>调整筛选条件，或前往用例管理创建用例</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button size='sm' variant='outline' onClick={() => {}}>
              前往用例管理
            </Button>
          </EmptyContent>
        </Empty>
      ) : view === 'table' ? (
        <div className='overflow-hidden rounded-lg border'>
          <table className='w-full text-left text-sm'>
            <thead className='bg-muted/50 border-b'>
              <tr className='text-muted-foreground text-xs'>
                <th className='w-10 px-4 py-2.5'>
                  {!readOnly && (
                    <Checkbox
                      checked={selection.allVisibleSelected}
                      aria-label='正选当前页'
                      className='size-4'
                      onCheckedChange={selection.toggleAllVisible}
                    />
                  )}
                </th>
                <th className='px-2 py-2.5 font-medium'>用例名称</th>
                <th className='px-2 py-2.5 font-medium'>算法</th>
                <th className='px-2 py-2.5 font-medium'>标签</th>
                <th className='px-2 py-2.5 font-medium'>轮次/时长</th>
                <th className='px-4 py-2.5 text-end font-medium'>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((item) => {
                const selected = selection.manualCaseIds.includes(item.id)
                return (
                  <tr
                    key={item.id}
                    className={cn(
                      'border-b last:border-0 hover:bg-muted/30',
                      selected && 'bg-primary/5'
                    )}
                  >
                    <td className='px-4 py-2.5'>
                      {!readOnly ? (
                        <Checkbox
                          checked={selected}
                          aria-label={`选择 ${item.name}`}
                          className='size-4'
                          onCheckedChange={() => selection.toggleCase(item.id)}
                        />
                      ) : (
                        <span className='text-primary flex justify-center text-xs'>✓</span>
                      )}
                    </td>
                    <td className='px-2 py-2.5'>
                      <span className='block font-medium'>{item.name}</span>
                      {item.description && (
                        <span className='text-muted-foreground block truncate text-xs'>
                          {item.description}
                        </span>
                      )}
                    </td>
                    <td className='px-2 py-2.5'>
                      <Badge variant='secondary' className='text-[11px]'>
                        {item.algorithmType ?? '—'}
                      </Badge>
                    </td>
                    <td className='px-2 py-2.5'>
                      <div className='flex items-center gap-1'>
                        {item.tags.slice(0, 2).map((tag) => (
                          <Badge key={tag} variant='outline' className='text-[11px]'>
                            {tag}
                          </Badge>
                        ))}
                        {item.tags.length > 2 && (
                          <Badge variant='outline' className='text-[11px]'>
                            +{item.tags.length - 2}
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className='px-2 py-2.5 text-xs whitespace-nowrap tabular-nums'>
                      {item.rounds} 轮 · {formatDuration(item.totalDuration)}
                    </td>
                    <td className='px-4 py-2.5 text-end font-mono text-xs whitespace-nowrap tabular-nums'>
                      {item.updatedAt?.slice(5, 16) ?? '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>
          {cases.map((item) => {
            const selected = selection.manualCaseIds.includes(item.id)
            return (
              <div
                key={item.id}
                className={cn(
                  'flex flex-col gap-2 rounded-xl border p-3 transition-colors',
                  selected ? 'border-primary ring-primary/20 ring-2' : 'border-border hover:bg-muted/30'
                )}
              >
                <div className='flex items-start gap-2'>
                  {!readOnly ? (
                    <Checkbox
                      checked={selected}
                      aria-label={`选择 ${item.name}`}
                      className='mt-0.5 size-4'
                      onCheckedChange={() => selection.toggleCase(item.id)}
                    />
                  ) : (
                    <span className='text-primary mt-0.5 text-xs'>✓</span>
                  )}
                  <span className='min-w-0 flex-1'>
                    <span className='block truncate text-sm font-medium'>{item.name}</span>
                    <span className='text-muted-foreground mt-0.5 flex flex-wrap items-center gap-1 text-xs'>
                      <span className='tabular-nums'>
                        {item.rounds} 轮 · {formatDuration(item.totalDuration)}
                      </span>
                    </span>
                  </span>
                </div>
                <div className='flex flex-wrap gap-1'>
                  {item.tags.slice(0, 8).map((tag) => (
                    <Badge key={tag} variant='outline' className='text-[11px]'>
                      {tag}
                    </Badge>
                  ))}
                  {item.tags.length > 8 && (
                    <Badge variant='outline' className='text-[11px]'>
                      +{item.tags.length - 8}
                    </Badge>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 分页 */}
      <div className='flex items-center justify-between text-xs'>
        <span className='text-muted-foreground'>
          共 {total} 条用例
        </span>
        <span className='text-muted-foreground'>每页 10 条 · 第 1 / 1 页</span>
      </div>
    </div>
  )
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}
