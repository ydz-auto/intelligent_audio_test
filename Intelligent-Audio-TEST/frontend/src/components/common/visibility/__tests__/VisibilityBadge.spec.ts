/**
 * INT-467（UX 审计 P3）：VisibilityBadge 单测。
 * 锁定契约：仅私有资源渲染锁徽标（.vis-badge--private）；共享/缺省不渲染（减少视觉噪音）。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import VisibilityBadge from '../VisibilityBadge.vue'
import { Visibility } from '@/domain/enums'

describe('VisibilityBadge', () => {
  it('共享可见性不渲染徽标', () => {
    const wrapper = mount(VisibilityBadge, { props: { visibility: Visibility.SHARED } })
    expect(wrapper.find('.vis-badge').exists()).toBe(false)
  })

  it('缺省（undefined）不渲染徽标', () => {
    const wrapper = mount(VisibilityBadge, { props: {} })
    expect(wrapper.find('.vis-badge').exists()).toBe(false)
  })

  it('私有可见性渲染锁徽标（.vis-badge--private + 锁图标）', () => {
    const wrapper = mount(VisibilityBadge, { props: { visibility: Visibility.PRIVATE } })
    const badge = wrapper.find('.vis-badge--private')
    expect(badge.exists()).toBe(true)
    expect(badge.find('i.fa-lock').exists()).toBe(true)
    expect(badge.text()).toContain('私有')
  })

  it('未知可见性值不渲染（白名单外不误展示）', () => {
    const wrapper = mount(VisibilityBadge, { props: { visibility: 'everyone' } })
    expect(wrapper.find('.vis-badge').exists()).toBe(false)
  })
})
