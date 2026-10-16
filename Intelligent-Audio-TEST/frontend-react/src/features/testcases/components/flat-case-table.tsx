/**
 * 标签视图平铺表格（11_用例域.md §3.6：行=用例，后端 view=tag 契约保留前端拍平）。
 * 列同 §3.3（标签列 BadgeListCell 全显——一用例多标签按分类着色）；
 * 「标签」facet 选中某标签即等价原标签卡聚焦（工具栏联动）。
 */
import { ListChecks } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TagItem } from '@/domain/models/testTag'
import type { CaseColumnKey } from '@/features/testcases/constants'
import { CaseTableHeader, ViewOptions } from '@/features/testcases/components/case-table-header'
import { CaseTableRow, type CaseRowCallbacks } from '@/features/testcases/components/case-row'

export function FlatCaseTable({
  cases,
  loading,
  trash,
  selected,
  visible,
  onVisibleChange,
  tagRegistry,
  callbacks,
  onToggleSelect,
  onToggleAll,
  onCreate,
}: {
  cases: TestCaseListItem[]
  loading: boolean
  trash: boolean
  selected: Set<string>
  visible: Set<CaseColumnKey>
  onVisibleChange: (next: Set<CaseColumnKey>) => void
  tagRegistry: TagItem[]
  callbacks: CaseRowCallbacks
  onToggleSelect: (id: string, checked: boolean) => void
  onToggleAll: (ids: string[], checked: boolean) => void
  onCreate: () => void
}) {
  if (loading) {
    return (
      <div className='rounded-xl border'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  if (cases.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            {trash ? <span className='text-3xl'>🗑️</span> : <ListChecks aria-hidden='true' />}
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>{trash ? '回收站为空' : '暂无测试用例'}</EmptyTitle>
            <EmptyDescription>
              {trash
                ? '回收站中的用例会显示在这里，可恢复或彻底删除'
                : '点击右上角「新增用例」创建第一条用例，或调整筛选条件'}
            </EmptyDescription>
          </EmptyHeader>
          {!trash && (
            <EmptyContent>
              <Button size='sm' onClick={onCreate}>
                + 新增用例
              </Button>
            </EmptyContent>
          )}
        </Empty>
      </div>
    )
  }

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      <div className='flex items-center justify-between gap-2 border-b px-3 py-2'>
        <p className='text-muted-foreground text-xs'>
          {selected.size > 0 ? `已选择 ${selected.size} 个用例` : '全选以进行批量操作'}
        </p>
        <ViewOptions visible={visible} onChange={onVisibleChange} />
      </div>

      <div className='overflow-x-auto'>
        <table className='w-full min-w-[860px] text-[13px]'>
          <CaseTableHeader
            allChecked={cases.length > 0 && cases.every((c) => selected.has(c.id))}
            onToggleAll={(checked) => onToggleAll(cases.map((c) => c.id), checked)}
            visible={visible}
          />
          <tbody>
            {cases.map((c) => (
              <CaseTableRow
                key={c.id}
                caseItem={c}
                selected={selected.has(c.id)}
                visible={visible}
                tagRegistry={tagRegistry}
                callbacks={callbacks}
                onToggleSelect={onToggleSelect}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
