/**
 * §6.1a 30s 自动保存编排（application 层；17_配置运维.md §11 落位）。
 * 挂 algorithm-mutate-sheet.tsx：
 * - 触发：Sheet 打开且表单首次变脏（isDirty false→true）→ start(30)；
 *   每次内容变更（watch）重置回 30s；校验不过 stop()（恢复 valid 且仍脏 → 重新 start）。
 * - 归零：useCountdown 到达 0 自动停并重置回 30（isActive true→false），监听该转换 → 整表校验通过
 *   → 复用聚合提交自动保存（save.isPending 防重入，手动保存同源共享）；成功 toast「已自动保存」
 *   + form.reset(form.getValues()) 快照重置 + invalidate（save mutation onSuccess 已做）+ 不关 Sheet；
 *   失败 toast「自动保存失败，已恢复手动保存」不自动重试。
 * - 导出 secondsLeft/isActive 供 footer 倒计时渲染；isFormValid/isValidationBlocked 供保存钮/Alert。
 * 不引新接口（自动保存=手动保存同一聚合提交 POST/PUT /algorithm/definitions）；无逐参失焦保存。
 */
import { useCallback, useEffect, useRef } from 'react'
import type { UseFormReturn } from 'react-hook-form'
import { toast } from 'sonner'
import type { ZodType } from 'zod'

import { useCountdown } from '@/hooks/use-countdown'
import {
  AUTO_SAVE_COUNTDOWN_SECONDS,
  AUTO_SAVE_MESSAGES,
} from '@/features/algorithm-config/constants'
import { toSaveInput } from '@/features/algorithm-config/mutate/form-converters'
import type {
  AlgorithmFormValues,
  MutateMode,
} from '@/features/algorithm-config/types'
import type { SaveAlgorithmInput } from '@/infrastructure/api/algorithm-config-api'

export type UseAlgorithmAutoSaveOptions = {
  open: boolean
  form: UseFormReturn<AlgorithmFormValues>
  mode: MutateMode
  schema: ZodType<AlgorithmFormValues>
  save: {
    mutateAsync: (
      input: SaveAlgorithmInput & { isNew: boolean }
    ) => Promise<unknown>
    isPending: boolean
  }
}

export type UseAlgorithmAutoSaveResult = {
  secondsLeft: number
  isActive: boolean
  /** 整表校验结果（保存钮可用性，§6.2/6.3 实时计算口径） */
  isFormValid: boolean
  /** 校验不过暂停态（footer 内联 Alert 显示开关，不可手动关闭） */
  isValidationBlocked: boolean
}

export function useAlgorithmAutoSave({
  open,
  form,
  mode,
  schema,
  save,
}: UseAlgorithmAutoSaveOptions): UseAlgorithmAutoSaveResult {
  const countdown = useCountdown({ initialSeconds: AUTO_SAVE_COUNTDOWN_SECONDS })
  const { secondsLeft, isActive } = countdown

  // 归零信号只认自然计时到 0：手动 stop/reset（校验暂停/表单干净/关闭/手动保存）须跳过，
  // 用 manualStopRef 区分「手动停止」与「自然归零」（reset 后 secondsLeft 同为 30，不能靠数值判）。
  const manualStopRef = useRef(false)
  const prevActiveRef = useRef(isActive)
  const openRef = useRef(open)

  const watchedValues = form.watch()
  const isDirty = form.formState.isDirty
  const isFormValid = schema.safeParse(watchedValues).success
  const isNew = mode === 'create' || mode === 'clone'
  // save pending 中不视为校验不过（保存已在进行，避免 Alert 误导）
  const isValidationBlocked = open && isDirty && !isFormValid && !save.isPending

  useEffect(() => {
    openRef.current = open
  }, [open])

  // 归零 → 聚合提交自动保存（复用手动保存同一 mutation；save.isPending 防重入）
  const runAutoSave = useCallback(async () => {
    if (!openRef.current) return
    if (save.isPending) return
    // 归零瞬间防御性整表复验（时刻可能已变 invalid → 不保存）
    const values = form.getValues()
    if (!schema.safeParse(values).success) return
    try {
      await save.mutateAsync({ ...toSaveInput(values), isNew })
      toast.success(AUTO_SAVE_MESSAGES.success)
      // lastSaved 快照重置：isDirty 归零（§6.1 脏态离开守卫改按快照判定，不再误弹）；不关 Sheet
      form.reset(form.getValues())
    } catch {
      // 失败转手动：不自动重试（防重试风暴），保留编辑态由用户手动「保存」
      toast.error(AUTO_SAVE_MESSAGES.failure)
    }
  }, [save, form, schema, isNew])

  // runAutoSave 恒取最新闭包（save.isPending 等随渲染刷新）
  const runAutoSaveRef = useRef(runAutoSave)
  useEffect(() => {
    runAutoSaveRef.current = runAutoSave
  })

  // 暂停口径（合并）：Sheet 关闭 → 复位；校验不过 → stop；表单恢复干净（快照重置）→ stop。
  // 恢复可计时条件（open && isDirty && isFormValid && !pending）由下方 start 效果负责。
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

  // 归零信号：useCountdown 到达 0 自动停并重置回 30（isActive true→false）→ 自动保存
  useEffect(() => {
    const prev = prevActiveRef.current
    prevActiveRef.current = isActive
    if (!prev || isActive) return
    if (manualStopRef.current) {
      // 手动 stop/reset 引起的停止（校验暂停/关闭/表单干净/手动保存），非自然归零
      manualStopRef.current = false
      return
    }
    void runAutoSaveRef.current()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive])

  // 首次变脏 / 每次内容变更 / 恢复 valid → 重置 30s（save pending 中不重启，防保存期间误触发）。
  // watch 返回值为新引用（RHF 每次渲染重建），须以内容快照判定「真变更」，
  // 否则倒计时自身 tick 引发的重渲染会误触发 start 导致永远归不了零。
  const lastStartedSnapshotRef = useRef('')
  useEffect(() => {
    if (!open || !isDirty || !isFormValid || save.isPending) return
    const snapshot = JSON.stringify(watchedValues)
    if (snapshot === lastStartedSnapshotRef.current) return
    lastStartedSnapshotRef.current = snapshot
    manualStopRef.current = false
    countdown.start(AUTO_SAVE_COUNTDOWN_SECONDS)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchedValues, open, isDirty, isFormValid, save.isPending])

  return { secondsLeft, isActive, isFormValid, isValidationBlocked }
}
