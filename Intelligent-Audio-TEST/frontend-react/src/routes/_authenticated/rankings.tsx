import { createFileRoute } from '@tanstack/react-router'

import { AlgorithmCardGrid } from '@/components/algorithm-card-grid'
import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/**
 * 排行榜（benchmark 排行，归 INT-359 卡；顶部导航直达不进侧栏）。
 * INT-486 口径：本页算法切换经「算法卡片网格」（INT-442——页内大卡，不用右上角切换器）；
 * 榜单主体随 INT-359 卡落地。
 */
export const Route = createFileRoute('/_authenticated/rankings')({
  component: () => (
    <div className='flex h-full flex-col gap-4 overflow-y-auto p-4 sm:p-6'>
      <AlgorithmCardGrid title='选择算法' />
      <div className='min-h-0 flex-1'>
        <PagePlaceholder title='排行榜' note='benchmark 排行随 INT-359 卡落地' />
      </div>
    </div>
  ),
})
