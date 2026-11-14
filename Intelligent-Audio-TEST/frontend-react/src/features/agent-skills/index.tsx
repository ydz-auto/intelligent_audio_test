/**
 * Skill 管理页（features/agent-skills，INT-2550 / 方案 §4.4 / §11）。
 *
 * 入口：侧栏「AI 工具 → Skill 管理」；路由 /_authenticated/agent-skills，
 * 权限码 agent:skill:manage（守卫 + 导航同集合）。
 * 数据：列表一个 query key（来源 / 状态页签计数同源计算）；写操作成功后
 * invalidateQueries，不做局部手动改 state。
 *
 * 内容读取：正文经导出包的根级 SKILL.md（§11 无单条详情接口，zip 是唯一格式口径）。
 */
import { useEffect, useMemo, useState } from 'react'
import { BookOpen, Plus, Upload } from 'lucide-react'

import {
  SKILL_SCOPE,
  SKILL_SCOPE_FILTER,
  SKILL_STATUS_FILTER,
  isWritableSkill,
  skillPackageFilename,
  type AgentSkill,
  type SkillScopeFilter,
  type SkillStatusFilter,
} from '@/domain/models/agentSkill'
import {
  skillErrorMessage,
  useAgentSkillMutations,
  useAgentSkillsQuery,
} from '@/application/agent/use-agent-skills'
import { downloadBlob } from '@/infrastructure/api/agentSkillApi'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Main } from '@/components/layout/components/main'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { IconBadge } from '@/components/ui/icon-badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

import {
  AGENT_SKILLS_COPY,
  SKILL_ERROR_CODE_COPY,
  SKILL_SCOPE_TABS,
  SKILL_STATUS_TABS,
} from './constants'
import { AgentSkillList, type SkillRowAction } from './components/agent-skill-list'
import { SkillEditorDialog } from './components/skill-editor-dialog'
import { SkillForkDialog } from './components/skill-fork-dialog'
import { SkillImportDialog } from './components/skill-import-dialog'

export type AgentSkillsPageProps = {
  /** 对话沉淀入口预填（后端事件就绪时由会话页传入） */
  prefill?: { name?: string; description?: string } | null
}

export function AgentSkillsPage({ prefill = null }: AgentSkillsPageProps) {
  useEffect(() => {
    document.title = AGENT_SKILLS_COPY.pageTitle
  }, [])

  const list = useAgentSkillsQuery()
  const { disable, remove, exportPackage } = useAgentSkillMutations()

  const [scopeFilter, setScopeFilter] = useState<SkillScopeFilter>(
    SKILL_SCOPE_FILTER.ALL
  )
  const [statusFilter, setStatusFilter] = useState<SkillStatusFilter>(
    SKILL_STATUS_FILTER.ALL
  )
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<AgentSkill | null>(null)
  const [forkTarget, setForkTarget] = useState<AgentSkill | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [disableTarget, setDisableTarget] = useState<AgentSkill | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AgentSkill | null>(null)
  const [busy, setBusy] = useState<{
    id: string
    action: SkillRowAction
  } | null>(null)
  const [prefillConsumed, setPrefillConsumed] = useState(false)

  const skills = useMemo(() => list.data?.items ?? [], [list.data])
  const tools = useMemo(() => list.data?.tools ?? [], [list.data])

  // 对话沉淀预填：只消费一次，打开新建草稿
  useEffect(() => {
    if (!prefill || prefillConsumed) return
    setEditing(null)
    setEditorOpen(true)
    setPrefillConsumed(true)
  }, [prefill, prefillConsumed])

  /** 来源筛选后的条目（状态页签计数也在这上面算） */
  const byScope = useMemo(
    () =>
      scopeFilter === SKILL_SCOPE_FILTER.ALL
        ? skills
        : skills.filter((skill) => skill.scope === scopeFilter),
    [skills, scopeFilter]
  )

  /** 状态筛选后的条目（来源页签计数也在这上面算） */
  const byStatus = useMemo(
    () =>
      statusFilter === SKILL_STATUS_FILTER.ALL
        ? skills
        : skills.filter((skill) => skill.status === statusFilter),
    [skills, statusFilter]
  )

  const visible = useMemo(
    () =>
      byScope.filter(
        (skill) =>
          statusFilter === SKILL_STATUS_FILTER.ALL ||
          skill.status === statusFilter
      ),
    [byScope, statusFilter]
  )

  const scopeCounts = useMemo(() => {
    const counts: Record<string, number> = {
      ALL: byStatus.length,
      PLATFORM: 0,
      TENANT: 0,
      USER: 0,
    }
    for (const skill of byStatus) counts[skill.scope] = (counts[skill.scope] ?? 0) + 1
    return counts
  }, [byStatus])

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {
      ALL: byScope.length,
      DRAFT: 0,
      ACTIVE: 0,
      DISABLED: 0,
    }
    for (const skill of byScope) counts[skill.status] = (counts[skill.status] ?? 0) + 1
    return counts
  }, [byScope])

  const hasCustomSkills = useMemo(
    () => skills.some((skill) => skill.scope !== SKILL_SCOPE.PLATFORM),
    [skills]
  )

  const handleCreate = () => {
    setEditing(null)
    setEditorOpen(true)
  }

  const handleEdit = (skill: AgentSkill) => {
    if (!isWritableSkill(skill)) return
    setEditing(skill)
    setEditorOpen(true)
  }

  const handleExport = async (skill: AgentSkill) => {
    setBusy({ id: skill.id, action: 'export' })
    try {
      const blob = await exportPackage.mutateAsync(skill.id)
      downloadBlob(blob, skillPackageFilename(skill))
    } catch {
      // toast 已由 mutation onError 呈现
    } finally {
      setBusy(null)
    }
  }

  const handleDisable = async () => {
    if (!disableTarget) return
    const target = disableTarget
    setDisableTarget(null)
    setBusy({ id: target.id, action: 'disable' })
    try {
      await disable.mutateAsync(target.id)
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
    <Main>
      <div className='min-h-0 flex-1 overflow-y-auto px-3 py-3 sm:px-4 sm:py-6'>
        <div className='mx-auto grid w-full max-w-6xl gap-4'>
          <header className='flex flex-wrap items-start justify-between gap-3'>
            <div className='min-w-0'>
              <h1 className='text-xl font-semibold tracking-tight'>
                {AGENT_SKILLS_COPY.pageTitle}
              </h1>
              <p className='text-muted-foreground mt-1 max-w-3xl text-sm'>
                {AGENT_SKILLS_COPY.pageDescription}
              </p>
            </div>
            <div className='flex flex-wrap items-center gap-2'>
              <Button
                onClick={() => setImportOpen(true)}
                type='button'
                variant='outline'
              >
                <Upload data-icon='inline-start' aria-hidden='true' />
                {AGENT_SKILLS_COPY.importButton}
              </Button>
              <Button onClick={handleCreate} type='button'>
                <Plus data-icon='inline-start' aria-hidden='true' />
                {AGENT_SKILLS_COPY.createButton}
              </Button>
            </div>
          </header>

          <div className='border-primary/20 bg-primary/5 flex items-start gap-2.5 rounded-xl border px-3 py-2.5'>
            <IconBadge decorative size='sm' tone='info'>
              <BookOpen aria-hidden='true' />
            </IconBadge>
            <p className='text-muted-foreground text-xs leading-5'>
              {AGENT_SKILLS_COPY.permissionBoundary}
            </p>
          </div>

          <Card>
            <CardHeader className='pb-2'>
              <CardTitle className='flex flex-wrap items-center justify-between gap-2 text-base'>
                <span>{AGENT_SKILLS_COPY.listTitle}</span>
                <span className='text-muted-foreground text-xs font-normal'>
                  {list.data
                    ? `共 ${skills.length} 个 · 平台装载 ${list.data.skillsCount} 个`
                    : null}
                </span>
              </CardTitle>
              <p className='text-muted-foreground text-xs'>
                {AGENT_SKILLS_COPY.listDescription}
              </p>
            </CardHeader>
            <CardContent className='grid gap-3'>
              <Tabs
                onValueChange={(value) =>
                  setScopeFilter(value as SkillScopeFilter)
                }
                value={scopeFilter}
              >
                <TabsList aria-label='来源筛选'>
                  {SKILL_SCOPE_TABS.map((tab) => (
                    <TabsTrigger
                      data-testid={`skill-scope-tab-${tab.value}`}
                      key={tab.value}
                      value={tab.value}
                    >
                      {tab.label}
                      <span className='text-muted-foreground text-[11px]'>
                        {scopeCounts[tab.value] ?? 0}
                      </span>
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>

              <Tabs
                onValueChange={(value) =>
                  setStatusFilter(value as SkillStatusFilter)
                }
                value={statusFilter}
              >
                <TabsList aria-label='状态筛选'>
                  {SKILL_STATUS_TABS.map((tab) => (
                    <TabsTrigger
                      data-testid={`skill-status-tab-${tab.value}`}
                      key={tab.value}
                      value={tab.value}
                    >
                      {tab.label}
                      <span className='text-muted-foreground text-[11px]'>
                        {statusCounts[tab.value] ?? 0}
                      </span>
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>

              <AgentSkillList
                busyAction={busy?.action ?? null}
                busySkillId={busy?.id ?? null}
                errorMessage={
                  list.isError
                    ? skillErrorMessage(
                        list.error,
                        AGENT_SKILLS_COPY.loadErrorTitle,
                        SKILL_ERROR_CODE_COPY
                      )
                    : null
                }
                filtered={
                  scopeFilter !== SKILL_SCOPE_FILTER.ALL ||
                  statusFilter !== SKILL_STATUS_FILTER.ALL
                }
                hasCustomSkills={hasCustomSkills}
                isError={list.isError}
                isPending={list.isPending}
                onCreate={handleCreate}
                onDelete={(skill) => setDeleteTarget(skill)}
                onDisable={(skill) => setDisableTarget(skill)}
                onEdit={handleEdit}
                onExport={(skill) => void handleExport(skill)}
                onFork={(skill) => setForkTarget(skill)}
                onImport={() => setImportOpen(true)}
                onRetry={() => void list.refetch()}
                skills={visible}
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <SkillEditorDialog
        onOpenChange={setEditorOpen}
        onSaved={() => list.refetch()}
        open={editorOpen}
        prefill={prefill}
        skill={editing}
        tools={tools}
      />

      <SkillForkDialog
        onForked={() => void list.refetch()}
        onOpenChange={(open) => {
          if (!open) setForkTarget(null)
        }}
        open={forkTarget !== null}
        skill={forkTarget}
      />

      <SkillImportDialog
        onImported={() => void list.refetch()}
        onOpenChange={setImportOpen}
        open={importOpen}
      />

      <ConfirmDialog
        confirmText={AGENT_SKILLS_COPY.disableConfirm}
        desc={
          disableTarget
            ? `${disableTarget.name}：${AGENT_SKILLS_COPY.disableDescription}`
            : AGENT_SKILLS_COPY.disableDescription
        }
        handleConfirm={() => void handleDisable()}
        onOpenChange={(open) => {
          if (!open) setDisableTarget(null)
        }}
        open={disableTarget !== null}
        title={AGENT_SKILLS_COPY.disableTitle}
      />

      <ConfirmDialog
        confirmText={AGENT_SKILLS_COPY.deleteConfirm}
        desc={
          deleteTarget
            ? `${deleteTarget.name}：${AGENT_SKILLS_COPY.deleteDescription}`
            : AGENT_SKILLS_COPY.deleteDescription
        }
        destructive
        handleConfirm={() => void handleDelete()}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        open={deleteTarget !== null}
        title={AGENT_SKILLS_COPY.deleteTitle}
      />
    </Main>
  )
}

export default AgentSkillsPage
