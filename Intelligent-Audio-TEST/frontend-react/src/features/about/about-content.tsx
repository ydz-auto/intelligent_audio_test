import { RichContent } from '@/components/rich-content'

import '@/styles/guide.css'

/**
 * 关于页默认正文（06_关于.md §7 组件树：RichContent(markdown, .guide-prose)）。
 * 构建期 ?raw 资产 content/about.md，站内链接补 router 路径、外链 _blank + noopener。
 */
export function AboutContent({ content }: { content: string }) {
  return <RichContent content={content} className='guide-prose' />
}
