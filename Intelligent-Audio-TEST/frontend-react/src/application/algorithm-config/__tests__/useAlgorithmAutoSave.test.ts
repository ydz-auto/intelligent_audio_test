/**
 * useAlgorithmAutoSave 单测（INT-585，17_配置运维.md §6.1a）：
 * 首次变脏启动 30s / 每次变更重置 / 校验不过暂停 / 归零聚合提交自动保存
 * （成功 toast+快照重置不关 Sheet / 失败转手动不重试）/ 关闭不触发保存 / isNew 派生。
 * 用 fake timers 驱动 useCountdown 归零；断言 save.mutateAsync 只收聚合载荷（无逐参失焦保存）。
 */
import { act, renderHook } from '@testing-library/react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAlgorithmAutoSave } from '../useAlgorithmAutoSave'
import { AUTO_SAVE_MESSAGES } from '@/features/algorithm-config/constants'
import { algorithmEditFormSchema } from '@/features/algorithm-config/mutate/algorithm-form-schema'
import type { AlgorithmFormValues } from '@/features/algorithm-config/types'

const VALID_EDIT_VALUES: AlgorithmFormValues = {
  type: 'asr-v3',
  name: '语音识别',
  groupId: '1',
  displayOrder: 0,
  status: 'online',
  description: '',
  deviceParams: [],
  apiParams: [],
  caseParams: [],
  referenceParams: [],
  mappings: { device: [], api: [], evaluation: [] },
  associatedDimensions: [],
}

type SaveMock = {
  mutateAsync: ReturnType<typeof vi.fn>
  readonly isPending: boolean
}

/** 伪 save mutation：isPending 跟随调用实时切换（对齐 react-query UseMutationResult 语义） */
function createSaveMock(behavior: 'resolve' | 'reject' = 'resolve'): SaveMock {
  let pending = false
  const mutateAsync = vi.fn().mockImplementation(async (input: unknown) => {
    pending = true
    try {
      if (behavior === 'reject') throw new Error('mock 保存失败')
      return { id: 1, saved: input }
    } finally {
      pending = false
    }
  })
  return {
    mutateAsync,
    get isPending() {
      return pending
    },
  }
}

function useHarness(props: { open: boolean; mode?: 'edit' | 'create'; save: SaveMock }) {
  const form = useForm<AlgorithmFormValues>({
    mode: 'onChange',
    resolver: zodResolver(algorithmEditFormSchema),
    defaultValues: VALID_EDIT_VALUES,
  })
  const autoSave = useAlgorithmAutoSave({
    open: props.open,
    form,
    mode: props.mode ?? 'edit',
    schema: algorithmEditFormSchema,
    // vitest Mock 与 hook 签名（mutateAsync 具体入参）不直接兼容：断言需 Mock 的 .mock 元数据，
    // 传参边界做一次类型收窄（INT-585 遗留 typecheck 错误修复）
    save: props.save as unknown as Parameters<typeof useAlgorithmAutoSave>[0]['save'],
  })
  return { form, ...autoSave }
}

describe('useAlgorithmAutoSave', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(toast, 'success')
    vi.spyOn(toast, 'error')
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('表单干净（未编辑）不启动倒计时', () => {
    const save = createSaveMock()
    const { result } = renderHook(() => useHarness({ open: true, save }))
    expect(result.current.isActive).toBe(false)
    expect(result.current.isValidationBlocked).toBe(false)
  })

  it('首次变脏启动 30s 倒计时', () => {
    const save = createSaveMock()
    const { result } = renderHook(() => useHarness({ open: true, save }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))

    expect(result.current.isActive).toBe(true)
    expect(result.current.secondsLeft).toBe(30)
    expect(save.mutateAsync).not.toHaveBeenCalled()
  })

  it('每次内容变更重置回 30s', () => {
    const save = createSaveMock()
    const { result } = renderHook(() => useHarness({ open: true, save }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    act(() => vi.advanceTimersByTime(10_000))
    expect(result.current.secondsLeft).toBe(20)

    // 再次编辑 → 重置回 30
    act(() => result.current.form.setValue('description', '补充说明', { shouldDirty: true }))
    expect(result.current.secondsLeft).toBe(30)
  })

  it('归零后聚合提交自动保存：toast「已自动保存」+ 快照重置不关 Sheet', async () => {
    const save = createSaveMock()
    const { result } = renderHook(() => useHarness({ open: true, save }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    await act(async () => {
      vi.advanceTimersByTime(30_000)
      await Promise.resolve()
    })

    expect(save.mutateAsync).toHaveBeenCalledTimes(1)
    // 聚合载荷：整表字段 + isNew=false（编辑态走 PUT），无逐参失焦保存
    const input = save.mutateAsync.mock.calls[0][0] as {
      type: string
      name: string
      deviceParams: unknown[]
      isNew: boolean
    }
    expect(input.type).toBe('asr-v3')
    expect(input.name).toBe('语音识别-v2')
    expect(input.deviceParams).toEqual([])
    expect(input.isNew).toBe(false)
    expect(toast.success).toHaveBeenCalledWith(AUTO_SAVE_MESSAGES.success)

    // 快照重置：isDirty 归零（脏态守卫不再误弹），编辑值保留，Sheet 未关
    expect(result.current.form.formState.isDirty).toBe(false)
    expect(result.current.form.getValues('name')).toBe('语音识别-v2')
    expect(result.current.isActive).toBe(false)
  })

  it('create 模式自动保存载荷 isNew=true（走 POST）', async () => {
    const save = createSaveMock()
    const { result } = renderHook(() =>
      useHarness({ open: true, mode: 'create', save })
    )

    act(() => result.current.form.setValue('name', '新建算法', { shouldDirty: true }))
    await act(async () => {
      vi.advanceTimersByTime(30_000)
      await Promise.resolve()
    })

    const input = save.mutateAsync.mock.calls[0][0] as { isNew: boolean }
    expect(input.isNew).toBe(true)
  })

  it('校验不过暂停（Alert 显示）；修正后重新计时', () => {
    const save = createSaveMock()
    const { result } = renderHook(() => useHarness({ open: true, save }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    expect(result.current.isActive).toBe(true)

    // 改成非法值（name 必填为空）→ 暂停 + 校验不过 Alert
    act(() => result.current.form.setValue('name', '', { shouldDirty: true }))
    expect(result.current.isActive).toBe(false)
    expect(result.current.isValidationBlocked).toBe(true)
    expect(save.mutateAsync).not.toHaveBeenCalled()

    // 修正 → 重新计时
    act(() => result.current.form.setValue('name', '语音识别-v3', { shouldDirty: true }))
    expect(result.current.isActive).toBe(true)
    expect(result.current.secondsLeft).toBe(30)
    expect(result.current.isValidationBlocked).toBe(false)
  })

  it('校验不过时倒计时归零不触发保存', async () => {
    const save = createSaveMock()
    const { result } = renderHook(() => useHarness({ open: true, save }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    act(() => vi.advanceTimersByTime(10_000))
    // 校验不过 → 暂停
    act(() => result.current.form.setValue('name', '', { shouldDirty: true }))
    await act(async () => {
      vi.advanceTimersByTime(30_000)
      await Promise.resolve()
    })

    expect(save.mutateAsync).not.toHaveBeenCalled()
    expect(result.current.isValidationBlocked).toBe(true)
  })

  it('自动保存失败：toast「自动保存失败，已恢复手动保存」且不自动重试', async () => {
    const save = createSaveMock('reject')
    const { result } = renderHook(() => useHarness({ open: true, save }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    await act(async () => {
      vi.advanceTimersByTime(30_000)
      await Promise.resolve()
    })

    expect(save.mutateAsync).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledWith(AUTO_SAVE_MESSAGES.failure)
    // 失败保留编辑态：表单仍脏、不关 Sheet、倒计时不再自动重启
    expect(result.current.form.formState.isDirty).toBe(true)
    expect(result.current.isActive).toBe(false)
  })

  it('Sheet 关闭停止倒计时且不触发保存', () => {
    const save = createSaveMock()
    const { result, rerender } = renderHook(
      (props: { open: boolean; save: SaveMock }) => useHarness(props),
      { initialProps: { open: true, save } }
    )

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    expect(result.current.isActive).toBe(true)

    rerender({ open: false, save })
    expect(result.current.isActive).toBe(false)
    expect(save.mutateAsync).not.toHaveBeenCalled()
  })

  it('手动保存成功路径（快照重置）不触发自动保存', () => {
    const save = createSaveMock()
    const { result } = renderHook(() => useHarness({ open: true, save }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    // 手动保存成功 = form.reset(form.getValues())（§6.1a 快照重置口径）
    act(() =>
      result.current.form.reset(result.current.form.getValues())
    )

    expect(result.current.form.formState.isDirty).toBe(false)
    expect(result.current.isActive).toBe(false)
    expect(save.mutateAsync).not.toHaveBeenCalled()
  })
})
