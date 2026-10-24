/**
 * 用例卡「显示设置」（15_报告域.md §3.5.10，INT-1738）。
 *
 * 区级一份状态（作用于该报告内全部用例卡 + 三视图叶表），入口 = 工具栏右端 Button `outline` `size=sm`
 * 「显示设置」+ 非全选时 Badge「已隐藏 {n} 项」。
 * Popover（`w-[360px]`，内容 `max-h-[460px] overflow-y-auto`）= 4 个折叠 Section：
 * 卡片内容 / 评估维度（三级树）/ 轮次 / 资源与结果类型；底部「恢复默认（全部显示）」+ 说明小字。
 * 移动端（≤640px）改底部 Sheet，按钮收为 icon-only。
 *
 * **口径 A（当维由视图决定）**：设备视图「资源」、结果类型视图「结果类型」子项置灰只读，
 * 不参与勾选状态，换视图后恢复原勾选。
 */
import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'
import type { DimensionTreeSection } from '@/application/report-view/use-report-filter-taxonomy'
import {
  CONTENT_BLOCK_KEYS,
  CONTENT_BLOCK_LABELS,
  EXECUTION_CHILD_KEYS,
  EXECUTION_CHILD_LABELS,
  type CaseDisplaySettings as DisplaySettings,
  type ExecutionChildKey,
} from '@/application/report-view/use-case-display-settings'
import type { ReportCaseView } from '@/application/report-view/report-case-view-model'

import { FilterDimensionTree } from './filter-dimension-tree'

export interface CaseDisplaySettingsProps {
  /** 当前视图（决定当维锁定，口径 A） */
  view: ReportCaseView
  settings: DisplaySettings
  onChange: (patch: Partial<DisplaySettings>) => void
  onReset: () => void
  hiddenCount: number
  dimensionSections: DimensionTreeSection[]
  /** 轮次 chips（整体 / 第 N 轮；单轮用例时为空 → 不渲染本 Section） */
  rounds: { key: string; label: string }[]
  resourceOptions: { key: string; label: string; kind: 'device' | 'api' }[]
  resultTypeOptions: { key: string; label: string }[]
}

const toggleIn = <T extends string>(list: T[], value: T, checked: boolean): T[] =>
  checked ? list.filter((x) => x !== value) : [...new Set([...list, value])]

/** 折叠 Section 外壳（标题 + 计数 + 全选|清空） */
function Section({
  title,
  count,
  onSelectAll,
  children,
  defaultOpen = false,
}: {
  title: string
  count: string
  onSelectAll?: (checked: boolean) => void
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Collapsible open={open} onOpenChange={setOpen} className='border-b last:border-b-0'>
      <div className='flex items-center gap-2 py-1.5'>
        <CollapsibleTrigger
          render={<button type='button' className='flex min-w-0 flex-1 items-center gap-1.5 text-left' />}
        >
          <ChevronDown
            aria-hidden='true'
            className={cn('text-muted-foreground size-3.5 shrink-0 transition-transform', !open && '-rotate-90')}
          />
          <span className='truncate text-xs font-medium'>{title}</span>
          <span className='text-muted-foreground shrink-0 font-mono text-[11px] tabular-nums'>{count}</span>
        </CollapsibleTrigger>
        {onSelectAll && (
          <div className='flex shrink-0 items-center gap-0.5'>
            <Button
              variant='ghost'
              size='sm'
              className='text-muted-foreground h-6 px-1 text-[11px]'
              onClick={() => onSelectAll(true)}
            >
              全选
            </Button>
            <Button
              variant='ghost'
              size='sm'
              className='text-muted-foreground h-6 px-1 text-[11px]'
              onClick={() => onSelectAll(false)}
            >
              清空
            </Button>
          </div>
        )}
      </div>
      <CollapsibleContent className='pb-2'>{children}</CollapsibleContent>
    </Collapsible>
  )
}

/** 单项行（Checkbox + 文案 + 可选角标 / 置灰提示） */
function OptionRow({
  checked,
  label,
  badge,
  hint,
  disabled,
  onChange,
  className,
}: {
  checked: boolean
  label: string
  badge?: string
  hint?: string
  disabled?: boolean
  onChange: (checked: boolean) => void
  className?: string
}) {
  return (
    <label
      className={cn(
        'flex items-center gap-1.5 py-0.5 text-xs',
        disabled && 'cursor-not-allowed opacity-60',
        className
      )}
      title={hint}
    >
      <Checkbox
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onChange(value === true)}
      />
      <span className='truncate'>{label}</span>
      {badge && (
        <Badge variant='outline' className='px-1 py-0 text-[10px] font-normal'>
          {badge}
        </Badge>
      )}
      {hint && <span className='text-muted-foreground truncate text-[10px]'>{hint}</span>}
    </label>
  )
}

export function CaseDisplaySettings({
  view,
  settings,
  onChange,
  onReset,
  hiddenCount,
  dimensionSections,
  rounds,
  resourceOptions,
  resultTypeOptions,
}: CaseDisplaySettingsProps) {
  const isMobile = useIsMobile()

  // 资源 / 结果类型锁定（口径 A：当维由视图决定）
  const resourcesLocked = view === 'resource'
  const resultTypesLocked = view === 'resultType'

  const allMetrics = dimensionSections.flatMap((s) => s.groups.flatMap((g) => [g.main, ...g.subs]))
  const visibleMetrics = allMetrics.filter((m) => !settings.hiddenMetrics.includes(m))

  const body = (
    <div className='flex flex-col'>
      {/* 卡片内容（一级开关；执行结果带 5 子项 + 音频） */}
      <Section
        title='卡片内容'
        count={`${CONTENT_BLOCK_KEYS.length + EXECUTION_CHILD_KEYS.length - settings.hiddenBlocks.length - settings.hiddenExecution.length}/${CONTENT_BLOCK_KEYS.length + EXECUTION_CHILD_KEYS.length}`}
        onSelectAll={(checked) =>
          onChange({
            hiddenBlocks: checked ? [] : [...CONTENT_BLOCK_KEYS],
            hiddenExecution: checked ? [] : [...EXECUTION_CHILD_KEYS],
          })
        }
        defaultOpen
      >
        <div className='space-y-0.5'>
          <OptionRow
            checked={!settings.hiddenBlocks.includes('resultComparison')}
            label={CONTENT_BLOCK_LABELS.resultComparison}
            onChange={(checked) =>
              onChange({ hiddenBlocks: toggleIn(settings.hiddenBlocks, 'resultComparison', checked) })
            }
          />
          <OptionRow
            checked={!settings.hiddenBlocks.includes('metricTable')}
            label={CONTENT_BLOCK_LABELS.metricTable}
            onChange={(checked) =>
              onChange({ hiddenBlocks: toggleIn(settings.hiddenBlocks, 'metricTable', checked) })
            }
          />
          <OptionRow
            checked={!settings.hiddenBlocks.includes('multiRound')}
            label={CONTENT_BLOCK_LABELS.multiRound}
            onChange={(checked) =>
              onChange({ hiddenBlocks: toggleIn(settings.hiddenBlocks, 'multiRound', checked) })
            }
          />
          <OptionRow
            checked={!settings.hiddenBlocks.includes('execution')}
            label={CONTENT_BLOCK_LABELS.execution}
            onChange={(checked) =>
              onChange({ hiddenBlocks: toggleIn(settings.hiddenBlocks, 'execution', checked) })
            }
          />
          <div className='ms-4 space-y-0.5 border-s ps-2'>
            {EXECUTION_CHILD_KEYS.map((child: ExecutionChildKey) => (
              <OptionRow
                key={child}
                checked={!settings.hiddenExecution.includes(child)}
                label={EXECUTION_CHILD_LABELS[child]}
                disabled={settings.hiddenBlocks.includes('execution')}
                onChange={(checked) =>
                  onChange({ hiddenExecution: toggleIn(settings.hiddenExecution, child, checked) })
                }
              />
            ))}
          </div>
          <OptionRow
            checked={!settings.hiddenBlocks.includes('description')}
            label={CONTENT_BLOCK_LABELS.description}
            onChange={(checked) =>
              onChange({ hiddenBlocks: toggleIn(settings.hiddenBlocks, 'description', checked) })
            }
          />
          <OptionRow
            checked={!settings.hiddenBlocks.includes('logs')}
            label={CONTENT_BLOCK_LABELS.logs}
            onChange={(checked) =>
              onChange({ hiddenBlocks: toggleIn(settings.hiddenBlocks, 'logs', checked) })
            }
          />
        </div>
      </Section>

      {/* 评估维度（分类 → 主维度 → 子维度三级树） */}
      <Section
        title='评估维度'
        count={`${visibleMetrics.length}/${allMetrics.length}`}
        onSelectAll={(checked) =>
          onChange({ hiddenMetrics: checked ? [] : [...allMetrics] })
        }
        defaultOpen
      >
        <div className='space-y-2'>
          <FilterDimensionTree
            sections={dimensionSections}
            selected={visibleMetrics}
            onToggle={(names, checked) => {
              let hidden = settings.hiddenMetrics
              for (const name of names) hidden = toggleIn(hidden, name, checked)
              onChange({ hiddenMetrics: hidden })
            }}
            showSearch
          />
          {allMetrics.length === 0 && (
            <p className='text-muted-foreground text-xs'>未选择评估维度</p>
          )}
          <label className='flex items-center justify-between gap-2 border-t pt-2 text-xs'>
            <span>叶表包含子维度</span>
            <Switch
              size='sm'
              checked={settings.includeSubDimensions}
              onCheckedChange={(checked) => onChange({ includeSubDimensions: checked === true })}
            />
          </label>
        </div>
      </Section>

      {/* 轮次（仅多轮用例出现；单轮不渲染本 Section） */}
      {rounds.length > 0 && (
        <Section
          title='轮次'
          count={`${rounds.filter((r) => !settings.hiddenRounds.includes(r.key)).length}/${rounds.length}`}
          onSelectAll={(checked) =>
            onChange({ hiddenRounds: checked ? [] : rounds.map((r) => r.key) })
          }
        >
          <div className='flex flex-wrap gap-1.5'>
            {rounds.map((round) => {
              const active = !settings.hiddenRounds.includes(round.key)
              return (
                <button
                  key={round.key}
                  type='button'
                  aria-pressed={active}
                  onClick={() =>
                    onChange({ hiddenRounds: toggleIn(settings.hiddenRounds, round.key, active) })
                  }
                  className={cn(
                    'rounded-md border px-2 py-0.5 text-xs transition-colors',
                    active
                      ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                      : 'hover:bg-accent text-muted-foreground border-border'
                  )}
                >
                  {round.label}
                </button>
              )
            })}
          </div>
        </Section>
      )}

      {/* 资源与结果类型（当维锁定，口径 A） */}
      <Section
        title='资源与结果类型'
        count={`${resourceOptions.filter((r) => !settings.hiddenResources.includes(r.key)).length + resultTypeOptions.filter((t) => !settings.hiddenResultTypes.includes(t.key)).length}/${resourceOptions.length + resultTypeOptions.length}`}
        onSelectAll={(checked) =>
          onChange({
            // 锁定项不参与勾选状态（口径 A）
            hiddenResources: resourcesLocked
              ? settings.hiddenResources
              : checked
                ? []
                : resourceOptions.map((r) => r.key),
            hiddenResultTypes: resultTypesLocked
              ? settings.hiddenResultTypes
              : checked
                ? []
                : resultTypeOptions.map((t) => t.key),
          })
        }
      >
        <div className='space-y-2'>
          <div>
            <p className='text-muted-foreground mb-1 flex items-center gap-1 text-[11px] font-medium'>
              设备/API
              {resourcesLocked && <span>· 由设备视图节点决定</span>}
            </p>
            <div className='space-y-0.5'>
              {resourceOptions.map((option) => (
                <OptionRow
                  key={option.key}
                  checked={resourcesLocked ? true : !settings.hiddenResources.includes(option.key)}
                  label={option.label}
                  badge={option.kind === 'api' ? 'API' : undefined}
                  disabled={resourcesLocked}
                  hint={resourcesLocked ? '由设备视图节点决定' : undefined}
                  onChange={(checked) =>
                    onChange({ hiddenResources: toggleIn(settings.hiddenResources, option.key, checked) })
                  }
                />
              ))}
              {resourceOptions.length === 0 && (
                <p className='text-muted-foreground text-xs'>未选择资源 / 结果类型</p>
              )}
            </div>
          </div>
          {resultTypeOptions.length > 1 && (
            <div className='border-t pt-2'>
              <p className='text-muted-foreground mb-1 flex items-center gap-1 text-[11px] font-medium'>
                结果类型
                {resultTypesLocked && <span>· 由结果类型视图节点决定</span>}
              </p>
              <div className='space-y-0.5'>
                {resultTypeOptions.map((option) => (
                  <OptionRow
                    key={option.key}
                    checked={
                      resultTypesLocked ? true : !settings.hiddenResultTypes.includes(option.key)
                    }
                    label={option.label}
                    disabled={resultTypesLocked}
                    hint={resultTypesLocked ? '由结果类型视图节点决定' : undefined}
                    onChange={(checked) =>
                      onChange({
                        hiddenResultTypes: toggleIn(settings.hiddenResultTypes, option.key, checked),
                      })
                    }
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </Section>

      {/* 底部 sticky：恢复默认 + 说明 */}
      <div className='bg-popover sticky bottom-0 mt-2 flex items-center justify-between gap-2 border-t pt-2'>
        <p className='text-muted-foreground text-[10px] leading-tight'>
          用例详情弹窗始终显示全部内容
        </p>
        <Button variant='outline' size='sm' className='h-7 shrink-0 px-2 text-xs' onClick={onReset}>
          恢复默认（全部显示）
        </Button>
      </div>
    </div>
  )

  const label = (
    <>
      <SlidersHorizontal aria-hidden='true' className='size-3.5' />
      <span className='hidden sm:inline'>显示设置</span>
    </>
  )

  if (isMobile) {
    return (
      <div className='flex items-center gap-1.5'>
        <Sheet>
          <SheetTrigger render={<Button variant='outline' size='sm' className='h-7 px-2' aria-label='显示设置' />}>
            {label}
          </SheetTrigger>
          <SheetContent side='bottom' className='max-h-[80vh] overflow-y-auto'>
            <SheetHeader>
              <SheetTitle className='text-sm'>显示设置</SheetTitle>
            </SheetHeader>
            {body}
          </SheetContent>
        </Sheet>
        {hiddenCount > 0 && (
          <Badge variant='secondary' className='font-mono text-[11px] tabular-nums'>
            已隐藏 {hiddenCount} 项
          </Badge>
        )}
      </div>
    )
  }

  return (
    <div className='flex items-center gap-1.5'>
      <Popover>
        <PopoverTrigger render={<Button variant='outline' size='sm' className='h-7 gap-1 px-2 text-xs' />}>
          {label}
        </PopoverTrigger>
        <PopoverContent align='end' className='max-h-[460px] w-[360px] overflow-y-auto'>
          <p className='text-xs font-semibold'>显示设置</p>
          {body}
        </PopoverContent>
      </Popover>
      {hiddenCount > 0 && (
        <Badge variant='secondary' className='font-mono text-[11px] tabular-nums'>
          已隐藏 {hiddenCount} 项
        </Badge>
      )}
    </div>
  )
}
