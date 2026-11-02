/**
 * 设备参数配置抽屉的策略区（INT-2271 / INT-2341）：
 * ① 已绑定策略：「另存为新策略」与「克隆当前策略」都可用，表格标注三层生效值；
 * ② 未绑定：「另存为新策略」可点并打开命名弹窗，说明快照口径；
 * ③ 策略列表还在读：「另存」仍可用（三层由读接口解析，不依赖列表就绪）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ParamProfile } from '@/domain/models/paramProfile'

const { profileState, buildMock, createProfileMock, bindMock, cloneMock, paramsMock } = vi.hoisted(
  () => ({
    profileState: {
      value: {
        profiles: [] as ParamProfile[],
        boundProfileId: null as number | null,
        isLoading: false,
        isError: false,
      },
    },
    buildMock: vi.fn(),
    createProfileMock: vi.fn(),
    bindMock: vi.fn(),
    cloneMock: vi.fn(),
    paramsMock: vi.fn(async (_algorithmType: string): Promise<unknown[]> => []),
  })
)

vi.mock('@/application/test-execution/useTestAlgorithmOptions', () => ({
  useTestAlgorithmOptions: () => ({ data: [{ id: 'asr', name: '语音识别' }] }),
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({
    user: null,
    hasPermission: () => true,
    hasAnyPermission: () => true,
  }),
}))

vi.mock('@/application/devices/use-device-scope-mappings', () => ({
  deviceMappingsQueryKey: (algorithmType: string, deviceId: number, bucket: string) => [
    'devices',
    'device-mappings',
    algorithmType,
    deviceId,
    bucket,
  ],
}))

vi.mock('@/application/devices/use-device-param-profile', () => ({
  deviceProfileQueryKeys: {
    profiles: (algorithmType: string) => ['devices', 'param-profiles', algorithmType],
  },
  useDeviceParamProfileOptions: () => profileState.value,
  buildDeviceScopeProfileInput: buildMock,
}))

vi.mock('@/infrastructure/api/param-profile-api', () => ({
  bindDeviceProfile: bindMock,
  cloneProfile: cloneMock,
  createProfile: createProfileMock,
}))

vi.mock('@/infrastructure/api/device-param-api', () => ({
  fetchDeviceScopeParams: paramsMock,
  createDeviceScopeParam: vi.fn(),
  updateDeviceScopeParam: vi.fn(),
  deleteDeviceScopeParam: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('../device-mappings-section', () => ({
  DeviceMappingsSection: () => null,
}))

import { DeviceParamsDialog } from '../device-params-dialog'

const DEVICE = { id: 5, name: '接线测试_真机A' }

const BOUND_PROFILE: ParamProfile = {
  id: 12,
  scope: 'device',
  algorithmType: 'asr',
  name: '接线测试_设备策略X',
  description: null,
  status: 'online',
  clonedFrom: null,
  config: null,
  params: [],
  mappings: [],
  createdAt: null,
  updatedAt: null,
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DeviceParamsDialog
        open
        onOpenChange={() => undefined}
        device={DEVICE}
        defaultAlgorithmType='asr'
      />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  profileState.value = {
    profiles: [BOUND_PROFILE],
    boundProfileId: null,
    isLoading: false,
    isError: false,
  }
  paramsMock.mockResolvedValue([])
})

describe('DeviceParamsDialog 参数策略（INT-2271）', () => {
  it('已绑定策略：另存与克隆都可用，表格标注三层生效值', () => {
    profileState.value = {
      profiles: [BOUND_PROFILE],
      boundProfileId: BOUND_PROFILE.id,
      isLoading: false,
      isError: false,
    }

    renderDialog()

    expect(screen.getByRole('button', { name: '另存为新策略' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '克隆当前策略' })).toBeEnabled()
    expect(
      screen.getByText(/本表 = 算法类型级默认 → 绑定策略 → 本设备覆盖（三层生效值）/)
    ).toBeInTheDocument()
    expect(screen.getByText(/当前策略「接线测试_设备策略X」/)).toBeInTheDocument()
  })

  it('未绑定策略：另存可点并打开命名弹窗，说明快照口径', async () => {
    const user = userEvent.setup()
    renderDialog()

    const saveAsButton = screen.getByRole('button', { name: '另存为新策略' })
    expect(saveAsButton).toBeEnabled()
    expect(screen.getByRole('button', { name: '克隆当前策略' })).toBeDisabled()

    await user.click(saveAsButton)

    expect(await screen.findByText('另存为设备策略')).toBeInTheDocument()
    expect(screen.getByText(/三层生效值（算法级默认 → 绑定策略 → 本设备覆盖）/)).toBeInTheDocument()
    expect(buildMock).not.toHaveBeenCalled()
  })

  it('策略列表仍在读取：另存仍可用（三层由读接口解析，不依赖列表就绪）', () => {
    profileState.value = {
      profiles: [],
      boundProfileId: null,
      isLoading: true,
      isError: false,
    }

    renderDialog()

    expect(screen.getByRole('button', { name: '另存为新策略' })).toBeEnabled()
  })
})
