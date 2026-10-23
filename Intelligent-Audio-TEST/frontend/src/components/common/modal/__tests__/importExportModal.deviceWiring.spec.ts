/**
 * INT-1628：ImportExportModal 设备导入导出接线
 *
 * 覆盖：
 * 1) 预览按所选文件真实解析（不再出现「示例数据1/2/3」）；
 * 2) 导入走真实动作 → 弹窗内展示成功/更新/跳过计数 + 逐行错误 + 「状态以本环境为准」，
 *    成功后回调 onImported（列表/统计刷新），点「完成」才关闭；
 * 3) 导入失败（服务端 400 / 解析失败）错误留在弹窗内、不关闭；
 * 4) 不支持扩展名 / 空文件在本地拦截且不发请求；
 * 5) 导出走真实动作，范围/格式透传，失败不静默；
 * 6) 取消不发请求，重开无残留文件。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ImportExportModal from '../ImportExportModal.vue'

function selectFile(wrapper: ReturnType<typeof mount>, file: File) {
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  return input.trigger('change')
}

/** 等待异步文件读取/预览完成（FileReader 为宏任务，flushPromises 不保证已跑完） */
async function waitFor(predicate: () => boolean, timeout = 1000) {
  const startedAt = Date.now()
  while (!predicate()) {
    if (Date.now() - startedAt > timeout) throw new Error('waitFor timeout')
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
}

const DEVICES_JSON = JSON.stringify([
  { name: '接线测试_设备A', serial_number: 'SN-A', status: 'offline' },
  { name: '接线测试_设备B', serial_number: 'SN-B', status: 'offline' },
])

const baseProps = {
  title: '导入测试设备',
  mode: 'import',
  supportedFormats: ['json', 'csv', 'excel'],
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('INT-1628 导入弹窗', () => {
  it('预览为真实解析的前 N 行，不再出现示例数据', async () => {
    const wrapper = mount(ImportExportModal, { props: { ...baseProps } })
    await selectFile(wrapper, new File([DEVICES_JSON], 'devices.json', { type: 'application/json' }))
    await flushPromises()
    await waitFor(() => wrapper.find('.preview-table-container').exists())
    const preview = wrapper.find('.preview-table-container')
    expect(preview.text()).toContain('接线测试_设备A')
    expect(preview.text()).toContain('接线测试_设备B')
    expect(wrapper.text()).not.toContain('示例数据')
  })

  it('导入成功：展示计数/错误/状态口径，回调 onImported，点「完成」回传结果并关闭', async () => {
    const importAction = vi.fn().mockResolvedValue({
      importedCount: 1,
      updatedCount: 2,
      skippedCount: 1,
      errors: ['第3行: 缺少匹配键 serial_number'],
    })
    const onImported = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(ImportExportModal, {
      props: { ...baseProps, importAction, onImported },
    })

    await selectFile(wrapper, new File([DEVICES_JSON], 'devices.json', { type: 'application/json' }))
    await flushPromises()
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(importAction).toHaveBeenCalledTimes(1)
    expect(importAction.mock.calls[0][0]).toBeInstanceOf(File)
    expect(onImported).toHaveBeenCalledWith(expect.objectContaining({ importedCount: 1 }))

    expect(wrapper.find('.import-result-summary').text())
      .toBe('成功导入 1 个，更新 2 个，跳过 1 个')
    expect(wrapper.find('.import-result-note').text()).toBe('状态以本环境为准')
    expect(wrapper.find('.import-result-errors').text()).toContain('第3行')

    // 成功后不直接关闭：点「完成」才 confirm
    expect(wrapper.emitted('confirm')).toBeUndefined()
    const finish = wrapper.findAll('button').find((button) => button.text().includes('完成'))!
    await finish.trigger('click')
    const confirmPayload = wrapper.emitted('confirm')?.[0]?.[0] as any
    expect(confirmPayload).toMatchObject({ mode: 'import' })
    expect(confirmPayload.result).toMatchObject({ importedCount: 1, updatedCount: 2, skippedCount: 1 })
  })

  it('导入失败：错误可见、弹窗不关闭、不触发 onImported', async () => {
    const importAction = vi.fn().mockRejectedValue(new Error('导入数据为空'))
    const onImported = vi.fn()
    const wrapper = mount(ImportExportModal, {
      props: { ...baseProps, importAction, onImported },
    })

    await selectFile(wrapper, new File([DEVICES_JSON], 'devices.json'))
    await flushPromises()
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('.export-error').text()).toContain('导入数据为空')
    expect(onImported).not.toHaveBeenCalled()
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.find('.import-result').exists()).toBe(false)
    // 仍可重试/取消
    expect(wrapper.find('input[type="file"]').exists()).toBe(true)
  })

  it('不支持的扩展名：本地拦截并给出可见文案，不发请求', async () => {
    const importAction = vi.fn()
    const wrapper = mount(ImportExportModal, { props: { ...baseProps, importAction } })

    await selectFile(wrapper, new File(['hello'], 'devices.txt', { type: 'text/plain' }))
    await flushPromises()
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(importAction).not.toHaveBeenCalled()
    expect(wrapper.find('.export-error').text()).toContain('不支持的导入文件（.txt）')
    expect(wrapper.find('.export-error').text()).toContain('JSON / CSV / Excel')
  })

  it('空文件：本地拦截', async () => {
    const importAction = vi.fn()
    const wrapper = mount(ImportExportModal, { props: { ...baseProps, importAction } })

    await selectFile(wrapper, new File([], 'devices.json'))
    await flushPromises()
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(importAction).not.toHaveBeenCalled()
    expect(wrapper.find('.export-error').text()).toContain('文件为空')
  })

  it('取消不发请求；未选文件时导入按钮禁用（重开无残留）', async () => {
    const importAction = vi.fn()
    const wrapper = mount(ImportExportModal, { props: { ...baseProps, importAction } })

    const submit = wrapper.findAll('button').find((button) => button.text().includes('开始导入'))!
    expect(submit.attributes('disabled')).toBeDefined()
    await wrapper.findAll('button').find((button) => button.text().includes('取消'))!.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(importAction).not.toHaveBeenCalled()
  })

  it('提供 importAction 时不再派发旧 confirm 载荷（避免双口径）', async () => {
    const importAction = vi.fn().mockResolvedValue({ importedCount: 0, updatedCount: 0, skippedCount: 0, errors: [] })
    const wrapper = mount(ImportExportModal, { props: { ...baseProps, importAction } })
    await selectFile(wrapper, new File([DEVICES_JSON], 'devices.json'))
    await flushPromises()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const confirmPayload = wrapper.emitted('confirm')?.[0]?.[0] as any
    // 已提供真实动作时 confirm 只在点「完成」出现（且带 result），本次尚未点
    expect(confirmPayload).toBeUndefined()
  })
})

describe('INT-1628 导出弹窗', () => {
  it('导出动作透传格式/范围/字段；成功后 confirm 回传文件名', async () => {
    const exportAction = vi.fn().mockResolvedValue({ filename: 'test_devices_20261024_101500.json' })
    const wrapper = mount(ImportExportModal, {
      props: {
        mode: 'export',
        title: '导出测试设备',
        supportedFormats: ['json', 'excel'],
        exportRanges: [
          { value: 'all', label: '全部数据' },
          { value: 'selected', label: '选中数据（0 台）', disabled: true, hint: '请先在列表中勾选设备' },
          { value: 'filtered', label: '筛选后数据（2 台）' },
        ],
        exportAction,
      },
    })

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(exportAction).toHaveBeenCalledWith({ format: 'json', range: 'all', fields: [] })
    expect(wrapper.emitted('confirm')?.[0]?.[0]).toMatchObject({
      mode: 'export',
      result: { filename: 'test_devices_20261024_101500.json' },
    })
    // 不可选范围置灰并给出原因
    const selectedRadio = wrapper.find('#range-selected')
    expect(selectedRadio.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('请先在列表中勾选设备')
  })

  it('选中导出：范围切换后 exportAction 收到 range=selected', async () => {
    const exportAction = vi.fn().mockResolvedValue({ filename: 'x.json' })
    const wrapper = mount(ImportExportModal, {
      props: {
        mode: 'export',
        supportedFormats: ['json', 'excel'],
        exportRanges: [
          { value: 'all', label: '全部数据' },
          { value: 'selected', label: '选中数据（2 台）' },
        ],
        exportAction,
      },
    })

    await wrapper.find('#range-selected').setValue(true)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(exportAction).toHaveBeenCalledWith({ format: 'json', range: 'selected', fields: [] })
  })

  it('导出失败：错误可见且不当作文件下载（不 confirm）', async () => {
    const exportAction = vi.fn().mockRejectedValue(new Error('不支持的导出格式: csv'))
    const wrapper = mount(ImportExportModal, {
      props: { mode: 'export', supportedFormats: ['json', 'excel'], exportAction },
    })

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('.export-error').text()).toContain('不支持的导出格式')
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })
})
