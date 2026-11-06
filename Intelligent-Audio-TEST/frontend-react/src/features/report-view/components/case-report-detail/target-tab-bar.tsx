/**
 * 设备/API Tab 条（被测设备/API，一级切换轴）。
 *
 * 用例级详情（任务侧弹窗 / 报告侧用例卡）共用：
 * - 默认「全部对比」= 现状（评分指标按设备/API 列并排对比）；
 * - 选中单个设备/API 后，评分指标以下的模块整体收窄到该目标；
 * - 轮次为二级轴（RoundTabBar / 报告域既有轮次 Tab），两轴互不影响。
 */
import { cn } from '@/lib/utils'

/** 目标切换「全部对比」哨兵值 */
export const ALL_TARGETS = '__all__'

export function TargetTabBar({
  targetNames,
  activeTarget,
  onSelect,
  label = '设备/API',
}: {
  /** 目标展示名（设备名 / API 名） */
  targetNames: string[]
  activeTarget: string
  onSelect: (target: string) => void
  label?: string
}) {
  if (targetNames.length <= 1) return null
  const tabs = [
    { key: ALL_TARGETS, label: '全部对比' },
    ...targetNames.map((name) => ({ key: name, label: name })),
  ]
  return (
    <div className='flex flex-wrap items-center gap-1' role='tablist' aria-label='目标切换'>
      <span className='text-muted-foreground mr-1 text-xs'>{label}</span>
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type='button'
          role='tab'
          aria-selected={activeTarget === tab.key}
          className={cn(
            'rounded-md px-2.5 py-1 text-xs transition-colors',
            activeTarget === tab.key
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-muted'
          )}
          onClick={() => onSelect(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
