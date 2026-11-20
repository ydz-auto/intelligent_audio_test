/**
 * 正文 Markdown 渲染（AI 回复主文档面）：
 * 表格走标准 GFM 解析（分隔行 `---` 不再当正文渲染）、标题独立成块、
 * `[chart:uuid]` 仍渲染为图表占位卡。
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Response } from '../response'

describe('Response 正文渲染', () => {
  it('标题独立成块、表格分隔行不渲染成正文', () => {
    const markdown = [
      '## 结论',
      '',
      '| 项 | 值 |',
      '| --- | --- |',
      '| 报告 ID | 420 |',
      '| 关联任务 | 407 |',
    ].join('\n')

    render(<Response>{markdown}</Response>)

    expect(screen.getByRole('heading', { level: 2, name: '结论' })).toBeInTheDocument()
    const table = screen.getByRole('table')
    // 表头一行 + 两行数据；分隔行被解析掉，不当正文/表格行出现
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(screen.queryByText('---')).not.toBeInTheDocument()
    expect(within(table).getByText('报告 ID')).toBeInTheDocument()
  })

  it('[chart:uuid] 占位符渲染为图表占位卡，不混进正文段落', () => {
    render(<Response>{'前文\n\n[chart:chart-1]\n\n后文'}</Response>)

    expect(screen.getByText(/图表占位符 · chart-1/)).toBeInTheDocument()
    expect(screen.getByText('前文')).toBeInTheDocument()
    expect(screen.getByText('后文')).toBeInTheDocument()
  })
})
