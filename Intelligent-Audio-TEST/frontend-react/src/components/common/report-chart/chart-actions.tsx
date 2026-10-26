/**
 * ChartActions 对位（15_报告域.md §3.7：重置缩放 / 图表导出 图片·SVG·PDF）。
 * 共享平台件（INT-430 前置条件：报告域/工作台/benchmark 排行图表统一）。
 * PNG 走 VChart getDataURL → {title}.png 下载；SVG/PDF 走打印导出（§3.7 实测口径：
 * 「SVG/PDF 走序列化/打印导出」——现状打印导出承载；INT-1273 起图表引擎为 Visactor VChart）。
 */
import { Download, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

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
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger
          render={
            <Button variant='ghost' size='sm' className='h-7 gap-1 px-2 text-xs' />
          }
        >
          <Download aria-hidden='true' className='size-3.5' />
          导出
        </DropdownMenuTrigger>
        <DropdownMenuContent align='end' className='w-32'>
          <DropdownMenuItem onClick={onExportPng}>导出 PNG</DropdownMenuItem>
          <DropdownMenuItem onClick={() => window.print()}>导出 SVG</DropdownMenuItem>
          <DropdownMenuItem onClick={() => window.print()}>导出 PDF</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
