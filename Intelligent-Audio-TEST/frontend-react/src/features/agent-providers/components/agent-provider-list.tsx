/**
 * 供应商列表（features/agent-providers）：加载 / 空 / 错误三态 + 行操作。
 * 行内展示：名称、协议、模型、Base URL、有效窗口 + 来源、默认标记、状态、
 * 最近验证时间、Key 掩码；覆盖告警单独一行展示但不阻断保存。
 */
import {
  CheckCircle2,
  Cpu,
  KeyRound,
  Pencil,
  Plus,
  Star,
  Trash2,
} from 'lucide-react'

import {
  AGENT_PROVIDER_STATUS,
  AGENT_PROVIDER_STATUS_LABELS,
  CONTEXT_WINDOW_SOURCE_LABELS,
  agentProviderProtocolLabel,
  formatContextWindowTokens,
  formatVerifiedAt,
  type AgentProvider,
} from '@/domain/models/agentProvider'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

import { AGENT_PROVIDERS_COPY } from '../constants'

type AgentProviderListProps = {
  providers: AgentProvider[] | undefined
  isPending: boolean
  isError: boolean
  onRetry: () => void
  onAdd: () => void
  onEdit: (provider: AgentProvider) => void
  onDelete: (provider: AgentProvider) => void
  onSetDefault: (provider: AgentProvider) => void
  onVerify: (provider: AgentProvider) => void
  /** 行内操作在途标记（按 providerId 维度） */
  busyProviderId: string | null
  busyAction: 'verify' | 'default' | 'delete' | null
}

export function AgentProviderList({
  providers,
  isPending,
  isError,
  onRetry,
  onAdd,
  onEdit,
  onDelete,
  onSetDefault,
  onVerify,
  busyProviderId,
  busyAction,
}: AgentProviderListProps) {
  if (isPending) {
    return (
      <div
        aria-label={AGENT_PROVIDERS_COPY.loading}
        className='grid min-h-40 place-items-center'
        role='status'
      >
        <Spinner className='text-muted-foreground' />
      </div>
    )
  }

  if (isError) {
    return (
      <div className='flex flex-col items-center gap-2 py-10 text-center'>
        <p className='text-destructive text-sm'>{AGENT_PROVIDERS_COPY.loadErrorTitle}</p>
        <Button onClick={onRetry} size='sm' type='button' variant='outline'>
          {AGENT_PROVIDERS_COPY.retry}
        </Button>
      </div>
    )
  }

  if (!providers || providers.length === 0) {
    return (
      <Empty className='min-h-44'>
        <EmptyContent>
          <EmptyMedia variant='icon'>
            <KeyRound aria-hidden='true' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>{AGENT_PROVIDERS_COPY.emptyTitle}</EmptyTitle>
            <EmptyDescription>{AGENT_PROVIDERS_COPY.emptyDescription}</EmptyDescription>
          </EmptyHeader>
          <Button onClick={onAdd} size='sm' type='button'>
            <Plus data-icon='inline-start' aria-hidden='true' />
            {AGENT_PROVIDERS_COPY.addButton}
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <div className='grid gap-3'>
      {providers.map((provider) => (
        <AgentProviderRow
          busyAction={busyProviderId === provider.id ? busyAction : null}
          key={provider.id}
          onDelete={() => onDelete(provider)}
          onEdit={() => onEdit(provider)}
          onSetDefault={() => onSetDefault(provider)}
          onVerify={() => onVerify(provider)}
          provider={provider}
        />
      ))}
    </div>
  )
}

function AgentProviderRow({
  provider,
  busyAction,
  onEdit,
  onDelete,
  onSetDefault,
  onVerify,
}: {
  provider: AgentProvider
  busyAction: 'verify' | 'default' | 'delete' | null
  onEdit: () => void
  onDelete: () => void
  onSetDefault: () => void
  onVerify: () => void
}) {
  const invalid = provider.status === AGENT_PROVIDER_STATUS.INVALID
  const hasWarning = Boolean(provider.contextWindowWarning)

  return (
    <article
      className='border-border/60 bg-card rounded-xl border p-4 shadow-sm'
      data-testid='agent-provider-row'
    >
      <div className='flex flex-wrap items-start justify-between gap-2'>
        <div className='flex min-w-0 items-center gap-2'>
          <span className='bg-primary/12 text-primary grid size-8 shrink-0 place-items-center rounded-lg'>
            <Cpu className='size-4' aria-hidden='true' />
          </span>
          <div className='min-w-0'>
            <div className='flex flex-wrap items-center gap-1.5'>
              <h3 className='truncate text-sm font-semibold'>{provider.name}</h3>
              {provider.isDefault && (
                <Badge className='gap-1' variant='default'>
                  <Star className='size-3 fill-current' aria-hidden='true' />
                  {AGENT_PROVIDERS_COPY.defaultBadge}
                </Badge>
              )}
              <Badge variant={invalid ? 'destructive' : 'secondary'}>
                {AGENT_PROVIDER_STATUS_LABELS[provider.status]}
              </Badge>
            </div>
            <p className='text-muted-foreground mt-0.5 font-mono text-xs'>
              {provider.apiKeyMask || AGENT_PROVIDERS_COPY.keyMissing}
            </p>
          </div>
        </div>

        <div className='flex flex-wrap items-center gap-1.5'>
          <Button
            aria-label={AGENT_PROVIDERS_COPY.verifyAria(provider.name)}
            disabled={busyAction !== null}
            onClick={onVerify}
            size='sm'
            type='button'
            variant='outline'
          >
            {busyAction === 'verify' ? (
              <Spinner className='size-3.5' />
            ) : (
              <CheckCircle2 className='size-3.5' aria-hidden='true' />
            )}
            {busyAction === 'verify'
              ? AGENT_PROVIDERS_COPY.verifying
              : AGENT_PROVIDERS_COPY.verify}
          </Button>
          {!provider.isDefault && (
            <Button
              aria-label={AGENT_PROVIDERS_COPY.setDefaultAria(provider.name)}
              disabled={busyAction !== null}
              onClick={onSetDefault}
              size='sm'
              type='button'
              variant='outline'
            >
              <Star className='size-3.5' aria-hidden='true' />
              {AGENT_PROVIDERS_COPY.setDefault}
            </Button>
          )}
          <Button
            aria-label={AGENT_PROVIDERS_COPY.editAria(provider.name)}
            disabled={busyAction !== null}
            onClick={onEdit}
            size='sm'
            type='button'
            variant='ghost'
          >
            <Pencil className='size-3.5' aria-hidden='true' />
            {AGENT_PROVIDERS_COPY.edit}
          </Button>
          <Button
            aria-label={AGENT_PROVIDERS_COPY.deleteAria(provider.name)}
            className='text-destructive hover:bg-destructive/10'
            disabled={busyAction !== null}
            onClick={onDelete}
            size='sm'
            type='button'
            variant='ghost'
          >
            <Trash2 className='size-3.5' aria-hidden='true' />
            {AGENT_PROVIDERS_COPY.delete}
          </Button>
        </div>
      </div>

      <dl className='mt-3 grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2 lg:grid-cols-3'>
        <MetaItem label={AGENT_PROVIDERS_COPY.protocolLabel}>
          {agentProviderProtocolLabel(provider.protocol)}
        </MetaItem>
        <MetaItem label={AGENT_PROVIDERS_COPY.fieldModel}>{provider.model}</MetaItem>
        <MetaItem label='Base URL'>
          <span className='break-all'>{provider.baseUrl}</span>
        </MetaItem>
        <MetaItem label={AGENT_PROVIDERS_COPY.effectiveWindow}>
          <span className='font-mono'>
            {formatContextWindowTokens(provider.effectiveContextWindow)}
          </span>
          <span className='text-muted-foreground ml-1'>
            ({CONTEXT_WINDOW_SOURCE_LABELS[provider.contextWindowSource]})
          </span>
        </MetaItem>
        <MetaItem label={AGENT_PROVIDERS_COPY.lastVerified}>
          {formatVerifiedAt(provider.lastVerifiedAt)}
        </MetaItem>
        <MetaItem label={AGENT_PROVIDERS_COPY.createdAt}>
          {provider.createdAt ? formatVerifiedAt(provider.createdAt) : '—'}
        </MetaItem>
      </dl>

      {hasWarning && (
        <p
          className={cn(
            'border-warning/40 bg-warning/10 text-warning mt-3 rounded-lg border px-3 py-2 text-xs'
          )}
          data-testid='agent-provider-context-warning'
        >
          {provider.contextWindowWarningMessage ??
            AGENT_PROVIDERS_COPY.contextAboveCatalogWarning}
        </p>
      )}
    </article>
  )
}

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className='flex min-w-0 items-baseline gap-1.5'>
      <dt className='text-muted-foreground shrink-0'>{label}</dt>
      <dd className='text-foreground min-w-0 truncate'>{children}</dd>
    </div>
  )
}
