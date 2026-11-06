import type { ReactNode } from 'react'

import { buildGuideSource } from '@/application/guide/guideSource'
import { RichContent } from '@/components/rich-content'
import type { GuideDocument, GuidePath } from '@/domain/models/guide'

import '@/styles/guide.css'

import { GuideCodeBlock } from './guide-code-block'

function renderGuideCodeBlock(code: string, language: string): ReactNode {
  return <GuideCodeBlock code={code} language={language} />
}

/**
 * 手册文档组装（07_文档.md §7 interfaces/features/user-guide/guide-document.tsx）。
 * 占位符替换 → 目录提取/剥离 → 链接改写 → RichContent 渲染
 * （headingAnchors 标题锚点 + scrollableTables 表格滚动 + renderCodeBlock shiki 高亮）。
 */
export function createGuideDocument(
  content: string,
  path: GuidePath,
  apiBaseUrl: string
): GuideDocument {
  const { entries, body } = buildGuideSource(content, apiBaseUrl)

  const markup = (
    <RichContent
      headingAnchors
      scrollableTables
      renderCodeBlock={renderGuideCodeBlock}
      content={body}
      className='guide-prose'
    />
  )

  return { entries, markup, path }
}
