/**
 * 候选加载慢提示（INT-1280）：候选查询超过阈值仍无数据时替代无限骨架屏，
 * 给出可重试反馈——继续等待或「重新加载」（取消在途请求重新发起）。
 */
import { Clock, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function SlowCandidatesNotice({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      data-testid='slow-candidates-notice'
      className='flex flex-col items-center gap-2 py-10 text-center'
    >
      <Clock aria-hidden='true' className='text-muted-foreground size-6' />
      <p className='text-muted-foreground text-sm'>候选数据较多或后端繁忙，加载较慢</p>
      <p className='text-muted-foreground/70 text-xs'>
        仍在加载中，可继续等待或重新加载
      </p>
      <Button
        variant='outline'
        size='sm'
        className='mt-1 gap-1.5'
        onClick={onRetry}
      >
        <RefreshCw aria-hidden='true' className='size-3.5' />
        重新加载
      </Button>
    </div>
  )
}
