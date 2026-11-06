/**
 * ParamCard 参数卡（interfaces/features/test-execution/components；平台件，10_测试执行.md §6）。
 * playground-parameter-panel 单卡通用化：`border-border/70 bg-background/60 rounded-lg border p-3`，
 * 标签行 + Badge outline 值 + 说明 text-muted-foreground text-xs + 右侧控件；
 * 只读态（algo_engineer 观察/API 自动求合）opacity 弱化、控件隐藏。
 */
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'

interface ParamCardProps {
  label: string
  /** Badge outline 值（照 getParameterControlValueText 显示） */
  value: string
  description: string
  /** 只读态（隐藏控件，展示值） */
  readOnly?: boolean
  /** 值语义色（如 voice_llm 建议 text-warning） */
  valueClassName?: string
  children?: React.ReactNode
}

export function ParamCard({
  label,
  value,
  description,
  readOnly = false,
  valueClassName,
  children,
}: ParamCardProps) {
  return (
    <div
      className={cn(
        'border-border/70 bg-background/60 rounded-lg border p-3',
        readOnly && 'opacity-55'
      )}
    >
      <div className='flex items-center justify-between gap-2'>
        <span className='text-sm font-medium'>{label}</span>
        <Badge variant='outline' className={cn('text-[11px] tabular-nums', valueClassName)}>
          {value}
        </Badge>
      </div>
      <p className='text-muted-foreground mt-1 text-xs'>{description}</p>
      {!readOnly && children && <div className='mt-2'>{children}</div>}
    </div>
  )
}
