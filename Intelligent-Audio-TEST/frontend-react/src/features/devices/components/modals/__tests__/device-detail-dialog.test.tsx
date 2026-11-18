/**
 * 设备详情弹窗「系统」行归一（INT-2649）：原始小写 harmony 不得外露，
 * 与设备管理列表同源展示「HarmonyOS + 版本号」；无版本号时不产生多余空格。
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { TestDevice } from '@/domain/models/testDevice'

import { DeviceDetailDialog } from '../device-detail-dialog'

function makeTestDevice(overrides: Partial<TestDevice> = {}): TestDevice {
  return {
    id: 9,
    name: 'pura90小艺',
    model: 'Pura 90',
    description: null,
    type: 'physical',
    system: 'harmony',
    systemVersion: '1.0.0',
    apiLevel: null,
    appName: 'Default App',
    appVersion: '1.0.0',
    connectionType: 'usb',
    serialNumber: 'SN-0009',
    ip: null,
    remark: null,
    tags: null,
    customAttributes: null,
    priority: null,
    status: 'offline',
    lastOnlineAt: null,
    driverName: null,
    supportedAlgorithms: null,
    needsPromptAudio: false,
    maxAudioDuration: null,
    location: null,
    keywords: null,
    labId: null,
    labName: null,
    occupied: false,
    createdAt: null,
    updatedAt: null,
    ...overrides,
  }
}

function renderDialog(device: TestDevice) {
  render(
    <DeviceDetailDialog
      state={{ open: true, kind: 'test', device }}
      onOpenChange={vi.fn()}
      onEdit={vi.fn()}
      canUpdate={false}
    />
  )
  return screen.getByRole('dialog')
}

describe('DeviceDetailDialog 系统行归一（INT-2649）', () => {
  it('小写 harmony + 版本号展示为「HarmonyOS 1.0.0」', () => {
    const dialog = renderDialog(makeTestDevice({ system: 'harmony', systemVersion: '1.0.0' }))
    expect(within(dialog).getByText('HarmonyOS 1.0.0')).toBeInTheDocument()
    expect(within(dialog).queryByText(/harmony /)).not.toBeInTheDocument()
  })

  it('无版本号时只展示系统名，无尾随空格', () => {
    const dialog = renderDialog(makeTestDevice({ system: 'harmony', systemVersion: null }))
    expect(within(dialog).getByText('HarmonyOS')).toBeInTheDocument()
  })

  it('标准值 HarmonyOS 与大小写别名展示一致', () => {
    const dialog = renderDialog(makeTestDevice({ system: 'HarmonyOS', systemVersion: '1.0.0' }))
    expect(within(dialog).getByText('HarmonyOS 1.0.0')).toBeInTheDocument()
  })
})
