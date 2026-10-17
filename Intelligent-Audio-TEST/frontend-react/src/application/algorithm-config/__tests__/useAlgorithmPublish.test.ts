/**
 * useAlgorithmPublish 单测（INT-601，17_配置运维.md §6.2/§6.2a）：
 * 发布成功 toast + onPublished 回调；发布冲突 → AlertDialog 态 + 刷新丢弃路径；
 * 发布钮可用性随严格 schema 实时计算。
 */
import { act, renderHook } from '@testing-library/react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAlgorithmPublish } from '../useAlgorithmPublish'
import { PUBLISH_MESSAGES } from '@/features/algorithm-config/constants'
import {
  algorithmEditFormSchema,
  algorithmFormSchema,
} from '@/features/algorithm-config/mutate/algorithm-form-schema'
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
  apiParams: [],
  caseParams: [],
  referenceParams: [],
  mappings: { device: [], api: [], evaluation: [] },
  associatedDimensions: [],
}

function createPublishMock(behavior: 'resolve' | 'conflict' | 'code-exists' = 'resolve') {
  const publish = vi.fn().mockImplementation(async () => {
    if (behavior === 'conflict') throw new AlgorithmConflictError(3)
    if (behavior === 'code-exists') {
      const err = new Error(PUBLISH_MESSAGES.codeExists)
      Object.assign(err, { status: 409 })
      throw err
    }
    return { id: 1 } as never
  })
  return publish
}

function useHarness(props: {
  open: boolean
  mode?: 'edit' | 'create'
  publish: ReturnType<typeof createPublishMock>
  onPublished?: () => void
}) {
  const mode = props.mode ?? 'edit'
  // create 态算法代码需走新建正则 ^[a-z][a-z0-9_]*$（asr-v3 含连字符仅编辑态合法）
  const defaults =
    mode === 'create' ? { ...VALID_EDIT_VALUES, type: 'asr_v3' } : VALID_EDIT_VALUES
  const form = useForm<AlgorithmFormValues>({
    mode: 'onChange',
    resolver: zodResolver(mode === 'create' ? algorithmFormSchema : algorithmEditFormSchema),
    defaultValues: defaults,
  })
  const publish = useAlgorithmPublish({
    open: props.open,
    form,
    mode,
    schema: mode === 'create' ? algorithmFormSchema : algorithmEditFormSchema,
    publish: props.publish,
    onPublished: props.onPublished ?? (() => {}),
  })
  return { form, ...publish }
}

describe('useAlgorithmPublish', () => {
  beforeEach(() => {
    vi.spyOn(toast, 'success')
    vi.spyOn(toast, 'error')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('发布成功：toast「算法已发布」+ onPublished 回调', async () => {
    const publish = createPublishMock('resolve')
    const onPublished = vi.fn()
    const { result } = renderHook(() =>
      useHarness({ open: true, publish, onPublished })
    )

    await act(async () => {
      await result.current.publishNow()
    })

    expect(publish).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalledWith(PUBLISH_MESSAGES.published)
    expect(onPublished).toHaveBeenCalledWith(false)
  })

  it('create 模式发布成功：toast「算法已创建」+ created=true', async () => {
    const publish = createPublishMock('resolve')
    const onPublished = vi.fn()
    const { result } = renderHook(() =>
      useHarness({ open: true, mode: 'create', publish, onPublished })
    )

    await act(async () => {
      await result.current.publishNow()
    })

    expect(toast.success).toHaveBeenCalledWith(PUBLISH_MESSAGES.created)
    expect(onPublished).toHaveBeenCalledWith(true)
  })

  it('发布冲突：publishConflict=true（AlertDialog 态）', async () => {
    const publish = createPublishMock('conflict')
    const { result } = renderHook(() => useHarness({ open: true, publish }))

    await act(async () => {
      await result.current.publishNow()
    })

    expect(result.current.publishConflict).toBe(true)
    expect(result.current.publishError).toBeNull()
  })

  it('发布冲突「继续编辑」清除冲突态返回表单', async () => {
    const publish = createPublishMock('conflict')
    const { result } = renderHook(() => useHarness({ open: true, publish }))

    await act(async () => {
      await result.current.publishNow()
    })
    expect(result.current.publishConflict).toBe(true)

    act(() => result.current.clearConflict())
    expect(result.current.publishConflict).toBe(false)
  })

  it('后端 409「算法代码已存在」→ publishError 表单级 Alert', async () => {
    const publish = createPublishMock('code-exists')
    const { result } = renderHook(() => useHarness({ open: true, publish }))

    await act(async () => {
      await result.current.publishNow()
    })

    expect(result.current.publishError).toBe(PUBLISH_MESSAGES.codeExists)
    expect(result.current.publishConflict).toBe(false)
  })

  it('严格校验不过：publishNow 不触发请求（字段级红字）', async () => {
    const publish = createPublishMock('resolve')
    const { result } = renderHook(() =>
      useHarness({ open: true, mode: 'create', publish })
    )

    // create 态缺算法代码正则（大写开头非法）
    act(() =>
      result.current.form.setValue('type', 'AsrV3', { shouldDirty: true })
    )
    await act(async () => {
      await result.current.publishNow()
    })

    expect(publish).not.toHaveBeenCalled()
    // 发布钮可用性随 schema 实时计算
    expect(result.current.isFormValid).toBe(false)
  })
})
