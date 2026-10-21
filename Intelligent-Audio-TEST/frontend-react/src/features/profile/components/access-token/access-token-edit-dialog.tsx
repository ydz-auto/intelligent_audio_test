/**
 * 编辑 Access Token 对话框（features/profile/components/access-token，INT-1153）。
 * 支持重命名 / 换 scopes / 改有效时间 / 启停。expiresAt → 预设映射：
 * 0=永不过期；命中 30/90/180/365 天取对应预设；否则按自定义回填 datetime-local。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import type { AccessToken } from '@/domain/models/access-token'
import { ACCESS_TOKEN_SCOPE_CATALOG } from '@/domain/models/access-token'
import { PermissionMatrix } from '@/features/system-settings/components/permission-matrix'
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
  ACCESS_TOKEN_CANCEL,
  ACCESS_TOKEN_CUSTOM_EXPIRY_MIN_HINT,
  ACCESS_TOKEN_EDIT_DESCRIPTION,
  ACCESS_TOKEN_EDIT_SAVE,
  ACCESS_TOKEN_EDIT_SAVING,
  ACCESS_TOKEN_EDIT_TITLE,
  ACCESS_TOKEN_EXPIRY_FIELD,
  ACCESS_TOKEN_EXPIRY_NEVER_HINT,
  ACCESS_TOKEN_EXPIRY_PRESETS,
  ACCESS_TOKEN_NAME_FIELD,
  ACCESS_TOKEN_NAME_PLACEHOLDER,
  ACCESS_TOKEN_NAME_REQUIRED,
  ACCESS_TOKEN_NAME_TOO_LONG,
  ACCESS_TOKEN_SCOPES_FIELD,
  ACCESS_TOKEN_SCOPES_REQUIRED,
} from './constants'
import {
  ACCESS_TOKEN_EXPIRY_DAYS,
  type AccessTokenExpiryPreset,
} from './access-token-create-dialog'

const MIN_LIFETIME_MS = 60 * 60 * 1000

function expiryPresetFromTimestamp(expiresAt: number, nowMs: number): AccessTokenExpiryPreset {
  if (!expiresAt) return 'never'
  const diffDays = Math.round((expiresAt * 1000 - nowMs) / (24 * 60 * 60 * 1000))
  if (diffDays <= 30) return '30d'
  if (diffDays <= 90) return '90d'
  if (diffDays <= 180) return '180d'
  if (diffDays <= 365) return '1y'
  return 'custom'
}

function timestampToDatetimeLocal(seconds: number): string {
  if (!seconds) return ''
  const date = new Date(seconds * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const accessTokenEditSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, ACCESS_TOKEN_NAME_REQUIRED)
      .max(64, ACCESS_TOKEN_NAME_TOO_LONG),
    expiry: z.enum(['30d', '90d', '180d', '1y', 'custom', 'never']),
    customExpiresAt: z.string().optional(),
    scopes: z.array(z.string()),
  })
  .superRefine((values, ctx) => {
    if (
      values.expiry === 'custom' &&
      (!values.customExpiresAt ||
        new Date(values.customExpiresAt).getTime() < Date.now() + MIN_LIFETIME_MS)
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['customExpiresAt'],
        message: ACCESS_TOKEN_CUSTOM_EXPIRY_MIN_HINT,
      })
    }
    if (values.scopes.length === 0) {
      ctx.addIssue({
        code: 'custom',
        path: ['scopes'],
        message: ACCESS_TOKEN_SCOPES_REQUIRED,
      })
    }
  })

type AccessTokenEditValues = z.infer<typeof accessTokenEditSchema>

function resolveEditExpiry(
  values: Pick<AccessTokenEditValues, 'expiry' | 'customExpiresAt'>,
  nowMs: number
): number {
  if (values.expiry === 'never') return 0
  if (values.expiry === 'custom') {
    const time = values.customExpiresAt
      ? new Date(values.customExpiresAt).getTime()
      : 0
    return Math.floor(time / 1000)
  }
  const days = ACCESS_TOKEN_EXPIRY_DAYS[values.expiry]
  return Math.floor(nowMs / 1000) + days * 24 * 60 * 60
}

type AccessTokenEditDialogProps = {
  token: AccessToken
  pending: boolean
  onClose: () => void
  onSave: (input: {
    name?: string
    scopes?: string[]
    expiresAt?: number
  }) => Promise<boolean>
}

export function AccessTokenEditDialog(props: AccessTokenEditDialogProps) {
  const { token } = props
  const nowMs = useMemo(() => Date.now(), [])
  const initialPreset = expiryPresetFromTimestamp(token.expiresAt, nowMs)
  const [expiry, setExpiry] = useState<AccessTokenExpiryPreset>(initialPreset)

  const form = useForm<AccessTokenEditValues>({
    resolver: zodResolver(accessTokenEditSchema),
    defaultValues: {
      name: token.name,
      expiry: initialPreset,
      customExpiresAt:
        initialPreset === 'custom' ? timestampToDatetimeLocal(token.expiresAt) : undefined,
      scopes: token.scopes,
    },
  })
  const scopes = form.watch('scopes')

  const close = () => {
    if (!props.pending) props.onClose()
  }

  const onSubmit = async (values: AccessTokenEditValues) => {
    const saved = await props.onSave({
      name: values.name.trim(),
      scopes: values.scopes,
      expiresAt: resolveEditExpiry(values, Date.now()),
    })
    if (saved) props.onClose()
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) close() }}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{ACCESS_TOKEN_EDIT_TITLE}</DialogTitle>
          <DialogDescription>{ACCESS_TOKEN_EDIT_DESCRIPTION}</DialogDescription>
        </DialogHeader>
        <form
          id='access-token-edit-form'
          onSubmit={form.handleSubmit(onSubmit)}
          className='grid gap-4'
          noValidate
        >
          <div className='grid gap-2'>
            <Label htmlFor='access-token-edit-name'>{ACCESS_TOKEN_NAME_FIELD}</Label>
            <Input
              id='access-token-edit-name'
              placeholder={ACCESS_TOKEN_NAME_PLACEHOLDER}
              autoComplete='off'
              {...form.register('name')}
            />
            {form.formState.errors.name && (
              <p className='text-destructive text-sm'>
                {form.formState.errors.name.message}
              </p>
            )}
          </div>

          <div className='grid gap-2'>
            <Label htmlFor='access-token-edit-expiry'>{ACCESS_TOKEN_EXPIRY_FIELD}</Label>
            <Select
              value={expiry}
              onValueChange={(value) => {
                const next = value as AccessTokenExpiryPreset
                setExpiry(next)
                form.setValue('expiry', next)
              }}
            >
              <SelectTrigger id='access-token-edit-expiry' size='sm' className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ACCESS_TOKEN_EXPIRY_PRESETS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {expiry === 'never' && (
              <p className='text-muted-foreground text-xs'>
                {ACCESS_TOKEN_EXPIRY_NEVER_HINT}
              </p>
            )}
            {expiry === 'custom' && (
              <>
                <Input
                  id='access-token-edit-custom-expiry'
                  type='datetime-local'
                  className='w-full'
                  value={form.watch('customExpiresAt') ?? ''}
                  onChange={(event) =>
                    form.setValue('customExpiresAt', event.target.value)
                  }
                />
                {form.formState.errors.customExpiresAt && (
                  <p className='text-destructive text-sm'>
                    {form.formState.errors.customExpiresAt.message}
                  </p>
                )}
              </>
            )}
          </div>

          <div className='grid gap-2'>
            <div className='flex items-baseline justify-between gap-2'>
              <Label>{ACCESS_TOKEN_SCOPES_FIELD}</Label>
              {scopes.length > 0 && (
                <span className='text-muted-foreground text-xs'>
                  已选 {scopes.length} 项
                </span>
              )}
            </div>
            <div
              className={cn(
                'max-h-72 overflow-y-auto rounded-lg border p-2',
                form.formState.errors.scopes && 'border-destructive'
              )}
            >
              <PermissionMatrix
                value={form.watch('scopes')}
                onChange={(codes) => form.setValue('scopes', codes)}
                permissionModules={ACCESS_TOKEN_SCOPE_CATALOG}
              />
            </div>
            {form.formState.errors.scopes && (
              <p className='text-destructive text-sm'>
                {form.formState.errors.scopes.message}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              type='button'
              variant='outline'
              disabled={props.pending}
              onClick={close}
            >
              {ACCESS_TOKEN_CANCEL}
            </Button>
            <Button type='submit' disabled={props.pending}>
              {props.pending ? (
                <>
                  <Loader2 className='animate-spin' aria-hidden='true' />
                  {ACCESS_TOKEN_EDIT_SAVING}
                </>
              ) : (
                ACCESS_TOKEN_EDIT_SAVE
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
