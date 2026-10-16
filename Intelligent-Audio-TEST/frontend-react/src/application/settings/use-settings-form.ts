/**
 * 设置表单脏收集/差异提交（application 层纯逻辑，无 UI）：
 * 表单基线 = 服务端值；isDirty 时页头出琥珀徽标；保存只收集「脏且与基线不同」的字段
 * （对齐 newAPI use-settings-form + use-reset-form 实测）。
 */
import { useCallback, useMemo, useState } from 'react'

type UseSettingsFormOptions<T extends Record<string, unknown>> = {
  /** 服务端基线（选项解析后的类型化设置） */
  baseline: T
  /** 键 → 系统选项 key 映射（保存时逐项写回 KV） */
  optionKey: (field: keyof T) => string
}

export function useSettingsForm<T extends Record<string, unknown>>({
  baseline,
  optionKey,
}: UseSettingsFormOptions<T>) {
  const [draft, setDraft] = useState<T>(() => ({ ...baseline }))

  const setField = useCallback((field: keyof T, value: T[keyof T]) => {
    setDraft((prev) => ({ ...prev, [field]: value }))
  }, [])

  const dirtyFields = useMemo(() => {
    const entries: Array<{ key: string; value: unknown }> = []
    for (const field of Object.keys(draft) as Array<keyof T>) {
      if (draft[field] !== baseline[field]) {
        entries.push({ key: optionKey(field), value: draft[field] })
      }
    }
    return entries
  }, [draft, baseline, optionKey])

  const isDirty = dirtyFields.length > 0

  const reset = useCallback(() => {
    setDraft({ ...baseline })
  }, [baseline])

  /** 提交：无差异返回 null（调用方 toast.info「没有需要保存的更改」） */
  const collectChanges = useCallback(() => {
    return dirtyFields.length > 0 ? dirtyFields : null
  }, [dirtyFields])

  return { draft, setField, dirtyFields, isDirty, reset, collectChanges }
}
