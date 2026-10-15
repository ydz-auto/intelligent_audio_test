/**
 * INT-286：InputConfirmModal 单测（单字段表单输入确认模态，替代业务侧 window.prompt）。
 *
 * 锁定口径：
 * - 确认载荷 { value }（已 trim）；取消发 cancel 事件
 * - required（默认 true）：空/纯空白值确认按钮禁用且不 emit
 * - validate：返回错误文案时按钮禁用 + 行内错误可见，不 emit
 * - danger：确认按钮标红（btn-danger）；默认 btn-primary
 * - initialValue 预填；Enter 键等价点击确认
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

import InputConfirmModal from '../InputConfirmModal.vue'

const mountModal = (props: Record<string, unknown> = {}) =>
  mount(InputConfirmModal, {
    props: { modalId: 'm1', title: '输入', label: '名称', ...props },
  })

const findConfirmButton = (w: ReturnType<typeof mount>) =>
  w.findAll('button').find(b => b.text().includes('确定') || b.text().includes('确认') || b.text().includes('保存'))!

describe('InputConfirmModal（INT-286）', () => {
  it('确认：载荷携带 trim 后的 value，取消：发 cancel 事件', async () => {
    const w = mountModal({ initialValue: '  hello  ' })
    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')![0][0]).toEqual({ value: 'hello' })

    await w.findAll('button')[0].trigger('click')
    expect(w.emitted('cancel')).toHaveLength(1)
  })

  it('required（默认）：空值与纯空白值确认按钮禁用且不 emit', async () => {
    const empty = mountModal()
    expect((findConfirmButton(empty).element as HTMLButtonElement).disabled).toBe(true)
    await findConfirmButton(empty).trigger('click')
    expect(empty.emitted('confirm')).toBeUndefined()

    const blank = mountModal({ initialValue: '   ' })
    expect((findConfirmButton(blank).element as HTMLButtonElement).disabled).toBe(true)
  })

  it('required=false：允许空值确认（载荷携带空串）', async () => {
    const w = mountModal({ required: false })
    expect((findConfirmButton(w).element as HTMLButtonElement).disabled).toBe(false)
    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')![0][0]).toEqual({ value: '' })
  })

  it('validate 返回错误文案：按钮禁用 + 行内错误可见，不 emit；改合法后恢复', async () => {
    const w = mountModal({ initialValue: 'a b', validate: (v: string) => (/\s/.test(v) ? '不能包含空白' : null) })
    expect(w.find('.form-error').text()).toBe('不能包含空白')
    expect((findConfirmButton(w).element as HTMLButtonElement).disabled).toBe(true)
    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')).toBeUndefined()

    await w.find('input').setValue('ab')
    expect(w.find('.form-error').exists()).toBe(false)
    expect((findConfirmButton(w).element as HTMLButtonElement).disabled).toBe(false)
    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')![0][0]).toEqual({ value: 'ab' })
  })

  it('danger=true 确认按钮标红；默认主色', () => {
    const danger = mountModal({ danger: true, confirmText: '确认卸载' })
    expect(findConfirmButton(danger).classes()).toContain('btn-danger')

    const normal = mountModal({ confirmText: '保存' })
    expect(findConfirmButton(normal).classes()).toContain('btn-primary')
  })

  it('Enter 键等价点击确认（合法输入时）', async () => {
    const w = mountModal({ initialValue: 'abc' })
    await w.find('input').trigger('keydown.enter')
    expect(w.emitted('confirm')![0][0]).toEqual({ value: 'abc' })
  })

  it('渲染 label 与 hint', () => {
    const w = mountModal({ label: '应用包名', hint: '同名允许重复保存' })
    expect(w.find('.input-label').text()).toContain('应用包名')
    expect(w.find('.form-hint').text()).toBe('同名允许重复保存')
  })
})
