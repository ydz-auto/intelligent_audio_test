/**
 * 执行模式胶囊分段控件（interfaces/features/test-execution/components；10_测试执行.md
 * §3.6.1/3.6.2，INT-1119 2026-10-21）。「并行｜串行」单选，照 Tabs default 变体
 * `bg-muted p-[3px]` + 激活 `bg-background shadow-sm`；仅被选中目标显示。
 * 受控值经 useTargetModes（§3.6.5 唯一受控源），切卡/切模式不闪跳。
 */
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ExecutionMode } from '@/domain/models/testExecution'

interface ExecutionModeControlProps {
  value: ExecutionMode
  onChange: (mode: ExecutionMode) => void
  /** 紧凑形态（API 表格行内 h-6，§3.6.2） */
  compact?: boolean
  /** aria 文案（「{目标名} 执行模式」） */
  ariaLabel: string
  disabled?: boolean
}

export function ExecutionModeControl({
  value,
  onChange,
  compact = false,
  ariaLabel,
  disabled = false,
}: ExecutionModeControlProps) {
  return (
    <div
      role='radiogroup'
      aria-label={ariaLabel}
      className={cn(
        'bg-muted inline-flex items-center rounded-lg p-[3px]',
        compact ? 'h-6' : 'h-7'
      )}
    >
      {(['parallel', 'serial'] as const).map((mode) => (
        <button
          key={mode}
          type='button'
          role='radio'
          aria-checked={value === mode}
          disabled={disabled}
          onClick={() => onChange(mode)}
          className={cn(
            'text-muted-foreground hover:text-foreground rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all',
            value === mode && 'bg-background text-foreground shadow-sm',
            disabled && 'pointer-events-none opacity-50'
          )}
        >
          {mode === 'parallel' ? '并行' : '串行'}
        </button>
      ))}
    </div>
  )
}

/** 只读模式 Badge（§3.6.1/3.6.2 readOnly 观察态：并行=success 软底/串行=info 软底） */
export function ExecutionModeBadge({ mode }: { mode: ExecutionMode }) {
  return (
    <Badge
      className={cn(
        'h-5 px-2 text-[11px] font-medium',
        mode === 'parallel'
          ? 'bg-success/10 text-success'
          : 'bg-info/10 text-info'
      )}
    >
      {mode === 'parallel' ? '并行' : '串行'}
    </Badge>
  )
}
