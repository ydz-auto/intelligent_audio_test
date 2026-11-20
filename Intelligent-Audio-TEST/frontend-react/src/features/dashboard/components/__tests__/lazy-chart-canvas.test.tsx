/**
 * 图表视口懒加载（INT 性能治理）：视口外不渲染 VChart 分块，进入视口后才挂载；
 * 环境无 IntersectionObserver 时直接降级渲染，保证图表不缺席。
 */
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { LazyChartCanvas } from '@/features/dashboard/components/lazy-chart-canvas'

vi.mock('@/features/dashboard/components/chart-canvas', () => ({
  DashboardChart: () => <div data-testid='dashboard-chart' />,
}))

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = []

  private callback: IntersectionObserverCallback
  private elements: Element[] = []

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    MockIntersectionObserver.instances.push(this)
  }

  observe(element: Element) {
    this.elements.push(element)
  }

  unobserve() {}

  disconnect() {}

  takeRecords() {
    return []
  }

  triggerIntersect() {
    this.callback(
      this.elements.map(
        (element) => ({ isIntersecting: true, target: element }) as never
      ),
      this as unknown as IntersectionObserver
    )
  }
}

const initialIntersectionObserver = globalThis.IntersectionObserver

beforeEach(() => {
  MockIntersectionObserver.instances = []
  globalThis.IntersectionObserver =
    MockIntersectionObserver as unknown as typeof IntersectionObserver
})

afterEach(() => {
  globalThis.IntersectionObserver = initialIntersectionObserver
})

describe('LazyChartCanvas 视口懒加载', () => {
  it('容器未进入视口时不渲染图表', () => {
    render(<LazyChartCanvas kind='status' statusCounts={{ completed: 1 }} />)

    expect(screen.queryByTestId('dashboard-chart')).toBeNull()
    expect(MockIntersectionObserver.instances).toHaveLength(1)
  })

  it('容器进入视口后渲染图表', async () => {
    render(<LazyChartCanvas kind='status' statusCounts={{ completed: 1 }} />)

    act(() => {
      MockIntersectionObserver.instances[0].triggerIntersect()
    })

    expect(await screen.findByTestId('dashboard-chart')).toBeTruthy()
  })

  it('环境不支持 IntersectionObserver 时直接渲染（降级不阻塞图表）', async () => {
    globalThis.IntersectionObserver =
      undefined as unknown as typeof IntersectionObserver

    render(<LazyChartCanvas kind='status' statusCounts={{ completed: 1 }} />)

    expect(await screen.findByTestId('dashboard-chart')).toBeTruthy()
  })
})
