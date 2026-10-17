/**
 * 「合并方式」facet（18_挑选合并交互重设计.md §2.3/§7.1，INT-600）。
 * 单选：全部/整任务合并/结果挑选；§11-1 未落地前 mock 单源过滤。
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  MERGE_TYPE_OPTIONS,
} from '@/features/tasks/cherry-pick/constants'
import type { MergeType } from '@/domain/models/cherryPick'

export function MergeTypeFacet({
  value,
  onChange,
}: {
  value: 'all' | MergeType
  onChange: (value: 'all' | MergeType) => void
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as 'all' | MergeType)}>
      <SelectTrigger size='sm' aria-label='合并方式'>
        <SelectValue placeholder='合并方式'>
          {MERGE_TYPE_OPTIONS.find((o) => o.value === value)?.label ?? '合并方式'}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {MERGE_TYPE_OPTIONS.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
