/**
 * 手册正文加工纯函数测试（INT-512，07_文档.md §7 application/guide/guideSource.ts）：
 * 目录提取正则 / 三级以下缩进 / 占位符替换 / 站内链接改写 / 目录段剥离。
 */
import { describe, expect, it } from 'vitest'

import {
  buildGuideSource,
  extractTocEntries,
  replaceGuidePlaceholders,
  rewriteGuideLinks,
} from '../guideSource'

const SAMPLE = `# 平台使用手册

说明文字。

## 目录

- [快速开始](#快速开始)
- [准备工作](#准备工作)
- [嵌套小节](#嵌套小节)
- [深层小节](#深层小节)

## 快速开始

正文。

### 嵌套小节

三级小节（不缩进）。

#### 深层小节

四级小节（缩进）。
`

describe('guideSource', () => {
  it('extractTocEntries 解析目录条目，h3 不缩进、h4 及以上缩进', () => {
    const entries = extractTocEntries(SAMPLE)
    expect(entries).toHaveLength(4)
    expect(entries[0]).toEqual({ title: '快速开始', id: '快速开始', nested: false })
    expect(entries[2]).toEqual({ title: '嵌套小节', id: '嵌套小节', nested: false })
    expect(entries[3]).toEqual({ title: '深层小节', id: '深层小节', nested: true })
  })

  it('extractTocEntries 对锚点做 decodeURIComponent', () => {
    const encoded = SAMPLE.replace(
      '(#嵌套小节)',
      '(#%E5%B5%8C%E5%A5%97%E5%B0%8F%E8%8A%82)'
    )
    const entries = extractTocEntries(encoded)
    expect(entries[2].id).toBe('嵌套小节')
  })

  it('replaceGuidePlaceholders 展开 API_BASE_URL 与 API_ROOT', () => {
    const replaced = replaceGuidePlaceholders(
      'Base={{API_BASE_URL}} Root={{API_ROOT}}',
      'https://host/api'
    )
    expect(replaced).toBe('Base=https://host/api/v1 Root=https://host/api')
  })

  it('rewriteGuideLinks 将仓库相对链接改写为站内路由', () => {
    const body = rewriteGuideLinks(
      '[README](./README.md) [about](./about.md) [api](./api-guide.md) [ug](./user-guide.md)'
    )
    expect(body).toContain('(#目录)')
    expect(body).toContain('(/about)')
    expect(body).toContain('(/user-guide-api)')
    expect(body).toContain('(/user-guide)')
  })

  it('buildGuideSource 剥离目录段并保留正文与条目', () => {
    const { entries, body } = buildGuideSource(SAMPLE, 'https://host/api')
    expect(entries).toHaveLength(4)
    expect(body).toContain('## 快速开始')
    expect(body).not.toContain('## 目录')
    expect(body).not.toContain('- [快速开始](#快速开始)')
  })
})
