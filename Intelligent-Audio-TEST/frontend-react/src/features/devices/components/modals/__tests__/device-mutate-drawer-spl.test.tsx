/**
 * 播放设备编辑抽屉「声压映射」选项（INT-2347）：
 * ① 选项源与关联弹窗同源（GET /spl 全量），排除他机归属与类型不符的映射；
 * ② 当前已关联映射回显名称而非裸 id（即使它未归属本设备）；
 * ③ 选中未归属映射后触发钮显示映射名。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { SplMapping } from '@/domain/models/splMapping'

import { DeviceMutateDrawer } from '../device-mutate-drawer'

const mappingsState = vi.hoisted(() => ({ value: [] as SplMapping[] }))

vi.mock('@/application/spl/useSplMappings', () => ({
  useSplMappings: () => ({ data: mappingsState.value, isPending: false }),
}))

vi.mock('@/application/devices/use-devices', () => ({
  useDeviceMutations: () => ({
    createTest: { mutateAsync: vi.fn() },
    updateTest: { mutateAsync: vi.fn() },
    createPlayback: { mutateAsync: vi.fn() },
    updatePlayback: { mutateAsync: vi.fn() },
  }),
  useDriverKeywords: () => ({ data: [] }),
  useLaboratories: () => ({ data: [] }),
}))

vi.mock('@/application/hooks/use-algorithm-options', () => ({
  useAlgorithmOptions: () => ({ options: [], canRead: false }),
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({
    user: null,
    hasPermission: () => true,
    hasAnyPermission: () => true,
  }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const DEVICE: PlaybackDevice = {
  id: 6,
  name: '设备正左侧（1m-90°）',
  model: 'Speakon 6',
  description: null,
  deviceType: 'dry',
  sampleRate: 48_000,
  channelIndex: 0,
  deviceUniqueId: 'spk-6',
  status: 'online',
  currentSplMappingId: 16,
  currentSplMappingName: null,
  labId: null,
  labName: null,
  occupied: false,
  supportedFormats: null,
  supportedChannels: null,
  createdAt: null,
  updatedAt: null,
}

function mapping(overrides: Partial<SplMapping> & Pick<SplMapping, 'id' | 'name'>): SplMapping {
  return {
    description: null,
    deviceId: null,
    deviceName: null,
    deviceModel: null,
    deviceType: null,
    distance: 1,
    targetSpl: 65,
    digitalGain: 0,
    calibrationStatus: 'calibrated',
    testFrequency: 1000,
    calibrationData: null,
    isCurrent: null,
    createdAt: null,
    updatedAt: null,
    ...overrides,
  }
}

/** 抽屉里多个 Select；声压映射触发钮按已选映射名定位 */
function getSplTrigger(): HTMLElement {
  const trigger = screen
    .getAllByRole('combobox')
    .find((element) => element.textContent?.includes('已校准'))
  if (!trigger) throw new Error('未找到声压映射 Select 触发钮')
  return trigger
}

function renderDrawer() {
  return render(
    <DeviceMutateDrawer
      state={{ open: true, mode: 'edit', kind: 'playback', device: DEVICE }}
      onOpenChange={() => undefined}
    />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mappingsState.value = [
    mapping({ id: 16, name: '当前已关联映射', deviceType: 'dry' }),
    mapping({ id: 3, name: '未归属干声映射', deviceType: 'dry' }),
    mapping({ id: 2, name: '未归属噪声映射', deviceType: 'noise' }),
    mapping({ id: 4, name: '他机归属映射', deviceId: 12, deviceType: 'dry' }),
  ]
})

describe('DeviceMutateDrawer 声压映射', () => {
  it('编辑态回显当前映射名称而非裸 id', () => {
    renderDrawer()

    const trigger = getSplTrigger()
    expect(trigger).toHaveTextContent('当前已关联映射（已校准）')
    expect(trigger).not.toHaveTextContent('16')
  })

  it('选项含当前/未归属映射与类型匹配项，排除他机归属与类型不符', async () => {
    const user = userEvent.setup()
    renderDrawer()

    await user.click(getSplTrigger())

    expect(screen.getByRole('option', { name: '当前已关联映射（已校准）' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '未归属干声映射（已校准）' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: '未归属噪声映射（已校准）' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: '他机归属映射（已校准）' })).not.toBeInTheDocument()
    expect(screen.getByRole('option', { name: '不使用声压映射' })).toBeInTheDocument()
  })

  it('改选未归属映射后触发钮显示新映射名称', async () => {
    const user = userEvent.setup()
    renderDrawer()

    await user.click(getSplTrigger())
    await user.click(await screen.findByRole('option', { name: '未归属干声映射（已校准）' }))

    expect(getSplTrigger()).toHaveTextContent('未归属干声映射（已校准）')
  })
})
