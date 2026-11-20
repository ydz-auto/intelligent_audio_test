/**
 * 评估服务设置表单页装配（interfaces 层）：
 * 普通项走 KV 脏收集（useSettingsForm），密钥项只进不出（留空=不修改），
 * 保存时合并提交；页头动作区/脏徽标/离开守卫与站点设置母版一致。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { useSettingsForm } from '@/application/settings/use-settings-form'
import {
  getSystemSecretMeta,
  putSystemOption,
  putSystemSecret,
  SYSTEM_OPTIONS_QUERY_KEY,
  SYSTEM_SECRETS_QUERY_KEY,
} from '@/infrastructure/api/optionApi'

import { FormDirtyIndicator } from '../components/form-dirty-indicator'
import { FormNavigationGuard } from '../components/form-navigation-guard'
import { SettingsPageFormActions } from '../components/settings-page-context'

export type EvalSecretState = {
  /** 已输入的明文（空 = 不修改） */
  value: (key: string) => string
  /** 更新输入 */
  set: (key: string, value: string) => void
  /** 已保存密钥的掩码（未配置为空串） */
  mask: (key: string) => string
}

type EvalFormPageProps<T extends Record<string, unknown>> = {
  baseline: T
  optionKey: (field: keyof T) => string
  /** 密钥键（只提交非空输入；留空表示不修改） */
  secretKeys: string[]
  /** 自定义脏字段 → KV 变更（如分维度模型需要拆成多个键） */
  collectChanges?: (
    draft: T,
    dirtyFields: Array<{ key: string; value: unknown }>
  ) => Array<{ key: string; value: unknown }>
  children: (
    draft: T,
    setField: (field: keyof T, value: T[keyof T]) => void,
    secret: EvalSecretState
  ) => ReactNode
}

export function EvalFormPage<T extends Record<string, unknown>>(
  props: EvalFormPageProps<T>
) {
  const { draft, setField, dirtyFields, isDirty, reset, collectChanges } =
    useSettingsForm({ baseline: props.baseline, optionKey: props.optionKey })
  const [secrets, setSecrets] = useState<Record<string, string>>({})
  const queryClient = useQueryClient()

  const secretsQuery = useQuery({
    queryKey: [...SYSTEM_SECRETS_QUERY_KEY],
    queryFn: getSystemSecretMeta,
  })
  const maskOf = (key: string) =>
    secretsQuery.data?.items.find((item) => item.key === key)?.mask ?? ''

  const hasSecretInput = Object.values(secrets).some((value) => value.trim())
  const dirty = isDirty || hasSecretInput

  const setSecret = (key: string, value: string) => {
    setSecrets((prev) => ({ ...prev, [key]: value }))
  }

  const save = useMutation({
    mutationFn: async () => {
      const changes = props.collectChanges
        ? props.collectChanges(draft, dirtyFields)
        : collectChanges() ?? []
      for (const change of changes) {
        await putSystemOption(change.key, change.value)
      }
      for (const key of props.secretKeys) {
        const value = (secrets[key] ?? '').trim()
        if (value) await putSystemSecret(key, value)
      }
    },
    onSuccess: () => {
      setSecrets({})
      void queryClient.invalidateQueries({ queryKey: SYSTEM_OPTIONS_QUERY_KEY })
      void queryClient.invalidateQueries({ queryKey: SYSTEM_SECRETS_QUERY_KEY })
      toast.success('设置已更新')
    },
    onError: () => toast.error('设置保存失败'),
  })

  const handleSave = () => {
    if (!dirty) {
      toast.info('没有需要保存的更改')
      return
    }
    save.mutate()
  }

  const handleReset = () => {
    reset()
    setSecrets({})
    toast.success('表单已重置为已保存的值')
  }

  const secretState: EvalSecretState = {
    value: (key) => secrets[key] ?? '',
    set: setSecret,
    mask: maskOf,
  }

  return (
    <>
      <FormDirtyIndicator isDirty={dirty} />
      <SettingsPageFormActions
        onSave={handleSave}
        onReset={handleReset}
        isSaving={save.isPending}
        isSaveDisabled={!dirty || save.isPending}
        isResetDisabled={!dirty}
      />
      <FormNavigationGuard isDirty={dirty} />
      {secretsQuery.isLoading ? (
        <div className='text-muted-foreground flex items-center gap-2 text-sm'>
          <Loader2 className='size-4 animate-spin' aria-hidden='true' />
          正在读取密钥状态…
        </div>
      ) : null}
      {secretsQuery.data && !secretsQuery.data.cipherAvailable ? (
        <p className='text-amber-600 text-sm'>
          服务端未配置 EVAL_CONFIG_MASTER_KEY，密钥暂不可保存（其余配置不受影响）。
        </p>
      ) : null}
      {props.children(draft, setField, secretState)}
    </>
  )
}
