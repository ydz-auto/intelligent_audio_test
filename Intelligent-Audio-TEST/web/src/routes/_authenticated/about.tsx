import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 关于（顶部导航「关于」入口落位） */
export const Route = createFileRoute('/_authenticated/about')({
  component: () => <PagePlaceholder title='关于' note='关于页随后续卡落地' />,
})
