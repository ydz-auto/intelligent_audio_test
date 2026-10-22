/**
 * INT-1285：任务导出失败经 toUserErrorMessage 降级，不泄漏原始 RPC/gRPC 文本。
 *
 * 覆盖：原始 gRPC 异常（RESOURCE_EXHAUSTED 大包超限）→ 展示固定友好文案；
 * 正常业务错误 → 原样展示；成功 → 下载 ZIP 并 emit exported / close。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  exportTasks: vi.fn(),
  downloadBlob: vi.fn(),
}))

vi.mock('../../../composables/task/dataTransferPort', () => ({
  dataTransferPort: { exportTasks: mocks.exportTasks },
}))

vi.mock('../../../utils/utils', () => ({
  downloadBlob: mocks.downloadBlob,
}))

import TaskDataExportDialog from '../TaskDataExportDialog.vue'

const mountDialog = () =>
  mount(TaskDataExportDialog, {
    props: { tasks: [{ id: 402, name: '任务402', status: 'completed' }] },
  })

const clickStart = async (wrapper: ReturnType<typeof mountDialog>) => {
  await wrapper.find('.dt-btn-primary').trigger('click')
  await flushPromises()
}

describe('TaskDataExportDialog 导出错误降级（INT-1285）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('原始 gRPC 文本（RESOURCE_EXHAUSTED）→ 固定友好文案，不泄漏原文', async () => {
    mocks.exportTasks.mockRejectedValue(
      new Error(
        '<_InactiveRpcError of RPC that terminated with: status=StatusCode.RESOURCE_EXHAUSTED ' +
          'details="CLIENT: Received message larger than max (23448138 vs. 4194304)">',
      ),
    )
    const wrapper = mountDialog()
    await clickStart(wrapper)

    const err = wrapper.find('.dt-error')
    expect(err.exists()).toBe(true)
    expect(err.text()).toBe('导出失败，请稍后重试')
    expect(err.text()).not.toContain('InactiveRpcError')
    expect(err.text()).not.toContain('RESOURCE_EXHAUSTED')
    expect(err.text()).not.toContain('23448138')
  })

  it('正常业务错误 → 原样展示（不走降级）', async () => {
    mocks.exportTasks.mockRejectedValue(new Error('参数校验失败'))
    const wrapper = mountDialog()
    await clickStart(wrapper)

    expect(wrapper.find('.dt-error').text()).toBe('参数校验失败')
  })

  it('导出成功 → 下载 ZIP 并 emit exported / close，无错误文案', async () => {
    mocks.exportTasks.mockResolvedValue(new Blob(['zip-bytes']))
    const wrapper = mountDialog()
    await clickStart(wrapper)

    expect(mocks.downloadBlob).toHaveBeenCalledWith(
      expect.any(Blob),
      expect.stringMatching(/^task_export_\d{14}\.zip$/),
    )
    expect(wrapper.emitted('exported')).toBeTruthy()
    expect(wrapper.emitted('close')).toBeTruthy()
    expect(wrapper.find('.dt-error').exists()).toBe(false)
  })
})
