/**
 * §6.2 草稿编排（application 层；17_配置运维.md §11 落位，替代原 useAlgorithmAutoSave 退役）。
 * 挂 algorithm-mutate-sheet.tsx：
 * - 30s 自动保存：Sheet 打开且首次变脏启动，每次内容变更重置，结构校验不过暂停；
 *   归零 → 宽松结构校验 → 写草稿（silent，仅时间戳更新，不弹 toast）。
 * - 参数行失焦防抖（§6.2 保留旧习惯）：参数表容器 focusout 触发 scheduleBlurSave，
 *   1.5s 防抖 → 结构校验 → 写草稿（toast「草稿已保存」）；不引逐参端点（INT-585 断言延续）。
 * - 手动「保存草稿」：saveDraftNow()。
 * - 成功 → footer「上次保存 HH:mm:ss」+ form.reset(form.getValues()) 快照重置（isDirty 归零，脏态守卫不再误弹）。
 * - 失败（非冲突）→ toast「草稿保存失败，请检查网络后重试」不自动重试；409 冲突 → draftConflict 态（§6.2a）。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { UseFormReturn } from 'react-hook-form'
import { toast } from 'sonner'
import type { ZodType } from 'zod'

import { useCountdown } from '@/hooks/use-countdown'
import {
  AUTO_SAVE_COUNTDOWN_SECONDS,
  DRAFT_MESSAGES,
  PARAM_BLUR_DEBOUNCE_MS,
} from '@/features/algorithm-config/constants'
import { toFormValues, toSaveInput } from '@/features/algorithm-config/mutate/form-converters'
import type {
  AlgorithmFormValues,
  MutateMode,
} from '@/features/algorithm-config/types'
import {
  AlgorithmConflictError,
  type DraftSaveResult,
  type SaveAlgorithmInput,
} from '@/infrastructure/api/algorithm-config-api'
import type { AlgorithmDefinition } from '@/domain/models/algorithmConfig'

export type UseAlgorithmDraftOptions = {
  open: boolean
  form: UseFormReturn<AlgorithmFormValues>
  /** 草稿宽松结构校验 schema（§6.2 草稿门槛） */
  schema: ZodType<AlgorithmFormValues>
  mode: MutateMode
  /** 草稿保存请求（mock 阶段 saveAlgorithmDraft；接线后草稿 RPC draft 分支） */
  saveDraft: (
    input: SaveAlgorithmInput,
    revision?: number
  ) => Promise<DraftSaveResult>
  /** 编辑态重拉最新发布版（§6.2a 乐观锁刷新；create/clone 无刷新源传 undefined） */
  refetchLatest?: () => Promise<AlgorithmDefinition | undefined>
}

export type UseAlgorithmDraftResult = {
  /** footer 倒计时剩余秒数（0 时隐藏倒计时形态） */
  secondsLeft: number
  isActive: boolean
  /** 草稿宽松校验结果（倒计时/保存门槛） */
  isFormValid: boolean
  /** 结构校验不过暂停态（footer 内联 Alert「有校验未通过，草稿暂存暂停」） */
  isValidationBlocked: boolean
  /** 上次草稿保存时间（footer「上次保存 HH:mm:ss」；null=未保存过） */
  lastSavedAt: Date | null
  /** 保存中态（footer「正在保存草稿…」+ 防重入） */
  isSavingDraft: boolean
  /** 乐观锁冲突态（§6.2a footer inline Alert「草稿已过期」） */
  draftConflict: boolean
  /** 手动「保存草稿」 */
  saveDraftNow: () => Promise<void>
  /** 参数表容器 blur → 失焦防抖草稿保存 */
  scheduleBlurSave: () => void
  /** 取消未决防抖保存（发布/关闭/刷新前调用） */
  cancelPendingSave: () => void
  /** 冲突「立即刷新」：重拉发布版并入表单 */
  refreshLatest: () => Promise<void>
  /** 冲突「继续编辑」：保留本地草稿 */
  clearConflict: () => void
}

export function useAlgorithmDraft({
  open,
  form,
  schema,
  saveDraft,
  refetchLatest,
}: UseAlgorithmDraftOptions): UseAlgorithmDraftResult {
  const countdown = useCountdown({ initialSeconds: AUTO_SAVE_COUNTDOWN_SECONDS })
  const { secondsLeft, isActive } = countdown

  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null)
  const [isSavingDraft, setIsSavingDraft] = useState(false)
  const [draftConflict, setDraftConflict] = useState(false)

  // 防重入：savingRef 用于闭包守卫（isSavingDraft 状态有滞后），状态供 footer 渲染
  const savingRef = useRef(false)
  const manualStopRef = useRef(false)
  const prevActiveRef = useRef(isActive)
  const openRef = useRef(open)
  const blurTimerRef = useRef<number | null>(null)
  const lastStartedSnapshotRef = useRef('')

  const watchedValues = form.watch()
  const isDirty = form.formState.isDirty
  const isFormValid = schema.safeParse(watchedValues).success
  const isValidationBlocked =
    open && isDirty && !isFormValid && !isSavingDraft

  useEffect(() => {
    openRef.current = open
  }, [open])

  /* ───────── 核心保存（silent=30s 自动保存静默；手动/失焦弹 toast） ───────── */

  const saveDraftInternal = useCallback(
    async ({ silent }: { silent: boolean }) => {
      if (!openRef.current) return
      if (savingRef.current) return
      // 归零/失焦瞬间防御性复验（时刻可能已变 invalid → 不保存）
      if (!schema.safeParse(form.getValues()).success) return
      savingRef.current = true
      setIsSavingDraft(true)
      try {
        const values = form.getValues()
        const result = await saveDraft(toSaveInput(values), values.revision)
        setLastSavedAt(new Date(result.savedAt))
        // lastSaved 快照重置：isDirty 归零（脏态离开守卫不再误弹）；不关 Sheet
        form.reset(form.getValues())
        if (!silent) toast.success(DRAFT_MESSAGES.saved)
      } catch (error) {
        if (error instanceof AlgorithmConflictError) {
          // 乐观锁冲突（§6.2a）：footer inline Alert + 就地动作
          setDraftConflict(true)
        } else {
          // 失败转手动：不自动重试（防重试风暴），保留编辑态
          toast.error(DRAFT_MESSAGES.failure)
        }
      } finally {
        savingRef.current = false
        setIsSavingDraft(false)
      }
    },
    [saveDraft, form, schema]
  )

  const saveDraftInternalRef = useRef(saveDraftInternal)
  useEffect(() => {
    saveDraftInternalRef.current = saveDraftInternal
  })

  /** 手动「保存草稿」 */
  const saveDraftNow = useCallback(async () => {
    await saveDraftInternalRef.current({ silent: false })
  }, [])

  /** 参数表容器 blur → 失焦防抖草稿保存（§6.2 保留旧习惯，草稿级聚合） */
  const scheduleBlurSave = useCallback(() => {
    if (!openRef.current) return
    if (blurTimerRef.current) window.clearTimeout(blurTimerRef.current)
    blurTimerRef.current = window.setTimeout(() => {
      blurTimerRef.current = null
      if (!form.formState.isDirty) return
      void saveDraftInternalRef.current({ silent: false })
    }, PARAM_BLUR_DEBOUNCE_MS)
  }, [form])

  /** 取消未决防抖保存（发布/关闭前调用，避免发布后残留草稿保存） */
  const cancelPendingSave = useCallback(() => {
    if (blurTimerRef.current) {
      window.clearTimeout(blurTimerRef.current)
      blurTimerRef.current = null
    }
  }, [])

  /* ───────── 归零信号：useCountdown 自然到 0（isActive true→false）→ 静默草稿保存 ───────── */

  useEffect(() => {
    const prev = prevActiveRef.current
    prevActiveRef.current = isActive
    if (!prev || isActive) return
    if (manualStopRef.current) {
      // 手动 stop/reset（校验暂停/关闭/表单干净），非自然归零
      manualStopRef.current = false
      return
    }
    void saveDraftInternalRef.current({ silent: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive])

  /* ───────── 暂停口径：关闭复位 / 校验不过 stop / 表单干净 stop ───────── */

  useEffect(() => {
    if (!open) {
      manualStopRef.current = true
      countdown.reset()
      return
    }
    if (isDirty && !isFormValid) {
      manualStopRef.current = true
      countdown.stop()
      return
    }
    if (!isDirty) {
      manualStopRef.current = true
      countdown.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isDirty, isFormValid])

  /* ───────── 首次变脏 / 内容变更 / 恢复 valid → 重置 30s ───────── */

  useEffect(() => {
    if (!open || !isDirty || !isFormValid || isSavingDraft) return
    const snapshot = JSON.stringify(watchedValues)
    if (snapshot === lastStartedSnapshotRef.current) return
    lastStartedSnapshotRef.current = snapshot
    manualStopRef.current = false
    countdown.start(AUTO_SAVE_COUNTDOWN_SECONDS)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchedValues, open, isDirty, isFormValid, isSavingDraft])

  /* ───────── 关闭/重新打开时复位内部态 ───────── */

  useEffect(() => {
    if (!open) {
      setDraftConflict(false)
      setLastSavedAt(null)
      setIsSavingDraft(false)
      savingRef.current = false
      cancelPendingSave()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  /* ───────── §6.2a 乐观锁冲突动作 ───────── */

  const refreshLatest = useCallback(async () => {
    if (!refetchLatest) return
    cancelPendingSave()
    try {
      const latest = await refetchLatest()
      if (!latest) {
        toast.error('该算法已不存在')
        return
      }
      form.reset(toFormValues(latest))
      setLastSavedAt(new Date())
      setDraftConflict(false)
      toast.success(DRAFT_MESSAGES.refreshed)
    } catch {
      toast.error(DRAFT_MESSAGES.failure)
    }
  }, [refetchLatest, cancelPendingSave, form])

  const clearConflict = useCallback(() => {
    setDraftConflict(false)
  }, [])

  return {
    secondsLeft,
    isActive,
    isFormValid,
    isValidationBlocked,
    lastSavedAt,
    isSavingDraft,
    draftConflict,
    saveDraftNow,
    scheduleBlurSave,
    cancelPendingSave,
    refreshLatest,
    clearConflict,
  }
}
