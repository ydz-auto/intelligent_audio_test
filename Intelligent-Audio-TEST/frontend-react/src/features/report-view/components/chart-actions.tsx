/**
 * ChartActions 对位（15_报告域.md §3.7：重置缩放 / 导出 PNG）。
 */
import { Download, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'

interface ChartActionsProps {
  onResetZoom: () => void
  onExportPng: () => void
}

export function ChartActions({ onResetZoom, onExportPng }: ChartActionsProps) {
  return (
    <div className='flex items-center gap-1'>
      <Button variant='ghost' size='sm' className='h-7 gap-1 px-2 text-xs' onClick={onResetZoom}>
        <RotateCcw aria-hidden='true' className='size-3.5' />
        重置缩放
      </Button>
      <Button variant='ghost' size='sm' className='h-7 gap-1 px-2 text-xs' onClick={onExportPng}>
        <Download aria-hidden='true' className='size-3.5' />
        导出 PNG
      </Button>
    </div>
  )
}
