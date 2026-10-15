/*
Copyright (C) 2023-2026 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/
'use client'

import { ArrowDown } from 'lucide-react'
import {
  createContext,
  type ComponentProps,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type ConversationContextValue = {
  isAtBottom: boolean
  scrollToBottom: () => void
  registerContent: (el: HTMLDivElement | null) => void
  notifyScroll: (el: HTMLDivElement) => void
}

const ConversationContext = createContext<ConversationContextValue | null>(null)

function useConversationContext(): ConversationContextValue {
  const context = useContext(ConversationContext)
  if (!context) {
    throw new Error('Conversation components must be used within Conversation')
  }
  return context
}

export type ConversationProps = ComponentProps<'div'>

/**
 * 会话粘底滚动容器（08_AI对话页.md §1.1 照 newAPI Conversation 语义）：
 * 外层 relative 裁剪，内层滚动；用户停留在底部时新消息自动粘底，否则保持阅读位置。
 */
export const Conversation = ({
  className,
  children,
  ...props
}: ConversationProps) => {
  const [isAtBottom, setIsAtBottom] = useState(true)
  const contentRef = useRef<HTMLDivElement | null>(null)
  const stickRef = useRef(true)

  const notifyScroll = useCallback((el: HTMLDivElement) => {
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    const atBottom = distance < 8
    stickRef.current = atBottom
    setIsAtBottom(atBottom)
  }, [])

  const scrollToBottom = useCallback(() => {
    stickRef.current = true
    setIsAtBottom(true)
    const el = contentRef.current
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  }, [])

  const registerContent = useCallback((el: HTMLDivElement | null) => {
    contentRef.current = el
  }, [])

  return (
    <ConversationContext.Provider
      value={{ isAtBottom, scrollToBottom, registerContent, notifyScroll }}
    >
      <div
        className={cn('relative min-h-0 flex-1 overflow-hidden', className)}
        {...props}
      >
        {children}
      </div>
    </ConversationContext.Provider>
  )
}

export type ConversationContentProps = ComponentProps<'div'>

export const ConversationContent = ({
  className,
  children,
  ...props
}: ConversationContentProps) => {
  const { registerContent, notifyScroll } = useConversationContext()
  const localRef = useRef<HTMLDivElement | null>(null)
  const stickRef = useRef(true)

  const refCallback = useCallback(
    (el: HTMLDivElement | null) => {
      localRef.current = el
      registerContent(el)
    },
    [registerContent]
  )

  // 新内容到达：停留在底部时自动粘底（初始 smooth 语义）
  useEffect(() => {
    const el = localRef.current
    if (el && stickRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [children])

  return (
    <div
      ref={refCallback}
      className={cn('min-h-0 flex-1 overflow-y-auto', className)}
      onScroll={(event) => {
        const el = event.currentTarget
        const distance = el.scrollHeight - el.scrollTop - el.clientHeight
        stickRef.current = distance < 8
        notifyScroll(el)
      }}
      {...props}
    >
      {children}
    </div>
  )
}

export type ConversationScrollButtonProps = ComponentProps<typeof Button>

export const ConversationScrollButton = ({
  className,
  ...props
}: ConversationScrollButtonProps) => {
  const { isAtBottom, scrollToBottom } = useConversationContext()

  return (
    !isAtBottom && (
      <Button
        className={cn(
          'absolute bottom-4 left-[50%] translate-x-[-50%]',
          className
        )}
        onClick={scrollToBottom}
        size='icon'
        type='button'
        variant='outline'
        aria-label='回到底部'
        {...props}
      >
        <ArrowDown className='size-4' aria-hidden='true' />
      </Button>
    )
  )
}
