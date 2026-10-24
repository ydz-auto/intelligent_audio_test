/**
 * API 连接测试结果弹窗错误态收缩约束（INT-1632，10 规范 §5.4）。
 * 真实库实测：后端返回 DNS 失败等异常全文（长串无空格）时，dl 的 1fr 列被 min-content
 * 撑宽，弹窗横向溢出、健康分/错误信息/「重新测试」被右边界裁切。
 * jsdom 无布局，不能量 scrollWidth，这里断言结构约束（min-w-0 + break-all）仍在位。
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ApiHealthDialog } from '../api-health-dialog'

const LONG_ERROR =
  '[Errno -2] Name or service not known: HTTPSConnectionPool(host=%27api.invalid.example%27, port=443): Max retries exceeded with url: /v1/health (Caused by NewConnectionError(%27<urllib3.connection.HTTPSConnection object at 0x000001F2A1B2C3D4>: Failed to establish a new connection: [Errno -2] Name or service not known%27))'

describe('ApiHealthDialog 错误态横向收缩（INT-1632）', () => {
  it('长错误串以 min-w-0 + break-all 收缩，不撑开弹窗', () => {
    render(
      <ApiHealthDialog
        open
        onOpenChange={vi.fn()}
        testing={false}
        onRetest={vi.fn()}
        result={{
          id: 1,
          status: 'offline',
          healthScore: 100,
          endpointsStatus: 'https://api.invalid.example/v1/health',
          statusCode: null,
          responseTime: null,
          error: LONG_ERROR,
          warning: null,
        }}
      />
    )

    const dialog = screen.getByRole('dialog')
    // 健康分完整渲染在弹窗内
    expect(within(dialog).getByText('100')).toBeTruthy()

    const dl = dialog.querySelector('dl')
    expect(dl).not.toBeNull()
    expect(dl!.className).toContain('min-w-0')

    // 错误信息 dd 与错误 Alert 都必须能任意断行
    const errorRow = within(dialog).getAllByText(LONG_ERROR)
    expect(errorRow.length).toBe(2)
    for (const node of errorRow) {
      expect(node.className).toContain('min-w-0')
      expect(node.className).toContain('break-all')
    }

    // 其余键值行同样带收缩约束，避免端点 URL 等长串重现撑宽
    for (const dd of dialog.querySelectorAll('dd')) {
      expect(dd.className).toContain('min-w-0')
      expect(dd.className).toContain('break-all')
    }

    // 「重新测试」按钮在位
    expect(within(dialog).getByRole('button', { name: /重新测试/ })).toBeTruthy()
  })
})
