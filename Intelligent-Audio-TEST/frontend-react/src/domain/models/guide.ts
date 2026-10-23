import type { ReactNode } from 'react'

/**
 * 文档手册目录条目（07_文档.md §7 domain/model/guide.ts）。
 * 对照 newAPI guide-document 的 entries 结构：标题 + 锚点 id + 三级以下缩进标记。
 */
export type GuideEntry = {
  title: string
  /** 正文标题锚点 id（渲染时 h1-h6 生成 slug，markdown.tsx:744-758） */
  id: string
  /** 三级及以下标题缩进展示 */
  nested: boolean
}

/** 手册路径（三本手册共用同一套页面骨架，仅内容不同） */
export type GuidePath = '/user-guide' | '/user-guide-api' | '/user-guide-integration'

/**
 * 组装完成的手册文档：目录条目 + 已渲染的正文 markup。
 * markup 由 interfaces 层 createGuideDocument 组装（07_文档.md §3.1 两手册共用 UserGuideContent）。
 */
export type GuideDocument = {
  entries: GuideEntry[]
  markup: ReactNode
  path: GuidePath
}
