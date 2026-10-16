/**
 * 设备统计徽章行（16_设备域.md §9；StatBadge ×4）。
 * 测试/播放页签：总设备数/在线设备/离线设备/异常设备（错误态聚合）。
 * API 页签：总测试API数/可用API/不可用API/测试中API。
 * 「测试中」占用态不参与统计口径（§3.4 注 / INT-487）：占用设备按其五态状态计数。
 * 加载中 Skeleton h-7；接口失败整行隐藏不报错（照 §4.1.2 口径）。
 */
import { Skeleton } from '@/components/ui/skeleton'

function StatBadge({
  label,
  value,
  dotClass,
}: {
  label: string
  value: string | number
  dotClass: string
}) {
  return (
    <span className='border-border/60 bg-muted/25 inline-flex h-7 items-center gap-2 rounded-md border px-2.5 text-xs shadow-xs'>
      <span aria-hidden='true' className={`h-3.5 w-0.5 rounded-full ${dotClass}`} />
      <span className='text-muted-foreground'>{label}</span>
      <span className='font-mono font-medium tabular-nums'>{value}</span>
    </span>
  )
}

export function DevicesStatsRow({
  labels,
  values,
  loading,
}: {
  labels: readonly string[]
  values: number[]
  loading: boolean
}) {
  if (loading) {
    return (
      <div className='flex flex-wrap items-center gap-2' aria-label='统计加载中'>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className='h-7 w-36 rounded-md' />
        ))}
      </div>
    )
  }
  // P4 返修：色条全走语义 token（neutral/success/muted/destructive，§2.1 口径）
  const dots = [
    'bg-[var(--muted-foreground)]',
    'bg-[var(--success)]',
    'bg-[var(--muted-foreground)]',
    'bg-[var(--destructive)]',
  ]
  return (
    <div className='flex flex-wrap items-center gap-2'>
      {labels.map((label, index) => (
        <StatBadge
          key={label}
          label={label}
          value={values[index] ?? 0}
          dotClass={dots[index] ?? 'bg-neutral-400'}
        />
      ))}
    </div>
  )
}
