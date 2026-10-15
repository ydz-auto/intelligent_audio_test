import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 个人中心（归 INT-358 卡；顶栏头像下拉「个人中心」入口落位） */
export const Route = createFileRoute('/_authenticated/profile')({
  component: () => (
    <PagePlaceholder title='个人中心' note='页面随 INT-358 卡落地' />
  ),
})
