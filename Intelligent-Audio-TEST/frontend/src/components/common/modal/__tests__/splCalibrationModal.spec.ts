/**
 * INT-558：SPL 校准弹窗提交改走 emit('confirm') 容器链路 —— 组件单测。
 *
 * 锁定口径：
 * - 提交不再直接调 props.onConfirm —— GlobalModalContainer 在真实应用里经 v-bind + @confirm
 *   把 onConfirm 合并为数组（[原校准回调, 容器处理]），直接调用抛 TypeError，校准数据永不
 *   落库、弹窗停留。改 emit('confirm', calibrationData) 走容器链路。
 * - 载荷结构：points 点集 + signalType / testFrequency / measurementDistance / testDevice /
 *   calibrationDate / minDb / maxDb / mode='db_curve'。
 * - 容器集成路径（mergeProps 复刻容器合并）：emit 依次触发数组内全部监听器 → 原校准回调单次
 *   落库 + 容器 resolve/close（弹窗关闭）；组件自身不再 emit('close')。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, mergeProps, nextTick, ref } from 'vue'

const mocks = vi.hoisted(() => ({
  getAll: vi.fn(),
}))

// 从 __tests__/ 上溯 4 级到 src/，与 SPLCalibrationModal.vue 的模块路径对齐
vi.mock('../../../../composables/device/playbackPort', () => ({
  playbackPort: { getAll: mocks.getAll },
}))

import SPLCalibrationModal from '../SPLCalibrationModal.vue'

type ConfirmFn = (data: any) => Promise<void>

const BASE_PROPS = {
  mappingId: 1,
  mappingName: '映射A',
  data: { testDevice: 'dev-1', minDb: -60, maxDb: 0 },
}

const startBtn = (w: ReturnType<typeof mount>) => w.find('.modal-footer .btn-primary')

/** 推进校准模拟：11 个增益点各 300ms + 保存 500ms，随后 handleStart 同步走到 emit */
async function runCalibration(w: ReturnType<typeof mount>) {
  const btn = startBtn(w)
  expect(btn.attributes('disabled')).toBeUndefined()
  await btn.trigger('click')
  for (let i = 0; i < 11; i++) {
    await vi.advanceTimersByTimeAsync(300)
  }
  await vi.advanceTimersByTimeAsync(500)
  // handleStart 已同步完成 emit；换回真实定时器以安全 flush（fake 下 flushPromises 的 setImmediate 不触发）
  vi.useRealTimers()
  await flushPromises()
  await nextTick()
}

describe('INT-558 P1：提交走 emit(\'confirm\') 容器链路', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mocks.getAll.mockResolvedValue([])
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('提交 emit(\'confirm\') 且组件自身不再 emit(\'close\')，载荷含 db_curve 点集', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    const w = mount(SPLCalibrationModal, {
      props: { ...BASE_PROPS, onConfirm },
    })
    await nextTick()

    await runCalibration(w)

    // emit('confirm') 触发 onConfirm 监听器（直挂单函数 props 时单次调用）
    expect(onConfirm).toHaveBeenCalledTimes(1)
    const payload = onConfirm.mock.calls[0][0]
    expect(payload.mode).toBe('db_curve')
    expect(payload.points).toHaveLength(11)
    expect(payload.points[0]).toMatchObject({
      gain: 1,
      spl: expect.any(Number),
      db: expect.any(Number),
      linearGain: expect.any(Number),
    })
    expect(payload.testDevice).toBe('dev-1')
    expect(payload.signalType).toBe('sine')

    expect(w.emitted('confirm')).toBeTruthy()
    expect(w.emitted('confirm')?.[0]).toEqual([expect.objectContaining({ mode: 'db_curve' })])
    // 容器关闭语义：组件自身不再 emit('close')
    expect(w.emitted('close')).toBeUndefined()
  })
})

/**
 * INT-558 P1 回归：真实应用路径（GlobalModalContainer 渲染）下「开始校准」提交必须生效。
 *
 * GlobalModalContainer 模板 `<component v-bind="{...props}" @confirm="handler"/>` 经 Vue
 * mergeProps 把 onConfirm 合并为数组 `[原校准回调, 容器处理]`；若 handleStart 直接调
 * props.onConfirm 抛 TypeError（单测直挂单函数 props 拦不住这个集成缺陷）。这里用
 * mergeProps 复刻容器合并，锁定提交走 emit('confirm') → 原回调单次落库 + 容器处理
 * resolve/close。
 */
describe('INT-558 P1：容器集成路径（v-bind+@confirm 合并 onConfirm 数组）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mocks.getAll.mockResolvedValue([])
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  /** 复刻 GlobalModalContainer：v-bind 透传 props（含 onConfirm 原回调）+ @confirm 容器处理 */
  function mountViaContainer(
    originalConfirm: ConfirmFn,
    containerConfirm: (data: unknown) => void = () => {},
  ) {
    const open = ref(true)
    const ContainerWrapper = defineComponent({
      setup() {
        return () =>
          open.value
            ? h(
                SPLCalibrationModal,
                mergeProps(
                  {
                    ...BASE_PROPS,
                    onConfirm: originalConfirm, // modalManager.open 传入的原校准回调
                  },
                  {
                    // GlobalModalContainer :32-47 同款容器处理：resolve + close
                    onConfirm: (data: unknown) => {
                      containerConfirm(data)
                      open.value = false
                    },
                  },
                ) as any,
              )
            : null
      },
    })
    return mount(ContainerWrapper)
  }

  it('onConfirm 合并为数组时提交仍单次落库 + 容器关闭（不再抛 TypeError）', async () => {
    const originalConfirm = vi.fn().mockResolvedValue(undefined)
    const containerConfirm = vi.fn()
    const w = mountViaContainer(originalConfirm, containerConfirm)
    await nextTick()

    await runCalibration(w)

    // 原回调（容器 props.onConfirm[0]）单次触发 = 单次校准落库
    expect(originalConfirm).toHaveBeenCalledTimes(1)
    expect(originalConfirm.mock.calls[0][0]).toMatchObject({ mode: 'db_curve' })
    // 容器处理（props.onConfirm[1]）被 emit 触发 = resolve/close
    expect(containerConfirm).toHaveBeenCalledTimes(1)
    expect(containerConfirm.mock.calls[0][0]).toMatchObject({ mode: 'db_curve' })
    // 容器关闭语义生效：弹窗已被容器处理移除
    expect(w.find('.spl-calibration-modal').exists()).toBe(false)
  })
})
