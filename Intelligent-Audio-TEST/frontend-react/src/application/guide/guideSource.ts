import { lexer } from 'marked'

import type { GuideEntry } from '@/domain/models/guide'

/** 锚点解码：非法 `%` 转义时原样返回，避免 URIError 使目录提取崩溃。 */
function safeDecodeURIComponent(encoded: string): string {
  try {
    return decodeURIComponent(encoded)
  } catch {
    return encoded
  }
}

/** 手册正文 → 目录条目（07_文档.md §7 application/guide/guideSource.ts）。
 * 目录提取正则照搬 newAPI guide-document.tsx：`## 目录` 段 + `- [标题](#锚点)` 列表；
 * 每条目按全文标题层级决定是否三级以下缩进（depth>3 → 缩进展示）。 */
export function extractTocEntries(content: string): GuideEntry[] {
  const directory =
    content.match(/^## [^\n]+\r?\n(?=\s*- \[)[\s\S]*?(?=^## )/m)?.[0] ?? ''
  const headingDepths = new Map<string, number>()
  for (const token of lexer(content)) {
    if (token.type === 'heading') headingDepths.set(token.text, token.depth)
  }
  return Array.from(
    directory.matchAll(/^- \[([^\]]+)\]\(#([^)]+)\)/gm),
    (match) => ({
      title: match[1],
      id: safeDecodeURIComponent(match[2]),
      nested: (headingDepths.get(match[1]) ?? 2) > 3,
    })
  )
}

/** 占位符替换：{{API_BASE_URL}} → `${apiBaseUrl}/v1`、{{API_ROOT}} → apiBaseUrl（07_文档.md §1.3-4）。 */
export function replaceGuidePlaceholders(
  content: string,
  apiBaseUrl: string
): string {
  return content
    .replaceAll('{{API_BASE_URL}}', `${apiBaseUrl}/v1`)
    .replaceAll('{{API_ROOT}}', apiBaseUrl)
}

/** 正文链接改写：仓库内相对链接换成站内目标（07_文档.md §1.3-3）。 */
export function rewriteGuideLinks(guideBody: string): string {
  return guideBody
    .replaceAll('(./README.md)', '(#目录)')
    .replaceAll('(./about.md)', '(/about)')
    .replaceAll('(./api-guide.md)', '(/user-guide-api)')
    .replaceAll('(./user-guide.md)', '(/user-guide)')
}

/**
 * 手册正文加工总入口：占位符替换 → 目录段提取/剥离 → 链接改写。
 * 返回目录条目与正文（markup 组装在 interfaces 层 createGuideDocument）。
 */
export function buildGuideSource(
  content: string,
  apiBaseUrl: string
): { entries: GuideEntry[]; body: string } {
  const replaced = replaceGuidePlaceholders(content, apiBaseUrl)
  const entries = extractTocEntries(replaced)
  const directory =
    replaced.match(/^## [^\n]+\r?\n(?=\s*- \[)[\s\S]*?(?=^## )/m)?.[0] ?? ''
  const body = rewriteGuideLinks(replaced.replace(directory, ''))
  return { entries, body }
}
