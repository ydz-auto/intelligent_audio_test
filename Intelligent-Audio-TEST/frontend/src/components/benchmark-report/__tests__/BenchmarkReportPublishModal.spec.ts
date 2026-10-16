/**
 * BenchmarkReportPublishModal 单测（INT-483 报告发布入口）
 *
 * 锁定口径：
 * - 确认载荷 { name, description?, suite?, category?, source? }（已 trim；空可选字段不发）
 * - name 必填：空/纯空白值确认按钮禁用且不 emit
 * - 取消发 close 事件
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

import BenchmarkReportPublishModal from '../BenchmarkReportPublishModal.vue'

const mountModal = (props: Record<string, unknown> = {}) =>
  mount(BenchmarkReportPublishModal, {
    props,
    // 弹窗内容经 Teleport 到 body：stub teleport 使其内联渲染，便于查询
    global: { stubs: { teleport: true } },
  })

const findConfirmButton = (w: ReturnType<typeof mount>) =>
  w.findAll('button').find(b => b.text().includes('发布'))!

describe('BenchmarkReportPublishModal（INT-483）', () => {
  it('确认：载荷携带 trim 后的 name/description/suite/category/source', async () => {
    const w = mountModal()
    await w.find('input.form-input').setValue('  LibriSpeech 基准报告  ')
    await w.find('textarea.form-textarea').setValue(' 正式回归  ')
    await w.find('input[placeholder*="librispeech"]').setValue('librispeech-test-clean')
    const selects = w.findAll('select.form-select')
    await selects[0].setValue('asr')
    await selects[1].setValue('platform_test')
    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')![0][0]).toEqual({
      name: 'LibriSpeech 基准报告',
      description: '正式回归',
      suite: 'librispeech-test-clean',
      category: 'asr',
      source: 'platform_test',
    })
  })

  it('name 必填：空值与纯空白值确认按钮禁用且不 emit', async () => {
    const empty = mountModal()
    expect((findConfirmButton(empty).element as HTMLButtonElement).disabled).toBe(true)
    await findConfirmButton(empty).trigger('click')
    expect(empty.emitted('confirm')).toBeUndefined()

    const blank = mountModal()
    await blank.find('input.form-input').setValue('   ')
    expect((findConfirmButton(blank).element as HTMLButtonElement).disabled).toBe(true)
    await findConfirmButton(blank).trigger('click')
    expect(blank.emitted('confirm')).toBeUndefined()
  })

  it('取消：发 close 事件', async () => {
    const w = mountModal()
    await w.findAll('button')[0].trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })
})
