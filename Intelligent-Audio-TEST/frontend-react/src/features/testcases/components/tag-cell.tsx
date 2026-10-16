/**
 * 用例行标签徽章（11_用例域.md §3.3 标签列 + INT-487 按分类呈现）：
 * 依 TagItem.categoryName 分组着色、分类名小字角标；分类色值走标签 color 字段
 * （数据驱动色，非主题色——Badge 内联 style backgroundColor 照规范 §6 口径）。
 * 展示最多 2 个 + 「+N」tooltip 全量（BadgeListCell 语义）。
 */
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { TagItem } from '@/domain/models/testTag'

/** 单枚标签徽章（数据驱动色 + 分类角标） */
export function TagBadge({
  tag,
  className,
}: {
  tag: TagItem
  className?: string
}) {
  const color = tag.color ?? '#94a3b8'
  return (
    <Badge
      variant='outline'
      className={cn('h-5 gap-1 rounded-md px-1.5', className)}
      title={`${tag.name} · 分类：${tag.categoryName ?? '未分类'}`}
      style={{
        backgroundColor: `${color}1a`,
        borderColor: `${color}40`,
        color,
      }}
    >
      <span
        aria-hidden='true'
        className='size-1.5 shrink-0 rounded-full'
        style={{ backgroundColor: color }}
      />
      <span className='font-medium'>{tag.name}</span>
      {tag.categoryName && (
        <span className='text-[10px] leading-none opacity-70'>
          {tag.categoryName}
        </span>
      )}
    </Badge>
  )
}

/** 标签列单元格：最多 2 枚 + 「+N」tooltip 全量 */
export function TagCell({
  tagNames,
  tagRegistry,
}: {
  tagNames: string[]
  tagRegistry: TagItem[]
}) {
  if (tagNames.length === 0) return <span className='text-muted-foreground'>—</span>

  const registry = new Map(tagRegistry.map((t) => [t.name, t]))
  const resolve = (name: string): TagItem =>
    registry.get(name) ?? {
      id: -1,
      name,
      description: null,
      color: '#94a3b8',
      categoryId: null,
      categoryName: null,
      createdAt: null,
      updatedAt: null,
    }

  const visible = tagNames.slice(0, 2)
  const hidden = tagNames.slice(2)

  return (
    <div className='flex flex-wrap items-center gap-1'>
      {visible.map((name) => (
        <TagBadge key={name} tag={resolve(name)} />
      ))}
      {hidden.length > 0 && (
        <Tooltip>
          <TooltipTrigger
            render={
              <Badge variant='secondary' className='rounded-md px-1.5' tabIndex={0} />
            }
          >
            +{hidden.length}
          </TooltipTrigger>
          <TooltipContent className='max-w-64'>
            <div className='flex flex-wrap gap-1'>
              {hidden.map((name) => (
                <TagBadge key={name} tag={resolve(name)} />
              ))}
            </div>
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}
