/**
 * 全局算法联动 chip（11_用例域.md §3.4，用例页变体）：
 * 只读展示全局算法切换器当前选择；× 清空（本地演示态，提示「清除后将显示全部算法的用例」）。
 * store 消费见 infrastructure/stores/algorithm-store.ts（INT-344 基座件，本页只读）。
 */
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { MOCK_ALGORITHMS } from '@/domain/models/algorithm'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

export function TestCasesAlgorithmChip() {
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)
  const [cleared, setCleared] = useState(false)

  const algorithm = MOCK_ALGORITHMS.find((a) => a.id === algorithmId)
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
              toast.success('已清除全局算法，显示全部算法的用例')
            }}
          >
            <X aria-hidden='true' />
          </Button>
        </Badge>
      </TooltipTrigger>
      <TooltipContent>由右上角全局算法切换器控制，点击 × 显示全部算法的用例</TooltipContent>
    </Tooltip>
  )
}
