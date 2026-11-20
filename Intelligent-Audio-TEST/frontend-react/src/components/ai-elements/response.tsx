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
import { type ComponentProps, useMemo } from 'react'

import { Markdown } from '@/components/ui/markdown'
import { cn } from '@/lib/utils'

type ResponseProps = ComponentProps<'div'> & {
  children: string
  final?: boolean
  /** 思考过程等次要位置用紧凑版排版（小字号灰字、更紧的行距） */
  compact?: boolean
}

/** 图表占位符行：`[chart:uuid]`（数据由后端按 ChartSpec 渲染，前端不执行模型脚本） */
const CHART_PLACEHOLDER_LINE = /^\s*\[chart:([^\]]+)\]\s*$/

type ResponseSegment =
  | { kind: 'markdown'; text: string }
  | { kind: 'chart'; chartId: string }

/**
 * 正文阅读排版（AI 回复主文档面）：
 * 统一走 marked + DOMPurify（§3.13），表格 / 标题 / 分隔线交给标准 Markdown 解析，
 * 不再用手写块解析器（手写版会把表格分隔行 `---` 当正文渲染、标题挤在段落里）。
 */
const BODY_MARKDOWN_CLASS = cn(
  'whitespace-normal text-[0.95rem] leading-7 text-foreground/95 sm:text-[0.975rem]',
  '[&_p]:my-2.5 [&_p]:leading-7',
  '[&_h1]:mt-6 [&_h1]:mb-2 [&_h1]:text-lg [&_h1]:font-semibold',
  '[&_h2]:mt-6 [&_h2]:mb-2 [&_h2]:text-base [&_h2]:font-semibold',
  '[&_h3]:mt-4 [&_h3]:mb-1.5 [&_h3]:text-sm [&_h3]:font-semibold',
  '[&_h4]:mt-3 [&_h4]:mb-1 [&_h4]:text-sm [&_h4]:font-semibold',
  '[&_ul]:my-2.5 [&_ol]:my-2.5 [&_ul]:pl-5 [&_ol]:pl-5',
  '[&_li]:my-1 [&_li]:leading-7',
  '[&_blockquote]:my-3 [&_blockquote]:rounded-r-lg [&_blockquote]:border-l-[3px] [&_blockquote]:border-primary/60 [&_blockquote]:bg-muted/40 [&_blockquote]:py-1.5 [&_blockquote]:pl-3 [&_blockquote]:text-foreground/80',
  '[&_table]:my-3 [&_table]:text-[0.8125rem] [&_table]:leading-6',
  '[&_thead]:bg-muted/50',
  '[&_th]:px-3 [&_th]:py-2 [&_th]:font-semibold [&_th]:whitespace-nowrap [&_th]:text-foreground/70',
  '[&_td]:px-3 [&_td]:py-2 [&_td]:align-top',
  '[&_tbody_tr:nth-child(even)]:bg-muted/20',
  '[&_hr]:my-6 [&_hr]:border-border/60',
  '[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2',
  '[&_code]:text-[0.85em]'
)

/** 思考过程 / 折叠区里的次要正文排版 */
const COMPACT_MARKDOWN_CLASS = cn(
  'whitespace-normal text-xs leading-5 text-muted-foreground',
  '[&_p]:my-1.5 [&_p]:leading-5',
  '[&_h1]:mt-2 [&_h1]:mb-1 [&_h1]:text-sm [&_h1]:font-semibold',
  '[&_h2]:mt-2 [&_h2]:mb-1 [&_h2]:text-sm [&_h2]:font-semibold',
  '[&_h3]:mt-2 [&_h3]:mb-1 [&_h3]:text-xs [&_h3]:font-semibold',
  '[&_h4]:mt-2 [&_h4]:mb-1 [&_h4]:text-xs [&_h4]:font-semibold',
  '[&_ul]:my-1.5 [&_ol]:my-1.5 [&_li]:my-0.5 [&_li]:leading-5',
  '[&_table]:my-2 [&_table]:text-[11px]',
  '[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:pl-3'
)

/** 按 `[chart:uuid]` 行切段：其余文本照常走 Markdown，占位行渲染成图表占位卡 */
function splitChartPlaceholders(markdown: string): ResponseSegment[] {
  const segments: ResponseSegment[] = []
  let buffer: string[] = []

  const flush = () => {
    const text = buffer.join('\n').trim()
    if (text) segments.push({ kind: 'markdown', text })
    buffer = []
  }

  for (const line of markdown.split('\n')) {
    const chartMatch = CHART_PLACEHOLDER_LINE.exec(line)
    if (chartMatch) {
      flush()
      segments.push({ kind: 'chart', chartId: chartMatch[1] })
      continue
    }
    buffer.push(line)
  }
  flush()
  return segments
}

function ChartPlaceholder({ chartId }: { chartId: string }) {
  return (
    <div className='border-border/70 bg-muted/40 text-muted-foreground my-2 flex min-h-28 flex-col items-center justify-center gap-1.5 rounded-lg border'>
      <ChartBar className='size-5' aria-hidden='true' />
      <span className='text-xs'>图表占位符 · {chartId}</span>
      <span className='text-[11px]'>数据按服务端校验的 ChartSpec 渲染</span>
    </div>
  )
}

/**
 * Markdown 文档面渲染（08_AI对话页.md §3.4 照 newAPI Response 组件语义）。
 * 渲染走 `marked` + DOMPurify（`@/components/ui/markdown`），支持标题/段落/表格/列表/
 * 引用/行内格式/代码块与 `[chart:uuid]` 图表占位符。
 */
export function Response({ className, children, compact = false }: ResponseProps) {
  const segments = useMemo(() => splitChartPlaceholders(children), [children])

  return (
    <div className={cn('not-prose', className)}>
      {segments.map((segment, index) =>
        segment.kind === 'chart' ? (
          <ChartPlaceholder chartId={segment.chartId} key={`chart-${index}`} />
        ) : (
          <Markdown
            breaks
            className={compact ? COMPACT_MARKDOWN_CLASS : BODY_MARKDOWN_CLASS}
            key={`markdown-${index}`}
            scrollableTables
          >
            {segment.text}
          </Markdown>
        )
      )}
    </div>
  )
}
