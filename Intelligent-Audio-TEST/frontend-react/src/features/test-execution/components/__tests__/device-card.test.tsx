/**
 * 设备卡「系统」徽章归一（INT-2649）：接口实测 system 可为小写别名（harmony/android），
 * 卡片必须与设备管理列表同源走 device-system 归一，不外露原始小写值；
 * 未知值仍原样回退，空值显示「—」。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Device } from '@/domain/models/device'

import { DeviceCard } from '../device-card'

function makeDevice(overrides: Partial<Device> = {}): Device {
  return {
    id: 9,
    name: 'pura90小艺',
    model: 'Pura 90',
    description: null,
    type: 'physical',
    system: 'harmony',
    systemVersion: '1.0.0',
    serialNumber: 'SN-0009',
    ip: null,
    status: 'offline',
    lastOnlineAt: null,
    supportedAlgorithms: null,
    connectionType: 'usb',
    labId: null,
    labName: null,
    ...overrides,
  }
}

function renderCard(device: Device) {
  render(
    <DeviceCard
      device={device}
      selected={false}
      canControl={false}
      testing={false}
      onToggle={vi.fn()}
      onTestConnection={vi.fn()}
    />
  )
}

describe('DeviceCard 系统徽章归一（INT-2649）', () => {
  it('小写 harmony 展示为 HarmonyOS', () => {
    renderCard(makeDevice({ system: 'harmony' }))
    expect(screen.getByText('HarmonyOS')).toBeInTheDocument()
    expect(screen.queryByText('harmony')).not.toBeInTheDocument()
  })

  it('小写 android 展示为 Android', () => {
    renderCard(makeDevice({ system: 'android' }))
    expect(screen.getByText('Android')).toBeInTheDocument()
    expect(screen.queryByText('android')).not.toBeInTheDocument()
  })

  it('未知系统原样回退', () => {
    renderCard(makeDevice({ system: 'custom-os' }))
    expect(screen.getByText('custom-os')).toBeInTheDocument()
  })

  it('系统为空显示「—」', () => {
    renderCard(makeDevice({ system: null }))
    expect(screen.queryByText('harmony')).not.toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})
