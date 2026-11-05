/**
 * 路由待定态（INT-2392）：
 * - RoutePending 是 router defaultPendingComponent 的渲染件，需带 role=status /
 *   aria-busy 可被无障碍与实测脚本识别（data-testid=route-pending）；
 * - ROUTE_PENDING_OPTIONS 锁死默认 pending 组件与时长——删掉 defaultPendingComponent
 *   会让 router 退回「旧页面一直挂着」的 INT-2388 现象。
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ROUTE_PENDING_OPTIONS } from '@/app/router-pending'
import { RoutePending } from '@/components/route-pending'

describe('RoutePending', () => {
  it('渲染为可访问的加载态：role=status + aria-busy + 中文文案', () => {
    const { getByRole, getByTestId } = render(<RoutePending />)

    const status = getByRole('status')
    expect(status).toHaveAttribute('aria-busy', 'true')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(getByTestId('route-pending')).toBe(status)
    expect(status.textContent).toContain('页面加载中')
  })

  it('配置接到 router：默认 pending 组件与时长', () => {
    expect(ROUTE_PENDING_OPTIONS.defaultPendingComponent).toBe(RoutePending)
    expect(ROUTE_PENDING_OPTIONS.defaultPendingMs).toBe(400)
    expect(ROUTE_PENDING_OPTIONS.defaultPendingMinMs).toBe(300)
  })
})
