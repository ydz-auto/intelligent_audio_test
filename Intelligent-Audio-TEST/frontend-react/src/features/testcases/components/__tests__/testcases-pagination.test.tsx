/**
 * 用例分页脚注测试（11_用例域.md §3.8）：总数文案、页码边界、by-tag 标签聚合页码指示。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'

import { PageFooterProvider } from '@/components/layout/components/page-footer'
import { TestCasesPagination } from '@/features/testcases/components/testcases-pagination'

function Fixture({ total, tagPages }: { total: number; tagPages?: number }) {
  const [footerContainer, setFooterContainer] = useState<HTMLDivElement | null>(
    null
  )
  return (
    <>
      <PageFooterProvider container={footerContainer}>
        <TestCasesPagination total={total} tagPage={1} tagPages={tagPages} />
      </PageFooterProvider>
      <div ref={setFooterContainer} data-testid='footer' />
    </>
  )
}

describe('TestCasesPagination', () => {
  it('渲染总数文案与当前区间', async () => {
    render(<Fixture total={45} />)
    expect(await screen.findByText('共 45 条')).toBeInTheDocument()
    expect(screen.getByText('1–10 / 45')).toBeInTheDocument()
  })

  it('首屏首页/上一页禁用，点击下一页前进', async () => {
    const user = userEvent.setup()
    render(<Fixture total={45} />)
    await screen.findByText('共 45 条')
    expect(screen.getByRole('button', { name: '首页' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '下一页' }))
    expect(screen.getByText('11–20 / 45')).toBeInTheDocument()
  })

  it('by-tag 视图显示标签聚合页码指示', async () => {
    render(<Fixture total={45} tagPages={5} />)
    await screen.findByText('共 45 条')
    expect(screen.getByText('标签 1/5')).toBeInTheDocument()
  })
})
