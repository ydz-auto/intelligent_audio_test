/**
 * 参数策略管理弹窗（INT-2358）：
 * ① 列表接口不带 params / mappings，行内「字段 / 映射」必须由详情计数补齐，
 *    不能把「未知」渲染成 0（旧实现恒显示 0 / 0）；
 * ② 删除二次确认按策略作用域给出绑定方回落文案（api → API，device → 设备）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ParamProfile } from '@/domain/models/paramProfile'
import { ParamProfileManagerDialog } from '@/features/algorithm-config/param-profiles/param-profile-manager-dialog'

const { listProfilesMock, getProfileMock } = vi.hoisted(() => ({
  listProfilesMock: vi.fn(),
  getProfileMock: vi.fn(),
}))

vi.mock('@/infrastructure/api/param-profile-api', () => ({
  listProfiles: listProfilesMock,
  getProfile: getProfileMock,
  createProfile: vi.fn(),
  updateProfile: vi.fn(),
  deleteProfile: vi.fn(),
  cloneProfile: vi.fn(),
  bindApiProfile: vi.fn(),
  bindDeviceProfile: vi.fn(),
  saveApiScopeOverrides: vi.fn(),
}))

vi.mock('@/application/test-execution/useTestAlgorithmOptions', () => ({
  useTestAlgorithmOptions: () => ({ data: [], isLoading: false }),
}))

function makeProfile(overrides: Partial<ParamProfile>): ParamProfile {
  return {
    id: 1,
    scope: 'api',
    algorithmType: 'voice_llm',
    name: '策略',
    description: null,
    status: 'online',
    clonedFrom: null,
    config: null,
    // 列表接口的真实形态：没有 params / mappings（DTO 收敛为空数组）
    params: [],
    mappings: [],
    createdAt: null,
    updatedAt: null,
    ...overrides,
  }
}

function withCounts(profile: ParamProfile, paramCount: number, mappingCount: number) {
  return {
    ...profile,
    params: Array.from({ length: paramCount }, () => ({})) as ParamProfile['params'],
    mappings: Array.from({ length: mappingCount }, () => ({})) as ParamProfile['mappings'],
  }
}

const API_PROFILE = makeProfile({ id: 1, scope: 'api', name: 'API 默认策略' })
const DEVICE_PROFILE = makeProfile({ id: 2, scope: 'device', name: '设备默认策略' })

function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ParamProfileManagerDialog
        open
        onOpenChange={() => undefined}
        canManage
        defaultAlgorithmType=''
      />
    </QueryClientProvider>
  )
}

function rowOf(name: string): HTMLElement {
  return screen.getByText(name).closest('tr') as HTMLElement
}

beforeEach(() => {
  listProfilesMock.mockResolvedValue({
    profiles: [API_PROFILE, DEVICE_PROFILE],
    bindings: [],
    deviceBindings: [],
  })
  getProfileMock.mockImplementation(async (profileId: number) => {
    if (profileId === API_PROFILE.id) return withCounts(API_PROFILE, 3, 2)
    return withCounts(DEVICE_PROFILE, 0, 1)
  })
})

describe('ParamProfileManagerDialog（INT-2358）', () => {
  it('字段 / 映射列取详情计数，与详情一致（不再恒为 0）', async () => {
    renderDialog()

    const apiRow = await screen.findByText(API_PROFILE.name)
    await waitFor(() => {
      const cells = within(rowOf(API_PROFILE.name)).getAllByRole('cell')
      expect(cells[4]).toHaveTextContent('3')
      expect(cells[5]).toHaveTextContent('2')
    })
    // 设备策略真实为 0 字段 / 1 映射：0 是真实值而不是缺省值
    const deviceCells = within(rowOf(DEVICE_PROFILE.name)).getAllByRole('cell')
    expect(deviceCells[4]).toHaveTextContent('0')
    expect(deviceCells[5]).toHaveTextContent('1')
    expect(apiRow).toBeInTheDocument()
    // 两个策略各拉一次详情（列表接口无计数）
    expect(getProfileMock).toHaveBeenCalledTimes(2)
  })

  it('删除二次确认按作用域提示绑定方：设备策略提示设备、API 策略提示 API', async () => {
    const user = userEvent.setup()
    renderDialog()
    await screen.findByText(API_PROFILE.name)

    await user.click(within(rowOf(DEVICE_PROFILE.name)).getByRole('button', { name: '删除' }))
    expect(
      await screen.findByText(/绑定该策略的设备将回落为未绑定/)
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '取消' }))

    await user.click(within(rowOf(API_PROFILE.name)).getByRole('button', { name: '删除' }))
    expect(
      await screen.findByText(/绑定该策略的 API 将回落为未绑定（实例覆盖行保留）/)
    ).toBeInTheDocument()
  })
})
