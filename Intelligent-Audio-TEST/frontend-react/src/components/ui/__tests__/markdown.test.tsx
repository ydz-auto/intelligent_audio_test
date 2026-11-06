/**
 * Markdown 公式按需加载（INT-1274）：含公式的正文在 katex 动态加载完成后渲染成
 * KaTeX 标记；不含公式的正文不碰 katex，也不会出现占位残留。
 */
import { render, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Markdown } from '@/components/ui/markdown'

describe('Markdown 公式渲染', () => {
  it('含 $$ 公式的正文在 katex 加载完成后渲染出 KaTeX 标记', async () => {
    const { container } = render(<Markdown>{'质能方程 $$E = mc^2$$ 成立'}</Markdown>)

    await waitFor(() => {
      expect(container.querySelector('.katex')).not.toBeNull()
    })
    expect(container.querySelector('.markdown-math-pending')).toBeNull()
  })

  it('无公式正文只渲染纯文本，不产生 KaTeX 标记', () => {
    const { container } = render(<Markdown>{'## 标题\n\n普通段落正文'}</Markdown>)

    expect(container.querySelector('.katex')).toBeNull()
    expect(container.textContent).toContain('普通段落正文')
  })
})
