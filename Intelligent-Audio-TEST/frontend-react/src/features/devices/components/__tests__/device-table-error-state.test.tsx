/**
 * 设备三页签表格错误态测试（INT-2330）：列表接口失败不得伪装成「暂无设备」空态——
 * 首屏失败显示「…列表加载失败」+ 重试；失败但有旧数据时保留旧行 + 行内提示；
 * 仅在无错误且无行时才渲染空态。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { TestDevice } from '@/domain/models/testDevice'
import {
  TestDeviceTable,
  type TestDeviceTableProps,
} from '@/features/devices/components/test-device-table'
import {
  PlaybackDeviceTable,
  type PlaybackDeviceTableProps,
} from '@/features/devices/components/playback-device-table'
import {
  ApiDeviceTable,
  type ApiDeviceTableProps,
} from '@/features/devices/components/api-device-table'
import { DevicesStatsRow } from '@/features/devices/components/devices-stats-row'

const ROW: TestDevice = {
  id: 101,
  name: '接线测试_设备A',
  model: 'Pixel 8',
  description: null,
  type: 'physical',
  system: 'Android',
  systemVersion: '14',
  apiLevel: '34',
  appName: 'Demo App',
  appVersion: '1.0.0',
  connectionType: 'usb',
  serialNumber: 'SN-101',
  ip: null,
  remark: null,
  tags: [],
  customAttributes: [],
  priority: 1,
  status: 'online',
  lastOnlineAt: '2026-10-20T08:00:00Z',
  driverName: null,
  supportedAlgorithms: [],
  needsPromptAudio: false,
  maxAudioDuration: null,
  location: null,
  keywords: null,
  labId: null,
  labName: null,
  occupied: false,
  createdAt: '2026-10-20T08:00:00Z',
  updatedAt: '2026-10-20T08:00:00Z',
}

function baseTestProps(overrides: Partial<TestDeviceTableProps> = {}): TestDeviceTableProps {
  return {
    rows: [],
    loading: false,
    total: 0,
    searchKeyword: '',
    selectedIds: new Set<number>(),
    batchMode: false,
    sortOrder: 'desc',
    onSortChange: vi.fn(),
    onToggleSelect: vi.fn(),
    onToggleSelectAll: vi.fn(),
    canRead: true,
    canUpdate: true,
    canDelete: true,
    canControl: true,
    canHealth: true,
    onDetail: vi.fn(),
    onEdit: vi.fn(),
    onHealth: vi.fn(),
    onTest: vi.fn(),
    onStopTest: vi.fn(),
    onControl: vi.fn(),
    onDelete: vi.fn(),
    onEmptyAdd: vi.fn(),
    onInstallApp: vi.fn(),
    onUninstallApp: vi.fn(),
    ...overrides,
  }
}

function basePlaybackProps(
  overrides: Partial<PlaybackDeviceTableProps> = {}
): PlaybackDeviceTableProps {
  return {
    rows: [],
    loading: false,
    total: 0,
    searchKeyword: '',
    selectedIds: new Set<number>(),
    batchMode: false,
    sortOrder: 'desc',
    onSortChange: vi.fn(),
    onToggleSelect: vi.fn(),
    onToggleSelectAll: vi.fn(),
    canRead: true,
    canUpdate: true,
    canDelete: true,
    canControl: true,
    canHealth: true,
    onDetail: vi.fn(),
    onEdit: vi.fn(),
    onAssociateSpl: vi.fn(),
    onPlayTest: vi.fn(),
    onStop: vi.fn(),
    onControl: vi.fn(),
    onDelete: vi.fn(),
    onEmptyAdd: vi.fn(),
    ...overrides,
  }
}

function baseApiProps(overrides: Partial<ApiDeviceTableProps> = {}): ApiDeviceTableProps {
  return {
    rows: [],
    loading: false,
    total: 0,
    searchKeyword: '',
    selectedIds: new Set<number>(),
    batchMode: false,
    onToggleSelect: vi.fn(),
    onToggleSelectAll: vi.fn(),
    canRead: true,
    canUpdate: true,
    canDelete: true,
    canControl: true,
    canHealth: true,
    onDetail: vi.fn(),
    onEdit: vi.fn(),
    onHealth: vi.fn(),
    onStopTest: vi.fn(),
    onDelete: vi.fn(),
    onEmptyAdd: vi.fn(),
    ...overrides,
  }
}

describe('设备列表查询失败态（INT-2330）', () => {
  it('测试设备首屏失败：显示「设备列表加载失败」+ 重试，不渲染「暂无设备」', () => {
    const onRetry = vi.fn()
    render(<TestDeviceTable {...baseTestProps({ error: true, onRetry })} />)

    expect(screen.getByText('设备列表加载失败')).toBeInTheDocument()
    expect(screen.getByText('设备列表获取失败，请重试')).toBeInTheDocument()
    expect(screen.queryByText('暂无设备')).not.toBeInTheDocument()
    expect(
      screen.queryByText('点击右上角「添加设备」登记第一台设备，或调整筛选条件')
    ).not.toBeInTheDocument()
  })

  it('首屏失败：点「重试」触发 refetch 回调', async () => {
    const onRetry = vi.fn()
    render(<TestDeviceTable {...baseTestProps({ error: true, onRetry })} />)

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('播放设备首屏失败：显示「播放设备列表加载失败」，不渲染「暂无播放设备」', () => {
    render(<PlaybackDeviceTable {...basePlaybackProps({ error: true, onRetry: vi.fn() })} />)

    expect(screen.getByText('播放设备列表加载失败')).toBeInTheDocument()
    expect(screen.queryByText('暂无播放设备')).not.toBeInTheDocument()
  })

  it('测试 API 首屏失败：显示「测试 API 列表加载失败」，不渲染「暂无测试 API」', () => {
    render(<ApiDeviceTable {...baseApiProps({ error: true, onRetry: vi.fn() })} />)

    expect(screen.getByText('测试 API 列表加载失败')).toBeInTheDocument()
    expect(screen.queryByText('暂无测试 API')).not.toBeInTheDocument()
  })

  it('刷新失败但有旧数据：保留旧行 + 行内提示 + 重试，不清空列表', async () => {
    const onRetry = vi.fn()
    render(
      <TestDeviceTable
        {...baseTestProps({ rows: [ROW], total: 1, error: true, onRetry })}
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent(
      '设备列表加载失败，当前显示的是上一次加载的数据'
    )
    expect(screen.getByText(ROW.name)).toBeInTheDocument()
    expect(screen.queryByText('暂无设备')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('无错误且无行：仍渲染「暂无设备」空态', () => {
    render(<TestDeviceTable {...baseTestProps()} />)

    expect(screen.getByText('暂无设备')).toBeInTheDocument()
    expect(screen.queryByText('设备列表加载失败')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('统计徽章行：接口失败整行隐藏，不把 0 当作真实统计（§4.1.2）', () => {
    const { container } = render(
      <DevicesStatsRow
        labels={['总设备数', '在线设备', '离线设备', '异常设备']}
        values={[0, 0, 0, 0]}
        loading={false}
        error
      />
    )

    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByText('总设备数')).not.toBeInTheDocument()
  })
})
