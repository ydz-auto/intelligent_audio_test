/**
 * 任务域组件测试——TasksPagination（09_任务域.md §3.11）：总数文案、
 * 首页/上一页/下一页/末页边界禁用、页码翻页与每页条数切换。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'

import { PageFooterProvider } from '@/components/layout/components/page-footer'
import { TasksPagination } from '@/features/tasks/components/tasks-pagination'

/** 对位 SectionPageLayout：footer 容器经 ref 回调写回 state 后 Portal 落位 */
function Fixture({ total }: { total: number }) {
  const [footerContainer, setFooterContainer] = useState<HTMLDivElement | null>(
    null
  )
  return (
    <>
      <PageFooterProvider container={footerContainer}>
        <TasksPagination total={total} />
      </PageFooterProvider>
      <div ref={setFooterContainer} data-testid='footer' />
    </>
  )
}

describe('TasksPagination', () => {
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
    expect(screen.getByRole('button', { name: '上一页' })).toBeEnabled()
  })

  it('切换每页条数回到第一页并更新区间', async () => {
    const user = userEvent.setup()
    render(<Fixture total={45} />)
    await screen.findByText('共 45 条')
    await user.click(screen.getByRole('combobox', { name: '每页条数' }))
    await user.click(await screen.findByRole('option', { name: '20' }))
    expect(screen.getByText('1–20 / 45')).toBeInTheDocument()
  })
})
