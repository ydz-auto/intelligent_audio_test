/**
 * OAuth 提供方分区（interfaces 层，INT-347 §4.2 母版 B）：
 * 说明 Alert（回调地址格式 code + 复制回调地址）→ 工具行（「添加提供方」）→
 * StaticDataTable（图标/名称/Slug/状态/Client ID/授权端点/操作）→
 * 新建/编辑 Dialog（自动发现区 + 字段 + 四字段映射）→ 删除 ConfirmDialog。
 * 母版 B 唯一分区（算法/测试域五分区随 INT-417 移出）。
 */
import { useEffect, useState } from 'react'
import { AlertCircle, Ellipsis, KeyRound, Plus, Sparkles } from 'lucide-react'

import { usePermissions } from '@/application/hooks/use-permissions'
import {
  useOAuthProvidersQuery,
  useOAuthProviderMutations,
} from '@/application/oauth/use-oauth-providers'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CopyButton } from '@/components/copy-button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ErrorState } from '@/components/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import {
  OAUTH_CALLBACK_TEMPLATE,
  type OAuthProvider,
} from '@/domain/models/oauth-provider'
import { cn } from '@/lib/utils'

import { SettingsSection } from '../components/settings-section'
import { StaticDataTable, type StaticDataTableColumn } from '../components/static-data-table'

export function OAuthProvidersPage() {
  const { hasPermission } = usePermissions()
  const providersQuery = useOAuthProvidersQuery()
  const mutations = useOAuthProviderMutations()

  const canManage = hasPermission('auth:manage_provider')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogProvider, setDialogProvider] = useState<OAuthProvider | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<OAuthProvider | null>(null)

  const openCreate = () => {
    setDialogProvider(null)
    setDialogOpen(true)
  }
  const openEdit = (provider: OAuthProvider) => {
    setDialogProvider(provider)
    setDialogOpen(true)
  }

  const columns: Array<StaticDataTableColumn<OAuthProvider>> = [
    {
      key: 'name',
      header: '名称',
      render: (row) => (
        <div className='flex items-center gap-2'>
          <span className='bg-muted flex size-7 items-center justify-center rounded-md'>
            <KeyRound className='size-3.5' aria-hidden='true' />
          </span>
          <span className='font-medium'>{row.name}</span>
        </div>
      ),
    },
    { key: 'slug', header: 'Slug', render: (row) => <span className='font-mono text-xs'>{row.slug}</span> },
    {
      key: 'status',
      header: '状态',
      render: (row) => (
        <Badge variant={row.status === 'enabled' ? 'default' : 'secondary'}>
          {row.status === 'enabled' ? '启用' : '停用'}
        </Badge>
      ),
    },
    { key: 'clientId', header: 'Client ID', render: (row) => <span className='font-mono text-xs'>{row.clientId}</span> },
    {
      key: 'authorizationEndpoint',
      header: '授权端点',
      render: (row) => (
        <span className='text-muted-foreground line-clamp-1 max-w-[200px] font-mono text-xs'>
          {row.authorizationEndpoint}
        </span>
      ),
    },
  ]

  return (
    <SettingsSection
      title='OAuth 提供方'
      description='管理用于用户认证的自定义 OAuth 提供方'
    >
      <Alert>
        <AlertCircle className='size-4' aria-hidden='true' />
        <AlertTitle>回调地址格式</AlertTitle>
        <AlertDescription>
          <span className='mt-1 flex items-center gap-2'>
            <code className='border-border/70 bg-muted/60 rounded px-1.5 py-0.5 font-mono text-xs'>
              {OAUTH_CALLBACK_TEMPLATE}
            </code>
            <CopyButton value={OAUTH_CALLBACK_TEMPLATE} aria-label='复制回调地址' />
          </span>
          注册自定义 OAuth 提供方时使用此回调地址。
        </AlertDescription>
      </Alert>

      <div className='flex flex-wrap items-center justify-between gap-2'>
        <p className='text-muted-foreground text-sm'>
          注册自定义 OAuth 提供方时使用此回调地址。
        </p>
        {canManage && (
          <Button size='sm' onClick={openCreate}>
            <Plus data-icon='inline-start' />
            添加提供方
          </Button>
        )}
      </div>

      {providersQuery.isLoading ? (
        <div aria-busy='true' className='overflow-hidden rounded-lg border'>
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className='flex gap-4 border-b p-4 last:border-0'>
              <Skeleton className='h-5 w-40' />
              <Skeleton className='h-5 w-24' />
              <Skeleton className='h-5 flex-1' />
            </div>
          ))}
        </div>
      ) : providersQuery.isError ? (
        <ErrorState
          title='加载失败'
          description='OAuth 提供方列表加载失败，请重试'
          onRetry={() => void providersQuery.refetch()}
        />
      ) : (
        <StaticDataTable
          columns={columns}
          rows={providersQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText='尚未配置自定义 OAuth 提供方。'
          emptyDescription='点击「添加提供方」注册自定义 OAuth 提供方'
          minWidth='720px'
          actions={
            canManage
              ? (row) => (
                  <DropdownMenu modal={false}>
                    <DropdownMenuTrigger
                      render={
                        <Button
                          variant='ghost'
                          size='icon-sm'
                          aria-label={`提供方操作：${row.name}`}
                        />
                      }
                    >
                      <Ellipsis className='size-4' />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align='end' className='w-36'>
                      <DropdownMenuItem onClick={() => openEdit(row)}>
                        编辑
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        variant='destructive'
                        onClick={() => setDeleteTarget(row)}
                      >
                        删除
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )
              : undefined
          }
        />
      )}

      {/* 新建/编辑 Dialog */}
      <OAuthProviderDialog
        open={dialogOpen}
        provider={dialogProvider}
        onOpenChange={setDialogOpen}
        onSave={(input) => {
          if (dialogProvider) {
            mutations.updateProvider.mutate({
              providerId: dialogProvider.id,
              patch: input,
            })
          } else {
            mutations.createProvider.mutate(input)
          }
          setDialogOpen(false)
        }}
      />

      {/* 删除确认 */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title='确认删除提供方'
        desc={
          deleteTarget
            ? `删除后不可恢复，将移除 ${deleteTarget.name} 提供方的登录入口。`
            : ''
        }
        destructive
        cancelBtnText='取消'
        confirmText='删除'
        isLoading={mutations.deleteProvider.isPending}
        handleConfirm={() => {
          if (deleteTarget) mutations.deleteProvider.mutate(deleteTarget.id)
          setDeleteTarget(null)
        }}
      />
    </SettingsSection>
  )
}

// ---------------------------------------------------------------------------
// 新建/编辑提供方对话框（自动发现区 + 字段 + 四字段映射）
// ---------------------------------------------------------------------------

type OAuthProviderDialogProps = {
  open: boolean
  provider: OAuthProvider | null
  onOpenChange: (open: boolean) => void
  onSave: (input: Omit<OAuthProvider, 'id' | 'createdAt'>) => void
}

/** 表单字段（字段级错误的定位键，与 Input 的 id 后缀一致） */
type OAuthProviderField =
  | 'name'
  | 'slug'
  | 'clientId'
  | 'clientSecret'
  | 'authorizationEndpoint'
  | 'tokenEndpoint'
  | 'userinfoEndpoint'

type OAuthProviderFieldErrors = Partial<Record<OAuthProviderField, string>>

/** Slug 口径（§6：小写字母/数字/连字符、不以连字符开头或结尾；与后端 slug 校验一致） */
const OAUTH_SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

function OAuthProviderDialog(props: OAuthProviderDialogProps) {
  const { discoverEndpoints } = useOAuthProviderMutations()
  const isCreate = props.provider === null

  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [icon, setIcon] = useState('')
  const [status, setStatus] = useState<'enabled' | 'disabled'>('enabled')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [authorizationEndpoint, setAuthorizationEndpoint] = useState('')
  const [tokenEndpoint, setTokenEndpoint] = useState('')
  const [userinfoEndpoint, setUserinfoEndpoint] = useState('')
  const [scopes, setScopes] = useState('')
  const [userIdentifier, setUserIdentifier] = useState('sub')
  const [userName, setUserName] = useState('preferred_username')
  const [displayName, setDisplayName] = useState('name')
  const [email, setEmail] = useState('email')
  const [issuerUrl, setIssuerUrl] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<OAuthProviderFieldErrors>({})

  useEffect(() => {
    if (!props.open) return
    const target = props.provider
    setName(target?.name ?? '')
    setSlug(target?.slug ?? '')
    setIcon(target?.icon ?? '')
    setStatus(target?.status ?? 'enabled')
    setClientId(target?.clientId ?? '')
    setClientSecret('')
    setAuthorizationEndpoint(target?.authorizationEndpoint ?? '')
    setTokenEndpoint(target?.tokenEndpoint ?? '')
    setUserinfoEndpoint(target?.userinfoEndpoint ?? '')
    setScopes(target?.scopes ?? '')
    setUserIdentifier(target?.fieldMapping.userIdentifier ?? 'sub')
    setUserName(target?.fieldMapping.userName ?? 'preferred_username')
    setDisplayName(target?.fieldMapping.displayName ?? 'name')
    setEmail(target?.fieldMapping.email ?? 'email')
    setIssuerUrl('')
    setFieldErrors({})
  }, [props.open, props.provider])

  const clearFieldError = (field: OAuthProviderField) =>
    setFieldErrors((prev) => {
      if (!prev[field]) return prev
      const next = { ...prev }
      delete next[field]
      return next
    })

  const handleDiscover = async () => {
    if (!issuerUrl.trim() || discovering) return
    setDiscovering(true)
    try {
      const endpoints = await discoverEndpoints(issuerUrl)
      if (endpoints) {
        setAuthorizationEndpoint(endpoints.authorizationEndpoint)
        setTokenEndpoint(endpoints.tokenEndpoint)
        setUserinfoEndpoint(endpoints.userinfoEndpoint)
      }
    } finally {
      setDiscovering(false)
    }
  }

  /** 前端必填/格式校验（§6：Client Secret 新建必填、编辑留空保留原值；三端点必填；Slug 小写字母/数字/连字符） */
  const validate = (): OAuthProviderFieldErrors => {
    const errors: OAuthProviderFieldErrors = {}
    const trimmedSlug = slug.trim()
    if (!name.trim()) errors.name = '请输入名称'
    if (!trimmedSlug) errors.slug = '请输入 Slug'
    else if (!OAUTH_SLUG_PATTERN.test(trimmedSlug))
      errors.slug = '仅允许小写字母、数字与连字符'
    if (!clientId.trim()) errors.clientId = '请输入 Client ID'
    if (isCreate && !clientSecret.trim()) errors.clientSecret = '请输入 Client Secret'
    if (!authorizationEndpoint.trim()) errors.authorizationEndpoint = '请输入授权端点'
    if (!tokenEndpoint.trim()) errors.tokenEndpoint = '请输入 Token 端点'
    if (!userinfoEndpoint.trim()) errors.userinfoEndpoint = '请输入用户信息端点'
    return errors
  }

  const handleSave = () => {
    const errors = validate()
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return
    props.onSave({
      name: name.trim(),
      slug: slug.trim(),
      icon: icon.trim() || undefined,
      status,
      clientId: clientId.trim(),
      clientSecret: clientSecret.trim() || undefined,
      authorizationEndpoint: authorizationEndpoint.trim(),
      tokenEndpoint: tokenEndpoint.trim(),
      userinfoEndpoint: userinfoEndpoint.trim(),
      scopes: scopes.trim(),
      fieldMapping: {
        userIdentifier,
        userName,
        displayName,
        email,
      },
    })
  }

  const inputClass = cn('h-8')

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-[640px]'>
        <DialogHeader>
          <DialogTitle>{isCreate ? '新建提供方' : '编辑提供方'}</DialogTitle>
          <DialogDescription>
            注册自定义 OAuth 提供方，用户可使用其账号登录平台
          </DialogDescription>
        </DialogHeader>
        <div className='max-h-[60vh] space-y-4 overflow-y-auto pr-1'>
          {/* 自动发现 */}
          <div className='bg-muted/20 flex flex-col gap-2 rounded-xl border px-3 py-2.5'>
            <Label htmlFor='oauth-issuer'>Issuer URL 或 Discovery URL</Label>
            <div className='flex items-center gap-2'>
              <Input
                id='oauth-issuer'
                className={inputClass}
                placeholder='如 https://idp.example.com'
                value={issuerUrl}
                onChange={(event) => setIssuerUrl(event.target.value)}
              />
              <Button
                type='button'
                variant='outline'
                size='sm'
                className='h-8 shrink-0'
                disabled={discovering}
                onClick={() => void handleDiscover()}
              >
                <Sparkles
                  className={cn('size-3.5', discovering && 'animate-spin')}
                  aria-hidden='true'
                />
                {discovering ? '发现中…' : '自动发现端点'}
              </Button>
            </div>
          </div>

          {/* 基本信息 */}
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-name' required>
                名称
              </Label>
              <Input
                id='oauth-name'
                className={inputClass}
                placeholder='如 GitHub'
                value={name}
                aria-invalid={Boolean(fieldErrors.name)}
                aria-describedby={fieldErrors.name ? 'oauth-name-error' : undefined}
                onChange={(event) => {
                  setName(event.target.value)
                  clearFieldError('name')
                }}
              />
              {fieldErrors.name && (
                <p id='oauth-name-error' className='text-destructive text-xs'>
                  {fieldErrors.name}
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-slug' required>
                Slug
              </Label>
              <Input
                id='oauth-slug'
                className={inputClass}
                placeholder='github'
                value={slug}
                aria-invalid={Boolean(fieldErrors.slug)}
                aria-describedby={fieldErrors.slug ? 'oauth-slug-error' : 'oauth-slug-hint'}
                onChange={(event) => {
                  setSlug(event.target.value)
                  clearFieldError('slug')
                }}
              />
              {fieldErrors.slug ? (
                <p id='oauth-slug-error' className='text-destructive text-xs'>
                  {fieldErrors.slug}
                </p>
              ) : (
                <p id='oauth-slug-hint' className='text-muted-foreground text-xs'>
                  小写字母/数字/连字符
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-icon'>图标（可选）</Label>
              <Input
                id='oauth-icon'
                className={inputClass}
                placeholder='图标名称'
                value={icon}
                onChange={(event) => setIcon(event.target.value)}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-status'>状态</Label>
              <Select
                value={status}
                onValueChange={(value) => setStatus(value as 'enabled' | 'disabled')}
              >
                <SelectTrigger id='oauth-status' className={inputClass}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='enabled'>启用</SelectItem>
                  <SelectItem value='disabled'>停用</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-client-id' required>
                Client ID
              </Label>
              <Input
                id='oauth-client-id'
                className={inputClass}
                value={clientId}
                aria-invalid={Boolean(fieldErrors.clientId)}
                aria-describedby={fieldErrors.clientId ? 'oauth-client-id-error' : undefined}
                onChange={(event) => {
                  setClientId(event.target.value)
                  clearFieldError('clientId')
                }}
              />
              {fieldErrors.clientId && (
                <p id='oauth-client-id-error' className='text-destructive text-xs'>
                  {fieldErrors.clientId}
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-client-secret' required={isCreate}>
                Client Secret
              </Label>
              <Input
                id='oauth-client-secret'
                type='password'
                className={inputClass}
                placeholder={isCreate ? '' : '留空保留原值'}
                value={clientSecret}
                aria-invalid={Boolean(fieldErrors.clientSecret)}
                aria-describedby={
                  fieldErrors.clientSecret ? 'oauth-client-secret-error' : undefined
                }
                onChange={(event) => {
                  setClientSecret(event.target.value)
                  clearFieldError('clientSecret')
                }}
              />
              {fieldErrors.clientSecret && (
                <p id='oauth-client-secret-error' className='text-destructive text-xs'>
                  {fieldErrors.clientSecret}
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-authz-endpoint' required>
                授权端点
              </Label>
              <Input
                id='oauth-authz-endpoint'
                className={inputClass}
                value={authorizationEndpoint}
                aria-invalid={Boolean(fieldErrors.authorizationEndpoint)}
                aria-describedby={
                  fieldErrors.authorizationEndpoint ? 'oauth-authz-endpoint-error' : undefined
                }
                onChange={(event) => {
                  setAuthorizationEndpoint(event.target.value)
                  clearFieldError('authorizationEndpoint')
                }}
              />
              {fieldErrors.authorizationEndpoint && (
                <p id='oauth-authz-endpoint-error' className='text-destructive text-xs'>
                  {fieldErrors.authorizationEndpoint}
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-token-endpoint' required>
                Token 端点
              </Label>
              <Input
                id='oauth-token-endpoint'
                className={inputClass}
                value={tokenEndpoint}
                aria-invalid={Boolean(fieldErrors.tokenEndpoint)}
                aria-describedby={
                  fieldErrors.tokenEndpoint ? 'oauth-token-endpoint-error' : undefined
                }
                onChange={(event) => {
                  setTokenEndpoint(event.target.value)
                  clearFieldError('tokenEndpoint')
                }}
              />
              {fieldErrors.tokenEndpoint && (
                <p id='oauth-token-endpoint-error' className='text-destructive text-xs'>
                  {fieldErrors.tokenEndpoint}
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-userinfo-endpoint' required>
                用户信息端点
              </Label>
              <Input
                id='oauth-userinfo-endpoint'
                className={inputClass}
                value={userinfoEndpoint}
                aria-invalid={Boolean(fieldErrors.userinfoEndpoint)}
                aria-describedby={
                  fieldErrors.userinfoEndpoint ? 'oauth-userinfo-endpoint-error' : undefined
                }
                onChange={(event) => {
                  setUserinfoEndpoint(event.target.value)
                  clearFieldError('userinfoEndpoint')
                }}
              />
              {fieldErrors.userinfoEndpoint && (
                <p id='oauth-userinfo-endpoint-error' className='text-destructive text-xs'>
                  {fieldErrors.userinfoEndpoint}
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-scopes'>Scopes（可选）</Label>
              <Input
                id='oauth-scopes'
                className={inputClass}
                placeholder='openid profile email'
                value={scopes}
                onChange={(event) => setScopes(event.target.value)}
              />
            </div>
          </div>

          {/* 字段映射 */}
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-map-id'>用户标识字段</Label>
              <Input
                id='oauth-map-id'
                className={inputClass}
                value={userIdentifier}
                onChange={(event) => setUserIdentifier(event.target.value)}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-map-name'>用户名字段</Label>
              <Input
                id='oauth-map-name'
                className={inputClass}
                value={userName}
                onChange={(event) => setUserName(event.target.value)}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-map-display'>显示名字段</Label>
              <Input
                id='oauth-map-display'
                className={inputClass}
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='oauth-map-email'>邮箱字段</Label>
              <Input
                id='oauth-map-email'
                className={inputClass}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
