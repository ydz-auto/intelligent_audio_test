/**
 * 叶明细分页列表（INT-1510 §8.2.3 第 4 条，接线卡 INT-1819）。
 * 树骨架来自 `candidates/tree`，结果行明细不在树响应内——展开节点时按
 * 「task_ids + case_ids + device_id 或 api_id + result_type」调 candidates 分页，
 * `total` 取响应值（不客户端计数），翻页 result_id 不重不漏。
 */
import { TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import {
  LEAF_PAGE_SIZE,
  usePickLeafPage,
} from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import type {
  PickLeafFilter,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import { buildLeafFilterKey, UNKNOWN_CASE_NAME } from '@/domain/lib/pick-candidate-tree'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { LeafRow } from '@/features/tasks/cherry-pick/components/pick-leaf-row'

/** 候选行 → 叶行（缺名兜底：用例查不到 → 「未知用例」，不裸显 UUID） */
function toLeaf(
  row: {
    resultId: number
    taskName: string
    caseName: string | null
    deviceId: number | null
    deviceName: string | null
    apiId: number | null
    apiName: string | null
    resultType: string | null
    executionStatus: string
    evaluationStatus: string
    createdAt: string | null
  },
  addedResultIds: ReadonlySet<number>
): PickTreeLeaf {
  return {
    kind: 'leaf',
    key: `leaf:${row.resultId}`,
    resultId: row.resultId,
    taskName: row.taskName,
    caseName: row.caseName?.trim() || UNKNOWN_CASE_NAME,
    deviceId: row.deviceId,
    deviceName: row.deviceName,
    apiId: row.apiId,
    apiName: row.apiName,
    resultType: row.resultType,
    executionStatus: row.executionStatus,
    evaluationStatus: row.evaluationStatus,
    createdAt: row.createdAt,
    added: addedResultIds.has(row.resultId),
  }
}

export interface PickLeafListProps {
  filter: PickLeafFilter
  selectedIds: ReadonlySet<number>
  onToggleLeaf: (leaf: PickTreeLeaf) => void
  showLeafTask?: boolean
}

/** 节点下的结果行分页列表（每节点独立翻页状态；切节点回到第 1 页） */
export function PickLeafList({
  filter,
  selectedIds,
  onToggleLeaf,
  showLeafTask,
}: PickLeafListProps) {
  const filterKey = buildLeafFilterKey(filter)
  const [page, setPage] = useState(1)
  useEffect(() => {
    setPage(1)
  }, [filterKey])

  const query = usePickLeafPage(filter, page)
  const addedResultIds = usePickCartStore((s) => s.resultIdSet)
  const leaves = useMemo(
    () => (query.data?.items ?? []).map((row) => toLeaf(row, addedResultIds)),
    [query.data, addedResultIds]
  )

  const total = query.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / LEAF_PAGE_SIZE))
  const start = total === 0 ? 0 : (page - 1) * LEAF_PAGE_SIZE + 1
  const end = Math.min(page * LEAF_PAGE_SIZE, total)

  if (query.isLoading) {
    return (
      <div className='flex flex-col gap-1 py-1 pl-8'>
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className='h-7 w-full' />
        ))}
      </div>
    )
  }
  if (query.isError) {
    return (
      <div className='text-muted-foreground flex items-center gap-2 py-2 pl-8 text-xs'>
        <TriangleAlert aria-hidden='true' className='text-destructive size-3.5' />
        <span>结果行加载失败</span>
        <Button variant='ghost' size='xs' className='h-6' onClick={() => void query.refetch()}>
          重试
        </Button>
      </div>
    )
  }
  if (leaves.length === 0) {
    return (
      <p className='text-muted-foreground/70 py-2 pl-8 text-xs'>该节点下暂无结果行</p>
    )
  }

  return (
    <div className='flex flex-col'>
      {leaves.map((leaf) => (
        <LeafRow
          key={leaf.key}
          leaf={leaf}
          selected={selectedIds.has(leaf.resultId)}
          onToggle={onToggleLeaf}
          showLeafTask={showLeafTask}
        />
      ))}
      {total > LEAF_PAGE_SIZE && (
        <div className='text-muted-foreground flex items-center justify-end gap-2 py-1 pr-2 pl-8 text-[11px] tabular-nums'>
          <span>
            第 {start}–{end} 条 / 共 {total} 条
          </span>
          <Button
            variant='ghost'
            size='xs'
            className='h-6'
            disabled={page <= 1}
            aria-label='结果行上一页'
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            上一页
          </Button>
          <span>
            {page} / {pageCount}
          </span>
          <Button
            variant='ghost'
            size='xs'
            className='h-6'
            disabled={page >= pageCount}
            aria-label='结果行下一页'
            onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  )
}
