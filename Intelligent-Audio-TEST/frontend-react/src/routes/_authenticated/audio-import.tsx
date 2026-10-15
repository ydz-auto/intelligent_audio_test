import { createFileRoute } from '@tanstack/react-router'

import { PagePlaceholder } from '@/features/placeholder/page-placeholder'

/** 音频管理（导入音频，页面规范归设备域 INT-361 卡） */
export const Route = createFileRoute('/_authenticated/audio-import')({
  component: () => (
    <PagePlaceholder title='音频管理' note='页面随 INT-361 卡落地' />
  ),
})
