/**
 * 挑选/购物车 compact 用例卡（18_挑选合并交互重设计.md §3.8.3/§4.2，INT-1047）。
 * CaseCard compact 变体：复用 features/testcases/components/case-card.tsx 字段口径
 * （名称 / CaseIdBadge / 算法徽章 / 标签 / 时长 / 轮次 / 计数 Badge），hideMeta + 精简操作区 + 展开三角。
 * 用例视图用例节点与购物车用例节点共用；勾选走 R6 用例级（购物车侧为批量移除选择）。
 */
import { ChevronDown, ChevronRight } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import type { SelectionState } from '@/domain/models/cherryPick'
import { CaseCard } from '@/features/testcases/components/case-card'

export interface PickCaseCardProps {
  /** 用例名（已降级友好文案「用例不可用 {前 8 位}…」） */
  name: string
  /** case_id（CaseIdBadge 点击复制） */
  caseId?: string
  /** 算法类型（算法徽章） */
  algorithmType?: string | null
  /** 算法类型码 → 中文名（真实 GET /algorithm/options，useAlgorithmLabels）；缺项时不渲染算法徽章 */
  algorithmLabels?: Record<string, string>
  /** 用例标签（§11-7 真实名；标签行 TagBadge） */
  tags?: string[]
  /** 用例时长（秒；徽章「{时长}」） */
  totalDuration?: number | null
  /** 用例轮次（徽章「{n} 轮」） */
  rounds?: number | null
  /** 计数 Badge「{n} 条」 */
  count: number
  /** 勾选态（R3 三态） */
  state: SelectionState
  /** 勾选切换（R6 用例级 / 购物车批量移除选择） */
  onToggle: (select: boolean) => void
  open: boolean
  onToggleOpen: () => void
  /** 徽章行前导（购物车失效提示等） */
  badgeLeading?: React.ReactNode
  /** 右操作区（购物车：移除该组钮） */
  actions?: React.ReactNode
  /** 展开区（设备/结果类型子树） */
  children?: React.ReactNode
}

export function PickCaseCard({
  name,
  caseId,
  algorithmType,
  algorithmLabels,
  tags = [],
  totalDuration = null,
  rounds = null,
  count,
  state,
  onToggle,
  open,
  onToggleOpen,
  badgeLeading,
  actions,
  children,
}: PickCaseCardProps) {
  return (
    <CaseCard
      caseItem={{
        id: caseId ?? name,
        name,
        tags,
        algorithmType: algorithmType ?? null,
        totalDuration,
        rounds: rounds ?? undefined,
      }}
      selected={state === 'checked'}
      algorithmLabels={algorithmLabels}
      showCheckbox={false}
      leading={
        <Checkbox
          checked={state === 'checked'}
          indeterminate={state === 'indeterminate'}
          onCheckedChange={(c) => onToggle(c)}
          aria-label={`选择 ${name}`}
          className='mt-1 shrink-0'
        />
      }
      hideMeta
      badgeLeading={
        <>
          <Badge
            variant='secondary'
            className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'
          >
            {count} 条
          </Badge>
          {badgeLeading}
        </>
      }
      actions={
        <div className='flex items-center gap-0.5'>
          {actions}
          <Button
            variant='ghost'
            size='icon-xs'
            aria-label={open ? '收起' : '展开'}
            className='text-muted-foreground shrink-0'
            onClick={onToggleOpen}
          >
            {open ? (
              <ChevronDown aria-hidden='true' className='size-3.5' />
            ) : (
              <ChevronRight aria-hidden='true' className='size-3.5' />
            )}
          </Button>
        </div>
      }
      expandedContent={open ? children : undefined}
    />
  )
}
