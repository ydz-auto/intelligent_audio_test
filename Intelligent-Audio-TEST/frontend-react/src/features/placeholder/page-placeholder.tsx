import { Construction } from 'lucide-react'

/**
 * 页面占位稿（可视稿通用）：
 * 基座卡只出导航壳与路由骨架，各业务页本体归对应功能卡
 * （dashboard→INT-346、任务→INT-354、端到端/API→INT-355、用例→INT-356 等）。
 */
export function PagePlaceholder({
  title,
  note,
}: {
  title: string
  note?: string
}) {
  return (
    <div className='flex h-full min-h-[60vh] flex-col items-center justify-center gap-3 p-8 text-center'>
      <div className='bg-muted text-muted-foreground flex size-12 items-center justify-center rounded-xl'>
        <Construction aria-hidden='true' className='size-6' />
      </div>
      <h1 className='text-lg font-semibold'>{title}</h1>
      <p className='text-muted-foreground max-w-md text-sm'>
        {note ?? '页面本体随对应功能卡落地'}
      </p>
    </div>
  )
}
