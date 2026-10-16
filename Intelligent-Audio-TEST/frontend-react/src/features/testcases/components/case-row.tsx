/**
 * 用例表格行（11_用例域.md §3.3 列定义，分组/平铺两视图共用）。
 * 单元格 `py-2`、字号 13px；数值列 mono tabular-nums；回收站行 DISABLED_ROW
 * （muted 底 + 左标线）+ 状态位「已删除」destructive 徽章。
 * INT-486 用例不分类型口径（负责人 2026-10-16）：类型徽章移除——正式类型维度=算法类型列。
 */
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TagItem } from '@/domain/models/testTag'
import {
  formatCaseDuration,
  getAlgorithmLabel,
  type CaseColumnKey,
} from '@/features/testcases/constants'
import { TagCell } from '@/features/testcases/components/tag-cell'
import { CaseRowActions } from '@/features/testcases/components/case-row-actions'

export interface CaseRowCallbacks {
  onPreview: (caseItem: TestCaseListItem) => void
  onEdit: (caseItem: TestCaseListItem) => void
  onReferenceParams: (caseItem: TestCaseListItem) => void
  onDelete: (caseItem: TestCaseListItem) => void
  onRestore: (caseItem: TestCaseListItem) => void
  onPurge: (caseItem: TestCaseListItem) => void
}

export function CaseTableRow({
  caseItem,
  selected,
  visible,
  tagRegistry,
  callbacks,
  onToggleSelect,
}: {
  caseItem: TestCaseListItem
  selected: boolean
  visible: Set<CaseColumnKey>
  tagRegistry: TagItem[]
  callbacks: CaseRowCallbacks
  onToggleSelect: (id: string, checked: boolean) => void
}) {
  const disabled = caseItem.deleted === true
  const col = (key: CaseColumnKey) => visible.has(key)

  return (
    <tr
      data-state={selected ? 'selected' : undefined}
      className={cn(
        'hover:bg-muted/40 border-border/60 border-b transition-colors',
        selected && 'bg-accent/40',
        disabled && 'bg-[var(--table-disabled)] text-muted-foreground',
        disabled &&
          '[&>td:first-child]:border-l-4 [&>td:first-child]:border-l-[var(--table-disabled-border)]'
      )}
    >
      <td className='px-3 py-2'>
        <Checkbox
          checked={selected}
          aria-label={`选择 ${caseItem.name}`}
          onCheckedChange={(c) => onToggleSelect(caseItem.id, c)}
        />
      </td>
      {col('name') && (
        <td className='max-w-64 px-3 py-2'>
          <div className='block max-w-full text-left'>
            <span className='flex items-center gap-1.5 font-medium truncate'>
              <span className='truncate'>{caseItem.name}</span>
            </span>
            <span className='text-muted-foreground block truncate'>
              {disabled
                ? `删除时间 ${caseItem.deletedAt ? caseItem.deletedAt.slice(0, 16).replace('T', ' ') : '—'} · 删除人 ${caseItem.deletedByUserId ? `用户#${caseItem.deletedByUserId}` : '—'}`
                : (caseItem.description ?? '')}
            </span>
          </div>
        </td>
      )}
      {col('algorithm') && (
        <td className='px-3 py-2'>
          <Badge variant='secondary' className='rounded-md px-1.5'>
            {getAlgorithmLabel(caseItem.algorithmType)}
          </Badge>
        </td>
      )}
      {col('tags') && (
        <td className='px-3 py-2'>
          <TagCell tagNames={caseItem.tags} tagRegistry={tagRegistry} />
        </td>
      )}
      {col('rounds') && (
        <td className='min-w-28 px-3 py-2'>
          <div className='font-mono text-xs tabular-nums'>{caseItem.rounds} 轮</div>
          <div className='text-muted-foreground font-mono text-xs tabular-nums'>
            {formatCaseDuration(caseItem.totalDuration)}
          </div>
        </td>
      )}
      {col('updatedAt') && (
        <td className='px-3 py-2 font-mono text-xs whitespace-nowrap tabular-nums'>
          {caseItem.updatedAt ? caseItem.updatedAt.slice(0, 16).replace('T', ' ') : '—'}
        </td>
      )}
      {col('id') && (
        <td className='px-3 py-2'>
          <button
            type='button'
            className='text-muted-foreground font-mono text-xs truncate tabular-nums hover:underline'
            title='点击复制'
            onClick={() => {
              void navigator.clipboard?.writeText(caseItem.id)
              toast.success('已复制')
            }}
          >
            {caseItem.id}
          </button>
        </td>
      )}
      <td className='px-3 py-2 text-right'>
        <CaseRowActions
          caseItem={caseItem}
          onPreview={callbacks.onPreview}
          onEdit={callbacks.onEdit}
          onReferenceParams={callbacks.onReferenceParams}
          onDelete={callbacks.onDelete}
          onRestore={callbacks.onRestore}
          onPurge={callbacks.onPurge}
        />
      </td>
    </tr>
  )
}
