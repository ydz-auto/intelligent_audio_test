/**
 * 报告域组件测试——ReportTabs 受控双页签（规范 §3.3）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReportTabs } from '@/features/reports/components/report-tabs'

describe('ReportTabs', () => {
  it('渲染测试报告/历史报告两个页签', () => {
    render(<ReportTabs value='test' onChange={vi.fn()} />)
    expect(screen.getByRole('tab', { name: '测试报告' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '历史报告' })).toBeInTheDocument()
  })

  it('点击历史报告触发 onChange 回调', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ReportTabs value='test' onChange={onChange} />)
    await user.click(screen.getByRole('tab', { name: '历史报告' }))
    expect(onChange).toHaveBeenCalledWith('history')
  })

  it('点击当前激活页签不产生变更回调', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ReportTabs value='history' onChange={onChange} />)
    await user.click(screen.getByRole('tab', { name: '历史报告' }))
    expect(onChange).not.toHaveBeenCalled()
  })
})
