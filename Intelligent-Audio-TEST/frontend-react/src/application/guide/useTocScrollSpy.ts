import { useEffect, useRef, useState } from 'react'

import type { GuideEntry } from '@/domain/models/guide'

/** 滚动追踪阈值：标题顶边 ≤112px 视为当前节（07_文档.md §1.3-5，站头下缘）。 */
const TOP_OFFSET = 112

/**
 * 目录滚动追踪（07_文档.md §7 application/guide/useTocScrollSpy.ts）。
 * rAF 节流 + 顶边 ≤112px 的最后一节为当前；页面触底强制高亮最后一节；
 * 点击条目立即置 active（activeId 由调用方在 onClick 中同步覆盖）。
 */
export function useTocScrollSpy(entries: GuideEntry[]) {
  const articleRef = useRef<HTMLElement | null>(null)
  const [activeId, setActiveId] = useState<string | undefined>(entries[0]?.id)

  useEffect(() => {
    const headings = entries.flatMap((entry) => {
      const heading = articleRef.current?.querySelector<HTMLElement>(
        `[id="${entry.id}"]`
      )
      return heading ? [heading] : []
    })
    let frame = 0
    const updateActiveHeading = () => {
      let current = entries[0]?.id
      for (const heading of headings) {
        if (heading.getBoundingClientRect().top <= TOP_OFFSET) current = heading.id
      }
      const pageHeight = document.documentElement.scrollHeight
      if (
        pageHeight > window.innerHeight &&
        window.scrollY + window.innerHeight >= pageHeight - 2
      ) {
        current = headings.at(-1)?.id ?? current
      }
      setActiveId(current)
    }
    const onScroll = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(updateActiveHeading)
    }
    updateActiveHeading()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [entries])

  return { activeId, articleRef, setActiveId }
}
