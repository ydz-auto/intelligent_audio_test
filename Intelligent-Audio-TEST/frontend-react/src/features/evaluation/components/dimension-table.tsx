/**
 * 评估维度表格（features/evaluation；11_用例域.md §4.1.1 列定义）。
 * 列表/分组双视图共用同一行渲染（现 EvaluationDimensionTable 共用思路平移）：
 * 九列——选择/维度名称（层级树）/描述/分类/关联算法/权重滑杆/API 状态/状态/操作。
 * 权重滑杆 onValueCommitted 才提交（§4.1 拖动停止提交 + toast，§10-4）。
 */
import { ArrowDown, ArrowUp, Activity, Bot, Calculator, Copy, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Slider } from '@/components/ui/slider'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { WEIGHT_MAX, WEIGHT_MIN, getAlgorithmLabel } from '@/features/evaluation/constants'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import { cn } from '@/lib/utils'

/** 层级行（主/子维度同屏聚合后的行视图；_level 0=主 1=子） */
export interface HierarchicalDimension extends Dimension {
  _level: 0 | 1
  _isMain: boolean
  _parentName: string
}

export function DimensionTable({
  items,
  selectedIds,
  onToggleSelection,
  onToggleSelectAll,
  showHeaderCheckbox = true,
  categories,
  canManage,
  canRead,
  canMoveUp,
  canMoveDown,
  weightPendingIds,
  onEdit,
  onDelete,
  onDuplicate,
  onAddSub,
  onTestApi,
  onRuleCalc,
  onToggleStatus,
  onMove,
  onWeightCommit,
}: {
  items: HierarchicalDimension[]
  selectedIds: Set<number | string>
  onToggleSelection: (id: number | string) => void
  onToggleSelectAll?: () => void
  showHeaderCheckbox?: boolean
  categories: EvaluationCategory[]
  canManage: boolean
  canRead: boolean
  canMoveUp: (dimension: HierarchicalDimension) => boolean
  canMoveDown: (dimension: HierarchicalDimension) => boolean
  weightPendingIds: Set<number | string>
  onEdit: (dimension: Dimension) => void
  onDelete: (dimension: Dimension) => void
  onDuplicate: (dimension: Dimension) => void
  onAddSub: (dimension: Dimension) => void
  onTestApi: (dimension: Dimension) => void
  onRuleCalc: (dimension: Dimension) => void
  onToggleStatus: (dimension: Dimension) => void
  onMove: (dimension: Dimension, direction: -1 | 1) => void
  onWeightCommit: (dimension: Dimension, weight: number) => void
}) {
  const allSelected =
    items.length > 0 && items.every((item) => selectedIds.has(item.id))

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[980px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              <th className='w-11 px-2 py-2'>
                {showHeaderCheckbox && (
                  <Checkbox
                    aria-label='全选当前维度'
                    checked={allSelected}
                    onCheckedChange={onToggleSelectAll}
                  />
                )}
              </th>
              <th className='min-w-52 px-3 py-2 text-left font-medium'>
                维度名称
              </th>
              <th className='min-w-44 px-3 py-2 text-left font-medium'>描述</th>
              <th className='min-w-28 px-3 py-2 text-left font-medium'>分类</th>
              <th className='min-w-40 px-3 py-2 text-left font-medium'>
                关联算法
              </th>
              <th className='min-w-40 px-3 py-2 text-left font-medium'>权重</th>
              <th className='min-w-24 px-3 py-2 text-left font-medium'>
                API 状态
              </th>
              <th className='min-w-20 px-3 py-2 text-left font-medium'>状态</th>
              <th className='w-72 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((dimension) => {
              const isSub = dimension._level === 1
              const category = categories.find(
                (c) => c.id === dimension.categoryId
              )
              const isLlmJudge = dimension.resultType === 'llm_judge'
              const apiOnline = dimension.apiStatus !== 'offline'
              // 禁用态 Tooltip 口径（§7 注 1）：写权限缺失 →「无 {权限码} 权限」；移动边界 → 边界提示
              const permManageTooltip = '无 evaluation:dim_manage 权限'
              const permReadTooltip = '无 evaluation:read 权限'
              return (
                <tr
                  key={dimension.id}
                  className='hover:bg-muted/40 border-border/50 border-b last:border-b-0'
                  data-level={dimension._level}
                >
                  <td className='px-2 py-2'>
                    <Checkbox
                      aria-label={`选择维度 ${dimension.name}`}
                      checked={selectedIds.has(dimension.id)}
                      onCheckedChange={() => onToggleSelection(dimension.id)}
                    />
                  </td>
                  <td className='px-3 py-2'>
                    <div
                      className='flex min-w-0 items-center gap-1.5'
                      style={{ paddingLeft: isSub ? '28px' : '0' }}
                    >
                      {isSub && (
                        <span
                          aria-hidden='true'
                          className='text-muted-foreground/50'
                        >
                          └
                        </span>
                      )}
                      <span
                        className={cn(
                          'inline-flex h-5 shrink-0 items-center rounded-md px-1.5 text-xs font-medium',
                          isSub
                            ? 'bg-muted text-muted-foreground'
                            : 'bg-primary/10 text-primary'
                        )}
                      >
                        {isSub ? '子' : '主'}
                      </span>
                      <span
                        className='min-w-0 truncate font-medium'
                        title={dimension.name}
                      >
                        {dimension.name}
                      </span>
                      {isSub && dimension._parentName && (
                        <span className='text-muted-foreground shrink-0 text-xs'>
                          （{dimension._parentName}）
                        </span>
                      )}
                    </div>
                  </td>
                  <td className='max-w-52 px-3 py-2'>
                    <p
                      className='text-muted-foreground truncate'
                      title={dimension.description ?? ''}
                    >
                      {dimension.description || '—'}
                    </p>
                  </td>
                  <td className='px-3 py-2'>
                    <span className='truncate'>
                      {category ? category.name : '未分类'}
                    </span>
                  </td>
                  <td className='px-3 py-2'>
                    {dimension.associatedAlgorithms &&
                    dimension.associatedAlgorithms.length > 0 ? (
                      <div className='flex min-w-0 flex-wrap items-center gap-1'>
                        {dimension.associatedAlgorithms.map((algo) => (
                          <Badge
                            key={algo.algorithmType}
                            variant='secondary'
                            className={cn(
                              'h-5 gap-1 px-1.5 text-xs font-normal',
                              algo.isDefault &&
                                'border-primary/60 text-primary'
                            )}
                          >
                            {getAlgorithmLabel(algo.algorithmType)}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <span className='text-muted-foreground'>—</span>
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    <WeightCell
                      value={dimension.weight ?? WEIGHT_MIN}
                      disabled={!canManage}
                      pending={weightPendingIds.has(dimension.id)}
                      onCommit={(weight) =>
                        onWeightCommit(dimension, weight)
                      }
                    />
                  </td>
                  <td className='px-3 py-2'>
                    {isLlmJudge ? (
                      <StatusBadge
                        label='LLM Judge'
                        icon={Bot}
                        variant='purple'
                        size='sm'
                      />
                    ) : (
                      <StatusBadge
                        label={apiOnline ? '在线' : '离线'}
                        variant={apiOnline ? 'success' : 'danger'}
                        size='sm'
                      />
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    <StatusBadge
                      label={dimension.status ? '启用' : '禁用'}
                      variant={dimension.status ? 'success' : 'neutral'}
                      size='sm'
                    />
                  </td>
                  <td className='px-3 py-2'>
                    <div className='flex items-center justify-end gap-0.5'>
                      <ActionButton
                        label='上移'
                        ariaLabel={`上移维度 ${dimension.name}`}
                        disabled={!canManage || !canMoveUp(dimension)}
                        disabledTooltip={
                          !canManage
                            ? permManageTooltip
                            : canMoveUp(dimension)
                              ? undefined
                              : '已是首行'
                        }
                        onClick={() => onMove(dimension, -1)}
                      >
                        <ArrowUp aria-hidden='true' className='size-3.5' />
                      </ActionButton>
                      <ActionButton
                        label='下移'
                        ariaLabel={`下移维度 ${dimension.name}`}
                        disabled={!canManage || !canMoveDown(dimension)}
                        disabledTooltip={
                          !canManage
                            ? permManageTooltip
                            : canMoveDown(dimension)
                              ? undefined
                              : '已是末行'
                        }
                        onClick={() => onMove(dimension, 1)}
                      >
                        <ArrowDown aria-hidden='true' className='size-3.5' />
                      </ActionButton>
                      <ActionButton
                        label='编辑'
                        ariaLabel={`编辑维度 ${dimension.name}`}
                        disabled={!canManage}
                        disabledTooltip={permManageTooltip}
                        onClick={() => onEdit(dimension)}
                      >
                        <Pencil aria-hidden='true' className='size-3.5' />
                      </ActionButton>
                      <ActionButton
                        label='复制'
                        ariaLabel={`复制维度 ${dimension.name}`}
                        disabled={!canManage}
                        disabledTooltip={permManageTooltip}
                        onClick={() => onDuplicate(dimension)}
                      >
                        <Copy aria-hidden='true' className='size-3.5' />
                      </ActionButton>
                      <ActionButton
                        label={dimension.status ? '禁用' : '启用'}
                        ariaLabel={`${dimension.status ? '禁用' : '启用'}维度 ${dimension.name}`}
                        disabled={!canManage}
                        disabledTooltip={permManageTooltip}
                        onClick={() => onToggleStatus(dimension)}
                      >
                        <span
                          className={cn(
                            'size-1.5 rounded-full',
                            dimension.status
                              ? 'bg-success'
                              : 'bg-muted-foreground'
                          )}
                        />
                      </ActionButton>
                      {dimension._isMain && (
                        <ActionButton
                          label='添加子维度'
                          ariaLabel={`为维度 ${dimension.name} 添加子维度`}
                          disabled={!canManage}
                          disabledTooltip={permManageTooltip}
                          onClick={() => onAddSub(dimension)}
                        >
                          <Plus aria-hidden='true' className='size-3.5' />
                        </ActionButton>
                      )}
                      <ActionButton
                        label='测试 API'
                        ariaLabel={`测试维度 ${dimension.name} 的 API`}
                        disabled={!canRead}
                        disabledTooltip={permReadTooltip}
                        onClick={() => onTestApi(dimension)}
                      >
                        <Activity aria-hidden='true' className='size-3.5' />
                      </ActionButton>
                      <ActionButton
                        label='规则试算'
                        ariaLabel={`规则试算维度 ${dimension.name}`}
                        disabled={!canManage}
                        disabledTooltip={permManageTooltip}
                        onClick={() => onRuleCalc(dimension)}
                      >
                        <Calculator aria-hidden='true' className='size-3.5' />
                      </ActionButton>
                      <ActionButton
                        label='删除'
                        ariaLabel={`删除维度 ${dimension.name}`}
                        disabled={!canManage}
                        disabledTooltip={permManageTooltip}
                        destructive
                        onClick={() => onDelete(dimension)}
                      >
                        <Trash2 aria-hidden='true' className='size-3.5' />
                      </ActionButton>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** 操作 ghost icon 钮（权限/边界禁用 + Tooltip 文案；§7 注 1「无 {权限码} 权限」口径） */
function ActionButton({
  label,
  ariaLabel,
  disabled,
  disabledTooltip,
  destructive,
  onClick,
  children,
}: {
  label: string
  ariaLabel: string
  disabled?: boolean
  /** 禁用态 Tooltip（权限码/边界原因；缺省回退 label） */
  disabledTooltip?: string
  destructive?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  const button = (
    <Button
      variant='ghost'
      size='icon-sm'
      aria-label={ariaLabel}
      className={cn(destructive && 'text-destructive', 'text-muted-foreground')}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </Button>
  )
  if (disabled) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <span tabIndex={0} className='inline-flex cursor-not-allowed'>
              {button}
            </span>
          }
        />
        <TooltipContent>{disabledTooltip ?? label}</TooltipContent>
      </Tooltip>
    )
  }
  return (
    <Tooltip>
      <TooltipTrigger render={button} />
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

/**
 * 权重滑杆单元格（§4.1/§10-4：拖动停止 onValueCommitted 才提交 PUT，进行中 Spinner +
 * 成功 toast「权重更新成功」；替代现拖动即弹成功模态窗的打扰交互）。
 */
function WeightCell({
  value,
  disabled,
  pending,
  onCommit,
}: {
  value: number
  disabled?: boolean
  pending: boolean
  onCommit: (weight: number) => void
}) {
  const [draft, setDraft] = useState(value)

  // 外部数据变化（刷新/编辑）时同步草稿
  useEffect(() => {
    setDraft(value)
  }, [value])

  const toNumber = (next: number | readonly number[]): number =>
    typeof next === 'number' ? next : (next[0] ?? WEIGHT_MIN)

  const handleCommit = (next: number) => {
    setDraft(next)
    onCommit(next)
  }

  return (
    <div className='flex min-w-32 items-center gap-2'>
      <Slider
        min={WEIGHT_MIN}
        max={WEIGHT_MAX}
        step={1}
        value={[draft]}
        disabled={disabled}
        onValueChange={(next) => setDraft(toNumber(next))}
        onValueCommitted={(next) => handleCommit(toNumber(next))}
        className='w-24'
        aria-label={`权重 ${value}`}
      />
      <span className='tabular-nums'>{draft}</span>
      {pending && <Spinner className='size-3.5' />}
    </div>
  )
}
