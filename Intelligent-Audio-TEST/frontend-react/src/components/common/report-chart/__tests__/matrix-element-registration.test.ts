/**
 * INT-1829 回归：热力图以 Chart.js `type='matrix'` 构建，chartjs-chart-matrix 要求控制器与元素成对注册。
 * ReportChart 只注册 MatrixController 时，构造期抛 `"matrix" is not a registered element`，
 * 整页被 React 错误边界兜成 500。此用例锁住控制器与元素都已注册。
 */
import { Chart } from 'chart.js'
import { MatrixController, MatrixElement } from 'chartjs-chart-matrix'
import { describe, expect, it } from 'vitest'

import '@/components/common/report-chart'

describe('ReportChart 热力图注册', () => {
  it('matrix 控制器与元素都注册到 Chart.js', () => {
    expect(Chart.registry.getController('matrix')).toBe(MatrixController)
    expect(Chart.registry.getElement('matrix')).toBe(MatrixElement)
  })
})
