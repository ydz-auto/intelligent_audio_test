/**
 * Access Token 列表行（features/profile/components/access-token，INT-1153）。
 * 对位 new-api access-token-item：名称 + 掩码 token_hint + scopes Badge（目录标签，
 * 超出 3 个折叠计数）+ 创建/有效时间/最近使用 + 状态徽章 + 操作（编辑/启停/删除）。
 */
import { Pencil, Trash2 } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'

import type { AccessToken } from '@/domain/models/access-token'
import { ACCESS_TOKEN_SCOPE_FLAT } from '@/domain/models/access-token'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

import {
  ACCESS_TOKEN_DELETE_ARIA,
  ACCESS_TOKEN_DISABLED_BADGE,
  ACCESS_TOKEN_EDIT_ARIA,
  ACCESS_TOKEN_ENABLED_BADGE,
  ACCESS_TOKEN_EXPIRED_LABEL,
  ACCESS_TOKEN_LAST_USED_LABEL,
  ACCESS_TOKEN_NEVER_EXPIRES_LABEL,
  ACCESS_TOKEN_NEVER_USED_LABEL,
  ACCESS_TOKEN_TOGGLE_ABLE,
  ACCESS_TOKEN_TOGGLE_DISABLE,
} from './constants'

const VISIBLE_SCOPE_BADGES = 3

const SCOPE_LABELS = new Map(
  ACCESS_TOKEN_SCOPE_FLAT.map((permission) => [permission.code, permission.name])
)

function formatTime(seconds: number): string {
  if (!seconds) return ''
  return new Date(seconds * 1000).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function scopeSummary(scopes: string[]): ReactNode {
  const labels = scopes
    .map((scope) => SCOPE_LABELS.get(scope) ?? scope)
    .slice(0, VISIBLE_SCOPE_BADGES)
  const hiddenCount = scopes.length - labels.length
  return (
    <div className='flex flex-wrap gap-1'>
      {labels.map((label) => (
        <Badge key={label} variant='secondary'>
          {label}
        </Badge>
      ))}
      {hiddenCount > 0 && <Badge variant='outline'>+{hiddenCount}</Badge>}
      {scopes.length === 0 && (
        <Badge variant='outline' className='text-muted-foreground'>
          继承用户全部权限
        </Badge>
      )}
    </div>
  )
}

type AccessTokenItemProps = {
  token: AccessToken
  now: number
  pending: boolean
  onEdit: (token: AccessToken) => void
  onToggle: (token: AccessToken) => void
  onDelete: (token: AccessToken) => void
}

export function AccessTokenItem(props: AccessTokenItemProps) {
  const { token, now } = props
  const isExpired = token.expiresAt > 0 && token.expiresAt * 1000 <= now
  const expiryNode = token.expiresAt === 0 ? (
    <span>{ACCESS_TOKEN_NEVER_EXPIRES_LABEL}</span>
  ) : isExpired ? (
    <span className='text-destructive'>{ACCESS_TOKEN_EXPIRED_LABEL}</span>
  ) : (
    <span>有效至 {formatTime(token.expiresAt)}</span>
  )

  const lastUsedNode = useMemo(() => {
    if (!token.lastUsedAt) return <span>{ACCESS_TOKEN_NEVER_USED_LABEL}</span>
    const label = `${ACCESS_TOKEN_LAST_USED_LABEL} ${formatTime(token.lastUsedAt)}`
    return (
      <span className='break-all'>
        {label}
        {token.lastUsedIp ? ` · ${token.lastUsedIp}` : ''}
      </span>
    )
  }, [token.lastUsedAt, token.lastUsedIp])

  return (
    <div className='flex items-start gap-3 py-3'>
      <div className='min-w-0 flex-1 space-y-1.5'>
        <div className='flex flex-wrap items-center gap-x-2 gap-y-1'>
          <p className='font-medium break-all'>{token.name}</p>
          <code className='text-muted-foreground text-xs'>
            at_…{token.tokenHint}
          </code>
          <Badge
            variant={token.status === 'enabled' ? 'default' : 'secondary'}
            className={cn(token.status === 'disabled' && 'opacity-70')}
          >
            {token.status === 'enabled'
              ? ACCESS_TOKEN_ENABLED_BADGE
              : ACCESS_TOKEN_DISABLED_BADGE}
          </Badge>
        </div>
        {scopeSummary(token.scopes)}
        <p className='text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 text-xs'>
          <span>创建于 {formatTime(token.createdAt)}</span>
          {expiryNode}
          {lastUsedNode}
        </p>
      </div>
      <div className='flex shrink-0 items-center gap-1'>
        <Button
          type='button'
          variant='ghost'
          size='icon-sm'
          aria-label={ACCESS_TOKEN_EDIT_ARIA}
          disabled={props.pending}
          onClick={() => props.onEdit(token)}
        >
          <Pencil aria-hidden='true' />
        </Button>
        <span
          className='flex items-center gap-1 text-xs'
          title={token.status === 'enabled' ? ACCESS_TOKEN_TOGGLE_DISABLE : ACCESS_TOKEN_TOGGLE_ABLE}
        >
          <Switch
            size='sm'
            checked={token.status === 'enabled'}
            disabled={props.pending}
            aria-label={
              token.status === 'enabled'
                ? ACCESS_TOKEN_TOGGLE_DISABLE
                : ACCESS_TOKEN_TOGGLE_ABLE
            }
            onCheckedChange={() => props.onToggle(token)}
          />
        </span>
        <Button
          type='button'
          variant='ghost'
          size='icon-sm'
          aria-label={ACCESS_TOKEN_DELETE_ARIA}
          className='text-destructive hover:text-destructive'
          disabled={props.pending}
          onClick={() => props.onDelete(token)}
        >
          <Trash2 aria-hidden='true' />
        </Button>
      </div>
    </div>
  )
}
