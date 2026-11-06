import type { ReactNode } from 'react'

import { useAboutContent } from '@/application/about/useAboutContent'
import { RichContent } from '@/components/rich-content'
import { PublicFooter, PublicHeader } from '@/features/home/components/public-shell'

import { AboutContent } from './about-content'
import { AboutLinks } from './about-links'
import { AboutStatusCard } from './about-status-card'

/**
 * 关于页（06_关于.md §3.1/§3.2）：公开路由，五角色+未登录同一视图。
 * 公共壳消费首页门户的 PublicHeader/PublicFooter（页本级最小壳）。
 * TODO(导航栏卡 INT-344): 共享 PublicLayout/public-header/footer 落地后，
 * 本页改直用共享壳，删除本文件的 AboutLayout 组装。
 */
function AboutLayout({
  showMainContainer = true,
  children,
}: {
  showMainContainer?: boolean
  children: ReactNode
}) {
  return (
    <div className='bg-background min-h-svh'>
      <PublicHeader />
      {showMainContainer !== false ? (
        <main className='container px-4 py-6 pt-20'>{children}</main>
      ) : (
        children
      )}
      <PublicFooter />
    </div>
  )
}

export function About() {
  const content = useAboutContent()

  // URL 态：iframe 沙箱整页嵌入（showMainContainer=false，06_关于.md §1.3 分支②）
  if (content.status === 'url') {
    return (
      <AboutLayout showMainContainer={false}>
        <iframe
          src={content.url}
          className='h-[calc(100vh-3.5rem)] w-full border-0'
          title='关于'
          sandbox='allow-forms allow-popups allow-popups-to-escape-sandbox allow-scripts'
        />
      </AboutLayout>
    )
  }

  // HTML 态：RichContent mode='html' 隔离沙箱整页渲染（分支③）
  if (content.status === 'html') {
    return (
      <AboutLayout showMainContainer={false}>
        <RichContent
          mode='html'
          htmlVariant='isolated'
          content={content.html}
          className='prose-neutral dark:prose-invert max-w-none'
        />
      </AboutLayout>
    )
  }

  // 默认 md 分支：单列正文 + 状态卡 + 链接卡（分支④/空态回退默认）
  return (
    <AboutLayout>
      <div className='mx-auto max-w-4xl space-y-8 py-8'>
        <AboutContent content={content.content} />
        <AboutStatusCard />
        <AboutLinks />
      </div>
    </AboutLayout>
  )
}
