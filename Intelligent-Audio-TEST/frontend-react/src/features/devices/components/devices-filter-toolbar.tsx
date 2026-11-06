/**
 * 设备管理页筛选工具栏（16_设备域.md §3.1/§9；DataTableToolbar 对位）。
 * 搜索（debounce 500ms）+ 按页签 facet：测试=状态/连接方式/分组/实验室；
 * 播放=状态/设备类型/实验室；API=状态/协议/环境（API 无实验室维度 §3.6 注）。
 * 实验室 facet 选项动态 GET /laboratories（INT-487：DTO 未暴露前规范隐藏，mock 先行展示）。
 * 算法统一走右上角全局算法切换器（a231d8477 筛选栏去算法·全局化），页面内不再渲染联动 chip。
 */
import { Check, ChevronDown, FilterX, Search } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import {
  API_ENV_FILTER_OPTIONS,
  API_PROTOCOL_FILTER_OPTIONS,
  API_STREAMING_FILTER_OPTIONS,
  CONNECTION_TYPE_FILTER_OPTIONS,
  DEVICES_SEARCH_DEBOUNCE_MS,
  DEVICES_SEARCH_PLACEHOLDER,
  PLAYBACK_TYPE_FILTER_OPTIONS,
  STATUS_FILTER_OPTIONS,
  type DevicesTabKey,
} from '@/features/devices/constants'
import { flattenDeviceGroups } from '@/features/devices/lib/device-group-tree'
import type { Laboratory } from '@/domain/models/laboratory'
import type { DeviceGroup } from '@/domain/models/deviceGroup'

export interface DevicesFilterToolbarProps {
  tab: DevicesTabKey
  searchValue: string
  onSearch: (value: string) => void
  status: string | null
  onStatus: (value: string | null) => void
  labs: Laboratory[]
  labId: string | null
  onLabId: (value: string | null) => void
  groups: DeviceGroup[]
  groupId: string | null
  onGroupId: (value: string | null) => void
  connectionType: string | null
  onConnectionType: (value: string | null) => void
  deviceType: string | null
  onDeviceType: (value: string | null) => void
  protocol: string | null
  onProtocol: (value: string | null) => void
  /** 流式性 facet（INT-1800：协议之外的第二维，独立筛选） */
  streaming: string | null
  onStreaming: (value: string | null) => void
  environment: string | null
  onEnvironment: (value: string | null) => void
  isFiltered: boolean
  onReset: () => void
}

/** 单选 facet chip（Popover + 选项列表；对位 audio-filter-toolbar SingleFacet） */
function SingleFacet({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string | null
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

/** 实验室 facet（选项动态 GET /laboratories；未选中「全部」） */
function LabFacet({
  value,
  labs,
  onChange,
}: {
  value: string | null
  labs: Laboratory[]
  onChange: (value: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const current = labs.find((l) => String(l.id) === value)
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
        <span className='text-muted-foreground'>实验室</span>
        <span className='max-w-28 truncate font-medium'>
          {current?.name ?? '全部'}
        </span>
        <ChevronDown
          aria-hidden='true'
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
        />
      </PopoverTrigger>
      <PopoverContent align='start' className='max-w-56 min-w-48 p-1.5'>
        {labs.length === 0 ? (
          <p className='text-muted-foreground px-3 py-4 text-center text-sm'>
            暂无实验室
          </p>
        ) : (
          labs.map((lab) => (
            <button
              key={lab.id}
              type='button'
              onClick={() => {
                onChange(String(lab.id) === value ? null : String(lab.id))
                setOpen(false)
              }}
              className={cn(
                'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
                String(lab.id) === value && 'bg-accent'
              )}
            >
              <span className='min-w-0 flex-1 truncate'>{lab.name}</span>
              {lab.status !== 'active' && (
                <Badge variant='outline' className='rounded-sm px-1 font-normal'>
                  {lab.status === 'maintenance' ? '维护中' : '停用'}
                </Badge>
              )}
              {String(lab.id) === value && (
                <Check aria-hidden='true' className='size-4 shrink-0' />
              )}
            </button>
          ))
        )}
      </PopoverContent>
    </Popover>
  )
}

export function DevicesFilterToolbar(props: DevicesFilterToolbarProps) {
  const [searchInput, setSearchInput] = useState(props.searchValue)
  const debounceTimer = useRef<number | null>(null)

  // 外部重置时同步输入框
  useEffect(() => {
    setSearchInput(props.searchValue)
  }, [props.searchValue])

  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchInput(value)
      if (debounceTimer.current) window.clearTimeout(debounceTimer.current)
      debounceTimer.current = window.setTimeout(() => {
        props.onSearch(value.trim())
      }, DEVICES_SEARCH_DEBOUNCE_MS)
    },
    [props.onSearch]
  )

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
            placeholder={DEVICES_SEARCH_PLACEHOLDER[props.tab]}
            className='h-8 w-full sm:w-[200px] lg:w-[240px] ps-7'
            aria-label={DEVICES_SEARCH_PLACEHOLDER[props.tab]}
          />
        </div>

        <SingleFacet
          label='状态'
          value={props.status}
          options={STATUS_FILTER_OPTIONS}
          onChange={props.onStatus}
        />

        {props.tab === 'test' && (
          <SingleFacet
            label='连接方式'
            value={props.connectionType}
            options={CONNECTION_TYPE_FILTER_OPTIONS}
            onChange={props.onConnectionType}
          />
        )}
        {props.tab === 'playback' && (
          <SingleFacet
            label='设备类型'
            value={props.deviceType}
            options={PLAYBACK_TYPE_FILTER_OPTIONS}
            onChange={props.onDeviceType}
          />
        )}
        {props.tab === 'api' && (
          <>
            <SingleFacet
              label='协议'
              value={props.protocol}
              options={API_PROTOCOL_FILTER_OPTIONS}
              onChange={props.onProtocol}
            />
            <SingleFacet
              label='流式性'
              value={props.streaming}
              options={API_STREAMING_FILTER_OPTIONS}
              onChange={props.onStreaming}
            />
            <SingleFacet
              label='环境'
              value={props.environment}
              options={API_ENV_FILTER_OPTIONS}
              onChange={props.onEnvironment}
            />
          </>
        )}

        {/* 分组（§3.4 仅测试设备页签；嵌套分组摊平后全部可选，INT-864） */}
        {props.tab === 'test' && (
          <SingleFacet
            label='分组'
            value={props.groupId}
            options={flattenDeviceGroups(props.groups)
              .filter((g) => g.groupType === 'test')
              .map((g) => ({ value: String(g.id), label: g.name }))}
            onChange={props.onGroupId}
          />
        )}

        {/* 实验室 facet（INT-487：mock 先行展示；DTO 未暴露前规范隐藏；API 页签无实验室维度 §3.6 注） */}
        {props.tab !== 'api' && (
          <LabFacet value={props.labId} labs={props.labs} onChange={props.onLabId} />
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
