/**
 * INT-274：GlobalModalContainer 确认分支必须执行 caller 的 onSave，且确认弹窗显示定制文案
 *
 * 回归覆盖（真实容器链路，非单测直挂组件）：ModalConfirm 只消费 `content` prop
 * （`message` 键不显示定制文案）；容器 @confirm 分支调用 `props.onSave`（而非 onConfirm）。
 * INT-274 修复口径：业务侧统一传 `content` + `onSave`。本用例锁定该契约在真实容器
 * （v-bind 透传 props + @confirm/@cancel 监听）下成立：
 * 1) DELETE_CONFIRM 正文渲染 content 定制文案，点「确定清除」→ 容器调用 onSave 恰好一次；
 * 2) IMPORT_EXPORT（export）点「开始导出」→ onSave 收到 { mode, config } 载荷（logView
 *    据此映射 range/format 调 logsPort.export）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import GlobalModalContainer from '../GlobalModalContainer.vue'
import ModalConfirm from '../ModalConfirm.vue'
import ImportExportModal from '../ImportExportModal.vue'
import { getModalManager } from '../../../../composables/modal/useModal'
import { MODAL_TYPES } from '../../../../composables/modal/constants'

describe('INT-274 容器 onSave 契约', () => {
  beforeEach(() => {
    const manager = getModalManager()
    manager.closeAll()
    manager.registerModal(MODAL_TYPES.DELETE_CONFIRM, { component: ModalConfirm, defaultConfig: { title: '删除确认', content: '确定要执行此操作吗？', confirmText: '确定', cancelText: '取消', danger: true } })
    manager.registerModal(MODAL_TYPES.IMPORT_EXPORT, { component: ImportExportModal, defaultConfig: { mode: 'import' } })
  })

  it('DELETE_CONFIRM + content/onSave：正文显示定制文案，确认后 onSave 被容器调用', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const manager = getModalManager()
    mount(GlobalModalContainer)
    const p = manager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '确认清除',
      content: '确定要清除所有日志吗？此操作不可撤销。',
      confirmText: '确定清除',
      cancelText: '取消',
      onSave,
    })
    await flushPromises()

    // ModalConfirm 只消费 content：定制确认文案必须显示（修复前 message 键不显示）
    expect(document.body.querySelector('.modal-confirmMessage')?.textContent)
      .toBe('确定要清除所有日志吗？此操作不可撤销。')

    // 点「确定清除」→ 容器 @confirm 分支调 props.onSave（修复前传 onConfirm 时无人调用）
    const btns = Array.from(document.body.querySelectorAll('button'))
    btns.find(b => b.textContent?.includes('确定清除'))!.click()
    await flushPromises()
    await new Promise(r => setTimeout(r, 10))
    expect(onSave).toHaveBeenCalledTimes(1)
    await p.catch(() => {})
  }, 60000)

  it('IMPORT_EXPORT export + onSave：确认后 onSave 收到 { mode, config } 载荷', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const manager = getModalManager()
    mount(GlobalModalContainer)
    const p = manager.open(MODAL_TYPES.IMPORT_EXPORT, {
      mode: 'export',
      title: '导出日志',
      supportedFormats: ['json', 'excel'],
      exportFields: [{ key: 'time', label: '时间', defaultChecked: true }],
      onSave,
    })
    await flushPromises()

    const btns = Array.from(document.body.querySelectorAll('button'))
    btns.find(b => b.textContent?.includes('开始导出'))!.click()
    await flushPromises()
    await new Promise(r => setTimeout(r, 10))

    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave.mock.calls[0][0]).toMatchObject({ mode: 'export' })
    // logView 依据 config.range/config.format 映射导出参数
    expect(onSave.mock.calls[0][0].config).toMatchObject({ format: 'json', range: 'all' })
    await p.catch(() => {})
  }, 60000)
})
