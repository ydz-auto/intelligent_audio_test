/**
 * INT-467（UX 审计 P3）：VisibilitySelector 单测。
 * 锁定契约：缺省共享（双选说明文案）；切换私有/共享触发 update:modelValue 与 change 事件。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import VisibilitySelector from '../VisibilitySelector.vue'
import { Visibility } from '@/domain/enums'

describe('VisibilitySelector', () => {
  it('缺省选中共享', () => {
    const wrapper = mount(VisibilitySelector)
    const shared = wrapper.find('input[value="shared"]').element as HTMLInputElement
    const priv = wrapper.find('input[value="private"]').element as HTMLInputElement
    expect(shared.checked).toBe(true)
    expect(priv.checked).toBe(false)
  })

  it('modelValue=private 时选中私有', () => {
    const wrapper = mount(VisibilitySelector, { props: { modelValue: Visibility.PRIVATE } })
    const shared = wrapper.find('input[value="shared"]').element as HTMLInputElement
    const priv = wrapper.find('input[value="private"]').element as HTMLInputElement
    expect(shared.checked).toBe(false)
    expect(priv.checked).toBe(true)
  })

  it('点击私有选项派发 update:modelValue 与 change', async () => {
    const wrapper = mount(VisibilitySelector)
    const privInput = wrapper.find('input[value="private"]')
    await privInput.setValue()
    const update = wrapper.emitted('update:modelValue')
    const change = wrapper.emitted('change')
    expect(update).toBeTruthy()
    expect(update?.[0]).toEqual([Visibility.PRIVATE])
    expect(change?.[0]).toEqual([Visibility.PRIVATE])
  })

  it('点击共享选项派发 shared', async () => {
    const wrapper = mount(VisibilitySelector, { props: { modelValue: Visibility.PRIVATE } })
    const sharedInput = wrapper.find('input[value="shared"]')
    await sharedInput.setValue()
    const update = wrapper.emitted('update:modelValue')
    expect(update?.[0]).toEqual([Visibility.SHARED])
  })
})
