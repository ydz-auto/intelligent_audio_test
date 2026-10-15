import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 排行榜（benchmark 排行，归 INT-359 卡；顶部导航直达不进侧栏） */
export const Route = createFileRoute('/_authenticated/rankings')({
  component: () => (
    <PagePlaceholder title='排行榜' note='benchmark 排行随 INT-359 卡落地' />
  ),
})
