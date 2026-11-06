/**
 * 母版 A KV 表单分区页装配（interfaces 层，INT-347 §4.1）：
 * useSettingsForm（基线/脏收集）→ 保存 mutation（仅脏字段逐项 PUT）→
 * 页头动作区（重置/保存）+ 脏徽标 + 离开守卫 全套接入；
 * 无差异 toast.info「没有需要保存的更改」、成功 toast「设置已更新」、
 * 重置 toast「表单已重置为已保存的值」（INT-489 返修③）。
 */
import type { ReactNode } from 'react'
import { toast } from 'sonner'

import { useSettingsForm } from '@/application/settings/use-settings-form'
import { useUpdateOption } from '@/application/settings/use-update-option'

import { FormDirtyIndicator } from './form-dirty-indicator'
import { FormNavigationGuard } from './form-navigation-guard'
import { SettingsPageFormActions } from './settings-page-context'

type SettingsFormPageProps<T extends Record<string, unknown>> = {
  baseline: T
  /** 字段 → 系统选项 KV 键（保存时逐项写回） */
  optionKey: (field: keyof T) => string
  children: (
    draft: T,
    setField: (field: keyof T, value: T[keyof T]) => void
  ) => ReactNode
}

export function SettingsFormPage<T extends Record<string, unknown>>(
  props: SettingsFormPageProps<T>
) {
  const { draft, setField, isDirty, reset, collectChanges } = useSettingsForm({
    baseline: props.baseline,
    optionKey: props.optionKey,
  })
  const updateOption = useUpdateOption()

  const handleSave = () => {
    const changes = collectChanges()
    if (!changes) {
      toast.info('没有需要保存的更改')
      return
    }
    updateOption.mutate(changes)
  }

  const handleReset = () => {
    reset()
    toast.success('表单已重置为已保存的值')
  }

  return (
    <>
      <FormDirtyIndicator isDirty={isDirty} />
      <SettingsPageFormActions
        onSave={handleSave}
        onReset={handleReset}
        isSaving={updateOption.isPending}
        isSaveDisabled={!isDirty || updateOption.isPending}
        isResetDisabled={!isDirty}
      />
      <FormNavigationGuard isDirty={isDirty} />
      {props.children(draft, setField)}
    </>
  )
}
