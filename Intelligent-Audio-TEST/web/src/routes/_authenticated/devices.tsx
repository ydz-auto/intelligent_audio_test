import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 设备管理（设备/SPL 映射域，归 INT-361 卡） */
export const Route = createFileRoute('/_authenticated/devices')({
  component: () => (
    <PagePlaceholder title='设备管理' note='设备/SPL 映射域随 INT-361 卡落地' />
  ),
})
