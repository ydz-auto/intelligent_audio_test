/**
 * INT-1377：SPL 表单边界值无校验（distance=0 / test_frequency=30000 可落库）
 *
 * 根因：CRUDFormModal 表单 novalidate + useFormValidation 只校验必填/正则/array，
 * 不校验 number 字段的 min/max。本用例锁定 JS 侧 min/max 兜底：
 * - distance（min=0.1）填 0 → 拦截并报「不能小于 0.1」；
 * - testFrequency（min=20, max=20000）填 30000 → 拦截并报「不能大于 20000」；
 * - 边界值本身（0.1 / 20000）通过；
 * - v-model number input 返回 string，字符串形式同样校验。
 */
import { describe, it, expect } from 'vitest'
import { useFormValidation } from '../useFormValidation'

const distanceField = { key: 'distance', label: '测量距离 (米)', type: 'number', required: true, min: 0.1 }
const testFrequencyField = { key: 'testFrequency', label: '测试频率 (Hz)', type: 'number', required: true, min: 20, max: 20000 }

describe('useFormValidation 数字字段 min/max 边界校验（INT-1377）', () => {
  it('distance 填 0（低于 min=0.1）时拦截并报错', () => {
    const { validateForm, errors } = useFormValidation()
    const ok = validateForm([distanceField], { distance: 0 })
    expect(ok).toBe(false)
    expect(errors.distance).toBe('测量距离 (米)不能小于 0.1')
  })

  it('testFrequency 填 30000（超过 max=20000）时拦截并报错', () => {
    const { validateForm, errors } = useFormValidation()
    const ok = validateForm([testFrequencyField], { testFrequency: 30000 })
    expect(ok).toBe(false)
    expect(errors.testFrequency).toBe('测试频率 (Hz)不能大于 20000')
  })

  it('number input 的字符串形式（"0"）同样被拦截', () => {
    const { validateForm, errors } = useFormValidation()
    const ok = validateForm([distanceField], { distance: '0' })
    expect(ok).toBe(false)
    expect(errors.distance).toBe('测量距离 (米)不能小于 0.1')
  })

  it('边界值本身（distance=0.1 / testFrequency=20000）通过校验', () => {
    const { validateForm, errors } = useFormValidation()
    const ok = validateForm([distanceField, testFrequencyField], { distance: 0.1, testFrequency: 20000 })
    expect(ok).toBe(true)
    expect(Object.keys(errors)).toHaveLength(0)
  })

  it('低于 min 的值通过 validateField 单字段校验时同样被拦截', () => {
    const { validateField, errors } = useFormValidation()
    const ok = validateField(testFrequencyField, 30000)
    expect(ok).toBe(false)
    expect(errors.testFrequency).toBe('测试频率 (Hz)不能大于 20000')
  })

  it('未配置 min/max 的数字字段不受影响（如结果最小值）', () => {
    const { validateForm, errors } = useFormValidation()
    const plainNumber = { key: 'resultMin', label: '结果最小值', type: 'number', required: true }
    const ok = validateForm([plainNumber], { resultMin: -100 })
    expect(ok).toBe(true)
    expect(errors.resultMin).toBeUndefined()
  })
})
