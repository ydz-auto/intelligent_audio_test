import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 文档（顶部导航「文档」入口落位） */
export const Route = createFileRoute('/_authenticated/user-guide')({
  component: () => <PagePlaceholder title='文档' note='文档页随后续卡落地' />,
})
