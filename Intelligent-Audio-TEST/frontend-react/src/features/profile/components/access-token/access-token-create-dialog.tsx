/**
 * 创建 Access Token 对话框（features/profile/components/access-token，INT-1153）。
 * 对位 new-api access-token-create-dialog：名称 + 有效时间预设（30/90/180 天、
 * 1 年、自定义、永不过期）+ 业务可暴露 scopes 目录勾选（复用系统设置权限矩阵）。
 * 明文只在创建成功后由 reveal 对话框显示一次，本表单不缓存任何明文。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { ACCESS_TOKEN_SCOPE_CATALOG } from '@/domain/models/access-token'
import type { AccessTokenExpiryValue } from '@/infrastructure/dto/access-token.dto'
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
  ACCESS_TOKEN_CREATE_DESCRIPTION,
  ACCESS_TOKEN_CREATE_SUBMIT,
  ACCESS_TOKEN_CREATE_TITLE,
  ACCESS_TOKEN_CREATING,
  ACCESS_TOKEN_CUSTOM_EXPIRY_MIN_HINT,
  ACCESS_TOKEN_CUSTOM_EXPIRY_REQUIRED,
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

export const ACCESS_TOKEN_EXPIRY_DAYS: Record<string, number> = {
  '30d': 30,
  '90d': 90,
  '180d': 180,
  '1y': 365,
}

export type AccessTokenExpiryPreset =
  (typeof ACCESS_TOKEN_EXPIRY_PRESETS)[number]['value']

const MIN_LIFETIME_MS = 60 * 60 * 1000

const accessTokenFormSchema = z
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

type AccessTokenFormValues = z.infer<typeof accessTokenFormSchema>

const DEFAULT_VALUES: AccessTokenFormValues = {
  name: '',
  expiry: '30d',
  customExpiresAt: undefined,
  scopes: [],
}

/** Date → 本地「YYYY-MM-DDTHH:mm」字符串（datetime-local 同款 naive 形态）。
 *  后端把 naive ISO 按东八区解析，与前端本地时间一致，预设/自定义可往返。 */
export function datetimeLocalString(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/**
 * 表单有效时间 → 提交值（0=永不过期，否则 ISO 时间字符串，对齐后端 _parse_expires_at
 * 契约——非零整数会 400，故不再算 Unix 秒）。
 */
export function resolveAccessTokenExpiry(
  values: Pick<AccessTokenFormValues, 'expiry' | 'customExpiresAt'>,
  nowMs: number
): AccessTokenExpiryValue {
  if (values.expiry === 'never') return 0
  if (values.expiry === 'custom') {
    // datetime-local 值即为 naive ISO 字符串；表单校验保证已选且 ≥1h
    return values.customExpiresAt ?? 0
  }
  const days = ACCESS_TOKEN_EXPIRY_DAYS[values.expiry]
  return datetimeLocalString(new Date(nowMs + days * 24 * 60 * 60 * 1000))
}

type AccessTokenCreateDialogProps = {
  open: boolean
  pending: boolean
  onOpenChange: (open: boolean) => void
  onCreate: (input: {
    name: string
    scopes: string[]
    expiresAt: AccessTokenExpiryValue
  }) => Promise<boolean>
}

export function AccessTokenCreateDialog(props: AccessTokenCreateDialogProps) {
  const form = useForm<AccessTokenFormValues>({
    resolver: zodResolver(accessTokenFormSchema),
    defaultValues: DEFAULT_VALUES,
  })
  const expiry = form.watch('expiry')
  const scopes = form.watch('scopes')

  const close = () => {
    if (props.pending) return
    form.reset(DEFAULT_VALUES)
    props.onOpenChange(false)
  }

  const onSubmit = async (values: AccessTokenFormValues) => {
    const created = await props.onCreate({
      name: values.name.trim(),
      scopes: values.scopes,
      expiresAt: resolveAccessTokenExpiry(values, Date.now()),
    })
    if (!created) return
    form.reset(DEFAULT_VALUES)
    props.onOpenChange(false)
  }

  return (
    <Dialog open={props.open} onOpenChange={(open) => { if (!open) close() }}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{ACCESS_TOKEN_CREATE_TITLE}</DialogTitle>
          <DialogDescription>{ACCESS_TOKEN_CREATE_DESCRIPTION}</DialogDescription>
        </DialogHeader>
        <form
          id='access-token-create-form'
          onSubmit={form.handleSubmit(onSubmit)}
          className='grid gap-4'
          noValidate
        >
          <div className='grid gap-2'>
            <Label htmlFor='access-token-name'>{ACCESS_TOKEN_NAME_FIELD}</Label>
            <Input
              id='access-token-name'
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
            <Label htmlFor='access-token-expiry'>{ACCESS_TOKEN_EXPIRY_FIELD}</Label>
            <Select
              value={expiry}
              onValueChange={(value) =>
                form.setValue('expiry', value as AccessTokenExpiryPreset)
              }
            >
              <SelectTrigger id='access-token-expiry' size='sm' className='w-full'>
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
                  id='access-token-custom-expiry'
                  type='datetime-local'
                  className='w-full'
                  value={form.watch('customExpiresAt') ?? ''}
                  onChange={(event) =>
                    form.setValue('customExpiresAt', event.target.value)
                  }
                />
                {form.formState.errors.customExpiresAt && (
                  <p className='text-destructive text-sm'>
                    {form.formState.errors.customExpiresAt.message ??
                      ACCESS_TOKEN_CUSTOM_EXPIRY_REQUIRED}
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
                  {ACCESS_TOKEN_CREATING}
                </>
              ) : (
                ACCESS_TOKEN_CREATE_SUBMIT
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
