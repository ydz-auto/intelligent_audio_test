/**
 * INT-2044：音频试听配置弹窗（播放模式 / 播放设备 / 声压级 / 偏移量）
 *
 * 锁定契约（对齐 React 版试听弹窗 audio-preview-dialog.tsx）：
 * 1. 默认浏览器播放：不走设备，确认直接起播（device=null）；
 * 2. 实验室播放：列真实播放设备、默认首台，确认时把所选设备带给播放器；
 * 3. 无可用播放设备：实验室播放给出空态提示，且「开始试听」禁用（不得用假设备兜底）；
 * 4. 再次打开复用上次模式与设备（initial* props），失效设备回退首台。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import AudioPreviewConfigModal from '../AudioPreviewConfigModal.vue'

const devices = [
  { id: 1, name: '音箱0°', model: 'RME Fireface UCX II' },
  { id: 2, name: '音箱90°' },
] as any[]

function mountModal(overrides: Record<string, unknown> = {}) {
  return mount(AudioPreviewConfigModal, {
    props: {
      visible: true,
      audioTitle: 'url_src_A.wav',
      playbackDevices: devices,
      ...overrides,
    },
    global: { stubs: { teleport: true } },
  })
}

const selectLabMode = async (wrapper: any) => {
  await wrapper.find('input[type="radio"][value="backend"]').setValue(true)
  await wrapper.vm.$nextTick()
}

const confirmBtn = (wrapper: any) =>
  wrapper.findAll('button').find((b: any) => b.text().includes('开始试听'))

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('AudioPreviewConfigModal（INT-2044 试听配置）', () => {
  it('默认浏览器播放：设备区不渲染，确认送出 backend 之外的模式且不带设备', async () => {
    const wrapper = mountModal()

    expect(wrapper.findAll('select[aria-label="播放设备"]')).toHaveLength(0)
    await confirmBtn(wrapper)!.trigger('click')

    const payload = wrapper.emitted('confirm')?.[0]?.[0] as any
    expect(payload.playbackMode).toBe('frontend')
    expect(payload.device).toBeNull()
    expect(payload.spl).toBe(65)
    expect(payload.offset).toBe(0)
  })

  it('实验室播放：列出真实播放设备，默认首台，确认带上所选设备', async () => {
    const wrapper = mountModal()
    await selectLabMode(wrapper)

    const select = wrapper.find('select[aria-label="播放设备"]')
    expect(select.exists()).toBe(true)
    const options = select.findAll('option')
    expect(options).toHaveLength(2)
    expect((select.element as HTMLSelectElement).value).toBe('1')
    expect(select.text()).toContain('音箱0°')

    await confirmBtn(wrapper)!.trigger('click')
    const payload = wrapper.emitted('confirm')?.[0]?.[0] as any
    expect(payload.playbackMode).toBe('backend')
    expect(payload.device?.id).toBe(1)
    expect(payload.device?.name).toBe('音箱0°')
  })

  it('无可用播放设备：实验室播放给出空态提示且开始试听禁用', async () => {
    const wrapper = mountModal({ playbackDevices: [] })
    await selectLabMode(wrapper)

    expect(wrapper.findAll('select[aria-label="播放设备"]')).toHaveLength(0)
    expect(wrapper.find('.device-empty').exists()).toBe(true)
    expect(wrapper.find('.device-empty').text()).toContain('暂无可用的播放设备')
    expect(confirmBtn(wrapper)!.attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })

  it('复用上次配置：initialPlaybackMode/initialSpl/initialOffset 回填，失效设备回退首台', async () => {
    const wrapper = mountModal({
      initialPlaybackMode: 'backend',
      initialDeviceId: '999',
      initialSpl: 80,
      initialOffset: 3,
    })
    await wrapper.vm.$nextTick()

    const select = wrapper.find('select[aria-label="播放设备"]')
    expect((select.element as HTMLSelectElement).value).toBe('1')
    const numbers = wrapper.findAll('input[type="number"]')
    expect((numbers[0].element as HTMLInputElement).value).toBe('80')
    expect((numbers[1].element as HTMLInputElement).value).toBe('3')

    await confirmBtn(wrapper)!.trigger('click')
    const payload = wrapper.emitted('confirm')?.[0]?.[0] as any
    expect(payload.device?.id).toBe(1)
    expect(payload.spl).toBe(80)
    expect(payload.offset).toBe(3)
  })
})
