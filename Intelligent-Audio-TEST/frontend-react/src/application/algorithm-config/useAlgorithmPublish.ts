/**
 * §6.2 发布编排（application 层；17_配置运维.md §11 落位）。
 * 挂 algorithm-mutate-sheet.tsx：显式「发布」→ 严格全量校验 → 后端发布事务 RPC →
 * toast「算法已发布/算法已创建」+ invalidate + 关 Sheet；发布冲突 409 → AlertDialog（§6.2a）。
 * 发布按钮 disabled 当 invalid（schema.safeParse 实时计算口径）。
 */
import { useCallback, useRef, useState } from 'react'
import type { UseFormReturn } from 'react-hook-form'
import { toast } from 'sonner'
import type { ZodType } from 'zod'

import { PUBLISH_MESSAGES } from '@/features/algorithm-config/constants'
import { toFormValues, toSaveInput } from '@/features/algorithm-config/mutate/form-converters'
import type {
  AlgorithmFormValues,
  MutateMode,
} from '@/features/algorithm-config/types'
import {
  AlgorithmConflictError,
  type SaveAlgorithmInput,
} from '@/infrastructure/api/algorithm-config-api'
import type { AlgorithmDefinition } from '@/domain/models/algorithmConfig'

export type UseAlgorithmPublishOptions = {
  open: boolean
  form: UseFormReturn<AlgorithmFormValues>
  /** 发布严格 schema（mode 对应 algorithmFormSchema / algorithmEditFormSchema） */
  schema: ZodType<AlgorithmFormValues>
  mode: MutateMode
  /** 发布事务请求（mock 阶段 publishAlgorithm；接线后后端发布事务 RPC） */
  publish: (
    input: SaveAlgorithmInput,
    revision?: number
  ) => Promise<AlgorithmDefinition>
  /** 冲突「刷新并丢弃我的更改」重拉最新发布版（§6.2a） */
  refetchLatest?: () => Promise<AlgorithmDefinition | undefined>
  /** 发布成功回调（invalidate + 关 Sheet） */
  onPublished: (created: boolean) => void
}

export type UseAlgorithmPublishResult = {
  /** 发布严格校验结果（发布钮 disabled 当 invalid） */
  isFormValid: boolean
  isPublishing: boolean
  /** 发布冲突 AlertDialog 开关（§6.2a） */
  publishConflict: boolean
  /** 表单级错误（409 算法代码已存在 / 网络失败），Sheet 顶部 Alert 展示 */
  publishError: string | null
  publishNow: () => Promise<void>
  /** 冲突「刷新并丢弃我的更改」 */
  refreshAndDiscard: () => Promise<void>
  /** 冲突「继续编辑」返回表单复核 */
  clearConflict: () => void
  clearError: () => void
}

export function useAlgorithmPublish({
  open,
  form,
  schema,
  mode,
  publish,
  refetchLatest,
  onPublished,
}: UseAlgorithmPublishOptions): UseAlgorithmPublishResult {
  const [isPublishing, setIsPublishing] = useState(false)
  const [publishConflict, setPublishConflict] = useState(false)
  const [publishError, setPublishError] = useState<string | null>(null)

  const publishingRef = useRef(false)
  const isNew = mode === 'create' || mode === 'clone'
  const watchedValues = form.watch()
  const isFormValid = schema.safeParse(watchedValues).success

  const publishNow = useCallback(async () => {
    if (!open) return
    if (publishingRef.current) return
    // 严格全量校验：失败触发字段级红字（§6.2/§6.6）
    const valid = await form.trigger()
    if (!valid) return
    publishingRef.current = true
    setIsPublishing(true)
    setPublishError(null)
    try {
      const values = form.getValues()
      await publish(toSaveInput(values), values.revision)
      toast.success(isNew ? PUBLISH_MESSAGES.created : PUBLISH_MESSAGES.published)
      onPublished(isNew)
    } catch (error) {
      if (error instanceof AlgorithmConflictError) {
        // 发布冲突 AlertDialog（§6.2a）
        setPublishConflict(true)
      } else if (typeof error === 'object' && error !== null && (error as { status?: number }).status === 409) {
        setPublishError(PUBLISH_MESSAGES.codeExists)
      } else {
        setPublishError(PUBLISH_MESSAGES.failure)
      }
    } finally {
      publishingRef.current = false
      setIsPublishing(false)
    }
  }, [open, form, publish, isNew, onPublished])

  const refreshAndDiscard = useCallback(async () => {
    if (!refetchLatest) return
    setPublishConflict(false)
    setPublishError(null)
    try {
      const latest = await refetchLatest()
      if (!latest) {
        toast.error('该算法已不存在')
        return
      }
      form.reset(toFormValues(latest))
      toast.success('已刷新为最新版本')
    } catch {
      setPublishError(PUBLISH_MESSAGES.failure)
    }
  }, [refetchLatest, form])

  const clearConflict = useCallback(() => {
    setPublishConflict(false)
  }, [])

  const clearError = useCallback(() => {
    setPublishError(null)
  }, [])

  return {
    isFormValid,
    isPublishing,
    publishConflict,
    publishError,
    publishNow,
    refreshAndDiscard,
    clearConflict,
    clearError,
  }
}
