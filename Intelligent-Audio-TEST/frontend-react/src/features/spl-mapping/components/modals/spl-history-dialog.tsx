/**
 * 物理域校准历史（§6.9；Dialog sm:max-w-2xl）。
 * 列表（GET /spl/{id}/history，SplHistoryItem：距离/测试频率/校准点数/时间）+ 每项展开点集；
 * 空态「暂无校准记录」。
 */
import { useState } from 'react'
import { ChevronDown } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useSplHistory } from '@/application/spl/useSplMappings'
import { formatDateTime, formatDistance, formatTestFrequency } from '@/features/spl-mapping/lib/format'

export type SplHistoryDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mappingId: number | null
}

export function SplHistoryDialog(props: SplHistoryDialogProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const historyQuery = useSplHistory(props.mappingId)
  const history = historyQuery.data ?? []

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>校准历史</DialogTitle>
          <DialogDescription>
            该增益映射的历史校准记录（每次校准成功追加一条）
          </DialogDescription>
        </DialogHeader>

        {historyQuery.isLoading ? (
          <div className='space-y-2'>
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className='h-12 w-full rounded-lg' />
            ))}
          </div>
        ) : history.length === 0 ? (
          <div className='bg-card ring-foreground/10 text-muted-foreground rounded-lg px-3 py-8 text-center text-sm ring-1'>
            暂无校准记录
          </div>
        ) : (
          <div className='space-y-2'>
            {history.map((item) => {
              const pointCount = item.calibrationData?.points.length ?? 0
              const expanded = expandedId === item.id
              return (
                <div key={item.id} className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
                  <button
                    type='button'
                    onClick={() => setExpandedId(expanded ? null : item.id)}
                    className='hover:bg-muted/40 flex w-full items-center gap-2 px-3 py-2.5 text-start transition-colors'
                    aria-expanded={expanded}
                  >
                    <ChevronDown
                      aria-hidden='true'
                      className={cn(
                        'text-muted-foreground size-4 shrink-0 transition-transform',
                        expanded && 'rotate-180'
                      )}
                    />
                    <span className='min-w-0 flex-1 text-sm'>
                      {formatDateTime(item.createdAt)}
                    </span>
                    <Badge variant='secondary' className='shrink-0 rounded-md px-1.5 font-normal'>
                      {pointCount} 个校准点
                    </Badge>
                    <span className='text-muted-foreground shrink-0 text-xs tabular-nums'>
                      {formatDistance(item.distance)} · {formatTestFrequency(item.testFrequency)}
                    </span>
                  </button>
                  {expanded && item.calibrationData?.points.length ? (
                    <div className='border-border/50 overflow-x-auto border-t px-3 py-2'>
                      <table className='w-full min-w-0 text-xs'>
                        <thead>
                          <tr className='text-muted-foreground'>
                            <th className='py-1 text-right font-medium'>增益偏移</th>
                            <th className='py-1 text-right font-medium'>基础电平</th>
                            <th className='py-1 text-right font-medium'>最终电平</th>
                            <th className='py-1 text-right font-medium'>实测 SPL</th>
                          </tr>
                        </thead>
                        <tbody>
                          {item.calibrationData.points.map((point, index) => (
                            <tr key={index} className='border-border/50 border-b last:border-b-0'>
                              <td className='py-1.5 pr-2 text-right font-mono tabular-nums'>
                                {point.gainOffset != null ? `${point.gainOffset} dB` : '—'}
                              </td>
                              <td className='py-1.5 pr-2 text-right font-mono tabular-nums'>
                                {point.baseLevel != null ? `${point.baseLevel} dBFS` : '—'}
                              </td>
                              <td className='py-1.5 pr-2 text-right font-mono tabular-nums'>
                                {point.finalLevel != null ? `${point.finalLevel} dBFS` : '—'}
                              </td>
                              <td className='py-1.5 pr-2 text-right font-mono tabular-nums'>
                                {point.spl != null ? `${point.spl} dB` : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
