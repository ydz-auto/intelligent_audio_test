/**
 * 容器组成区四视图切换 + 工具行（18_挑选合并功能交互重设计.md §5.5.3 ② / §5.5.4，INT-1711）。
 * 四视图：任务视图（默认）｜用例｜设备｜结果类型——直接复用购物车 `CartViewSwitcher`，层级与购物车同源。
 * 工具行：执行状态 / 评估状态筛选（纯客户端，命中叶保留、祖先保留、分支计数按命中集重算）、
 * 全部展开 / 全部收起；用例视图叠加用例层组织控件（复用 `PickCaseOrgControls`）。
 * 降级期在工具行右端显示一次性提示「结果级状态待后端补字段，当前按用例状态显示」（§5.5.4）。
 * 纯 props，不取数。
 */
import { ChevronsDownUp, ChevronsUpDown } from 'lucide-react'

import type { PickOrgDimension, PickSubView } from '@/application/tasks/cherry-pick/use-pick-org'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type {
  CompositionEvaluationFilter,
  CompositionExecutionFilter,
} from '@/domain/lib/container-composition'
import {
  CartViewSwitcher,
  type CartView,
} from '@/features/tasks/cherry-pick/components/cart-view-switcher'
import { PickCaseOrgControls } from '@/features/tasks/cherry-pick/components/pick-case-org-list'

const EXECUTION_OPTIONS: Array<{ value: CompositionExecutionFilter; label: string }> = [
  { value: 'all', label: '全部执行状态' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '已失败' },
  { value: 'stopped', label: '已停止' },
]

const EVALUATION_OPTIONS: Array<{ value: CompositionEvaluationFilter; label: string }> = [
  { value: 'all', label: '全部评估状态' },
  { value: 'evaluated', label: '已评估' },
  { value: 'unevaluated', label: '未评估' },
]

export function ContainerViewSwitcher({
  view,
  onChange,
}: {
  view: CartView
  onChange: (view: CartView) => void
}) {
  return <CartViewSwitcher view={view} onChange={onChange} />
}

export interface ContainerCompositionToolbarProps {
  view: CartView
  onViewChange: (view: CartView) => void
  execution: CompositionExecutionFilter
  onExecutionChange: (value: CompositionExecutionFilter) => void
  evaluation: CompositionEvaluationFilter
  onEvaluationChange: (value: CompositionEvaluationFilter) => void
  onExpandAll: () => void
  onCollapseAll: () => void
  /** 结果级状态未返、叶行状态取自容器用例行（§5.5.4 降级口径） */
  degraded: boolean
  /** 用例层组织（用例视图生效；四视图共享同一会话态） */
  org: PickOrgDimension
  subView: PickSubView
  onOrgChange: (org: PickOrgDimension) => void
  onSubViewChange: (subView: PickSubView) => void
}

export function ContainerCompositionToolbar({
  view,
  onViewChange,
  execution,
  onExecutionChange,
  evaluation,
  onEvaluationChange,
  onExpandAll,
  onCollapseAll,
  degraded,
  org,
  subView,
  onOrgChange,
  onSubViewChange,
}: ContainerCompositionToolbarProps) {
  return (
    <div className='flex flex-col gap-2'>
      <div className='flex flex-wrap items-center gap-1.5'>
        <ContainerViewSwitcher view={view} onChange={onViewChange} />

        <Select
          value={execution}
          onValueChange={(value) => onExecutionChange(value as CompositionExecutionFilter)}
        >
          <SelectTrigger size='sm' className='h-7 gap-1.5 px-2.5' aria-label='执行状态筛选'>
            <SelectValue>
              {EXECUTION_OPTIONS.find((o) => o.value === execution)?.label}
            </SelectValue>
          </SelectTrigger>
          <SelectContent align='start'>
            {EXECUTION_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={evaluation}
          onValueChange={(value) => onEvaluationChange(value as CompositionEvaluationFilter)}
        >
          <SelectTrigger size='sm' className='h-7 gap-1.5 px-2.5' aria-label='评估状态筛选'>
            <SelectValue>
              {EVALUATION_OPTIONS.find((o) => o.value === evaluation)?.label}
            </SelectValue>
          </SelectTrigger>
          <SelectContent align='start'>
            {EVALUATION_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button variant='ghost' size='sm' className='h-7 gap-1 px-2 text-xs' onClick={onExpandAll}>
          <ChevronsUpDown aria-hidden='true' className='size-3.5' />
          全部展开
        </Button>
        <Button variant='ghost' size='sm' className='h-7 gap-1 px-2 text-xs' onClick={onCollapseAll}>
          <ChevronsDownUp aria-hidden='true' className='size-3.5' />
          全部收起
        </Button>

        {degraded && (
          <span
            className='text-muted-foreground/70 ml-auto shrink-0 text-[11px]'
            data-testid='composition-degraded-hint'
          >
            结果级状态待后端补字段，当前按用例状态显示
          </span>
        )}
      </div>

      {view === 'case' && (
        <PickCaseOrgControls
          org={org}
          subView={subView}
          onOrgChange={onOrgChange}
          onSubViewChange={onSubViewChange}
        />
      )}
    </div>
  )
}
