import { Link } from '@tanstack/react-router'
import { BookOpen, ChevronDown, Code2, Plug } from 'lucide-react'
import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'

import { useTocScrollSpy } from '@/application/guide/useTocScrollSpy'
import { useApiBaseUrl } from '@/application/status/useApiBaseUrl'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import type { GuideDocument } from '@/domain/models/guide'
import { PublicFooter, PublicHeader } from '@/features/home/components/public-shell'
import { useMediaQuery } from '@/hooks/use-media-query'
import { USER_GUIDE_DOCUMENT } from '@/infrastructure/content/guideAssets'
import { cn } from '@/lib/utils'

import { createGuideDocument } from './guide-document'

/**
 * 文档页公共壳（07_文档.md §3.1 对位 newAPI PublicLayout，页本级最小壳）。
 * TODO(导航栏卡 INT-344): 共享 PublicLayout/public-header/footer 落地后，
 * 本页改直用共享壳（同关于页 AboutLayout 口径），删除本文件的 GuideLayout 组装。
 */
export function GuideLayout({ children }: { children: ReactNode }) {
  return (
    <div className='bg-background min-h-svh'>
      <PublicHeader />
      <main className='container px-4 py-6 pt-20 md:px-4'>{children}</main>
      <PublicFooter />
    </div>
  )
}

/**
 * 手册正文骨架（07_文档.md §3.1）：左目录 + 右正文双栏，桌面目录吸附、移动端折叠。
 * 两本手册共用本组件，仅 guide 内容不同（对位 newAPI UserGuideContent）。
 */
export function UserGuideContent(props: { guide?: GuideDocument }) {
  const apiBaseUrl = useApiBaseUrl()
  const guide = useMemo(
    () =>
      props.guide ??
      createGuideDocument(USER_GUIDE_DOCUMENT, '/user-guide', apiBaseUrl),
    [props.guide, apiBaseUrl]
  )
  const entries = guide.entries
  const isDesktop = useMediaQuery('(min-width: 1024px)')
  const [menuOpen, setMenuOpen] = useState(false)
  const { activeId, articleRef, setActiveId } = useTocScrollSpy(entries)

  return (
    <div className='mx-auto grid max-w-[76rem] gap-8 py-6 lg:grid-cols-[15rem_minmax(0,48rem)] lg:justify-center lg:gap-14 lg:py-10'>
      <aside
        id='目录'
        className='scroll-mt-24 self-start rounded-xl border p-3 lg:sticky lg:top-24 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto lg:rounded-none lg:border-0 lg:p-0 lg:pr-2'
      >
        <nav
          aria-label='用户手册'
          className='mb-6 flex flex-col gap-1.5 border-b pb-5'
        >
          <Link
            to='/user-guide'
            aria-current={guide.path === '/user-guide' ? 'page' : undefined}
            className={buttonVariants({
              variant: guide.path === '/user-guide' ? 'secondary' : 'ghost',
              size: 'sm',
              className:
                'h-auto min-h-10 justify-start px-3 py-2 text-sm whitespace-normal',
            })}
          >
            <BookOpen aria-hidden className='size-4 shrink-0' />
            使用手册
          </Link>
          <Link
            to='/user-guide-api'
            aria-current={guide.path === '/user-guide-api' ? 'page' : undefined}
            className={buttonVariants({
              variant:
                guide.path === '/user-guide-api' ? 'secondary' : 'ghost',
              size: 'sm',
              className:
                'h-auto min-h-10 justify-start px-3 py-2 text-sm whitespace-normal',
            })}
          >
            <Code2 aria-hidden className='size-4 shrink-0' />
            API 手册
          </Link>
          <Link
            to='/user-guide-integration'
            aria-current={
              guide.path === '/user-guide-integration' ? 'page' : undefined
            }
            className={buttonVariants({
              variant:
                guide.path === '/user-guide-integration' ? 'secondary' : 'ghost',
              size: 'sm',
              className:
                'h-auto min-h-10 justify-start px-3 py-2 text-sm whitespace-normal',
            })}
          >
            <Plug aria-hidden className='size-4 shrink-0' />
            接入指南
          </Link>
        </nav>
        <h2 className='text-muted-foreground mb-3 hidden px-3 text-xs font-semibold tracking-wide lg:block'>
          目录
        </h2>
        <Collapsible open={isDesktop || menuOpen} onOpenChange={setMenuOpen}>
          <CollapsibleTrigger
            render={
              <Button
                variant='ghost'
                className='group w-full justify-between lg:hidden'
              />
            }
          >
            <span className='flex items-center gap-2'>
              <BookOpen aria-hidden className='size-4' />
              目录
            </span>
            <ChevronDown
              aria-hidden
              className='size-4 transition-transform group-aria-expanded:rotate-180'
            />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <nav aria-label='目录'>
              <ul className='space-y-0.5'>
                {entries.map((entry) => (
                  <li key={entry.id}>
                    <a
                      href={`#${encodeURIComponent(entry.id)}`}
                      aria-current={
                        activeId === entry.id ? 'location' : undefined
                      }
                      className={cn(
                        'text-muted-foreground hover:bg-muted/60 hover:text-foreground focus-visible:ring-ring block rounded-r-md border-l-2 border-transparent px-3 py-2 text-[13px] leading-5 break-words transition-colors outline-none focus-visible:ring-2',
                        entry.nested && 'pl-6 text-xs',
                        activeId === entry.id &&
                          'border-primary bg-primary/5 text-primary font-medium'
                      )}
                      onClick={() => {
                        setActiveId(entry.id)
                        if (!isDesktop) {
                          setMenuOpen(false)
                          const heading =
                            articleRef.current?.querySelector<HTMLElement>(
                              `[id="${entry.id}"]`
                            )
                          if (heading) {
                            heading.tabIndex = -1
                            heading.focus({ preventScroll: true })
                          }
                        }
                      }}
                    >
                      {entry.title}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </CollapsibleContent>
        </Collapsible>
      </aside>
      <article ref={articleRef} className='min-w-0'>
        {guide.markup}
      </article>
    </div>
  )
}

/** /user-guide 使用手册（07_文档.md §3.1）：公开路由，公共壳 + 使用手册正文。 */
export function UserGuide() {
  return (
    <GuideLayout>
      <UserGuideContent />
    </GuideLayout>
  )
}
