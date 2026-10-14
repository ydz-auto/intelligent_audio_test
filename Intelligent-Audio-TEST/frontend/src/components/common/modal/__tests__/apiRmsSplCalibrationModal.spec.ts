/**
 * INT-330：API RMS-SPL 校准弹窗行级校验阻塞提交 —— 组件单测。
 *
 * 锁定口径：
 * - 缺陷1：行级校验错误存在时提交按钮禁用（isValid === false），超范围值不再放行落库
 *   （含未触碰的既有坏点：打开弹窗即亮红字并阻塞）
 * - 缺陷1 边角：touched 按行 uid 记账，删行后标记不错位（红字不丢失、未编辑行不误报）
 * - 缺陷2：「按参考生成」入口恒显示；已有非空点集时两步确认防误覆盖，空点集直接生成
 * - 合法点集提交走 onConfirm + confirm 事件
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import ApiRmsSplCalibrationModal from '../ApiRmsSplCalibrationModal.vue'
import type { ApiCalibrationPoint } from '../../../../domain'

type ConfirmFn = (payload: { points: ApiCalibrationPoint[] }) => Promise<void>

const BASE_DATA = {
  referenceSpl: 65,
  referenceGainLinear: 1.0,
  minGainLinear: 0.001,
  maxGainLinear: 10.0,
}

const mountModal = (data: Record<string, unknown> = {}, onConfirm?: ConfirmFn) =>
  mount(ApiRmsSplCalibrationModal, {
    props: {
      mappingId: 1,
      mappingName: '映射A',
      apiId: 7,
      data: { ...BASE_DATA, ...data },
      onConfirm,
    },
  })

/** 数据行（排除表头行） */
const dataRows = (w: ReturnType<typeof mount>) =>
  w.findAll('.point-row').filter(r => !r.classes().includes('point-row--head'))

const submitBtn = (w: ReturnType<typeof mount>) => w.find('.modal-footer .btn-primary')

/** 定位某行的目标 SPL / 线性增益输入框 */
const rowInputs = (row: ReturnType<typeof dataRows>[number]) => row.findAll('input')

describe('INT-330 缺陷1：行级校验阻塞提交', () => {
  it('既有坏点（targetSpl=500）挂载即亮红字并禁用提交（未触碰也阻塞）', () => {
    const w = mountModal({
      calibrationPoints: [
        { targetSpl: 500, gainLinear: 1 },
        { targetSpl: 65, gainLinear: 1 },
      ],
    })

    expect(dataRows(w)[0].classes()).toContain('has-error')
    expect(w.find('.point-error').text()).toContain('目标 SPL')
    expect(submitBtn(w).attributes('disabled')).toBeDefined()
    expect((w.vm as any).isValid).toBe(false)
  })

  it('手输超范围值时禁用；改回合法值后放行并提交 onConfirm', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    const w = mountModal({}, onConfirm)

    // 空弹窗：无有效点，本就不可提交
    expect(submitBtn(w).attributes('disabled')).toBeDefined()

    await w.findAll('button').find(b => b.text().includes('添加校准点'))!.trigger('click')
    let rows = dataRows(w)
    expect(rows).toHaveLength(1)

    await rowInputs(rows[0])[0].setValue('500')
    await rowInputs(rows[0])[1].setValue('1')
    expect(submitBtn(w).attributes('disabled')).toBeDefined()
    expect((w.vm as any).isValid).toBe(false)

    // 改回合法值 → 解禁并正常提交
    await rowInputs(rows[0])[0].setValue('80')
    expect((w.vm as any).isValid).toBe(true)
    expect(submitBtn(w).attributes('disabled')).toBeUndefined()

    await submitBtn(w).trigger('click')
    await flushPromises()
    // onConfirm 仅一次（回归：emit('confirm') 会经 v-bind 透传的 onConfirm 监听器二次触发提交）
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onConfirm).toHaveBeenCalledWith({ points: [{ targetSpl: 80, gainLinear: 1, rmsDbfs: undefined }] })
    // 成功后关弹窗（对齐设备域：显式回调 + close 事件）
    expect(w.emitted('close')).toBeTruthy()
  })

  it('线性增益超限幅上限时阻塞提交', async () => {
    const w = mountModal()
    await w.findAll('button').find(b => b.text().includes('添加校准点'))!.trigger('click')

    const rows = dataRows(w)
    await rowInputs(rows[0])[0].setValue('80')
    await rowInputs(rows[0])[1].setValue('50') // > maxGainLinear 10.0

    expect(w.find('.point-error').text()).toContain('增益超出限幅')
    expect(submitBtn(w).attributes('disabled')).toBeDefined()
    expect((w.vm as any).isValid).toBe(false)
  })

  it('删行后 touched 按行 uid 记账不错位：剩余行的红字不丢失', async () => {
    const w = mountModal()
    const addBtn = w.findAll('button').find(b => b.text().includes('添加校准点'))!
    await addBtn.trigger('click')
    await addBtn.trigger('click')

    let rows = dataRows(w)
    expect(rows).toHaveLength(2)

    // 第二行手输超范围值 → 红字出现
    await rowInputs(rows[1])[0].setValue('500')
    expect(w.findAll('.point-error')).toHaveLength(1)

    // 删除第一行 → 旧实现按行索引记账会丢标记、红字消失；uid 记账红字仍在
    await rows[0].find('.icon-btn').trigger('click')
    rows = dataRows(w)
    expect(rows).toHaveLength(1)
    expect(rows[0].classes()).toContain('has-error')
    expect(w.findAll('.point-error')).toHaveLength(1)
    expect(submitBtn(w).attributes('disabled')).toBeDefined()
  })

  it('既有合法点集不受阻塞：提交按钮可用', () => {
    const w = mountModal({
      calibrationPoints: [
        { targetSpl: 45, gainLinear: 0.1 },
        { targetSpl: 85, gainLinear: 10 },
      ],
    })
    expect(w.findAll('.point-error')).toHaveLength(0)
    expect((w.vm as any).isValid).toBe(true)
    expect(submitBtn(w).attributes('disabled')).toBeUndefined()
  })
})

describe('INT-330 缺陷2：按参考生成入口恒显示', () => {
  it('已有点集时入口仍显示；点击一次不覆盖（进入确认态），再点覆盖为 5 点', async () => {
    const w = mountModal({
      calibrationPoints: [
        { targetSpl: 30, gainLinear: 0.5 },
        { targetSpl: 90, gainLinear: 2 },
      ],
    })

    const genBtn = w.findAll('button').find(b => b.text().includes('按参考生成'))!
    expect(genBtn).toBeTruthy()

    // 第一次点击：不覆盖，进入确认态
    await genBtn.trigger('click')
    expect(dataRows(w)).toHaveLength(2)
    expect((rowInputs(dataRows(w)[0])[0].element as HTMLInputElement).value).toBe('30')
    expect(genBtn.text()).toContain('再点一次确认覆盖')

    // 第二次点击：覆盖为参考生成的 5 点（65dB 中心 ±20dB / 每 10dB 一点）
    await genBtn.trigger('click')
    const rows = dataRows(w)
    expect(rows).toHaveLength(5)
    const targets = rows.map(r => Number((rowInputs(r)[0].element as HTMLInputElement).value))
    expect(targets).toEqual([45, 55, 65, 75, 85])
    expect((w.vm as any).isValid).toBe(true)
  })

  it('空点集时点击直接生成（无需两步确认）', async () => {
    const w = mountModal()
    const genBtn = w.findAll('button').find(b => b.text().includes('按参考生成'))!
    await genBtn.trigger('click')
    expect(dataRows(w)).toHaveLength(5)
    expect(genBtn.text()).not.toContain('再点一次确认覆盖')
  })
})
