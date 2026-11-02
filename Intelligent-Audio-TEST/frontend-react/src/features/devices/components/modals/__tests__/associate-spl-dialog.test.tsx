/**
 * 关联声压映射弹窗测试（INT-2343）：
 * ① 选项源为 GET /spl 全量，排除已归属其他设备的映射；未归属/归属本设备的都可见；
 * ② 无任何可关联映射时给出空态文案；
 * ③ 选中后「关联」按数字 splMappingId 提交并提示成功。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { SplMapping } from '@/domain/models/splMapping'

import { AssociateSplDialog } from '../associate-spl-dialog'

const mappingsState = vi.hoisted(() => ({ value: [] as SplMapping[] }))
const associateMock = vi.hoisted(() => vi.fn())
const toastSuccessMock = vi.hoisted(() => vi.fn())

vi.mock('@/application/spl/useSplMappings', () => ({
  useSplMappings: () => ({
    data: mappingsState.value,
    isPending: false,
  }),
}))

vi.mock('@/application/devices/use-devices', () => ({
  useAssociateSplMutation: () => ({ associate: { mutateAsync: associateMock } }),
}))

vi.mock('sonner', () => ({
  toast: { success: toastSuccessMock, error: vi.fn() },
}))

const DEVICE: PlaybackDevice = {
  id: 6,
  name: '设备正左侧（1m-90°）',
  model: null,
  description: null,
  deviceType: 'dry',
  sampleRate: 48_000,
  channelIndex: 0,
  deviceUniqueId: 'spk-6',
  status: null,
  currentSplMappingId: null,
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

beforeEach(() => {
  vi.clearAllMocks()
  associateMock.mockResolvedValue(undefined)
  mappingsState.value = [
    mapping({ id: 3, name: '设备正右斜侧（1m-90°）' }),
    mapping({ id: 5, name: '本设备自建映射', deviceId: 6 }),
    mapping({ id: 9, name: '其他设备映射', deviceId: 12 }),
  ]
})

describe('AssociateSplDialog', () => {
  it('下拉列出未归属与归属本设备的映射，排除其他设备的映射', async () => {
    const user = userEvent.setup()
    render(<AssociateSplDialog state={{ open: true, device: DEVICE }} onOpenChange={() => undefined} />)

    await user.click(screen.getByRole('combobox', { name: '选择声压映射' }))

    expect(screen.getByRole('option', { name: '设备正右斜侧（1m-90°）（已校准）' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '本设备自建映射（已校准）' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: '其他设备映射（已校准）' })).not.toBeInTheDocument()
  })

  it('没有可关联映射时给出空态文案', async () => {
    const user = userEvent.setup()
    mappingsState.value = [mapping({ id: 9, name: '其他设备映射', deviceId: 12 })]
    render(<AssociateSplDialog state={{ open: true, device: DEVICE }} onOpenChange={() => undefined} />)

    await user.click(screen.getByRole('combobox', { name: '选择声压映射' }))

    expect(screen.getByText('暂无可关联的声压映射')).toBeInTheDocument()
  })

  it('选中映射后按数字 id 提交并提示成功', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<AssociateSplDialog state={{ open: true, device: DEVICE }} onOpenChange={onOpenChange} />)

    await user.click(screen.getByRole('combobox', { name: '选择声压映射' }))
    await user.click(await screen.findByRole('option', { name: '设备正右斜侧（1m-90°）（已校准）' }))
    await user.click(screen.getByRole('button', { name: '关联' }))

    expect(associateMock).toHaveBeenCalledWith({ deviceId: 6, splMappingId: 3 })
    expect(toastSuccessMock).toHaveBeenCalledWith('SPL 映射关联成功')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
