/**
 * LLM 供应商管理弹窗（interfaces 层 ai-chat/input；08_AI对话页.md §3.11）。
 * chatbox 式用户自管：名称/Base URL/API Key/模型列表/测试连接/默认/删除；
 * 供应商仅存本机 localStorage（iatp:ai-chat:v1:providers），不上传平台后端。
 * 表单校验：name/baseUrl 必填；apiKey 首供应商必填（§3.11）。
 * 「测试连接/自动获取模型列表」走真实 GET {baseUrl}/models（2026-10-17 审计 P2-1 返修；
 * 密钥直连用户自配 Base URL，不上传平台后端）。
 */
import { Eye, EyeOff, PenLine, Plus, Settings2, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'

import type { LlmProvider } from '@/domain/models/aiChat'
import { PROVIDER_MANAGER_COPY } from '@/features/ai-chat/constants'
import type { LlmProviderDraft } from '@/features/ai-chat/hooks/use-llm-providers'

type ProviderManagerProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  providers: LlmProvider[]
  onAdd: (draft: LlmProviderDraft) => void
  onUpdate: (id: string, draft: Partial<LlmProviderDraft>) => void
  onRemove: (id: string) => void
  onSetDefault: (id: string) => void
  onTestConnection: (draft: Pick<LlmProvider, 'baseUrl' | 'apiKey'>) => Promise<{
    ok: boolean
    models: string[]
    error?: string
  }>
  onFetchModels: (draft: Pick<LlmProvider, 'baseUrl' | 'apiKey'>) => Promise<string[]>
}

type FormState = {
  name: string
  baseUrl: string
  apiKey: string
  models: string[]
}

const EMPTY_FORM: FormState = { name: '', baseUrl: '', apiKey: '', models: [] }

/** 模型列表 ArrayField：每行模型 id Input + 删除（§3.11） */
function ModelListField({
  models,
  onChange,
}: {
  models: string[]
  onChange: (next: string[]) => void
}) {
  const updateAt = (index: number, value: string) => {
    onChange(models.map((item, i) => (i === index ? value : item)))
  }
  const removeAt = (index: number) => {
    onChange(models.filter((_, i) => i !== index))
  }
  return (
    <div className='grid gap-1.5'>
      {/* 行 key 只用下标：key 含输入值会让每次按键重建整行 input，焦点与后续键入全部丢失（INT-1596） */}
      {models.map((model, index) => (
        <div className='flex items-center gap-1.5' key={index}>
          <Input
            className='h-7 font-mono text-xs'
            onChange={(event) => updateAt(index, event.target.value)}
            placeholder='如 gpt-4o'
            value={model}
          />
          <Button
            aria-label='删除模型'
            className='text-muted-foreground hover:text-destructive size-7 shrink-0'
            onClick={() => removeAt(index)}
            type='button'
            variant='ghost'
          >
            <Trash2 className='size-3.5' />
          </Button>
        </div>
      ))}
      <Button
        className='text-muted-foreground h-7 justify-start px-2 text-xs'
        onClick={() => onChange([...models, ''])}
        type='button'
        variant='ghost'
      >
        <Plus className='size-3.5' />
        添加模型
      </Button>
    </div>
  )
}

/** 添加/编辑供应商表单（同一 Dialog 内视图切换；§3.11 表单） */
function ProviderForm({
  initial,
  isFirst,
  isEditing,
  onSave,
  onCancel,
  onTestConnection,
  onFetchModels,
}: {
  initial: FormState
  isFirst: boolean
  isEditing: boolean
  onSave: (draft: LlmProviderDraft) => void
  onCancel: () => void
  onTestConnection: ProviderManagerProps['onTestConnection']
  onFetchModels: ProviderManagerProps['onFetchModels']
}) {
  const [form, setForm] = useState<FormState>(initial)
  const [showKey, setShowKey] = useState(false)
  const [errors, setErrors] = useState<{ name?: string; baseUrl?: string; apiKey?: string }>({})
  const [testing, setTesting] = useState(false)
  const [fetching, setFetching] = useState(false)

  /** 字段填了合法值就把该字段的校验红字清掉，不必等下次保存（INT-1596） */
  const clearError = (key: 'name' | 'baseUrl' | 'apiKey') => {
    setErrors((prev) => {
      if (!prev[key]) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    if (key === 'models') return
    if (!String(value).trim()) return
    clearError(key)
  }

  const validate = (): boolean => {
    const next: typeof errors = {}
    if (!form.name.trim()) next.name = '请输入供应商名称'
    if (!form.baseUrl.trim()) next.baseUrl = '请输入 API Base URL'
    // apiKey 任一供应商至少一份，首供应商必填（§3.11）
    if (isFirst && !form.apiKey.trim()) next.apiKey = '请输入 API Key'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const handleTest = async () => {
    setTesting(true)
    const result = await onTestConnection({ baseUrl: form.baseUrl, apiKey: form.apiKey })
    setTesting(false)
    if (result.ok) {
      toast.success(PROVIDER_MANAGER_COPY.testSuccess.replace('{n}', String(result.models.length)))
    } else {
      toast.error(result.error ?? PROVIDER_MANAGER_COPY.testFail)
    }
  }

  const handleFetchModels = async () => {
    setFetching(true)
    const models = await onFetchModels({ baseUrl: form.baseUrl, apiKey: form.apiKey })
    setFetching(false)
    if (models.length > 0) {
      setField('models', [...new Set([...form.models, ...models])])
      toast.success(PROVIDER_MANAGER_COPY.fetchSuccess.replace('{n}', String(models.length)))
    } else {
      toast.error(PROVIDER_MANAGER_COPY.testFail)
    }
  }

  const handleSave = () => {
    if (!validate()) return
    onSave({
      name: form.name.trim(),
      baseUrl: form.baseUrl.trim(),
      apiKey: form.apiKey.trim(),
      models: form.models.map((m) => m.trim()).filter(Boolean),
    })
  }

  return (
    <div className='grid gap-4 py-1'>
      <div className='grid gap-2'>
        <Label htmlFor='provider-name'>{PROVIDER_MANAGER_COPY.name}</Label>
        <Input
          autoFocus
          id='provider-name'
          onChange={(event) => setField('name', event.target.value)}
          placeholder='如 OpenAI / DeepSeek'
          value={form.name}
        />
        {errors.name && <p className='text-destructive text-xs'>{errors.name}</p>}
      </div>

      <div className='grid gap-2'>
        <Label htmlFor='provider-base-url'>{PROVIDER_MANAGER_COPY.baseUrl}</Label>
        <Input
          className='font-mono text-xs'
          id='provider-base-url'
          onChange={(event) => setField('baseUrl', event.target.value)}
          placeholder={PROVIDER_MANAGER_COPY.baseUrlPlaceholder}
          value={form.baseUrl}
        />
        {errors.baseUrl && <p className='text-destructive text-xs'>{errors.baseUrl}</p>}
      </div>

      <div className='grid gap-2'>
        <Label htmlFor='provider-api-key'>{PROVIDER_MANAGER_COPY.apiKey}</Label>
        <div className='relative'>
          <Input
            className='pr-9 font-mono text-xs'
            id='provider-api-key'
            onChange={(event) => setField('apiKey', event.target.value)}
            placeholder='sk-…'
            type={showKey ? 'text' : 'password'}
            value={form.apiKey}
          />
          <button
            aria-label={PROVIDER_MANAGER_COPY.showHide}
            className='text-muted-foreground hover:text-foreground absolute right-2 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded'
            onClick={() => setShowKey((v) => !v)}
            type='button'
          >
            {showKey ? <EyeOff className='size-3.5' /> : <Eye className='size-3.5' />}
          </button>
        </div>
        {errors.apiKey && <p className='text-destructive text-xs'>{errors.apiKey}</p>}
      </div>

      <div className='grid gap-2'>
        <Label>{PROVIDER_MANAGER_COPY.modelList}</Label>
        <ModelListField models={form.models} onChange={(next) => setField('models', next)} />
        <Button
          className='text-muted-foreground h-7 justify-start px-2 text-xs'
          disabled={fetching}
          onClick={handleFetchModels}
          type='button'
          variant='ghost'
        >
          {fetching ? '获取中…' : PROVIDER_MANAGER_COPY.fetchModels}
        </Button>
      </div>

      <div className='flex items-center gap-2'>
        <Button
          className='text-xs'
          disabled={testing}
          onClick={handleTest}
          type='button'
          variant='outline'
        >
          {testing ? '连接中…' : PROVIDER_MANAGER_COPY.testConnection}
        </Button>
      </div>

      <DialogFooter className='gap-2'>
        <Button onClick={onCancel} type='button' variant='ghost'>
          {PROVIDER_MANAGER_COPY.cancel}
        </Button>
        <Button onClick={handleSave} type='button'>
          {PROVIDER_MANAGER_COPY.save}
        </Button>
      </DialogFooter>
      {isEditing && <p className='sr-only'>编辑供应商</p>}
    </div>
  )
}

export function ProviderManager({
  open,
  onOpenChange,
  providers,
  onAdd,
  onUpdate,
  onRemove,
  onSetDefault,
  onTestConnection,
  onFetchModels,
}: ProviderManagerProps) {
  const [view, setView] = useState<'list' | 'form'>('list')
  const [editing, setEditing] = useState<LlmProvider | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<LlmProvider | null>(null)

  const openAdd = () => {
    setEditing(null)
    setView('form')
  }
  const openEdit = (provider: LlmProvider) => {
    setEditing(provider)
    setView('form')
  }
  const handleClose = () => {
    onOpenChange(false)
    setView('list')
    setEditing(null)
  }

  const handleSave = (draft: LlmProviderDraft) => {
    if (editing) {
      onUpdate(editing.id, draft)
    } else {
      onAdd(draft)
    }
    setView('list')
    setEditing(null)
  }

  const handleDelete = () => {
    if (!deleteTarget) return
    onRemove(deleteTarget.id)
    setDeleteTarget(null)
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) handleClose()
          else onOpenChange(next)
        }}
      >
        <DialogContent className='sm:max-w-xl'>
          <DialogHeader>
            <DialogTitle>{PROVIDER_MANAGER_COPY.title}</DialogTitle>
            <DialogDescription>{PROVIDER_MANAGER_COPY.description}</DialogDescription>
          </DialogHeader>

          {view === 'form' ? (
            <ProviderForm
              initial={
                editing
                  ? {
                      name: editing.name,
                      baseUrl: editing.baseUrl,
                      apiKey: editing.apiKey,
                      models: editing.models,
                    }
                  : EMPTY_FORM
              }
              isEditing={Boolean(editing)}
              isFirst={providers.length === 0}
              onCancel={() => setView('list')}
              onFetchModels={onFetchModels}
              onSave={handleSave}
              onTestConnection={onTestConnection}
            />
          ) : (
            <div className='grid gap-3'>
              <div className='flex items-center justify-end'>
                <Button onClick={openAdd} size='sm' type='button'>
                  <Plus className='size-4' />
                  {PROVIDER_MANAGER_COPY.addProvider}
                </Button>
              </div>

              {providers.length === 0 ? (
                <div className='bg-muted/40 text-muted-foreground flex flex-col items-center gap-2 rounded-lg px-4 py-8 text-center text-sm'>
                  <Settings2 className='size-5' />
                  尚未配置 LLM 供应商，点击右上角「添加供应商」开始。
                </div>
              ) : (
                providers.map((provider) => {
                  const hasKey = Boolean(provider.apiKey)
                  return (
                    <div
                      className='hover:bg-muted/50 flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors'
                      key={provider.id}
                    >
                      <div className='min-w-0 flex-1'>
                        <div className='flex items-center gap-2'>
                          <span className='text-sm font-medium'>{provider.name}</span>
                          {provider.isDefault && (
                            <Badge variant='secondary'>{PROVIDER_MANAGER_COPY.default}</Badge>
                          )}
                        </div>
                        <p className='text-muted-foreground truncate font-mono text-xs'>
                          {provider.baseUrl}
                        </p>
                      </div>
                      <Badge variant={hasKey ? 'outline' : 'secondary'}>
                        {hasKey
                          ? PROVIDER_MANAGER_COPY.keyConfigured
                          : PROVIDER_MANAGER_COPY.keyMissing}
                      </Badge>
                      <div className='flex items-center gap-0.5'>
                        {!provider.isDefault && (
                          <Button
                            aria-label={PROVIDER_MANAGER_COPY.setDefault}
                            className='text-muted-foreground hover:text-primary size-7'
                            onClick={() => onSetDefault(provider.id)}
                            type='button'
                            variant='ghost'
                          >
                            <Star className='size-3.5' />
                          </Button>
                        )}
                        <Button
                          aria-label={PROVIDER_MANAGER_COPY.edit}
                          className='text-muted-foreground hover:text-foreground size-7'
                          onClick={() => openEdit(provider)}
                          type='button'
                          variant='ghost'
                        >
                          <PenLine className='size-3.5' />
                        </Button>
                        <Button
                          aria-label={PROVIDER_MANAGER_COPY.delete}
                          className='text-muted-foreground hover:text-destructive size-7'
                          onClick={() => setDeleteTarget(provider)}
                          type='button'
                          variant='ghost'
                        >
                          <Trash2 className='size-3.5' />
                        </Button>
                      </div>
                    </div>
                  )
                })
              )}

              <p className={cn('text-muted-foreground px-1 text-xs leading-5')}>
                {PROVIDER_MANAGER_COPY.footerHint}
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        destructive
        confirmText={PROVIDER_MANAGER_COPY.delete}
        desc={PROVIDER_MANAGER_COPY.deleteDesc}
        handleConfirm={handleDelete}
        onOpenChange={(next) => {
          if (!next) setDeleteTarget(null)
        }}
        open={Boolean(deleteTarget)}
        title={PROVIDER_MANAGER_COPY.deleteTitle}
      />
    </>
  )
}
