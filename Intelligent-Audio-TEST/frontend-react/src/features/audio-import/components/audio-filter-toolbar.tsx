/**
 * 音频列表筛选工具栏（§5.1 DataTableToolbar 形态）：
 * 搜索（debounce 500ms）+ 格式/音频类型/采样率/时长 facet chips + 标签 facet（多选
 * + OR/AND 模式）+ 全局算法联动 chip + 重置。对位 newAPI faceted-filter 单选语义。
 */
import { Check, ChevronDown, FilterX, Search } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import {
  AUDIO_SEARCH_DEBOUNCE_MS,
  AUDIO_TYPE_OPTIONS,
  DURATION_OPTIONS,
  FORMAT_OPTIONS,
  SAMPLE_RATE_OPTIONS,
  TAG_MODE_OPTIONS,
} from '@/features/audio-import/constants'
import { AudioAlgorithmChip } from '@/features/audio-import/components/global-algorithm-chip'
import type { AudioListFilters, TagMode } from '@/features/audio-import/types'

export interface AudioFilterToolbarProps {
  filters: AudioListFilters
  tags: string[]
  onChange: (next: AudioListFilters) => void
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

/** 标签 facet（§5.3.2：多选 + OR/AND 模式切换，useTagFilter 平移） */
function TagFacet({
  value,
  tagMode,
  tags,
  onChange,
  onModeChange,
}: {
  value: string[]
  tagMode: TagMode
  tags: string[]
  onChange: (value: string[]) => void
  onModeChange: (mode: TagMode) => void
}) {
  const [open, setOpen] = useState(false)
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
        <span className='text-muted-foreground'>标签</span>
        {value.length > 0 ? (
          <Badge className='rounded-sm px-1 font-normal'>{value.length}</Badge>
        ) : (
          <span className='max-w-28 truncate font-medium'>全部</span>
        )}
        <ChevronDown
          aria-hidden='true'
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
        />
      </PopoverTrigger>
      <PopoverContent align='start' className='max-w-72 min-w-56 p-1.5'>
        <div className='border-border/60 mb-1 flex items-center gap-1 border-b pb-1.5'>
          {TAG_MODE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type='button'
              onClick={() => onModeChange(option.value as TagMode)}
              className={cn(
                'hover:bg-accent rounded-md px-2 py-1 text-xs font-medium transition-colors',
                tagMode === option.value && 'bg-accent text-foreground'
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        {tags.length === 0 ? (
          <p className='text-muted-foreground px-3 py-4 text-center text-sm'>
            暂无标签
          </p>
        ) : (
          <>
            <div className='max-h-60 overflow-y-auto'>
              {tags.map((tag) => {
                const checked = value.includes(tag)
                return (
                  <label
                    key={tag}
                    className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors'
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() =>
                        onChange(
                          checked
                            ? value.filter((v) => v !== tag)
                            : [...value, tag]
                        )
                      }
                    />
                    <span className='min-w-0 flex-1 truncate'>{tag}</span>
                  </label>
                )
              })}
            </div>
            <div className='border-t pt-1'>
              <button
                type='button'
                className='text-muted-foreground hover:text-foreground text-xs font-medium transition-colors'
                onClick={() => onChange([])}
              >
                清空选择
              </button>
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}

export function AudioFilterToolbar(props: AudioFilterToolbarProps) {
  const searchRef = useRef<HTMLInputElement>(null)
  const [searchInput, setSearchInput] = useState(props.filters.search)
  const debounceTimer = useRef<number | null>(null)

  // 外部重置（onReset 清空 filters.search）时同步输入框
  useEffect(() => {
    setSearchInput(props.filters.search)
  }, [props.filters.search])

  const update = useCallback(
    (patch: Partial<AudioListFilters>) =>
      props.onChange({ ...props.filters, ...patch }),
    [props.filters, props.onChange]
  )

  const handleSearchChange = (value: string) => {
    setSearchInput(value)
    if (debounceTimer.current) window.clearTimeout(debounceTimer.current)
    debounceTimer.current = window.setTimeout(() => {
      update({ search: value.trim() })
    }, AUDIO_SEARCH_DEBOUNCE_MS)
  }

  return (
    <div className='bg-card/50 rounded-lg border p-2.5 sm:p-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='relative'>
          <Search
            aria-hidden='true'
            className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2'
          />
          <Input
            ref={searchRef}
            value={searchInput}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder='搜索文件名或标注'
            className='h-8 w-full sm:w-[200px] lg:w-[240px] ps-7'
            aria-label='搜索音频'
          />
        </div>

        <SingleFacet
          label='格式'
          value={props.filters.format}
          options={FORMAT_OPTIONS}
          onChange={(v) => update({ format: v })}
        />
        <SingleFacet
          label='音频类型'
          value={props.filters.audioType}
          options={AUDIO_TYPE_OPTIONS}
          onChange={(v) => update({ audioType: v as AudioListFilters['audioType'] })}
        />
        <SingleFacet
          label='采样率'
          value={props.filters.sampleRate}
          options={SAMPLE_RATE_OPTIONS}
          onChange={(v) => update({ sampleRate: v })}
        />
        <SingleFacet
          label='音频时长'
          value={props.filters.duration}
          options={DURATION_OPTIONS}
          onChange={(v) =>
            update({ duration: v as AudioListFilters['duration'] })
          }
        />
        <TagFacet
          value={props.filters.tags}
          tagMode={props.filters.tagMode}
          tags={props.tags}
          onChange={(tagNames) => update({ tags: tagNames })}
          onModeChange={(mode) => update({ tagMode: mode })}
        />

        <AudioAlgorithmChip />

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
