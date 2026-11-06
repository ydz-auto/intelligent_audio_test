/**
 * useAlgorithmDraft 单测（INT-601，17_配置运维.md §6.2/§6.2a）：
 * 30s 自动保存（首次变脏启动/变更重置/校验不过暂停/归零静默写草稿）+ 手动/失焦防抖保存 toast
 * + 快照重置不关 Sheet + 失败不自动重试 + 乐观锁冲突 → draftConflict。
 * 用 fake timers 驱动 useCountdown 归零；断言 saveDraft 只收聚合载荷（草稿级聚合，无逐参失焦端点）。
 */
import { act, renderHook } from '@testing-library/react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAlgorithmDraft } from '../useAlgorithmDraft'
import { DRAFT_MESSAGES } from '@/features/algorithm-config/constants'
import { algorithmDraftFormSchema } from '@/features/algorithm-config/mutate/algorithm-form-schema'
import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import { AlgorithmConflictError } from '@/infrastructure/api/algorithm-config-api'

const VALID_EDIT_VALUES: AlgorithmFormValues = {
  type: 'asr-v3',
  name: '语音识别',
  groupId: '1',
  displayOrder: 0,
  status: 'online',
  description: '',
  deviceParams: [],
  caseParams: [],
  referenceParams: [],
  mappings: { device: [], evaluation: [] },
  associatedDimensions: [],
}

type DraftMock = ReturnType<typeof createDraftMock>

/** 伪 saveDraft：可配 resolve/reject/conflict，返回草稿结果 */
function createDraftMock(
  behavior: 'resolve' | 'reject' | 'conflict' = 'resolve'
) {
  const saveDraft = vi.fn().mockImplementation(
    async (_input: unknown, _revision?: number) => {
      if (behavior === 'reject') throw new Error('mock 草稿保存失败')
      if (behavior === 'conflict') throw new AlgorithmConflictError(2)
      return { revision: 1, savedAt: new Date().toISOString() }
    }
  )
  return { saveDraft }
}

function useHarness(props: {
  open: boolean
  mode?: 'edit' | 'create'
  draft: DraftMock
}) {
  const form = useForm<AlgorithmFormValues>({
    mode: 'onChange',
    resolver: zodResolver(algorithmDraftFormSchema),
    defaultValues: VALID_EDIT_VALUES,
  })
  const draft = useAlgorithmDraft({
    open: props.open,
    form,
    mode: props.mode ?? 'edit',
    schema: algorithmDraftFormSchema,
    saveDraft: props.draft.saveDraft,
  })
  return { form, ...draft }
}

describe('useAlgorithmDraft', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(toast, 'success')
    vi.spyOn(toast, 'error')
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('表单干净（未编辑）不启动倒计时', () => {
    const draft = createDraftMock()
    const { result } = renderHook(() => useHarness({ open: true, draft }))
    expect(result.current.isActive).toBe(false)
    expect(result.current.isValidationBlocked).toBe(false)
  })

  it('首次变脏启动 30s 倒计时', () => {
    const draft = createDraftMock()
    const { result } = renderHook(() => useHarness({ open: true, draft }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))

    expect(result.current.isActive).toBe(true)
    expect(result.current.secondsLeft).toBe(30)
    expect(draft.saveDraft).not.toHaveBeenCalled()
  })

  it('每次内容变更重置回 30s', () => {
    const draft = createDraftMock()
    const { result } = renderHook(() => useHarness({ open: true, draft }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    act(() => vi.advanceTimersByTime(10_000))
    expect(result.current.secondsLeft).toBe(20)

    act(() => result.current.form.setValue('description', '补充说明', { shouldDirty: true }))
    expect(result.current.secondsLeft).toBe(30)
  })

  it('归零后静默写草稿：时间戳更新 + 快照重置不关 Sheet，无「草稿已保存」toast', async () => {
    const draft = createDraftMock()
    const { result } = renderHook(() => useHarness({ open: true, draft }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    await act(async () => {
      vi.advanceTimersByTime(30_000)
      await Promise.resolve()
    })

    expect(draft.saveDraft).toHaveBeenCalledTimes(1)
    // 草稿级聚合载荷：整表字段（无逐参端点）+ revision 透传
    const input = draft.saveDraft.mock.calls[0][0] as {
      type: string
      name: string
      deviceParams: unknown[]
    }
    expect(input.type).toBe('asr-v3')
    expect(input.name).toBe('语音识别-v2')
    expect(input.deviceParams).toEqual([])
    // 30s 自动保存静默：不弹 toast
    expect(toast.success).not.toHaveBeenCalledWith(DRAFT_MESSAGES.saved)
    // 快照重置：isDirty 归零（脏态守卫不再误弹），编辑值保留，Sheet 未关
    expect(result.current.form.formState.isDirty).toBe(false)
    expect(result.current.form.getValues('name')).toBe('语音识别-v2')
    expect(result.current.lastSavedAt).not.toBeNull()
  })

  it('手动保存草稿：toast「草稿已保存」+ 时间戳更新', async () => {
    const draft = createDraftMock()
    const { result } = renderHook(() => useHarness({ open: true, draft }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    await act(async () => {
      await result.current.saveDraftNow()
    })

    expect(draft.saveDraft).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalledWith(DRAFT_MESSAGES.saved)
    expect(result.current.form.formState.isDirty).toBe(false)
  })

  it('校验不过暂停（倒计时停 + Alert）；修正后重新计时', () => {
    const draft = createDraftMock()
    const { result } = renderHook(() => useHarness({ open: true, draft }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    expect(result.current.isActive).toBe(true)

    // 结构级门槛不满足（§6.2：参数代码非空）→ 草稿校验不过 → 暂停
    act(() =>
      result.current.form.setValue('deviceParams', [
        { key: 'd-1', paramCode: '', paramName: '', direction: 'input', paramType: 'text', required: false, defaultValue: '', helpText: '' },
      ], { shouldDirty: true })
    )
    expect(result.current.isActive).toBe(false)
    expect(result.current.isValidationBlocked).toBe(true)
    expect(draft.saveDraft).not.toHaveBeenCalled()

    // 修正 → 重新计时
    act(() =>
      result.current.form.setValue('deviceParams', [
        { key: 'd-1', paramCode: 'good_code', paramName: '', direction: 'input', paramType: 'text', required: false, defaultValue: '', helpText: '' },
      ], { shouldDirty: true })
    )
    expect(result.current.isActive).toBe(true)
    expect(result.current.isValidationBlocked).toBe(false)
  })

  it('正则不符/类型未选的参数代码不再阻断草稿（§6.2 草稿宽松：正则/类型草稿阶段不校验）', () => {
    const draft = createDraftMock()
    const { result } = renderHook(() => useHarness({ open: true, draft }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    expect(result.current.isActive).toBe(true)

    // 参数代码含连字符/大写（发布正则非法）且参数类型未选（发布必填）——草稿宽松放行
    act(() =>
      result.current.form.setValue('deviceParams', [
        { key: 'd-1', paramCode: 'input-audio-V1', paramName: '', direction: 'input', paramType: '', required: false, defaultValue: '', helpText: '' },
      ], { shouldDirty: true })
    )
    expect(result.current.isValidationBlocked).toBe(false)
    expect(result.current.isActive).toBe(true)
  })

  it('保存失败：toast「草稿保存失败，请检查网络后重试」且不自动重试', async () => {
    const draft = createDraftMock('reject')
    const { result } = renderHook(() => useHarness({ open: true, draft }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    await act(async () => {
      vi.advanceTimersByTime(30_000)
      await Promise.resolve()
    })

    expect(draft.saveDraft).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledWith(DRAFT_MESSAGES.failure)
    expect(result.current.form.formState.isDirty).toBe(true)
    expect(result.current.isActive).toBe(false)
    expect(result.current.draftConflict).toBe(false)
  })

  it('乐观锁冲突：草稿保存 409 → draftConflict=true（footer「草稿已过期」）', async () => {
    const draft = createDraftMock('conflict')
    const { result } = renderHook(() => useHarness({ open: true, draft }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    await act(async () => {
      await result.current.saveDraftNow()
    })

    expect(result.current.draftConflict).toBe(true)
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('失焦防抖保存：blur 调度 1.5s 后写草稿 + toast「草稿已保存」', async () => {
    const draft = createDraftMock()
    const { result } = renderHook(() => useHarness({ open: true, draft }))

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    act(() => result.current.scheduleBlurSave())
    expect(draft.saveDraft).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(1500)
      await Promise.resolve()
    })

    expect(draft.saveDraft).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalledWith(DRAFT_MESSAGES.saved)
  })

  it('Sheet 关闭停止倒计时且不触发保存，草稿冲突/时间戳复位', () => {
    const draft = createDraftMock()
    const { result, rerender } = renderHook(
      (props: { open: boolean; draft: DraftMock }) => useHarness(props),
      { initialProps: { open: true, draft } }
    )

    act(() => result.current.form.setValue('name', '语音识别-v2', { shouldDirty: true }))
    expect(result.current.isActive).toBe(true)

    rerender({ open: false, draft })
    expect(result.current.isActive).toBe(false)
    expect(result.current.lastSavedAt).toBeNull()
    expect(draft.saveDraft).not.toHaveBeenCalled()
  })
})
