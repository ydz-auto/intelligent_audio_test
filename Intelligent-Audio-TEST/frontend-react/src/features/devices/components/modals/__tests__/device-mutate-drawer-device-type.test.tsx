/**
 * 测试设备编辑抽屉「设备类型」三值归一 + 未知值展示（INT-2640）：
 * ① 三值之外的存量值（历史 phone）关闭态显示「未知」，不外露英文原值；
 * ② 下拉可选项为三值枚举 + 当前未知项（共 4 项）；
 * ③ 不改类型直接保存时不改写 type（原值保留，数据不丢）；
 * ④ 主动改选三值后保存写回所选枚举。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TestDevice } from '@/domain/models/testDevice'

import { DeviceMutateDrawer } from '../device-mutate-drawer'

const mutations = vi.hoisted(() => ({
  createTest: vi.fn(),
  updateTest: vi.fn(),
}))

vi.mock('@/application/spl/useSplMappings', () => ({
  useSplMappings: () => ({ data: [], isPending: false }),
}))

vi.mock('@/application/devices/use-devices', () => ({
  useDeviceMutations: () => ({
    createTest: { mutateAsync: mutations.createTest },
    updateTest: { mutateAsync: mutations.updateTest },
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

/** 适配器已归一的历史数据：type=null（原始 phone 存于 rawType） */
const LEGACY_DEVICE: TestDevice = {
  id: 10,
  name: 'pura90豆包',
  model: 'Harmony Device',
  description: null,
  type: null,
  rawType: 'phone',
  system: 'HarmonyOS',
  systemVersion: '4.2',
  apiLevel: '3.1',
  appName: 'Demo App',
  appVersion: '1.0.0',
  connectionType: 'usb',
  serialNumber: 'SN-10',
  ip: null,
  remark: null,
  tags: [],
  customAttributes: [],
  priority: 5,
  status: 'offline',
  lastOnlineAt: null,
  driverName: null,
  supportedAlgorithms: [],
  needsPromptAudio: false,
  maxAudioDuration: null,
  location: null,
  keywords: null,
  labId: null,
  labName: null,
  occupied: false,
  createdAt: null,
  updatedAt: null,
}

function renderDrawer(device: TestDevice = LEGACY_DEVICE) {
  return render(
    <DeviceMutateDrawer
      state={{ open: true, mode: 'edit', kind: 'test', device }}
      onOpenChange={() => undefined}
    />
  )
}

/** 设备类型 Select 触发钮：按当前展示文案定位（「未知」/「真机」等） */
function getTypeTrigger(label: string): HTMLElement {
  const trigger = screen
    .getAllByRole('combobox')
    .find((element) => element.textContent?.trim() === label)
  if (!trigger) throw new Error(`未找到展示「${label}」的设备类型 Select 触发钮`)
  return trigger
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DeviceMutateDrawer 设备类型归一（INT-2640）', () => {
  it('历史 phone 关闭态显示「未知」，不回显英文原值', () => {
    renderDrawer()

    const trigger = getTypeTrigger('未知')
    expect(trigger).toHaveTextContent('未知')
    expect(trigger).not.toHaveTextContent('phone')
  })

  it('下拉为三值枚举 + 当前未知项', async () => {
    const user = userEvent.setup()
    renderDrawer()

    await user.click(getTypeTrigger('未知'))

    expect(screen.getByRole('option', { name: '真机' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'HTTP API' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Realtime WS' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '未知' })).toBeInTheDocument()
  })

  it('不改类型保存时不改写 type（原值保留）', async () => {
    const user = userEvent.setup()
    renderDrawer()

    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(mutations.updateTest).toHaveBeenCalledTimes(1)
    const payload = mutations.updateTest.mock.calls[0][0] as {
      id: number
      patch: Record<string, unknown>
    }
    expect(payload.id).toBe(10)
    expect(payload.patch).not.toHaveProperty('type')
  })

  it('主动改选三值后保存写回所选枚举', async () => {
    const user = userEvent.setup()
    renderDrawer()

    await user.click(getTypeTrigger('未知'))
    await user.click(await screen.findByRole('option', { name: '真机' }))
    expect(getTypeTrigger('真机')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(mutations.updateTest).toHaveBeenCalledTimes(1)
    const payload = mutations.updateTest.mock.calls[0][0] as {
      patch: Record<string, unknown>
    }
    expect(payload.patch.type).toBe('physical')
  })
})
