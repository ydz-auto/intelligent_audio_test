import { useMemo } from 'react'

import { useApiBaseUrl } from '@/application/status/useApiBaseUrl'
import { INTEGRATION_GUIDE_DOCUMENT } from '@/infrastructure/content/guideAssets'

import { GuideLayout, UserGuideContent } from '.'
import { createGuideDocument } from './guide-document'

/**
 * 接入指南内容（07_文档.md §3.1 同壳复用）：构建 guide 后复用 UserGuideContent，
 * 与使用手册 / API 手册共用同一套页面骨架（对位 newAPI ApiGuideContent 模式）。
 * 三章：Realtime API / 普通 HTTP API / 实体设备 E2E（源稿 doc/接入指南_*.md，INT-1291 产出）。
 */
export function IntegrationGuideContent() {
  const apiBaseUrl = useApiBaseUrl()
  const guide = useMemo(
    () =>
      createGuideDocument(
        INTEGRATION_GUIDE_DOCUMENT,
        '/user-guide-integration',
        apiBaseUrl
      ),
    [apiBaseUrl]
  )
  return <UserGuideContent guide={guide} />
}

/** /user-guide-integration 接入指南：公开路由，同壳跨路由手册切换。 */
export function IntegrationGuide() {
  return (
    <GuideLayout>
      <IntegrationGuideContent />
    </GuideLayout>
  )
}
