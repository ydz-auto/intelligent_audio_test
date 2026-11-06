/**
 * 报告上下文选择器（interfaces 层 ai-chat/input；08_AI对话页.md §3.5 对位 newAPI
 * ModelGroupSelector，换形不换件：左列类型分组 / 右列搜索列表，layout 类值照搬）。
 * 前置审核定稿（INT-598 方案A）：组件树先落；Demo 态——Agent 后端立项前——
 * 整块不渲染（§3.5/§3.10），本组件当前不被页面装配；立项后放开渲染并接线现有端点。
 * 桌面 Popover 双列；移动 Sheet bottom（Drawer 依赖 vaul 未引入，用 Sheet 等价版式）。
 */
import { Check, ChevronsUpDown, FileBarChart } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'

import type { ReportContextOption } from '@/domain/models/aiChat'
import type {
  ReportContextGroup,
  ReportContextGroupType,
} from '@/features/ai-chat/hooks/use-report-context'

export type SelectedContext = {
  id: string
  label: string
  badge: string
  type: ReportContextOption['type']
}

type ReportContextSelectorProps = {
  value: SelectedContext | null
  groups: ReportContextGroup[]
  onSelect: (option: ReportContextOption) => void
  disabled?: boolean
  className?: string
}

const LAYOUT = {
  panel: 'max-h-[min(50vh,28rem)] overflow-hidden',
  content:
    'grid h-[min(50vh,28rem)] max-h-[min(50vh,28rem)] min-h-0 gap-3 p-2 md:grid-cols-[9.5rem_minmax(0,1fr)]',
  groupScroll:
    'mt-2 grid min-h-0 flex-1 auto-rows-[2rem] content-start gap-1 overflow-y-auto pr-1',
  modelColumn: 'flex h-full min-h-0 min-w-0 overflow-hidden rounded-lg border',
  modelList:
    'min-h-0 flex-1 max-h-none [scrollbar-color:var(--border)_transparent] [scrollbar-width:thin] [&::-webkit-scrollbar]:block [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-track]:bg-transparent',
  modelItem:
    'relative mb-0.5 flex items-center justify-between rounded-md border border-transparent px-2 py-1.5 pl-3 text-[12px] leading-4 transition-colors before:absolute before:inset-y-2 before:left-1 before:w-1 before:rounded-full before:bg-transparent',
  selectedItem: 'border-primary/40 bg-primary/12 text-foreground shadow-sm before:bg-primary',
  unselectedItem: 'text-muted-foreground hover:bg-accent hover:text-foreground',
} as const

export function ReportContextSelector({
  value,
  groups,
  onSelect,
  disabled,
  className,
}: ReportContextSelectorProps) {
  const isMobile = useIsMobile()
  const [open, setOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  /** 左列类型钮过滤：点击过滤右列到该组；再点当前组回「全部」（§3.5 对位 ModelGroupSelector） */
  const [activeGroup, setActiveGroup] = useState<ReportContextGroupType | null>(null)

  const filteredOptions = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    const base = activeGroup
      ? groups.filter((group) => group.type === activeGroup)
      : groups
    if (!query) return base
    return base
      .map((group) => ({
        ...group,
        options: group.options.filter((option) =>
          `${option.label} ${option.badge} ${option.description ?? ''}`
            .toLowerCase()
            .includes(query)
        ),
      }))
      .filter((group) => group.options.length > 0)
  }, [groups, searchQuery, activeGroup])

  const handleSelect = (option: ReportContextOption) => {
    onSelect(option)
    setOpen(false)
    setSearchQuery('')
  }

  const trigger = (
    <Button
      aria-expanded={open}
      className={cn(
        'h-8 max-w-[15rem] justify-start gap-2 border px-2.5 font-medium shadow-none',
        'bg-background/80 hover:bg-accent/70 text-foreground focus:!ring-0 focus:!outline-none',
        className
      )}
      disabled={disabled}
      role='combobox'
      size='sm'
      type='button'
      variant='outline'
    >
      <FileBarChart className='text-muted-foreground size-4 shrink-0' />
      <span className='min-w-0 truncate text-xs'>
        {value?.label ?? '绑定报告上下文'}
      </span>
      {value?.badge && (
        <span className='bg-muted text-muted-foreground hidden max-w-20 shrink-0 rounded px-1.5 py-0.5 text-[10px] sm:inline-flex'>
          {value.badge}
        </span>
      )}
      <ChevronsUpDown className='text-muted-foreground ml-auto size-3.5 shrink-0 opacity-60' />
    </Button>
  )

  const content = (
    <div className={cn('min-h-0', isMobile ? 'grid gap-3 p-2' : LAYOUT.content)}>
      <div className='flex h-full min-h-0 min-w-0 flex-col overflow-hidden'>
        <div className='text-muted-foreground px-1 text-[11px] leading-4 font-medium'>
          报告上下文
        </div>
        <div className={cn('grid gap-1', LAYOUT.groupScroll)}>
          {groups.map((group) => {
            const isSelected = value?.type === group.type
            const isActive = activeGroup === group.type
            return (
              <button
                aria-pressed={isActive}
                className={cn(
                  'flex min-w-0 items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-[12px] leading-4 transition-colors',
                  isSelected || isActive
                    ? 'bg-primary/10 text-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
                key={group.type}
                onClick={() =>
                  setActiveGroup((current) =>
                    current === group.type ? null : group.type
                  )
                }
                type='button'
              >
                <span className='min-w-0 truncate font-medium'>
                  {group.label}
                </span>
                <Check
                  className={cn(
                    'size-3.5 shrink-0',
                    isSelected ? 'opacity-100' : 'opacity-0'
                  )}
                />
              </button>
            )
          })}
        </div>
      </div>

      <div className={cn('min-w-0 overflow-hidden rounded-lg border', LAYOUT.modelColumn)}>
        <div className='flex min-h-0 w-full flex-1 flex-col p-1'>
          <Input
            className='h-8 text-[13px]'
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder='搜索报告…'
            value={searchQuery}
          />
          <div className={cn('mt-1 overflow-y-auto', LAYOUT.modelList)}>
            {filteredOptions.length === 0 ? (
              <div className='text-muted-foreground px-3 py-8 text-center text-[12px] leading-5'>
                未找到匹配报告
              </div>
            ) : (
              filteredOptions.map((group) => (
                <div key={group.type}>
                  <div className='text-muted-foreground px-2 py-1 text-[10px] font-medium'>
                    {group.label}
                  </div>
                  {group.options.map((option) => (
                    <button
                      className={cn(
                        LAYOUT.modelItem,
                        value?.id === option.id
                          ? LAYOUT.selectedItem
                          : LAYOUT.unselectedItem
                      )}
                      key={option.id}
                      onClick={() => handleSelect(option)}
                      type='button'
                    >
                      <span
                        className={cn(
                          'min-w-0 truncate',
                          value?.id === option.id ? 'font-semibold text-foreground' : 'font-medium'
                        )}
                      >
                        {option.label}
                      </span>
                      <Check
                        className={cn(
                          'size-3.5 shrink-0',
                          value?.id === option.id ? 'opacity-100' : 'opacity-0'
                        )}
                      />
                    </button>
                  ))}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger render={trigger} />
        <SheetContent className='max-h-[80vh] min-h-[60vh] overflow-hidden rounded-t-xl' side='bottom'>
          <SheetHeader>
            <SheetTitle className='flex items-center gap-2 text-left text-lg font-medium'>
              <FileBarChart className='size-4' />
              选择报告上下文
            </SheetTitle>
          </SheetHeader>
          {content}
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={trigger} />
      <PopoverContent
        align='end'
        className={cn(
          'bg-popover z-50 w-[34rem] max-w-[calc(100vw-2rem)] rounded-xl border p-0 shadow-lg',
          LAYOUT.panel
        )}
        collisionPadding={8}
        side='top'
        sideOffset={8}
      >
        {content}
      </PopoverContent>
    </Popover>
  )
}
