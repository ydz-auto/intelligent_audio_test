/**
 * INT-1323：确认弹窗自定义 message 丢失 —— 基座层归一回归
 *
 * 现象：设备域等确认弹窗（BASIC_CONFIRM / DELETE_CONFIRM）调用方传 `message` 键，
 * ModalConfirm 只消费 `content`（默认「确定要执行此操作吗？」）→ 定制说明丢失。
 *
 * 修复口径（useModal.open 基座层收敛）：调用方未显式传 `content` 时，以 `message`
 * 兜底为 content；并以 `type: 'danger'` 兼容 `danger: true`。逐一改 100+ 调用点
 * 成本高，基座层归一后全部确认弹窗自动生效。
 *
 * 回归锁定（真实容器链路，非单测直挂组件，同 INT-274）：
 * 1) BASIC_CONFIRM + message → 正文渲染 message 定制文案；
 * 2) content 显式传入时优先（兼容已统一为 content 的调用方，INT-274 契约不回退）；
 * 3) message + type: 'danger' → danger 图标样式生效（--danger class）；
 * 4) DELETE_CONFIRM + message → 同样渲染 message（不受 defaultConfig content 干扰）。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import GlobalModalContainer from '../GlobalModalContainer.vue'
import ModalConfirm from '../ModalConfirm.vue'
import { getModalManager } from '../../../../composables/modal/useModal'
import { MODAL_TYPES } from '../../../../composables/modal/constants'

describe('INT-1323 确认弹窗 message → content 基座层归一', () => {
  const confirmDefault = { title: '确认操作', content: '确定要执行此操作吗？', confirmText: '确定', cancelText: '取消', danger: false }
  const deleteDefault = { title: '删除确认', content: '确定要执行此操作吗？', confirmText: '确定', cancelText: '取消', danger: true }

  let wrapper: ReturnType<typeof mount> | undefined
  const manager = getModalManager()

  beforeEach(() => {
    manager.closeAll()
    manager.registerModal(MODAL_TYPES.BASIC_CONFIRM, { component: ModalConfirm, defaultConfig: confirmDefault })
    manager.registerModal(MODAL_TYPES.DELETE_CONFIRM, { component: ModalConfirm, defaultConfig: deleteDefault })
    wrapper = mount(GlobalModalContainer)
  })

  afterEach(() => {
    manager.closeAll()
    wrapper?.unmount()
    wrapper = undefined
  })

  it('BASIC_CONFIRM + message：正文渲染调用方定制文案（修复前显示默认文案）', async () => {
    const p = manager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认批量删除',
      message: '确定要删除选中的 2 个设备吗？',
      confirmText: '删除',
      cancelText: '取消',
    })
    await flushPromises()

    expect(document.body.querySelector('.modal-confirmMessage')?.textContent)
      .toBe('确定要删除选中的 2 个设备吗？')
    manager.closeAll()
    await p.catch(() => {})
  }, 60000)

  it('content 显式传入时优先：message 不作为兜底覆盖', async () => {
    const p = manager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除',
      content: '确定要删除该测试用例吗？',
      message: '应被忽略的兜底文案',
      danger: true,
    })
    await flushPromises()

    expect(document.body.querySelector('.modal-confirmMessage')?.textContent)
      .toBe('确定要删除该测试用例吗？')
    manager.closeAll()
    await p.catch(() => {})
  }, 60000)

  it('message + type: "danger"：危险确认图标样式生效（type 归一为 danger）', async () => {
    const p = manager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除',
      message: '确定要删除该设备吗？',
      type: 'danger',
      confirmText: '删除',
      cancelText: '取消',
    })
    await flushPromises()

    const icon = document.body.querySelector('.modal-confirmIcon')
    expect(icon?.classList.contains('modal-confirmIcon--danger')).toBe(true)
    expect(document.body.querySelector('.modal-confirmMessage')?.textContent)
      .toBe('确定要删除该设备吗？')
    manager.closeAll()
    await p.catch(() => {})
  }, 60000)

  it('DELETE_CONFIRM + message：同样渲染 message，不受 defaultConfig content 干扰', async () => {
    const p = manager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '确认清除',
      message: '确定要清除所有日志吗？此操作不可撤销。',
      confirmText: '确定清除',
      cancelText: '取消',
    })
    await flushPromises()

    expect(document.body.querySelector('.modal-confirmMessage')?.textContent)
      .toBe('确定要清除所有日志吗？此操作不可撤销。')
    manager.closeAll()
    await p.catch(() => {})
  }, 60000)
})
