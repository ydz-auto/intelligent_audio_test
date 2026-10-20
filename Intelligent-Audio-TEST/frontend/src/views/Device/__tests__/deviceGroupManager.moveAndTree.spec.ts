/**
 * INT-863：设备分组嵌套渲染（树）与移动操作单元测试。
 *
 * 锁定口径：
 * - 扁平列表按 parent_id 建树：父级行有 Chevron，展开后子分组行缩进显示
 * - 「移动」：startMove 打开目标父分组选择器（根=顶层），确认后调 moveGroup(id, parentId)
 * - 新建/编辑表单可选父分组（根或任一分组），编辑时排除自身与后代
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

/** 树形夹具：根 A（子 C1/C2）+ 独立根 B；children 由测试侧按 adapter 建树口径预挂 */
const TREE_GROUPS = [
  {
    id: 'a', name: '根分组A', groupType: 'test', description: '', deviceCount: 2, parentId: null,
    children: [
      { id: 'c1', name: '子分组1', groupType: 'test', description: '', deviceCount: 0, parentId: 'a', children: [] },
      { id: 'c2', name: '子分组2', groupType: 'playback', description: '', deviceCount: 0, parentId: 'a', children: [] },
    ],
  },
  { id: 'b', name: '根分组B', groupType: 'test', description: '', deviceCount: 0, parentId: null, children: [] },
]

beforeEach(() => {
  vi.clearAllMocks()
  ports.getGroups.mockResolvedValue({ items: TREE_GROUPS })
  ports.moveGroup.mockResolvedValue({})
  ports.getGroup.mockResolvedValue({ id: 'a', name: '根分组A', deviceIds: [] })
})

async function mountWithGroups() {
  const w = mount(DeviceGroupManager, { props: { visible: false, testDevices: [] } })
  await w.setProps({ visible: true })
  await flushPromises()
  return w
}

describe('DeviceGroupManager 树形渲染（INT-863）', () => {
  it('默认只显示根分组，子分组不展开', async () => {
    const w = await mountWithGroups()

    const bodyText = w.find('tbody').text()
    expect(bodyText).toContain('根分组A')
    expect(bodyText).toContain('根分组B')
    expect(bodyText).not.toContain('子分组1')
  })

  it('点击 Chevron 展开后显示子分组，再次点击折叠', async () => {
    const w = await mountWithGroups()

    const chevron = w.find('tbody button.dg-chevron')
    expect(chevron.exists()).toBe(true)
    await chevron.trigger('click')
    await flushPromises()

    let bodyText = w.find('tbody').text()
    expect(bodyText).toContain('子分组1')
    expect(bodyText).toContain('子分组2')

    // 折叠
    await chevron.trigger('click')
    await flushPromises()
    bodyText = w.find('tbody').text()
    expect(bodyText).not.toContain('子分组1')
  })
})

describe('DeviceGroupManager 移动（INT-863）', () => {
  it('点击「移动」打开目标父分组选择器，根分组B移入根分组A', async () => {
    const w = await mountWithGroups()

    const rowB = w.findAll('tbody tr').find(r => r.text().includes('根分组B'))!
    const moveBtn = rowB.findAll('button').find(b => b.text().includes('移动'))!
    await moveBtn.trigger('click')
    await flushPromises()

    // 选择器出现且含「根分组（顶层）」与候选父分组
    const select = w.find('.dg-form select')
    expect(select.exists()).toBe(true)
    const options = select.findAll('option').map(o => o.text())
    expect(options).toContain('根分组（顶层）')
    expect(options).toContain('根分组A')

    // 选根分组A并确认
    await select.setValue('a')
    await w.find('.dg-form .btn-primary').trigger('click')
    await flushPromises()

    expect(ports.moveGroup).toHaveBeenCalledWith('b', 'a')
    expect(notifications.success).toHaveBeenCalledWith('分组已移动')
  })

  it('选择「根分组（顶层）」移动后调 moveGroup(id, null)', async () => {
    const w = await mountWithGroups()

    // 展开树让子分组行可见后，将子分组2移到顶层
    await w.find('tbody button.dg-chevron').trigger('click')
    await flushPromises()
    const rowC2 = w.findAll('tbody tr').find(r => r.text().includes('子分组2'))!
    const moveBtn = rowC2.findAll('button').find(b => b.text().includes('移动'))!
    await moveBtn.trigger('click')
    await flushPromises()

    const select = w.find('.dg-form select')
    await select.setValue('')
    await w.find('.dg-form .btn-primary').trigger('click')
    await flushPromises()

    expect(ports.moveGroup).toHaveBeenCalledWith('c2', null)
  })
})

describe('DeviceGroupManager 新建/编辑父分组选项（INT-863）', () => {
  it('新建表单可选根或任一分组', async () => {
    const w = await mountWithGroups()

    await w.find('.dg-toolbar .btn-primary').trigger('click')
    await flushPromises()

    const select = w.find('.dg-form select')
    const options = select.findAll('option').map(o => o.text())
    expect(options).toContain('根分组（顶层）')
    expect(options).toContain('根分组A')
    expect(options).toContain('根分组B')
  })

  it('编辑已有分组时表单回显 parentId，且选项不含自身与后代', async () => {
    const w = await mountWithGroups()

    // 展开树让子分组行可见后编辑子分组1
    await w.find('tbody button.dg-chevron').trigger('click')
    await flushPromises()
    const rowC1 = w.findAll('tbody tr').find(r => r.text().includes('子分组1'))!
    const editBtn = rowC1.findAll('button').find(b => b.text().includes('编辑'))!
    await editBtn.trigger('click')
    await flushPromises()

    const select = w.find('.dg-form select')
    expect((select.element as HTMLSelectElement).value).toBe('a')
    const options = select.findAll('option').map(o => o.text())
    expect(options).not.toContain('子分组1') // 自身排除
  })

  it('编辑/移动后提交 createGroup/updateGroup 携带 parentId', async () => {
    const w = await mountWithGroups()

    await w.find('.dg-toolbar .btn-primary').trigger('click')
    await flushPromises()
    const select = w.find('.dg-form select')
    await select.setValue('a')
    await w.find('.dg-form input').setValue('新子分组')
    await w.find('.dg-form .btn-primary').trigger('click')
    await flushPromises()

    expect(ports.createGroup).toHaveBeenCalledWith(expect.objectContaining({ parentId: 'a' }))
  })
})
