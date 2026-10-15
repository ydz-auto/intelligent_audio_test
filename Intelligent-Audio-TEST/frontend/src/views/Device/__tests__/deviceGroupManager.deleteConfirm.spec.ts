/**
 * INT-286：设备分组删除确认回归（window.confirm → BASIC_CONFIRM danger 模态）。
 *
 * 锁定口径：
 * - 删除分组打开 BASIC_CONFIRM（title=删除设备分组、danger=true），文案含分组名与成员提示
 * - 确认（open resolve）→ deleteGroup(id, true) 下发并刷新；取消（reject）→ 不下发
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const ports = vi.hoisted(() => ({
  getGroups: vi.fn(),
  getGroup: vi.fn(),
  createGroup: vi.fn(),
  updateGroup: vi.fn(),
  deleteGroup: vi.fn(),
  addDevicesToGroup: vi.fn(),
  removeDevicesFromGroup: vi.fn(),
}))
const modalOpen = vi.hoisted(() => vi.fn())
const notifications = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))

vi.mock('../../../composables/device/devicesPort', () => ({ devicesPort: ports }))
vi.mock('../../../composables/modal/useNotification', () => ({ useNotification: () => notifications }))
vi.mock('../../../composables/modal/useModal', () => ({ useModalControl: () => ({ open: modalOpen }) }))

import DeviceGroupManager from '../DeviceGroupManager.vue'
import { MODAL_TYPES } from '../../../composables/modal/constants'

const GROUPS = [
  { id: 'g1', name: '会议室组', groupType: 'test', description: '', deviceCount: 3 },
  { id: 'g2', name: '空分组', groupType: 'playback', description: '', deviceCount: 0 },
]

beforeEach(() => {
  vi.clearAllMocks()
  ports.getGroups.mockResolvedValue({ items: GROUPS })
  ports.deleteGroup.mockResolvedValue({})
})

async function mountWithGroups() {
  const w = mount(DeviceGroupManager, { props: { visible: false, testDevices: [] } })
  await w.setProps({ visible: true })
  await flushPromises()
  return w
}

const findRowDeleteButton = (w: ReturnType<typeof mount>, rowName: string) => {
  const row = w.findAll('tbody tr').find(r => r.text().includes(rowName))!
  return row.findAll('button').find(b => b.text().includes('删除'))!
}

describe('DeviceGroupManager 删除分组（INT-286）', () => {
  it('打开 BASIC_CONFIRM（danger）确认模态，文案含分组名与成员数提示', async () => {
    modalOpen.mockResolvedValue({ confirmed: true })
    const w = await mountWithGroups()

    await findRowDeleteButton(w, '会议室组').trigger('click')

    expect(modalOpen).toHaveBeenCalledTimes(1)
    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.BASIC_CONFIRM, expect.objectContaining({
      title: '删除设备分组',
      danger: true,
      confirmText: '删除',
    }))
    const content = modalOpen.mock.calls[0][1].content as string
    expect(content).toContain('会议室组')
    expect(content).toContain('3 个设备')
  })

  it('确认后按 (id, true) 下发 deleteGroup 并成功反馈', async () => {
    modalOpen.mockResolvedValue({ confirmed: true })
    const w = await mountWithGroups()

    await findRowDeleteButton(w, '会议室组').trigger('click')
    await flushPromises()

    expect(ports.deleteGroup).toHaveBeenCalledWith('g1', true)
    expect(notifications.success).toHaveBeenCalledWith('分组已删除')
  })

  it('取消（open reject）→ 不下发 deleteGroup', async () => {
    modalOpen.mockRejectedValue(new Error('cancel'))
    const w = await mountWithGroups()

    await findRowDeleteButton(w, '空分组').trigger('click')
    await flushPromises()

    expect(ports.deleteGroup).not.toHaveBeenCalled()
  })

  it('空分组文案不含成员数提示', async () => {
    modalOpen.mockResolvedValue({ confirmed: true })
    const w = await mountWithGroups()

    await findRowDeleteButton(w, '空分组').trigger('click')

    const content = modalOpen.mock.calls[0][1].content as string
    expect(content).toBe('确定删除分组「空分组」吗？')
  })
})
