/**
 * 用例卡（V9.7.10 TestCaseCard.vue 等价移植，11_用例域.md §3.5 卡片流）。
 * 卡头：勾选框 + 名称（超长 tooltip 截断）+ ID 徽章（点击复制）→ 描述/最后编辑时间 →
 * 算法徽章（getAlgorithmLabel）+ 标签（TagBadge 分类角标，≤6 +N 展开/收起）+ 时长/轮次徽章；
 * 回收站态整卡 muted + 删除时间/删除人元信息。
 * 行内操作五钮（预览/复制/收藏/编辑/删除；回收站态换 恢复/彻底删除）。
 * INT-486 用例不分类型口径：不落「类型徽章」（V9.7.10 基准含类型徽章，口径定稿移除）。
 */
import { Clock3, Copy, Pencil, Play, RotateCcw, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TagItem } from '@/domain/models/testTag'
import {
  formatCaseDuration,
  getAlgorithmLabel,
} from '@/features/testcases/constants'
import { TagBadge } from '@/features/testcases/components/tag-cell'

export interface CaseCardCallbacks {
  onPreview: (caseItem: TestCaseListItem) => void
  onCopy: (caseItem: TestCaseListItem) => void
  onFavorite: (caseItem: TestCaseListItem) => void
  onEdit: (caseItem: TestCaseListItem) => void
  onDelete: (caseItem: TestCaseListItem) => void
  onRestore: (caseItem: TestCaseListItem) => void
  onPurge: (caseItem: TestCaseListItem) => void
}

/** 卡内标签展示上限（对齐 V9.7.10 maxVisibleTags 语义：超限折叠 +N 展开/收起） */
const MAX_VISIBLE_TAGS = 6

export function CaseCard({
  caseItem,
  selected,
  tagRegistry,
  callbacks,
  onToggleSelect,
  showCheckbox = true,
}: {
  caseItem: TestCaseListItem
  selected: boolean
  tagRegistry: TagItem[]
  callbacks: CaseCardCallbacks
  onToggleSelect: (id: string, checked: boolean) => void
  showCheckbox?: boolean
}) {
  const [tagsExpanded, setTagsExpanded] = useState(false)
  const disabled = caseItem.deleted === true

  const registry = new Map(tagRegistry.map((t) => [t.name, t]))
  const resolveTag = (name: string): TagItem =>
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

  const shownTags = tagsExpanded
    ? caseItem.tags
    : caseItem.tags.slice(0, MAX_VISIBLE_TAGS)
  const hiddenCount = caseItem.tags.length - MAX_VISIBLE_TAGS

  const actionBtn = (
    label: string,
    icon: React.ReactNode,
    onClick: () => void,
    opts?: { destructive?: boolean }
  ) => (
    <Tooltip key={label}>
      <TooltipTrigger
        render={
          <Button
            variant='ghost'
            size='icon-sm'
            className={cn('size-7', opts?.destructive && 'text-destructive hover:text-destructive')}
            aria-label={label}
            onClick={onClick}
          />
        }
      >
        {icon}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )

  return (
    <div
      data-state={selected ? 'selected' : undefined}
      className={cn(
        'bg-card ring-foreground/10 rounded-xl ring-1 transition-colors',
        selected && 'bg-accent/40 ring-primary/30',
        disabled && 'bg-[var(--table-disabled)] text-muted-foreground'
      )}
    >
      <div className='flex items-start gap-3 p-3'>
        <div className='min-w-0 flex-1'>
          {/* 名称行 + 操作五钮 */}
          <div className='flex items-start justify-between gap-2'>
            <div className='min-w-0'>
              <div className='flex flex-wrap items-center gap-2'>
                {showCheckbox && (
                  <Checkbox
                    checked={selected}
                    aria-label={`选择 ${caseItem.name}`}
                    onCheckedChange={(c) => onToggleSelect(caseItem.id, c)}
                  />
                )}
                <span className='font-medium truncate' title={caseItem.name}>
                  {caseItem.name}
                </span>
                <button
                  type='button'
                  className='text-muted-foreground hover:text-foreground font-mono text-xs truncate tabular-nums hover:underline'
                  title='点击复制用例 ID'
                  onClick={() => {
                    void navigator.clipboard?.writeText(caseItem.id)
                    toast.success('已复制')
                  }}
                >
                  {caseItem.id}
                </button>
              </div>
              <p className='text-muted-foreground mt-1 text-xs truncate'>
                {caseItem.description ?? '—'}
              </p>
              <p className='text-muted-foreground/70 mt-0.5 text-xs'>
                最后编辑时间{' '}
                {caseItem.updatedAt
                  ? caseItem.updatedAt.slice(0, 16).replace('T', ' ')
                  : '—'}
              </p>
              {disabled && (
                <p className='text-muted-foreground/70 mt-0.5 text-xs'>
                  删除时间{' '}
                  {caseItem.deletedAt
                    ? caseItem.deletedAt.slice(0, 16).replace('T', ' ')
                    : '—'}{' '}
                  · 删除人{' '}
                  {caseItem.deletedByUserId ? `用户#${caseItem.deletedByUserId}` : '—'}
                </p>
              )}
            </div>
            <div className='flex shrink-0 items-center gap-0.5'>
              {disabled ? (
                <>
                  {actionBtn(
                    '恢复用例',
                    <RotateCcw aria-hidden='true' className='size-4' />,
                    () => callbacks.onRestore(caseItem)
                  )}
                  {actionBtn(
                    '彻底删除（不可恢复）',
                    <Trash2 aria-hidden='true' className='size-4' />,
                    () => callbacks.onPurge(caseItem),
                    { destructive: true }
                  )}
                </>
              ) : (
                <>
                  {actionBtn(
                    '预览音频',
                    <Play aria-hidden='true' className='size-4' />,
                    () => callbacks.onPreview(caseItem)
                  )}
                  {actionBtn(
                    '复制用例',
                    <Copy aria-hidden='true' className='size-4' />,
                    () => callbacks.onCopy(caseItem)
                  )}
                  {actionBtn(
                    caseItem.isFavorite ? '取消收藏' : '收藏',
                    <Star
                      aria-hidden='true'
                      className={cn(
                        'size-4',
                        caseItem.isFavorite && 'fill-amber-400 text-amber-400'
                      )}
                    />,
                    () => callbacks.onFavorite(caseItem)
                  )}
                  {actionBtn(
                    '编辑用例',
                    <Pencil aria-hidden='true' className='size-4' />,
                    () => callbacks.onEdit(caseItem)
                  )}
                  {actionBtn(
                    '删除用例',
                    <Trash2 aria-hidden='true' className='size-4' />,
                    () => callbacks.onDelete(caseItem),
                    { destructive: true }
                  )}
                </>
              )}
            </div>
          </div>

          {/* 徽章行：算法 / 时长 / 轮次 */}
          <div className='mt-2 flex flex-wrap items-center gap-1.5'>
            <Badge variant='secondary' className='rounded-md px-1.5'>
              {getAlgorithmLabel(caseItem.algorithmType)}
            </Badge>
            <Badge variant='outline' className='gap-1 rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
              <Clock3 aria-hidden='true' className='size-3' />
              {formatCaseDuration(caseItem.totalDuration)}
            </Badge>
            <Badge variant='outline' className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
              {caseItem.rounds} 轮
            </Badge>
          </div>

          {/* 标签行（分类角标） */}
          {caseItem.tags.length > 0 && (
            <div className='mt-2 flex flex-wrap items-center gap-1'>
              {shownTags.map((name) => (
                <TagBadge key={name} tag={resolveTag(name)} />
              ))}
              {hiddenCount > 0 && !tagsExpanded && (
                <button
                  type='button'
                  className='hover:bg-accent rounded-md px-1.5 py-0.5 text-xs transition-colors'
                  onClick={() => setTagsExpanded(true)}
                >
                  +{hiddenCount}
                </button>
              )}
              {tagsExpanded && hiddenCount > 0 && (
                <button
                  type='button'
                  className='text-muted-foreground hover:text-foreground text-xs transition-colors'
                  onClick={() => setTagsExpanded(false)}
                >
                  收起
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
