/**
 * INT-286/INT-863：设备分组删除确认回归（window.confirm → BASIC_CONFIRM danger 模态）。
 *
 * 锁定口径：
 * - 删除分组打开 BASIC_CONFIRM（title=删除设备分组、danger=true），文案含分组名与成员提示
 * - 含子分组（INT-863）：文案升级为「包含 {n} 个设备与 {m} 个子分组」，仍走 cascade=true
 * - 确认（open resolve）→ deleteGroup(id, true) 下发并刷新；取消（reject）→ 不下发
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const ports = vi.hoisted(() => ({
  getGroups: vi.fn(),
  getGroup: vi.fn(),
  createGroup: vi.fn(),
  updateGroup: vi.fn(),
  moveGroup: vi.fn(),
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
  { id: 'g1', name: '会议室组', groupType: 'test', description: '', deviceCount: 3, parentId: null, children: [] },
  { id: 'g2', name: '空分组', groupType: 'playback', description: '', deviceCount: 0, parentId: null, children: [] },
]

/** 含子分组的父分组（INT-863 文案升级用例） */
const PARENT_WITH_CHILDREN = [
  {
    id: 'p1', name: '根分组A', groupType: 'test', description: '', deviceCount: 2, parentId: null,
    children: [
      { id: 'c1', name: '子分组1', groupType: 'test', description: '', deviceCount: 0, parentId: 'p1', children: [] },
      { id: 'c2', name: '子分组2', groupType: 'playback', description: '', deviceCount: 0, parentId: 'p1', children: [] },
    ],
  },
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

describe('DeviceGroupManager 删除分组（INT-286/INT-863）', () => {
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

  it('取消（resolve null）→ 不下发 deleteGroup', async () => {
    // INT-1011：取消收敛为 resolve(null)，不再是 rejection
    modalOpen.mockResolvedValue(null)
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

  it('含子分组时文案升级：包含 {n} 个设备与 {m} 个子分组（INT-863）', async () => {
    ports.getGroups.mockResolvedValue({ items: PARENT_WITH_CHILDREN })
    modalOpen.mockResolvedValue({ confirmed: true })
    const w = await mountWithGroups()

    await findRowDeleteButton(w, '根分组A').trigger('click')

    const content = modalOpen.mock.calls[0][1].content as string
    expect(content).toBe(
      '分组「根分组A」包含 2 个设备与 2 个子分组。删除分组会把设备移出分组、子分组一并删除（设备本身保留），确定删除吗？'
    )
    expect(ports.deleteGroup).toHaveBeenCalledWith('p1', true)
  })
})
