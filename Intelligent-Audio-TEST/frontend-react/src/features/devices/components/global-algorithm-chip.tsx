/**
 * 设备管理页全局算法联动 chip（16_设备域.md §2.2/§3.4：测试设备页签显，播放/API 隐藏）。
 * 只读展示全局算法切换器当前选择；× 清空（本地演示态，提示「清除后将显示全部算法的设备」）。
 * 消费 infrastructure/stores/algorithm-store.ts（INT-344 基座件，本页只读）。
 */
import { X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'

export function DeviceAlgorithmChip() {
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)
  const [cleared, setCleared] = useState(false)
  const { options } = useAlgorithmOptions()

  const algorithm = options.find((a) => a.value === algorithmId)
  if (!algorithm || cleared) return null

  return (
    <Tooltip>
      <TooltipTrigger render={<div />}>
        <Badge variant='secondary' className='h-7 gap-1 rounded-md px-2.5'>
          <span className='text-muted-foreground'>算法：</span>
          <span className='font-medium'>{algorithm.name}</span>
          <Button
            variant='ghost'
            size='icon-xs'
            aria-label='清除全局算法'
            onClick={() => {
              setCleared(true)
              toast.success('已清除全局算法，显示全部算法的设备')
            }}
          >
            <X aria-hidden='true' />
          </Button>
        </Badge>
      </TooltipTrigger>
      <TooltipContent>由右上角全局算法切换器控制，点击 × 显示全部算法的设备</TooltipContent>
    </Tooltip>
  )
}
