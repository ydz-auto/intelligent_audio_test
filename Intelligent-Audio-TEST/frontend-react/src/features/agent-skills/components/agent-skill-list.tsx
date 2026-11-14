/**
 * Skill 列表（features/agent-skills）。
 *
 * 行内展示：名称、来源标签、状态、版本、contentHash 前 8 位、更新时间、被遮蔽
 * 标注；PLATFORM 行只读（仅 fork / 导出），USER 行另有编辑 / 发布 / 停用 / 删除。
 * 加载 / 空 / 错误三态齐全；空态只在「无自定义 Skill」时出现，平台 Skill 仍照常列出。
 */
import {
  Ban,
  BookOpen,
  Download,
  GitFork,
  Pencil,
  Plus,
  Trash2,
  Upload,
} from 'lucide-react'

import {
  SKILL_SCOPE,
  SKILL_SCOPE_LABELS,
  SKILL_STATUS,
  SKILL_STATUS_LABELS,
  isDisableableSkill,
  isWritableSkill,
  shortContentHash,
  type AgentSkill,
} from '@/domain/models/agentSkill'
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

import { AGENT_SKILLS_COPY, SKILL_SCOPE_BADGE_TONE } from '../constants'

export type SkillRowAction = 'fork' | 'export' | 'disable' | 'delete'

type AgentSkillListProps = {
  skills: AgentSkill[] | undefined
  isPending: boolean
  isError: boolean
  errorMessage?: string | null
  hasCustomSkills: boolean
  filtered: boolean
  busySkillId: string | null
  busyAction: SkillRowAction | null
  onRetry: () => void
  onCreate: () => void
  onImport: () => void
  onEdit: (skill: AgentSkill) => void
  onFork: (skill: AgentSkill) => void
  onExport: (skill: AgentSkill) => void
  onDisable: (skill: AgentSkill) => void
  onDelete: (skill: AgentSkill) => void
}

export function AgentSkillList({
  skills,
  isPending,
  isError,
  errorMessage,
  hasCustomSkills,
  filtered,
  busySkillId,
  busyAction,
  onRetry,
  onCreate,
  onImport,
  onEdit,
  onFork,
  onExport,
  onDisable,
  onDelete,
}: AgentSkillListProps) {
  if (isPending) {
    return (
      <div
        aria-label={AGENT_SKILLS_COPY.loading}
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
        <p className='text-destructive text-sm'>
          {errorMessage || AGENT_SKILLS_COPY.loadErrorTitle}
        </p>
        <Button onClick={onRetry} size='sm' type='button' variant='outline'>
          {AGENT_SKILLS_COPY.retry}
        </Button>
      </div>
    )
  }

  if (!skills || skills.length === 0) {
    return (
      <Empty className='min-h-44'>
        <EmptyContent>
          <EmptyMedia variant='icon'>
            <BookOpen aria-hidden='true' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>
              {filtered
                ? AGENT_SKILLS_COPY.emptyFilteredTitle
                : AGENT_SKILLS_COPY.emptyCustomTitle}
            </EmptyTitle>
            <EmptyDescription>
              {filtered
                ? AGENT_SKILLS_COPY.emptyFilteredDescription
                : AGENT_SKILLS_COPY.emptyCustomDescription}
            </EmptyDescription>
          </EmptyHeader>
          {!filtered && (
            <div className='flex flex-wrap items-center justify-center gap-2'>
              <Button onClick={onCreate} size='sm' type='button'>
                <Plus data-icon='inline-start' aria-hidden='true' />
                {AGENT_SKILLS_COPY.createButton}
              </Button>
              <Button onClick={onImport} size='sm' type='button' variant='outline'>
                <Upload data-icon='inline-start' aria-hidden='true' />
                {AGENT_SKILLS_COPY.importButton}
              </Button>
            </div>
          )}
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <div className='grid gap-3'>
      {!hasCustomSkills && (
        <div className='border-primary/20 bg-primary/5 flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3 py-2.5'>
          <p className='text-muted-foreground text-xs leading-5'>
            {AGENT_SKILLS_COPY.emptyCustomDescription}
          </p>
          <div className='flex items-center gap-2'>
            <Button onClick={onCreate} size='sm' type='button'>
              <Plus data-icon='inline-start' aria-hidden='true' />
              {AGENT_SKILLS_COPY.createButton}
            </Button>
            <Button onClick={onImport} size='sm' type='button' variant='outline'>
              <Upload data-icon='inline-start' aria-hidden='true' />
              {AGENT_SKILLS_COPY.importButton}
            </Button>
          </div>
        </div>
      )}
      {skills.map((skill) => (
        <AgentSkillRow
          busyAction={busySkillId === skill.id ? busyAction : null}
          key={`${skill.scope}:${skill.id || skill.name}`}
          onDelete={() => onDelete(skill)}
          onDisable={() => onDisable(skill)}
          onEdit={() => onEdit(skill)}
          onExport={() => onExport(skill)}
          onFork={() => onFork(skill)}
          skill={skill}
        />
      ))}
    </div>
  )
}

function AgentSkillRow({
  skill,
  busyAction,
  onEdit,
  onFork,
  onExport,
  onDisable,
  onDelete,
}: {
  skill: AgentSkill
  busyAction: SkillRowAction | null
  onEdit: () => void
  onFork: () => void
  onExport: () => void
  onDisable: () => void
  onDelete: () => void
}) {
  const writable = isWritableSkill(skill)
  const isPlatform = skill.scope === SKILL_SCOPE.PLATFORM
  const busy = busyAction !== null

  return (
    <article
      className='border-border/60 bg-card rounded-xl border p-4 shadow-sm'
      data-skill-name={skill.name}
      data-skill-scope={skill.scope}
      data-skill-status={skill.status}
      data-testid='agent-skill-row'
    >
      <div className='flex flex-wrap items-start justify-between gap-2'>
        <div className='min-w-0'>
          <div className='flex flex-wrap items-center gap-1.5'>
            <h3 className='truncate text-sm font-semibold'>{skill.name}</h3>
            <Badge variant={SKILL_SCOPE_BADGE_TONE[skill.scope]}>
              {SKILL_SCOPE_LABELS[skill.scope]}
            </Badge>
            <Badge
              variant={
                skill.status === SKILL_STATUS.ACTIVE
                  ? 'default'
                  : skill.status === SKILL_STATUS.DISABLED
                    ? 'outline'
                    : 'secondary'
              }
              data-testid='agent-skill-status-badge'
            >
              {SKILL_STATUS_LABELS[skill.status]}
            </Badge>
            {skill.maskedBy && (
              <Badge className='gap-1' variant='outline'>
                {AGENT_SKILLS_COPY.maskedByPrefix}
                {SKILL_SCOPE_LABELS[skill.maskedBy]}
                {AGENT_SKILLS_COPY.maskedBySuffix}
              </Badge>
            )}
          </div>
          <p className='text-muted-foreground mt-1 line-clamp-2 max-w-3xl text-xs leading-5'>
            {skill.description || '—'}
          </p>
        </div>

        <div className='flex flex-wrap items-center gap-1.5'>
          {isPlatform ? (
            <>
              <Button
                aria-label={`${AGENT_SKILLS_COPY.forkButton} ${skill.name}`}
                disabled={busy}
                onClick={onFork}
                size='sm'
                type='button'
                variant='outline'
              >
                <GitFork aria-hidden='true' className='size-3.5' />
                {AGENT_SKILLS_COPY.forkButton}
              </Button>
              <Button
                aria-label={`${AGENT_SKILLS_COPY.exportButton} ${skill.name}`}
                disabled={busy}
                onClick={onExport}
                size='sm'
                type='button'
                variant='ghost'
              >
                <Download aria-hidden='true' className='size-3.5' />
                {AGENT_SKILLS_COPY.exportButton}
              </Button>
              <span className='text-muted-foreground text-[11px]'>
                {AGENT_SKILLS_COPY.platformReadonly}
              </span>
            </>
          ) : (
            <>
              {writable && (
                <Button
                  aria-label={`${AGENT_SKILLS_COPY.editButton} ${skill.name}`}
                  disabled={busy}
                  onClick={onEdit}
                  size='sm'
                  type='button'
                  variant='outline'
                >
                  <Pencil aria-hidden='true' className='size-3.5' />
                  {AGENT_SKILLS_COPY.editButton}
                </Button>
              )}
              {isDisableableSkill(skill) && (
                <Button
                  aria-label={`${AGENT_SKILLS_COPY.disableButton} ${skill.name}`}
                  disabled={busy}
                  onClick={onDisable}
                  size='sm'
                  type='button'
                  variant='ghost'
                >
                  <Ban aria-hidden='true' className='size-3.5' />
                  {AGENT_SKILLS_COPY.disableButton}
                </Button>
              )}
              <Button
                aria-label={`${AGENT_SKILLS_COPY.exportButton} ${skill.name}`}
                disabled={busy}
                onClick={onExport}
                size='sm'
                type='button'
                variant='ghost'
              >
                <Download aria-hidden='true' className='size-3.5' />
                {AGENT_SKILLS_COPY.exportButton}
              </Button>
              <Button
                aria-label={`${AGENT_SKILLS_COPY.deleteButton} ${skill.name}`}
                className='text-destructive hover:bg-destructive/10'
                disabled={busy}
                onClick={onDelete}
                size='sm'
                type='button'
                variant='ghost'
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
                {AGENT_SKILLS_COPY.deleteButton}
              </Button>
            </>
          )}
        </div>
      </div>

      <dl className='text-muted-foreground mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs'>
        <div className='flex items-baseline gap-1.5'>
          <dt>{AGENT_SKILLS_COPY.versionShort}</dt>
          <dd className='text-foreground font-mono'>{skill.version || '—'}</dd>
        </div>
        <div className='flex items-baseline gap-1.5'>
          <dt>{AGENT_SKILLS_COPY.contentHash}</dt>
          <dd className='text-foreground font-mono'>
            {shortContentHash(skill.contentHash)}
          </dd>
        </div>
        <div className='flex items-baseline gap-1.5'>
          <dt>{AGENT_SKILLS_COPY.updatedAt}</dt>
          <dd className='text-foreground'>{formatSkillTime(skill.updatedAt)}</dd>
        </div>
        {skill.allowedTools.length > 0 && (
          <div className='flex min-w-0 items-baseline gap-1.5'>
            <dt>allowed-tools</dt>
            <dd className='text-foreground truncate font-mono'>
              {skill.allowedTools.join(', ')}
            </dd>
          </div>
        )}
        {busy && (
          <div className='flex items-center gap-1.5'>
            <Spinner className='size-3' />
            <span>处理中…</span>
          </div>
        )}
      </dl>
    </article>
  )
}

/** 本地时间展示（DTO 已补 UTC 时区；空值显示占位符） */
export function formatSkillTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { hour12: false })
}
