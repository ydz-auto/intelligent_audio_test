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

import { ChartBar } from 'lucide-react'
import {
  type ComponentProps,
  type ReactNode,
  createElement,
  Fragment,
} from 'react'

import { cn } from '@/lib/utils'

import { CodeBlock } from './code-block'

type ResponseProps = ComponentProps<'div'> & {
  children: string
  final?: boolean
}

/**
 * Markdown 文档面渲染（08_AI对话页.md §3.4 照 newAPI Response 组件语义；
 * 视觉稿内联实现，覆盖标题/段落/表格/列表/引用/行内格式/代码块/图表占位符）。
 * `[chart:uuid]` 占位符渲染为图表占位卡——数据由后端按 ChartSpec 渲染（§3.6，待后端立项），
 * 前端不执行模型指定脚本。
 */
export function Response({ className, children, ...props }: ResponseProps) {
  return (
    <div
      className={cn(
        'not-prose [&_p]:my-2 [&_ul]:my-2 [&_ol]:my-2 [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-6 [&_ol]:pl-6',
        className
      )}
      {...props}
    >
      {renderBlocks(children)}
    </div>
  )
}

/* ---------------------------------- 块级 ---------------------------------- */

function renderBlocks(markdown: string): ReactNode {
  const lines = markdown.split('\n')
  const blocks: ReactNode[] = []
  let buffer: string[] = []
  let inCode = false
  let codeLang = ''
  let codeLines: string[] = []
  let listType: 'ul' | 'ol' | null = null
  let listItems: string[] = []
  let tableLines: string[] | null = null

  const flushList = () => {
    if (listType && listItems.length > 0) {
      const Tag = listType
      blocks.push(
        createElement(
          Tag,
          { key: `list-${blocks.length}`, className: 'my-2 pl-6 space-y-1' },
          listItems.map((item, index) => (
            <li key={index} className='leading-6'>
              {parseInline(item)}
            </li>
          ))
        )
      )
      listItems = []
      listType = null
    }
  }

  const flushTable = () => {
    if (!tableLines) return
    blocks.push(
      <table
        className='border-border/70 my-3 w-full border-collapse overflow-hidden rounded-lg text-sm'
        key={`table-${blocks.length}`}
      >
        {renderTable(tableLines)}
      </table>
    )
    tableLines = null
  }

  const flushParagraph = () => {
    if (buffer.length > 0) {
      const joined = buffer.join('\n')
      // 图表占位符 [chart:uuid]（§3.6 占位卡；数据待后端按 ChartSpec 渲染）
      const chartMatch = /^\s*\[chart:([^\]]+)\]\s*$/.exec(joined)
      if (chartMatch) {
        blocks.push(
          <div
            className='border-border/70 bg-muted/40 text-muted-foreground my-2 flex min-h-28 flex-col items-center justify-center gap-1.5 rounded-lg border'
            key={`chart-${blocks.length}`}
          >
            <ChartBar className='size-5' aria-hidden='true' />
            <span className='text-xs'>图表占位符 · {chartMatch[1]}</span>
            <span className='text-[11px]'>数据按服务端校验的 ChartSpec 渲染</span>
          </div>
        )
      } else {
        blocks.push(
          <p key={`p-${blocks.length}`} className='leading-6'>
            {parseInline(joined)}
          </p>
        )
      }
      buffer = []
    }
  }

  for (const line of lines) {
    // 代码块
    if (line.trimStart().startsWith('```')) {
      if (!inCode) {
        flushList()
        flushTable()
        flushParagraph()
        inCode = true
        codeLang = line.trim().slice(3).trim()
        codeLines = []
      } else {
        inCode = false
        blocks.push(
          <CodeBlock
            code={codeLines.join('\n')}
            key={`code-${blocks.length}`}
            language={codeLang}
          />
        )
      }
      continue
    }
    if (inCode) {
      codeLines.push(line)
      continue
    }

    // 表格：连续含 | 的行
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      flushList()
      flushParagraph()
      if (tableLines) {
        tableLines.push(line)
      } else {
        tableLines = [line]
      }
      continue
    } else if (tableLines) {
      flushTable()
    }

    const trimmed = line.trim()

    // 标题
    const heading = /^(#{1,3})\s+(.*)$/.exec(trimmed)
    if (heading) {
      flushList()
      flushTable()
      flushParagraph()
      const level = heading[1].length
      const Tag = `h${Math.min(level + 1, 4)}` as 'h2' | 'h3' | 'h4'
      blocks.push(
        createElement(
          Tag,
          {
            key: `h-${blocks.length}`,
            className:
              level === 1
                ? 'mt-4 mb-2 text-base font-semibold'
                : 'mt-3 mb-1.5 text-sm font-semibold',
          },
          parseInline(heading[2])
        )
      )
      continue
    }

    // 引用
    if (trimmed.startsWith('>')) {
      flushList()
      flushTable()
      flushParagraph()
      blocks.push(
        <blockquote
          className='border-border/70 text-muted-foreground my-2 border-l-2 pl-3 text-sm leading-6'
          key={`quote-${blocks.length}`}
        >
          {parseInline(trimmed.slice(1).trim())}
        </blockquote>
      )
      continue
    }

    // 无序列表
    const ulItem = /^[-*+]\s+(.*)$/.exec(trimmed)
    if (ulItem) {
      flushTable()
      flushParagraph()
      if (listType !== 'ul') flushList()
      listType = 'ul'
      listItems.push(ulItem[1])
      continue
    }

    // 有序列表
    const olItem = /^\d+\.\s+(.*)$/.exec(trimmed)
    if (olItem) {
      flushTable()
      flushParagraph()
      if (listType !== 'ol') flushList()
      listType = 'ol'
      listItems.push(olItem[1])
      continue
    }

    // 空行 → 落盘当前块
    if (trimmed === '') {
      flushList()
      flushTable()
      flushParagraph()
      continue
    }

    buffer.push(line)
  }

  if (inCode) {
    blocks.push(
      <CodeBlock code={codeLines.join('\n')} key={`code-${blocks.length}`} />
    )
  }
  flushList()
  flushTable()
  flushParagraph()

  return blocks
}

function renderTable(lines: string[]): ReactNode {
  const rows = lines
    .filter((line) => line.trim() !== '')
    .map((line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|'))
  const header = rows[0]
  const body = rows.slice(1).filter((row) => row.some((cell) => cell.trim() !== '—' && cell.trim() !== '-'))
  const hasHeader = header && header.length > 0

  return (
    <Fragment>
      {hasHeader && (
        <thead>
          <tr className='border-border/70 border-b'>
            {header.map((cell, index) => (
              <th
                className='bg-muted/50 px-3 py-1.5 text-left text-xs font-semibold'
                key={index}
              >
                {parseInline(cell.trim())}
              </th>
            ))}
          </tr>
        </thead>
      )}
      <tbody>
        {body.map((row, rowIndex) => (
          <tr className='border-border/50 border-b last:border-b-0' key={rowIndex}>
            {row.map((cell, cellIndex) => (
              <td className='px-3 py-1.5 text-xs leading-5' key={cellIndex}>
                {parseInline(cell.trim())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </Fragment>
  )
}

/* ---------------------------------- 行内 ---------------------------------- */

function parseInline(text: string): ReactNode {
  const nodes: ReactNode[] = []
  // 1) 行内代码
  const codeSplit = text.split(/(`[^`]+`)/g)
  codeSplit.forEach((part, partIndex) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
      nodes.push(
        <code
          className='bg-muted border-border/60 rounded border px-1 py-px font-mono text-[0.85em]'
          key={`code-${partIndex}`}
        >
          {part.slice(1, -1)}
        </code>
      )
      return
    }
    nodes.push(...parseInlineRich(part, partIndex))
  })
  return nodes
}

/** 富文本：加粗 **x** / 斜体 *x* / 链接 [label](url) */
function parseInlineRich(text: string, keyBase: string | number): ReactNode[] {
  if (!text) return []
  const nodes: ReactNode[] = []
  const regex = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)]+\))/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  let counter = 0

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(
        <Fragment key={`${keyBase}-t-${counter}`}>
          {text.slice(lastIndex, match.index)}
        </Fragment>
      )
    }
    const token = match[0]
    if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(
        <strong className='font-semibold' key={`${keyBase}-b-${counter}`}>
          {token.slice(2, -2)}
        </strong>
      )
    } else if (token.startsWith('*') && token.endsWith('*') && token.length > 2) {
      nodes.push(
        <em key={`${keyBase}-i-${counter}`}>{token.slice(1, -1)}</em>
      )
    } else {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token)
      if (linkMatch) {
        nodes.push(
          <a
            className='text-primary underline underline-offset-2'
            href={linkMatch[2]}
            key={`${keyBase}-a-${counter}`}
            rel='noreferrer'
            target='_blank'
          >
            {linkMatch[1]}
          </a>
        )
      } else {
        nodes.push(token)
      }
    }
    lastIndex = match.index + token.length
    counter += 1
  }

  if (lastIndex < text.length) {
    nodes.push(
      <Fragment key={`${keyBase}-t-end`}>{text.slice(lastIndex)}</Fragment>
    )
  }

  return nodes
}
