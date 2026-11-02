/**
 * SPL 映射表错误态测试（INT-2331）：列表接口失败不得伪装成「暂无增益映射 / 暂无 RMS-SPL 映射」
 * 空态——首屏失败显示「SPL 映射加载失败」+ 重试；失败但有上次数据时保留旧行 + 行内提示；
 * 仅在无错误且无行时才渲染空态（与 INT-1583 音频页同型）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ApiRmsSplMapping } from '@/domain/models/digitalSpl'
import type { SplMapping } from '@/domain/models/splMapping'
import { DeviceSplTable } from '@/features/spl-mapping/components/device-spl-table'
import { DigitalSplTable } from '@/features/spl-mapping/components/digital-spl-table'

const SPL_ROW: SplMapping = {
  id: 7,
  name: '接线测试_增益映射A',
  description: null,
  deviceId: 1,
  deviceName: '接线测试_设备A',
  deviceModel: 'M1',
  deviceType: 'dry',
  distance: 1,
  targetSpl: 65,
  digitalGain: 0,
  calibrationStatus: 'calibrated',
  testFrequency: 1000,
  calibrationData: null,
  isCurrent: true,
  createdAt: '2026-11-01T00:00:00Z',
  updatedAt: '2026-11-01T00:00:00Z',
}

const DIGITAL_ROW: ApiRmsSplMapping = {
  id: 9,
  apiId: 3,
  name: '接线测试_RMS映射A',
  description: null,
  vendor: null,
  protocol: 'websocket',
  referenceSpl: 65,
  referenceGainLinear: 1,
  calibrationStatus: 'uncalibrated',
  calibrationPoints: [],
  minGainLinear: 0.001,
  maxGainLinear: 10,
  createdAt: '2026-11-01T00:00:00Z',
  updatedAt: '2026-11-01T00:00:00Z',
}

function deviceProps(overrides: Partial<Parameters<typeof DeviceSplTable>[0]> = {}) {
  return {
    rows: [] as SplMapping[],
    loading: false,
    searchKeyword: '',
    canRead: true,
    canUpdate: true,
    canCreate: true,
    canDelete: true,
    onEmptyCreate: vi.fn(),
    onDetail: vi.fn(),
    onEdit: vi.fn(),
    onCalibrate: vi.fn(),
    onHistory: vi.fn(),
    onDelete: vi.fn(),
    ...overrides,
  }
}

function digitalProps(overrides: Partial<Parameters<typeof DigitalSplTable>[0]> = {}) {
  return {
    rows: [] as ApiRmsSplMapping[],
    apis: [],
    loading: false,
    searchKeyword: '',
    canRead: true,
    canUpdate: true,
    canCreate: true,
    canDelete: true,
    onEmptyCreate: vi.fn(),
    onDetail: vi.fn(),
    onEdit: vi.fn(),
    onCalibrate: vi.fn(),
    onToggleDefault: vi.fn(),
    onDelete: vi.fn(),
    ...overrides,
  }
}

describe('DeviceSplTable 查询失败态（INT-2331）', () => {
  it('首屏失败：显示「SPL 映射加载失败」+ 重试，不渲染「暂无增益映射」空态', async () => {
    const onRetry = vi.fn()
    render(<DeviceSplTable {...deviceProps({ isError: true, onRetry })} />)

    expect(screen.getByText('SPL 映射加载失败')).toBeInTheDocument()
    expect(screen.getByText('SPL 映射列表获取失败，请重试')).toBeInTheDocument()
    expect(screen.queryByText('暂无增益映射')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('失败且有上次数据：保留旧行 + 行内提示 + 重试，不渲染空态', async () => {
    const onRetry = vi.fn()
    render(
      <DeviceSplTable
        {...deviceProps({ rows: [SPL_ROW], isError: true, onRetry })}
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent(
      'SPL 映射加载失败，当前显示的是上一次加载的数据'
    )
    expect(screen.getByText(SPL_ROW.name)).toBeInTheDocument()
    expect(screen.queryByText('暂无增益映射')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('无错误且无行：仍渲染「暂无增益映射」空态', () => {
    render(<DeviceSplTable {...deviceProps()} />)

    expect(screen.getByText('暂无增益映射')).toBeInTheDocument()
    expect(screen.queryByText('SPL 映射加载失败')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('DigitalSplTable 查询失败态（INT-2331）', () => {
  it('首屏失败：显示「SPL 映射加载失败」+ 重试，不渲染「暂无 RMS-SPL 映射」空态', async () => {
    const onRetry = vi.fn()
    render(<DigitalSplTable {...digitalProps({ isError: true, onRetry })} />)

    expect(screen.getByText('SPL 映射加载失败')).toBeInTheDocument()
    expect(screen.getByText('RMS-SPL 映射列表获取失败，请重试')).toBeInTheDocument()
    expect(screen.queryByText('暂无 RMS-SPL 映射')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('失败且有上次数据：保留旧行 + 行内提示，不渲染空态', () => {
    render(<DigitalSplTable {...digitalProps({ rows: [DIGITAL_ROW], isError: true })} />)

    expect(screen.getByRole('alert')).toHaveTextContent(
      'SPL 映射加载失败，当前显示的是上一次加载的数据'
    )
    expect(screen.getByText(DIGITAL_ROW.name as string)).toBeInTheDocument()
    expect(screen.queryByText('暂无 RMS-SPL 映射')).not.toBeInTheDocument()
  })

  it('无错误且无行：仍渲染「暂无 RMS-SPL 映射」空态', () => {
    render(<DigitalSplTable {...digitalProps()} />)

    expect(screen.getByText('暂无 RMS-SPL 映射')).toBeInTheDocument()
    expect(screen.queryByText('SPL 映射加载失败')).not.toBeInTheDocument()
  })
})
