/**
 * 供应商新增 / 编辑弹窗（features/agent-providers）。
 * - 协议下拉用 Select items 给中文 label（Base UI 无 items 时会回显原始 value）；
 * - 编辑时 API Key 留空 = 不变，输入框带明文可见性切换，永不回显已有 Key；
 * - 上下文窗口三态：使用默认（contextWindow=null）/ 手动覆盖（8k–2M、1024 对齐）/
 *   恢复默认（回到 null）；超目录默认仅告警不阻断保存。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { Eye, EyeOff, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useForm, type UseFormReturn } from 'react-hook-form'
import { z } from 'zod'

import {
  DEFAULT_CONTEXT_WINDOW_BOUNDS,
  formatContextWindowTokens,
  type AgentProvider,
  type AgentProviderInput,
  type AgentProviderProtocol,
  type ContextWindowBounds,
  type ModelCatalog,
  resolveContextWindowPreview,
  validateContextWindowOverride,
} from '@/domain/models/agentProvider'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

import {
  AGENT_PROVIDER_PROTOCOL_SELECT_ITEMS,
  AGENT_PROVIDERS_COPY,
  CONTEXT_WINDOW_MODE,
  type ContextWindowMode,
} from '../constants'

const HTTP_URL_PATTERN = /^https?:\/\/\S+$/i
const API_KEY_MAX_LENGTH = 512
const BASE_URL_MAX_LENGTH = 500
const NAME_MAX_LENGTH = 100
const MODEL_MAX_LENGTH = 100

/**
 * 上下文窗口输入解析：支持纯数字，也支持 `32k` / `1M` 简写（1k=1024）。
 * 非法输入返回 null，由 schema 报错。
 */
export function parseContextWindowInput(text: string): number | null {
  const value = text.trim().toLowerCase()
  if (!value) return null
  const match = /^(\d+(?:\.\d+)?)([km])?$/.exec(value)
  if (!match) return null
  const base = Number(match[1])
  if (!Number.isFinite(base)) return null
  const multiplier = match[2] === 'm' ? 1024 * 1024 : match[2] === 'k' ? 1024 : 1
  const tokens = Math.round(base * multiplier)
  return Number.isFinite(tokens) ? tokens : null
}

function buildSchema(isEditing: boolean, bounds: ContextWindowBounds) {
  return z
    .object({
      name: z.string().max(NAME_MAX_LENGTH, `名称不能超过 ${NAME_MAX_LENGTH} 字符`),
      protocol: z.enum(['OPENAI_COMPATIBLE', 'ANTHROPIC']),
      baseUrl: z
        .string()
        .trim()
        .min(1, '请填写 Base URL')
        .max(BASE_URL_MAX_LENGTH, AGENT_PROVIDERS_COPY.invalidBaseUrlTooLong)
        .refine((value) => HTTP_URL_PATTERN.test(value), AGENT_PROVIDERS_COPY.invalidBaseUrl),
      model: z
        .string()
        .trim()
        .min(1, AGENT_PROVIDERS_COPY.invalidModel)
        .max(MODEL_MAX_LENGTH, `模型名不能超过 ${MODEL_MAX_LENGTH} 字符`),
      apiKey: z
        .string()
        .max(API_KEY_MAX_LENGTH, AGENT_PROVIDERS_COPY.invalidApiKeyTooLong),
      contextMode: z.enum([
        CONTEXT_WINDOW_MODE.DEFAULT,
        CONTEXT_WINDOW_MODE.OVERRIDE,
      ]),
      contextWindowText: z.string(),
    })
    .superRefine((values, ctx) => {
      if (!isEditing && !values.apiKey.trim()) {
        ctx.addIssue({
          code: 'custom',
          path: ['apiKey'],
          message: AGENT_PROVIDERS_COPY.invalidApiKey,
        })
      }
      if (values.contextMode === CONTEXT_WINDOW_MODE.OVERRIDE) {
        const parsed = parseContextWindowInput(values.contextWindowText)
        const problem =
          parsed === null
            ? AGENT_PROVIDERS_COPY.contextInvalid
            : validateContextWindowOverride(parsed, bounds)
        if (problem) {
          ctx.addIssue({
            code: 'custom',
            path: ['contextWindowText'],
            message: problem,
          })
        }
      }
    })
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>

type AgentProviderFormDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 编辑目标；null = 新增 */
  provider: AgentProvider | null
  catalog: ModelCatalog | undefined
  pending: boolean
  onSubmit: (input: AgentProviderInput) => Promise<boolean>
}

export function AgentProviderFormDialog({
  open,
  onOpenChange,
  provider,
  catalog,
  pending,
  onSubmit,
}: AgentProviderFormDialogProps) {
  const isEditing = Boolean(provider)
  const bounds = catalog?.bounds ?? DEFAULT_CONTEXT_WINDOW_BOUNDS
  const [showKey, setShowKey] = useState(false)

  const schema = useMemo(() => buildSchema(isEditing, bounds), [isEditing, bounds])
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    mode: 'onSubmit',
    defaultValues: toFormValues(provider),
  })

  // 每次打开按目标重置（编辑弹窗逐字段回显；新增清空上次输入）
  useEffect(() => {
    if (!open) return
    setShowKey(false)
    form.reset(toFormValues(provider))
  }, [open, provider, form])

  const protocol = form.watch('protocol') as AgentProviderProtocol
  const model = form.watch('model')
  const contextMode = form.watch('contextMode') as ContextWindowMode
  const contextWindowText = form.watch('contextWindowText')

  const overrideValue =
    contextMode === CONTEXT_WINDOW_MODE.OVERRIDE
      ? parseContextWindowInput(contextWindowText)
      : null
  const preview = useMemo(
    () => resolveContextWindowPreview(catalog, protocol, model, overrideValue),
    [catalog, protocol, model, overrideValue]
  )
  const aboveCatalogWarning =
    contextMode === CONTEXT_WINDOW_MODE.OVERRIDE &&
    preview.warning !== null &&
    overrideValue !== null

  const handleSubmit = form.handleSubmit(async (values) => {
    const contextWindow =
      values.contextMode === CONTEXT_WINDOW_MODE.OVERRIDE
        ? parseContextWindowInput(values.contextWindowText)
        : null
    const ok = await onSubmit({
      name: values.name,
      protocol: values.protocol,
      baseUrl: values.baseUrl,
      model: values.model,
      apiKey: values.apiKey.trim() || undefined,
      contextWindow,
    })
    if (ok) onOpenChange(false)
  })

  const apiKeyError = form.formState.errors.apiKey?.message

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? AGENT_PROVIDERS_COPY.editTitle
              : AGENT_PROVIDERS_COPY.addTitle}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? AGENT_PROVIDERS_COPY.editDescription
              : AGENT_PROVIDERS_COPY.addDescription}
          </DialogDescription>
        </DialogHeader>

        <form className='grid gap-4' onSubmit={handleSubmit}>
          <div className='grid gap-1.5'>
            <Label htmlFor='agent-provider-name'>
              {AGENT_PROVIDERS_COPY.fieldName}
            </Label>
            <Input
              id='agent-provider-name'
              placeholder={AGENT_PROVIDERS_COPY.fieldNamePlaceholder}
              {...form.register('name')}
            />
            {form.formState.errors.name && (
              <p className='text-destructive text-xs'>
                {form.formState.errors.name.message}
              </p>
            )}
          </div>

          <div className='grid gap-1.5'>
            <Label htmlFor='agent-provider-protocol'>
              {AGENT_PROVIDERS_COPY.fieldProtocol}
            </Label>
            <Select
              items={AGENT_PROVIDER_PROTOCOL_SELECT_ITEMS}
              value={protocol}
              onValueChange={(value) =>
                form.setValue('protocol', value as AgentProviderProtocol, {
                  shouldValidate: false,
                })
              }
            >
              <SelectTrigger
                className='w-full'
                id='agent-provider-protocol'
                size='sm'
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AGENT_PROVIDER_PROTOCOL_SELECT_ITEMS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className='grid gap-1.5'>
            <Label htmlFor='agent-provider-base-url'>
              {AGENT_PROVIDERS_COPY.fieldBaseUrl}
            </Label>
            <Input
              id='agent-provider-base-url'
              placeholder={AGENT_PROVIDERS_COPY.fieldBaseUrlPlaceholder}
              {...form.register('baseUrl')}
            />
            {form.formState.errors.baseUrl && (
              <p className='text-destructive text-xs'>
                {form.formState.errors.baseUrl.message}
              </p>
            )}
          </div>

          <div className='grid gap-1.5'>
            <Label htmlFor='agent-provider-model'>
              {AGENT_PROVIDERS_COPY.fieldModel}
            </Label>
            <Input
              id='agent-provider-model'
              placeholder={AGENT_PROVIDERS_COPY.fieldModelPlaceholder}
              {...form.register('model')}
            />
            {form.formState.errors.model && (
              <p className='text-destructive text-xs'>
                {form.formState.errors.model.message}
              </p>
            )}
          </div>

          <div className='grid gap-1.5'>
            <Label htmlFor='agent-provider-api-key'>
              {AGENT_PROVIDERS_COPY.fieldApiKey}
            </Label>
            <div className='relative'>
              <Input
                autoComplete='new-password'
                className='pr-9'
                id='agent-provider-api-key'
                placeholder={
                  isEditing
                    ? AGENT_PROVIDERS_COPY.fieldApiKeyPlaceholderEdit
                    : AGENT_PROVIDERS_COPY.fieldApiKeyPlaceholderCreate
                }
                type={showKey ? 'text' : 'password'}
                {...form.register('apiKey')}
              />
              <Button
                aria-label={
                  showKey ? AGENT_PROVIDERS_COPY.hideKey : AGENT_PROVIDERS_COPY.showKey
                }
                className='text-muted-foreground absolute top-1/2 right-1 size-7 -translate-y-1/2'
                onClick={() => setShowKey((value) => !value)}
                type='button'
                variant='ghost'
              >
                {showKey ? <EyeOff className='size-3.5' /> : <Eye className='size-3.5' />}
              </Button>
            </div>
            <p className='text-muted-foreground text-xs'>
              {AGENT_PROVIDERS_COPY.fieldApiKeyHint}
            </p>
            {apiKeyError && <p className='text-destructive text-xs'>{apiKeyError}</p>}
          </div>

          <div className='border-border/60 grid gap-2 rounded-lg border p-3'>
            <div className='flex flex-wrap items-center justify-between gap-2'>
              <Label>{AGENT_PROVIDERS_COPY.fieldContextWindow}</Label>
              <div className='flex items-center gap-1'>
                <div
                  className='border-border/60 bg-muted/40 flex items-center gap-0.5 rounded-md border p-0.5'
                  role='radiogroup'
                  aria-label={AGENT_PROVIDERS_COPY.fieldContextWindow}
                >
                  <ContextModeButton
                    active={contextMode === CONTEXT_WINDOW_MODE.DEFAULT}
                    label={AGENT_PROVIDERS_COPY.contextModeDefault}
                    onClick={() => setContextMode(form, CONTEXT_WINDOW_MODE.DEFAULT, preview)}
                  />
                  <ContextModeButton
                    active={contextMode === CONTEXT_WINDOW_MODE.OVERRIDE}
                    label={AGENT_PROVIDERS_COPY.contextModeOverride}
                    onClick={() =>
                      setContextMode(form, CONTEXT_WINDOW_MODE.OVERRIDE, preview)
                    }
                  />
                </div>
                {contextMode === CONTEXT_WINDOW_MODE.OVERRIDE && (
                  <Button
                    className='text-muted-foreground h-7 px-2 text-xs'
                    onClick={() =>
                      setContextMode(form, CONTEXT_WINDOW_MODE.DEFAULT, preview)
                    }
                    type='button'
                    variant='ghost'
                  >
                    <RotateCcw className='size-3.5' />
                    {AGENT_PROVIDERS_COPY.contextReset}
                  </Button>
                )}
              </div>
            </div>

            {contextMode === CONTEXT_WINDOW_MODE.OVERRIDE && (
              <div className='grid gap-1'>
                <Input
                  aria-label={AGENT_PROVIDERS_COPY.fieldContextWindow}
                  id='agent-provider-context-window'
                  inputMode='numeric'
                  placeholder='如 32768 或 32k'
                  value={contextWindowText}
                  onChange={(event) =>
                    form.setValue('contextWindowText', event.target.value, {
                      // 提交过一次后即时重校验：改正数值立即消掉旧报错
                      shouldValidate: form.formState.isSubmitted,
                    })
                  }
                />
                <p className='text-muted-foreground text-xs'>
                  {AGENT_PROVIDERS_COPY.contextInputHint}
                </p>
                {form.formState.errors.contextWindowText && (
                  <p className='text-destructive text-xs'>
                    {form.formState.errors.contextWindowText.message}
                  </p>
                )}
              </div>
            )}

            <div className='text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs'>
              <span>
                {AGENT_PROVIDERS_COPY.contextSourceHint}：
                <span className='text-foreground font-medium'>
                  {preview.source === 'MODEL_DEFAULT'
                    ? AGENT_PROVIDERS_COPY.contextCatalogHint
                    : preview.source === 'USER_OVERRIDE'
                      ? AGENT_PROVIDERS_COPY.contextModeOverride
                      : AGENT_PROVIDERS_COPY.contextFallbackHint}
                </span>
              </span>
              <span>
                {AGENT_PROVIDERS_COPY.effectiveWindow}：
                <span className='text-foreground font-mono'>
                  {formatContextWindowTokens(preview.effectiveContextWindow)}
                </span>
              </span>
              {preview.catalogMaxOutputTokens !== null && (
                <span>
                  {AGENT_PROVIDERS_COPY.contextMaxOutputHint}：
                  {formatContextWindowTokens(preview.catalogMaxOutputTokens)}
                </span>
              )}
            </div>

            {aboveCatalogWarning && (
              <div className='border-warning/40 bg-warning/10 text-warning rounded-lg border px-3 py-2 text-xs'>
                {AGENT_PROVIDERS_COPY.contextAboveCatalogWarning}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              onClick={() => onOpenChange(false)}
              type='button'
              variant='outline'
            >
              {AGENT_PROVIDERS_COPY.cancel}
            </Button>
            <Button disabled={pending} type='submit'>
              {pending ? AGENT_PROVIDERS_COPY.saving : AGENT_PROVIDERS_COPY.save}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ContextModeButton({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      aria-checked={active}
      className={cn(
        'rounded px-2 py-1 text-[11px] leading-4 font-medium transition-colors',
        active
          ? 'bg-background text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground'
      )}
      onClick={onClick}
      role='radio'
      type='button'
    >
      {label}
    </button>
  )
}

function setContextMode(
  form: UseFormReturn<FormValues>,
  mode: ContextWindowMode,
  preview: ReturnType<typeof resolveContextWindowPreview>
) {
  const shouldValidate = form.formState.isSubmitted
  form.setValue('contextMode', mode, { shouldValidate })
  if (mode === CONTEXT_WINDOW_MODE.OVERRIDE) {
    form.setValue(
      'contextWindowText',
      form.getValues('contextWindowText') || String(preview.effectiveContextWindow),
      { shouldValidate }
    )
  }
}

function toFormValues(provider: AgentProvider | null): FormValues {
  const hasOverride = provider?.contextWindow !== null && provider?.contextWindow !== undefined
  return {
    name: provider?.name ?? '',
    protocol: provider?.protocol ?? 'OPENAI_COMPATIBLE',
    baseUrl: provider?.baseUrl ?? '',
    model: provider?.model ?? '',
    apiKey: '',
    contextMode: hasOverride
      ? CONTEXT_WINDOW_MODE.OVERRIDE
      : CONTEXT_WINDOW_MODE.DEFAULT,
    contextWindowText:
      hasOverride && provider?.contextWindow !== null
        ? String(provider?.contextWindow)
        : '',
  }
}
