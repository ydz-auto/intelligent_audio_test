/**
 * 模型供应商管理页（features/agent-providers，INT-2493 / §6.4 / §6.4-9 / §11）。
 *
 * 入口：侧栏「AI 工具 → 模型供应商」+ Agent 工作台头行设置按钮 + 无 Key 引导。
 * 路由：/_authenticated/agent-providers，权限码 agent:provider:manage（守卫 + 导航同集合）。
 * 数据：列表与模型目录各一个 query key，所有写操作成功后 invalidate（会话页摘要同步）。
 */
import { useEffect, useMemo, useState } from 'react'

import { useAgentProviderMutations, useAgentModelCatalogQuery, useAgentProvidersQuery } from '@/application/agent/use-agent-providers'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Main } from '@/components/layout/components/main'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { IconBadge } from '@/components/ui/icon-badge'
import { KeyRound, Plus } from 'lucide-react'

import type { AgentProvider, AgentProviderInput } from '@/domain/models/agentProvider'

import { AGENT_PROVIDERS_COPY } from './constants'
import { AgentProviderFormDialog } from './components/agent-provider-form-dialog'
import { AgentProviderList } from './components/agent-provider-list'

export function AgentProvidersPage() {
  useEffect(() => {
    document.title = AGENT_PROVIDERS_COPY.pageTitle
  }, [])

  const list = useAgentProvidersQuery()
  const catalog = useAgentModelCatalogQuery()
  const { create, update, remove, setDefault, verify } = useAgentProviderMutations()

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<AgentProvider | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AgentProvider | null>(null)
  const [busy, setBusy] = useState<{
    id: string
    action: 'verify' | 'default' | 'delete'
  } | null>(null)

  const pending = create.isPending || update.isPending

  const busyProviderId = busy?.id ?? null
  const busyAction = busy?.action ?? null

  const handleAdd = () => {
    setEditing(null)
    setFormOpen(true)
  }

  const handleEdit = (provider: AgentProvider) => {
    setEditing(provider)
    setFormOpen(true)
  }

  const handleSubmit = async (input: AgentProviderInput): Promise<boolean> => {
    try {
      if (editing) {
        await update.mutateAsync({ id: editing.id, input })
      } else {
        await create.mutateAsync(input)
      }
      return true
    } catch {
      // toast 已由 mutation onError 呈现
      return false
    }
  }

  const handleSetDefault = async (provider: AgentProvider) => {
    setBusy({ id: provider.id, action: 'default' })
    try {
      await setDefault.mutateAsync(provider.id)
    } catch {
      // toast 已由 mutation onError 呈现
    } finally {
      setBusy(null)
    }
  }

  const handleVerify = async (provider: AgentProvider) => {
    setBusy({ id: provider.id, action: 'verify' })
    try {
      await verify.mutateAsync(provider.id)
    } catch {
      // toast 已由 mutation onError 呈现
    } finally {
      setBusy(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    const target = deleteTarget
    setDeleteTarget(null)
    setBusy({ id: target.id, action: 'delete' })
    try {
      await remove.mutateAsync(target.id)
    } catch {
      // toast 已由 mutation onError 呈现
    } finally {
      setBusy(null)
    }
  }

  const count = useMemo(() => list.data?.length ?? 0, [list.data])

  return (
    <Main>
      <div className='min-h-0 flex-1 overflow-y-auto px-3 py-3 sm:px-4 sm:py-6'>
        <div className='mx-auto grid w-full max-w-5xl gap-4'>
          <header className='flex flex-wrap items-start justify-between gap-3'>
            <div className='min-w-0'>
              <h1 className='text-xl font-semibold tracking-tight'>
                {AGENT_PROVIDERS_COPY.pageTitle}
              </h1>
              <p className='text-muted-foreground mt-1 max-w-3xl text-sm'>
                {AGENT_PROVIDERS_COPY.pageDescription}
              </p>
            </div>
            <Button onClick={handleAdd} type='button'>
              <Plus data-icon='inline-start' aria-hidden='true' />
              {AGENT_PROVIDERS_COPY.addButton}
            </Button>
          </header>

          <div className='border-primary/20 bg-primary/5 flex items-start gap-2.5 rounded-xl border px-3 py-2.5'>
            <IconBadge decorative size='sm' tone='info'>
              <KeyRound aria-hidden='true' />
            </IconBadge>
            <p className='text-muted-foreground text-xs leading-5'>
              {AGENT_PROVIDERS_COPY.securityNotice}
            </p>
          </div>

          <Card>
            <CardHeader className='pb-2'>
              <CardTitle className='flex items-center justify-between gap-2 text-base'>
                <span>{AGENT_PROVIDERS_COPY.listTitle}</span>
                <span className='text-muted-foreground text-xs font-normal'>
                  {count > 0 ? `共 ${count} 个` : null}
                </span>
              </CardTitle>
              <p className='text-muted-foreground text-xs'>
                {AGENT_PROVIDERS_COPY.listDescription}
              </p>
            </CardHeader>
            <CardContent>
              <AgentProviderList
                busyAction={busyAction}
                busyProviderId={busyProviderId}
                isError={list.isError}
                isPending={list.isPending}
                onAdd={handleAdd}
                onDelete={(provider) => setDeleteTarget(provider)}
                onEdit={handleEdit}
                onRetry={() => void list.refetch()}
                onSetDefault={(provider) => void handleSetDefault(provider)}
                onVerify={(provider) => void handleVerify(provider)}
                providers={list.data}
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <AgentProviderFormDialog
        catalog={catalog.data}
        onOpenChange={setFormOpen}
        onSubmit={handleSubmit}
        open={formOpen}
        pending={pending}
        provider={editing}
      />

      <ConfirmDialog
        confirmText={AGENT_PROVIDERS_COPY.delete}
        desc={
          deleteTarget
            ? `${deleteTarget.name}：${AGENT_PROVIDERS_COPY.deleteDescription}`
            : AGENT_PROVIDERS_COPY.deleteDescription
        }
        destructive
        handleConfirm={() => void handleDelete()}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        open={deleteTarget !== null}
        title={AGENT_PROVIDERS_COPY.deleteTitle}
      />
    </Main>
  )
}

export default AgentProvidersPage
