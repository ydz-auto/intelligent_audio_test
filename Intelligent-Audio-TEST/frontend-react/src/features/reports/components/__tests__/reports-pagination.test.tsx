/**
 * 报告域组件测试——ReportsPagination（对位 newAPI DataTablePagination 语义，规范 §3.9）：
 * 空态不渲染 / 页导航 / 每页条数 Select / 边界禁用。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReportsPagination } from '@/features/reports/components/reports-pagination'

function Fixture(props: {
  page?: number
  pageSize?: number
  total?: number
  pages?: number
}) {
  return (
    <ReportsPagination
      page={props.page ?? 1}
      pageSize={props.pageSize ?? 20}
      total={props.total ?? 45}
      pages={props.pages ?? 3}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
    />
  )
}

describe('ReportsPagination', () => {
  it('total=0 时整体不渲染（空态）', () => {
    const { container } = render(<Fixture total={0} pages={1} />)
    expect(container.firstChild).toBeNull()
  })

  it('渲染总数文案与页码导航', () => {
    render(<Fixture />)
    expect(screen.getByText(/个报告/)).toBeInTheDocument()
    expect(screen.getByText('45')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '分页' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled()
  })

  it('点击下一页触发 onPageChange(2)，末页禁用下一页', async () => {
    const user = userEvent.setup()
    const onPageChange = vi.fn()
    render(
      <ReportsPagination
        page={3}
        pageSize={20}
        total={45}
        pages={3}
        onPageChange={onPageChange}
        onPageSizeChange={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '上一页' }))
    expect(onPageChange).toHaveBeenCalledWith(2)
  })

  it('页码按钮标记 aria-current=page', async () => {
    render(<Fixture page={2} />)
    const pageButton = screen.getByRole('button', { name: '2' })
    expect(pageButton).toHaveAttribute('aria-current', 'page')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '3' }))
  })

  it('切换每页条数触发 onPageSizeChange', async () => {
    const user = userEvent.setup()
    const onPageSizeChange = vi.fn()
    render(
      <ReportsPagination
        page={1}
        pageSize={20}
        total={45}
        pages={3}
        onPageChange={vi.fn()}
        onPageSizeChange={onPageSizeChange}
      />
    )
    await user.click(screen.getByRole('combobox', { name: '每页条数' }))
    await user.click(await screen.findByRole('option', { name: '30 / 页' }))
    expect(onPageSizeChange).toHaveBeenCalledWith(30)
  })
})
