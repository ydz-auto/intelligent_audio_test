/**
 * 供应商管理弹窗（features/agent-providers）：对话页 / 浮窗等场景的轻量入口。
 * 复用列表、表单与删除确认，与 /agent-providers 页面共享同一套 query 缓存与
 * mutation 口径；因此弹窗内新增的供应商会立即出现在页面与会话摘要中。
 */
import { Plus } from 'lucide-react'
import { useState } from 'react'

import {
  useAgentModelCatalogQuery,
  useAgentProviderMutations,
  useAgentProvidersQuery,
} from '@/application/agent/use-agent-providers'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type {
  AgentProvider,
  AgentProviderInput,
} from '@/domain/models/agentProvider'

import { AGENT_PROVIDERS_COPY } from '../constants'
import { AgentProviderFormDialog } from './agent-provider-form-dialog'
import { AgentProviderList } from './agent-provider-list'

type BusyState = {
  id: string
  action: 'verify' | 'default' | 'delete'
} | null

type AgentProviderManagerDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function AgentProviderManagerDialog({
  open,
  onOpenChange,
}: AgentProviderManagerDialogProps) {
  const list = useAgentProvidersQuery()
  const catalog = useAgentModelCatalogQuery()
  const { create, update, remove, setDefault, verify, discoverModels } =
    useAgentProviderMutations()

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<AgentProvider | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AgentProvider | null>(null)
  const [busy, setBusy] = useState<BusyState>(null)

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

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className='sm:max-w-3xl'>
          <DialogHeader>
            <DialogTitle>{AGENT_PROVIDERS_COPY.pageTitle}</DialogTitle>
            <DialogDescription>
              {AGENT_PROVIDERS_COPY.listDescription}
            </DialogDescription>
          </DialogHeader>

          <div className='flex items-center justify-end'>
            <Button onClick={handleAdd} size='sm' type='button'>
              <Plus data-icon='inline-start' aria-hidden='true' />
              {AGENT_PROVIDERS_COPY.addButton}
            </Button>
          </div>

          <div className='max-h-[62vh] overflow-y-auto pr-1'>
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
          </div>
        </DialogContent>
      </Dialog>

      <AgentProviderFormDialog
        catalog={catalog.data}
        onDiscoverModels={(input) => discoverModels.mutateAsync(input)}
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
        onOpenChange={(next) => {
          if (!next) setDeleteTarget(null)
        }}
        open={deleteTarget !== null}
        title={AGENT_PROVIDERS_COPY.deleteTitle}
      />
    </>
  )
}
