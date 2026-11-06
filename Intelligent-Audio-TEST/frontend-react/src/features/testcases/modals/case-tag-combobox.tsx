/**
 * 用例表单标签 Combobox（11_用例域.md §5.1「标签」，INT-1591）：
 * TagInput chips（回车 / 逗号添加、✕ 移除）+ Combobox 建议下拉。
 * - 候选走 GET /tags/names（keyword 服务端搜索，`['tags','names']` queryKey）；
 * - 已添加项置灰禁选（disabled + 选中勾）；
 * - 输入词无同名候选时给「新建「{词}」」创建项，选中即落 chip——用例保存时后端按名称落标签
 *   （POST /testcases 的 tags 为名称数组，与自由输入回车添加同口径）。
 * 交互件照 newAPI components/ui/combobox.tsx（@base-ui/react Combobox 原语 + Chips/Chip 多选），
 * 壳色/圆角照本仓 components/ui 基元，不新造样式值。
 */
import { Combobox } from '@base-ui/react/combobox'
import { Check, Plus } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'

import { useTagNames } from '@/application/tags/useTags'
import { badgeVariants } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/** 键入防抖：候选按 keyword 走服务端搜索（GET /tags/names?keyword） */
function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export function CaseTagCombobox({
  value,
  onChange,
}: {
  value: string[]
  onChange: (next: string[]) => void
}) {
  const [draft, setDraft] = useState('')
  const [open, setOpen] = useState(false)
  /** 弹层 ref：高亮项在 Portal 里（不在输入容器内），回车判定需查弹层 DOM */
  const popupRef = useRef<HTMLDivElement | null>(null)
  const trimmed = draft.trim()
  const keyword = useDebouncedValue(trimmed, 250)
  const namesQuery = useTagNames(keyword)
  const names = namesQuery.data ?? []

  /** 输入词无同名候选且未添加 → 提供「新建「{词}」」创建项 */
  const createName =
    trimmed && !value.includes(trimmed) && !names.includes(trimmed) ? trimmed : null

  const items = useMemo(
    () => (createName ? [...names, createName] : names),
    [names, createName]
  )

  const commit = (next: string[]) => {
    const normalized = next.map((name) => name.trim()).filter(Boolean)
    onChange(Array.from(new Set(normalized)))
  }

  const addChip = (name: string) => {
    const next = name.trim()
    if (!next) return
    if (!value.includes(next)) commit([...value, next])
    setDraft('')
  }

  /**
   * 回车 / 逗号 chip 行为（原 TagInput 语义不回退）：
   * 高亮项已由 base-ui 在输入框内部处理时（defaultPrevented 或列表存在 data-highlighted），
   * 这里不再重复添加；否则回车把当前输入落 chip。
   */
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement
    if (target.tagName !== 'INPUT') return
    if (event.key === ',') {
      event.preventDefault()
      addChip(draft)
      return
    }
    if (event.key !== 'Enter' || event.defaultPrevented) return
    const highlighted = popupRef.current?.querySelector('[data-highlighted]')
    if (highlighted) return
    if (!trimmed) return
    event.preventDefault()
    addChip(draft)
  }

  return (
    <Combobox.Root
      multiple
      items={items}
      value={value}
      onValueChange={(next) => commit((next ?? []) as string[])}
      inputValue={draft}
      onInputValueChange={(next) => setDraft(next)}
      // 候选已由服务端按 keyword 过滤，关闭内置过滤以免把「新建」项滤掉
      filter={null}
      open={open}
      onOpenChange={setOpen}
    >
      <Combobox.InputGroup
        className='border-input focus-within:border-ring focus-within:ring-ring/50 flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-lg border bg-transparent px-2 py-1 text-sm transition-colors focus-within:ring-3'
        onKeyDown={handleKeyDown}
      >
        <Combobox.Value>
          {(selected: string[]) => (
            <Combobox.Chips className='flex min-w-0 flex-1 flex-wrap items-center gap-1.5'>
              {selected.map((name) => (
                <Combobox.Chip
                  key={name}
                  className={cn(
                    badgeVariants({ variant: 'secondary' }),
                    'gap-1 rounded-md px-1.5 font-normal'
                  )}
                >
                  {name}
                  <Combobox.ChipRemove
                    aria-label={`移除标签 ${name}`}
                    className='text-muted-foreground hover:text-destructive -mr-0.5 inline-flex size-3.5 items-center justify-center border-0 bg-transparent p-0'
                  >
                    ✕
                  </Combobox.ChipRemove>
                </Combobox.Chip>
              ))}
              <Combobox.Input
                aria-label='标签'
                placeholder={
                  selected.length === 0 ? '输入标签，按回车或逗号添加' : '继续添加标签…'
                }
                className='placeholder:text-muted-foreground h-6 min-w-40 flex-1 border-0 bg-transparent p-0 text-sm outline-none'
                onFocus={() => setOpen(true)}
              />
            </Combobox.Chips>
          )}
        </Combobox.Value>
      </Combobox.InputGroup>

      <Combobox.Portal>
        <Combobox.Positioner sideOffset={4} align='start' className='isolate z-50'>
          <Combobox.Popup
            ref={popupRef}
            className='bg-popover text-popover-foreground ring-foreground/10 w-(--anchor-width) max-h-64 min-w-56 overflow-y-auto rounded-lg p-1 shadow-md ring-1 outline-hidden duration-100'
          >
            {namesQuery.isLoading ? (
              <div className='text-muted-foreground px-2 py-6 text-center text-sm'>
                加载标签中…
              </div>
            ) : (
              items.length === 0 && (
                <div className='text-muted-foreground px-2 py-6 text-center text-sm'>
                  暂无匹配标签
                </div>
              )
            )}
            <Combobox.List>
              {(item: string) => {
                const isCreate = createName !== null && item === createName
                const added = value.includes(item)
                return (
                  <Combobox.Item
                    key={item}
                    value={item}
                    disabled={added}
                    className='data-highlighted:bg-accent data-highlighted:text-accent-foreground data-disabled:pointer-events-none data-disabled:opacity-50 relative flex w-full cursor-default items-center gap-2 rounded-md py-1 pr-8 pl-1.5 text-sm outline-hidden select-none'
                  >
                    <Combobox.ItemIndicator>
                      <Check aria-hidden='true' className='size-3.5 shrink-0' />
                    </Combobox.ItemIndicator>
                    {isCreate && (
                      <Plus aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
                    )}
                    <span className='min-w-0 truncate'>
                      {isCreate ? `新建「${item}」` : item}
                    </span>
                    {added && (
                      <span className='text-muted-foreground ml-auto text-xs'>已添加</span>
                    )}
                  </Combobox.Item>
                )
              }}
            </Combobox.List>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </Combobox.Root>
  )
}
