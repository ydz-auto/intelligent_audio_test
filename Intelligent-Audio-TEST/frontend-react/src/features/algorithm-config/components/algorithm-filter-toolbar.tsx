/**
 * 算法列表筛选工具栏（§3.4；DataTableToolbar 对位）。
 * 搜索「搜索算法类型或名称」+ 分组 facet（全部/分组名，单选）+ 状态 facet（全部/上线/下线）。
 * 页面不建独立算法筛选（§2.2 全局算法切换器口径）。
 */
import { Search } from 'lucide-react'

import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  ALGORITHM_STATUS_OPTIONS,
  GROUP_FILTER_ALL,
  STATUS_FILTER_ALL,
} from '@/features/algorithm-config/constants'
import type { AlgorithmGroup } from '@/domain/models/algorithmConfig'

export type AlgorithmFilterToolbarProps = {
  searchValue: string
  onSearch: (value: string) => void
  groups: AlgorithmGroup[]
  groupFilter: string
  onGroupFilter: (value: string) => void
  statusFilter: string
  onStatusFilter: (value: string) => void
}

export function AlgorithmFilterToolbar(props: AlgorithmFilterToolbarProps) {
  return (
    <div className='flex flex-wrap items-center gap-2'>
      <div className='relative min-w-0 flex-1 basis-56'>
        <Search
          aria-hidden='true'
          className='text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2'
        />
        <Input
          aria-label='搜索算法'
          value={props.searchValue}
          onChange={(e) => props.onSearch(e.target.value)}
          placeholder='搜索算法类型或名称'
          className='h-8 pl-8'
        />
      </div>

      <Select
        value={props.groupFilter}
        onValueChange={(value) => props.onGroupFilter(value ?? GROUP_FILTER_ALL)}
      >
        <SelectTrigger size='sm' className='w-36' aria-label='分组'>
          <SelectValue placeholder='全部分组' />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={GROUP_FILTER_ALL}>全部分组</SelectItem>
          {props.groups.map((group) => (
            <SelectItem key={group.id} value={String(group.id)}>
              {group.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={props.statusFilter}
        onValueChange={(value) => props.onStatusFilter(value ?? STATUS_FILTER_ALL)}
      >
        <SelectTrigger size='sm' className='w-32' aria-label='状态'>
          <SelectValue placeholder='全部状态' />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={STATUS_FILTER_ALL}>全部状态</SelectItem>
          {ALGORITHM_STATUS_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
