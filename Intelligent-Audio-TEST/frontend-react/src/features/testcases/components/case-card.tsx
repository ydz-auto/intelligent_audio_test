/**
 * 全站统一用例展示组件（11_用例域.md §3.3 全站用例显示统一口径，INT-1046）。
 * 用例管理（分组视图/标签视图）、报告具体用例（15_报告域 §3.3.7）、任务详情关联用例
 * （09_任务域 §4.4）、开始测试用例选择一律照本卡字段口径呈现用例信息，不另造平铺文本行；
 * 挑选/购物车侧 compact 变体 pick-case-card.tsx 由挑选合并卡另建（不属本卡）。
 *
 * 公共字段（§3.3，V9.7.10 TestCaseCard.vue 等价移植）：
 * - 卡头：勾选框 + 名称（超长 tooltip 截断，可点击开详情）+ ID 徽章（点击复制）+
 *   titleExtra（上下文附加，如报告分类/复核 Badge）；
 * - 次行：描述/最后编辑时间（回收站态换 删除时间/删除人元信息；meta 插槽可整体替代）；
 * - 徽章行：算法（getAlgorithmLabel，名取自真实 /algorithm/options）+ 时长/轮次（数据缺省不落空徽章）
 *   + badgeLeading 上下文前导；算法名未命中真实选项时整枚徽章不渲染（不显示类型码，INT-1687）；
 * - 标签行：TagBadge 分类角标（≤6 +N 展开/收起）；
 * - 行内操作区：缺省=行内五钮（预览/复制/收藏/编辑/删除；回收站态换 恢复/彻底删除），
 *   上下文差异经 actions 插槽覆盖；
 * - footer 底栏（任务人工/AI 复核入口）、expandedContent 展开详情（报告 CaseReportDetail）。
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
  formatDateTime,
  getAlgorithmLabel,
} from '@/features/testcases/constants'
import { TagBadge } from '@/features/testcases/components/tag-cell'

/** 全站用例展示的领域子集（11_用例域.md §3.3 字段口径；各消费域模型结构兼容，接线不改） */
export interface CaseCardItem {
  id: string
  name: string
  description?: string | null
  tags: string[]
  algorithmType?: string | null
  totalDuration?: number | null
  rounds?: number
  updatedAt?: string | null
  isFavorite?: boolean | null
  deleted?: boolean | null
  deletedAt?: string | null
  deletedByUserId?: number | null
  audioCount?: number | null
}

/** 行内操作五钮回调（11_用例域.md §3.3.2；回收站态换 恢复/彻底删除两钮） */
export interface CaseCardCallbacks<T extends CaseCardItem = TestCaseListItem> {
  onPreview: (caseItem: T) => void
  onCopy: (caseItem: T) => void
  onFavorite: (caseItem: T) => void
  onEdit: (caseItem: T) => void
  onDelete: (caseItem: T) => void
  onRestore: (caseItem: T) => void
  onPurge: (caseItem: T) => void
}

export interface CaseCardProps<T extends CaseCardItem> {
  caseItem: T
  selected: boolean
  /** 标签登记表（TagBadge 分类角标/数据驱动色；缺省空表走灰色兜底） */
  tagRegistry?: TagItem[]
  /** 算法类型码 → 中文名（真实 GET /algorithm/options，useAlgorithmLabels）；缺项时不渲染算法徽章 */
  algorithmLabels?: Record<string, string>
  /** 缺省行内五钮（回收站态换 恢复/彻底删除）；与 actions 互斥，传 actions 时忽略 */
  callbacks?: CaseCardCallbacks<T>
  /** 勾选切换；缺省/无时渲染勾选框也不可交互（showCheckbox=false 不渲染） */
  onToggleSelect?: (id: string, checked: boolean) => void
  showCheckbox?: boolean
  /** 名称行前导（报告状态指示点等） */
  leading?: React.ReactNode
  /** 名称旁附加（报告分类 Badge / 复核 Badge 等） */
  titleExtra?: React.ReactNode
  /** 次行自定义内容（任务分组名 + 轮次进度等）；缺省=描述/最后编辑时间/删除元信息 */
  meta?: React.ReactNode
  /** 徽章行前导（任务执行/评估状态徽章等） */
  badgeLeading?: React.ReactNode
  /** 右操作区自定义（报告下载日志/固定/展开、任务移除等）；缺省=callbacks 行内五钮 */
  actions?: React.ReactNode
  /** 底栏（任务人工/AI 复核入口等） */
  footer?: React.ReactNode
  /** 展开详情（报告 CaseReportDetail） */
  expandedContent?: React.ReactNode
  /** 名称可点击（任务域开用例详情弹窗） */
  onNameClick?: (caseItem: T) => void
  /** 隐藏次行（描述/最后编辑时间；报告侧无此数据不落空行） */
  hideMeta?: boolean
  /** 隐藏徽章行（算法/时长/轮次） */
  hideBadges?: boolean
}

/** 卡内标签展示上限（对齐 V9.7.10 maxVisibleTags 语义：超限折叠 +N 展开/收起） */
const MAX_VISIBLE_TAGS = 6

export function CaseCard<T extends CaseCardItem>({
  caseItem,
  selected,
  tagRegistry = [],
  algorithmLabels,
  callbacks,
  onToggleSelect,
  showCheckbox = true,
  leading,
  titleExtra,
  meta,
  badgeLeading,
  actions,
  footer,
  expandedContent,
  onNameClick,
  hideMeta = false,
  hideBadges = false,
}: CaseCardProps<T>) {
  const [tagsExpanded, setTagsExpanded] = useState(false)
  const disabled = caseItem.deleted === true
  /** 算法中文名（真实 /algorithm/options 的 value→name；未命中=null → 不渲染徽章，INT-1687） */
  const algorithmLabel = getAlgorithmLabel(caseItem.algorithmType, algorithmLabels)

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
    opts?: { destructive?: boolean; disabled?: boolean; tooltip?: string }
  ) => {
    const disabled = opts?.disabled ?? false
    const content = opts?.tooltip ?? label
    const btnClass = cn(
      'size-7',
      opts?.destructive && 'text-destructive hover:text-destructive',
      disabled && 'cursor-not-allowed opacity-50'
    )
    return (
      <Tooltip key={label}>
        {disabled ? (
          <TooltipTrigger render={<span className='inline-flex' />}>
            <Button
              variant='ghost'
              size='icon-sm'
              className={btnClass}
              aria-label={label}
              aria-disabled
              tabIndex={-1}
              disabled
            >
              {icon}
            </Button>
          </TooltipTrigger>
        ) : (
          <TooltipTrigger
            render={
              <Button
                variant='ghost'
                size='icon-sm'
                className={btnClass}
                aria-label={label}
                onClick={onClick}
              />
            }
          >
            {icon}
          </TooltipTrigger>
        )}
        <TooltipContent>{content}</TooltipContent>
      </Tooltip>
    )
  }

  /** §3.3.2 预览置灰：audioCount=0 时无关联音频（Tooltip 说明） */
  const hasAudio = caseItem.audioCount == null || caseItem.audioCount > 0

  /** 徽章行是否有可渲染内容（数据缺省不落空徽章，对齐 V9.7.10 TestCaseCard.vue v-if 口径） */
  const hasBadges =
    badgeLeading != null ||
    Boolean(algorithmLabel) ||
    (caseItem.totalDuration != null && caseItem.totalDuration > 0) ||
    (caseItem.rounds != null && caseItem.rounds > 0)

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
        {leading}
        <div className='min-w-0 flex-1'>
          {/* 名称行 + 操作区 */}
          <div className='flex items-start justify-between gap-2'>
            <div className='min-w-0'>
              <div className='flex flex-wrap items-center gap-2'>
                {showCheckbox && onToggleSelect && (
                  <Checkbox
                    checked={selected}
                    aria-label={`选择 ${caseItem.name}`}
                    onCheckedChange={(c) => onToggleSelect(caseItem.id, c)}
                  />
                )}
                {onNameClick ? (
                  <button
                    type='button'
                    className='font-medium truncate hover:text-primary'
                    title='查看用例详情'
                    onClick={() => onNameClick(caseItem)}
                  >
                    {caseItem.name}
                  </button>
                ) : (
                  <span className='font-medium truncate' title={caseItem.name}>
                    {caseItem.name}
                  </span>
                )}
                {titleExtra}
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
              {hideMeta ? null : meta !== undefined ? (
                <div className='mt-1'>{meta}</div>
              ) : (
                <>
                  <p className='text-muted-foreground mt-1 text-xs truncate'>
                    {caseItem.description ?? '—'}
                  </p>
                  <p className='text-muted-foreground/70 mt-0.5 text-xs'>
                    最后编辑时间{' '}
                    {formatDateTime(caseItem.updatedAt)}
                  </p>
                  {disabled && (
                    <p className='text-muted-foreground/70 mt-0.5 text-xs'>
                      删除时间{' '}
                      {formatDateTime(caseItem.deletedAt)}{' '}
                      · 删除人{' '}
                      {caseItem.deletedByUserId ? `用户#${caseItem.deletedByUserId}` : '—'}
                    </p>
                  )}
                </>
              )}
            </div>
            <div className='flex shrink-0 items-center gap-0.5'>
              {actions ??
                (disabled
                  ? callbacks && (
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
                    )
                  : callbacks && (
                      <>
                        {actionBtn(
                          '预览音频',
                          <Play aria-hidden='true' className='size-4' />,
                          () => callbacks.onPreview(caseItem),
                          {
                            disabled: !hasAudio,
                            tooltip: hasAudio ? undefined : '该测试用例没有关联音频文件',
                          }
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
                    ))}
            </div>
          </div>

          {/* 徽章行：上下文前导 + 算法 / 时长 / 轮次（数据缺省不落空徽章） */}
          {!hideBadges && hasBadges && (
            <div className='mt-2 flex flex-wrap items-center gap-1.5'>
              {badgeLeading}
              {algorithmLabel && (
                <Badge variant='secondary' className='rounded-md px-1.5'>
                  {algorithmLabel}
                </Badge>
              )}
              {caseItem.totalDuration != null && caseItem.totalDuration > 0 && (
                <Badge
                  variant='outline'
                  className='gap-1 rounded-md px-1.5 font-mono text-[11px] tabular-nums'
                >
                  <Clock3 aria-hidden='true' className='size-3' />
                  {formatCaseDuration(caseItem.totalDuration)}
                </Badge>
              )}
              {caseItem.rounds != null && caseItem.rounds > 0 && (
                <Badge
                  variant='outline'
                  className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'
                >
                  {caseItem.rounds} 轮
                </Badge>
              )}
            </div>
          )}

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

          {footer}
        </div>
      </div>
      {expandedContent}
    </div>
  )
}
