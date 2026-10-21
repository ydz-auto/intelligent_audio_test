/**
 * Access Token 管理卡（features/profile/components/access-token，INT-1153）。
 * 个人配置页 /profile 的 token 管理区块：创建（明文显示一次）/ 列表（掩码）/
 * 复制 / 编辑 scopes + expires_at / 启停 / 删除。真实请求走 accessTokenApi
 * （GET/POST/PATCH/DELETE /api/v1/auth/access-tokens），无 mock 残留。
 */
import { KeyRound, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'

import {
  useAccessTokenMutations,
  useAccessTokensQuery,
} from '@/application/access-token/use-access-tokens'
import type { AccessToken } from '@/domain/models/access-token'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { TitledCard } from '@/features/profile/components/titled-card'

import {
  ACCESS_TOKENS_CREATE_ARIA,
  ACCESS_TOKENS_CREATE_BUTTON,
  ACCESS_TOKENS_DESCRIPTION,
  ACCESS_TOKENS_EMPTY_DESCRIPTION,
  ACCESS_TOKENS_EMPTY_TITLE,
  ACCESS_TOKENS_ERROR_TITLE,
  ACCESS_TOKENS_LOADING_ARIA,
  ACCESS_TOKENS_RETRY,
  ACCESS_TOKENS_TITLE,
  ACCESS_TOKEN_DELETE_CONFIRM,
  ACCESS_TOKEN_DELETE_DESCRIPTION,
  ACCESS_TOKEN_DELETE_TITLE,
} from './constants'
import { AccessTokenCreateDialog } from './access-token-create-dialog'
import { AccessTokenEditDialog } from './access-token-edit-dialog'
import { AccessTokenItem } from './access-token-item'
import { AccessTokenRevealDialog } from './access-token-reveal-dialog'

export function AccessTokensCard() {
  const list = useAccessTokensQuery()
  const { create, update, remove } = useAccessTokenMutations()

  const [createOpen, setCreateOpen] = useState(false)
  const [revealToken, setRevealToken] = useState<string | null>(null)
  const [editTarget, setEditTarget] = useState<AccessToken | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AccessToken | null>(null)

  const pending = create.isPending || update.isPending || remove.isPending
  const now = useMemo(() => Date.now(), [])

  const handleCreate = async (input: {
    name: string
    scopes: string[]
    expiresAt: number
  }): Promise<boolean> => {
    try {
      const created = await create.mutateAsync(input)
      if (created?.token) {
        setRevealToken(created.token)
        return true
      }
      return false
    } catch {
      return false
    }
  }

  const handleSave = async (token: AccessToken, input: {
    name?: string
    scopes?: string[]
    expiresAt?: number
  }): Promise<boolean> => {
    try {
      await update.mutateAsync({ id: token.id, input })
      return true
    } catch {
      return false
    }
  }

  const handleToggle = (token: AccessToken) => {
    void update
      .mutateAsync({
        id: token.id,
        input: { status: token.status === 'enabled' ? 'disabled' : 'enabled' },
      })
      .catch(() => {})
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    const target = deleteTarget
    setDeleteTarget(null)
    try {
      await remove.mutateAsync(target.id)
    } catch {
      // 失败 toast 已由 mutation onError 呈现
    }
  }

  return (
    <>
      <TitledCard
        icon={<KeyRound aria-hidden='true' />}
        tone='info'
        title={ACCESS_TOKENS_TITLE}
        description={ACCESS_TOKENS_DESCRIPTION}
      >
        <div className='grid gap-3'>
          <div className='flex flex-wrap items-center justify-end gap-2'>
            <Button
              type='button'
              size='sm'
              disabled={pending}
              aria-label={ACCESS_TOKENS_CREATE_ARIA}
              onClick={() => setCreateOpen(true)}
            >
              <Plus data-icon='inline-start' aria-hidden='true' />
              {ACCESS_TOKENS_CREATE_BUTTON}
            </Button>
          </div>

          {list.isPending ? (
            <div role='status' aria-label={ACCESS_TOKENS_LOADING_ARIA} className='min-h-24'>
              <Spinner className='text-muted-foreground mx-auto mt-6' />
            </div>
          ) : list.isError ? (
            <div className='flex flex-col items-center gap-2 py-6 text-center'>
              <p className='text-muted-foreground text-sm'>{ACCESS_TOKENS_ERROR_TITLE}</p>
              <Button type='button' variant='outline' size='sm' onClick={() => void list.refetch()}>
                {ACCESS_TOKENS_RETRY}
              </Button>
            </div>
          ) : !list.data || list.data.length === 0 ? (
            <Empty className='min-h-32'>
              <EmptyContent>
                <EmptyMedia variant='icon'>
                  <KeyRound aria-hidden='true' />
                </EmptyMedia>
                <EmptyHeader>
                  <EmptyTitle>{ACCESS_TOKENS_EMPTY_TITLE}</EmptyTitle>
                  <EmptyDescription>{ACCESS_TOKENS_EMPTY_DESCRIPTION}</EmptyDescription>
                </EmptyHeader>
              </EmptyContent>
            </Empty>
          ) : (
            <div className='flex flex-col'>
              {list.data.map((token, index) => (
                <div key={token.id}>
                  {index > 0 && <Separator />}
                  <AccessTokenItem
                    token={token}
                    now={now}
                    pending={pending}
                    onEdit={setEditTarget}
                    onToggle={handleToggle}
                    onDelete={setDeleteTarget}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </TitledCard>

      <AccessTokenCreateDialog
        open={createOpen}
        pending={create.isPending}
        onOpenChange={setCreateOpen}
        onCreate={handleCreate}
      />
      {revealToken !== null && (
        <AccessTokenRevealDialog token={revealToken} onClose={() => setRevealToken(null)} />
      )}
      {editTarget && (
        <AccessTokenEditDialog
          key={editTarget.id}
          token={editTarget}
          pending={update.isPending}
          onClose={() => setEditTarget(null)}
          onSave={(input) => handleSave(editTarget, input)}
        />
      )}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setDeleteTarget(null)
        }}
        title={ACCESS_TOKEN_DELETE_TITLE}
        desc={ACCESS_TOKEN_DELETE_DESCRIPTION}
        confirmText={ACCESS_TOKEN_DELETE_CONFIRM}
        destructive
        isLoading={remove.isPending}
        handleConfirm={() => void handleDelete()}
      />
    </>
  )
}
