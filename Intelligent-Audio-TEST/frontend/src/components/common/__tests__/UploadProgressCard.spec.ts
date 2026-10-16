// VEGA-31 验收：上传失败文件的「逐文件失败原因」必须可见
//
// 后端拒绝错配秒传后返回的 message（可操作提示）由 audioImport.ts 写进 file.error，
// 而历史模板读的是 file.errorMessage —— 两者不一致会让提示在界面上完全不显示
// （只显示「N 个文件上传失败」）。本用例锁定模板对两个字段都认。
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import UploadProgressCard from '../UploadProgressCard.vue'

const REASON = '秒传未建用例：本次上传的「JS135.wav」与已有音频「JS121.wav」内容完全相同（md5 一致），但名称对不上…请把文件重命名为「JS121.wav」后重新上传'

function makeTask(file: Record<string, unknown>) {
  return {
    id: 1,
    totalFiles: 1,
    completedFiles: 0,
    failedFiles: 1,
    files: [
      { name: 'JS135.wav', size: 100, uploadedSize: 100, status: 'failed', ...file },
    ],
  }
}

function mountCard(file: Record<string, unknown>) {
  return mount(UploadProgressCard, {
    props: {
      uploadProgress: 100,
      currentTask: makeTask(file),
      currentUploadingFile: null,
      isRetryingFailed: false,
    },
  })
}

describe('UploadProgressCard 失败原因可见性（VEGA-31）', () => {
  it('file.error（audioImport.ts 实际写入的字段）能在界面上显示', () => {
    const wrapper = mountCard({ error: REASON })
    expect(wrapper.find('.error-message').exists()).toBe(true)
    expect(wrapper.find('.error-message').text()).toContain('JS135.wav')
    expect(wrapper.find('.error-message').text()).toContain('重命名')
  })

  it('file.errorMessage（历史字段）仍能显示', () => {
    const wrapper = mountCard({ errorMessage: 'Registration failed' })
    expect(wrapper.find('.error-message').text()).toContain('Registration failed')
  })

  it('两者都无时不渲染原因', () => {
    const wrapper = mountCard({})
    expect(wrapper.find('.error-message').exists()).toBe(false)
  })

  it('errorMessage 优先于 error（不改变既有展示口径）', () => {
    const wrapper = mountCard({ errorMessage: 'old', error: 'new' })
    expect(wrapper.find('.error-message').text()).toContain('old')
  })
})
