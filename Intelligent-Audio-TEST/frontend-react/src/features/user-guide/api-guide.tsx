import { useMemo } from 'react'

import { useApiBaseUrl } from '@/application/status/useApiBaseUrl'
import { API_GUIDE_DOCUMENT } from '@/infrastructure/content/guideAssets'

import { GuideLayout, UserGuideContent } from '.'
import { createGuideDocument } from './guide-document'

/**
 * API 手册内容（07_文档.md §4.3）：构建 guide 后复用 UserGuideContent，
 * 与使用手册共用同一套页面骨架（对位 newAPI ApiGuideContent）。
 */
export function ApiGuideContent() {
  const apiBaseUrl = useApiBaseUrl()
  const guide = useMemo(
    () => createGuideDocument(API_GUIDE_DOCUMENT, '/user-guide-api', apiBaseUrl),
    [apiBaseUrl]
  )
  return <UserGuideContent guide={guide} />
}

/** /user-guide-api API 手册：公开路由，同壳跨路由手册切换。 */
export function ApiGuide() {
  return (
    <GuideLayout>
      <ApiGuideContent />
    </GuideLayout>
  )
}
