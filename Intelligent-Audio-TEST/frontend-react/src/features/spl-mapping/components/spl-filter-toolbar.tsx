/**
 * 声压级映射筛选工具栏（§4.1.1 DataTableToolbar 形态）：
 * 搜索（debounce 500ms）+ 校准状态 facet（singleSelect）+ 关联播放设备 facet（设备页签动态
 * GET /playback-devices）+ 关联 API facet（数字页签动态 GET /apis）+ 重置。
 * 对位 newAPI faceted-filter 单选语义；本页无算法维度，全局算法 chip 隐藏（§4.1.1）。
 */
import { Check, ChevronDown, FilterX, Search } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { CALIBRATION_STATUS_OPTIONS, SPL_SEARCH_DEBOUNCE_MS } from '@/features/spl-mapping/constants'
import type { SplDomain, SplListFilters } from '@/features/spl-mapping/types'
import type { PlaybackDeviceRef } from '@/domain/models/splMapping'
import type { ApiConfigRef } from '@/domain/models/digitalSpl'

export interface SplFilterToolbarProps {
  domain: SplDomain
  filters: SplListFilters
  playbackDevices: PlaybackDeviceRef[]
  apis: ApiConfigRef[]
  onChange: (next: SplListFilters) => void
  onReset: () => void
  isFiltered: boolean
}

/** 单选 facet chip（Popover + 选项列表 + 选中态；对位 testcases SingleFacet） */
function SingleFacet({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string | null | undefined
  options: ReadonlyArray<{ value: string; label: string }>
  onChange: (value: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const current = options.find((o) => o.value === value)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant='outline'
            size='sm'
            className='h-8 gap-1.5 px-2.5 font-normal'
          />
        }
      >
        <span className='text-muted-foreground'>{label}</span>
        <span className='max-w-28 truncate font-medium'>
          {current?.label ?? '全部'}
        </span>
        <ChevronDown
          aria-hidden='true'
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
        />
      </PopoverTrigger>
      <PopoverContent align='start' className='min-w-48 p-1.5'>
        {options.map((option) => (
          <button
            key={option.value}
            type='button'
            onClick={() => {
              onChange(option.value === value ? null : option.value)
              setOpen(false)
            }}
            className={cn(
              'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
              option.value === value && 'bg-accent'
            )}
          >
            <span className='min-w-0 flex-1 truncate'>{option.label}</span>
            {option.value === value && (
              <Check aria-hidden='true' className='size-4 shrink-0' />
            )}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}

export function SplFilterToolbar(props: SplFilterToolbarProps) {
  const [searchInput, setSearchInput] = useState(props.filters.search)
  const debounceTimer = useRef<number | null>(null)

  // 外部重置（onReset 清空 filters.search）时同步输入框
  useEffect(() => {
    setSearchInput(props.filters.search)
  }, [props.filters.search])

  const update = useCallback(
    (patch: Partial<SplListFilters>) =>
      props.onChange({ ...props.filters, ...patch }),
    [props.filters, props.onChange]
  )

  const handleSearchChange = (value: string) => {
    setSearchInput(value)
    if (debounceTimer.current) window.clearTimeout(debounceTimer.current)
    debounceTimer.current = window.setTimeout(() => {
      update({ search: value.trim() })
    }, SPL_SEARCH_DEBOUNCE_MS)
  }

  const deviceOptions = props.playbackDevices.map((device) => ({
    value: String(device.id),
    label: device.model ? `${device.name}（${device.model}）` : device.name,
  }))

  const apiOptions = props.apis.map((api) => ({
    value: String(api.id),
    label: api.vendor ? `${api.name}（${api.vendor}）` : api.name,
  }))

  return (
    <div className='bg-card/50 rounded-lg border p-2.5 sm:p-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='relative'>
          <Search
            aria-hidden='true'
            className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2'
          />
          <Input
            value={searchInput}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder='搜索映射名称或描述'
            className='h-8 w-full sm:w-[200px] lg:w-[240px] ps-7'
            aria-label='搜索映射'
          />
        </div>

        <SingleFacet
          label='校准状态'
          value={props.filters.calibrationStatus === 'all' ? null : props.filters.calibrationStatus}
          options={CALIBRATION_STATUS_OPTIONS}
          onChange={(v) => update({ calibrationStatus: (v ?? 'all') as SplListFilters['calibrationStatus'] })}
        />

        {props.domain === 'device' ? (
          <SingleFacet
            label='关联播放设备'
            value={props.filters.deviceId}
            options={deviceOptions}
            onChange={(v) => update({ deviceId: v })}
          />
        ) : (
          <SingleFacet
            label='关联 API'
            value={props.filters.apiId}
            options={apiOptions}
            onChange={(v) => update({ apiId: v })}
          />
        )}

        {props.isFiltered && (
          <Button
            variant='ghost'
            size='sm'
            className='h-8 gap-1 px-2.5'
            onClick={props.onReset}
          >
            <FilterX aria-hidden='true' className='size-3.5' />
            重置
          </Button>
        )}
      </div>
    </div>
  )
}
