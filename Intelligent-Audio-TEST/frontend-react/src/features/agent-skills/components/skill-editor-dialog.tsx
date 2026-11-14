/**
 * Skill 编辑器（features/agent-skills）。
 *
 * - 表单化 frontmatter：name / description / allowed-tools / permissions 为字段，
 *   正文为 SKILL.md 正文（正文来自导出包的根级 SKILL.md，§11 无单条详情接口）。
 * - 保存 = POST（新建）/ PUT（保存），版本 +1；保存后服务端 `issues` 逐项回显，
 *   按 `field` 定位到具体输入项；前端只做必填与名称格式即时提示，不重复实现
 *   服务端校验规则（§4.4 落库前校验）。
 * - 发布门槛面板：发布动作即门槛检查；未达标保留 DRAFT 并禁用发布。
 */
import { useEffect, useRef, useState } from 'react'
import { BookOpen, RefreshCw } from 'lucide-react'

import {
  SKILL_BODY_TEMPLATE,
  SKILL_ISSUE_SEVERITY,
  SKILL_STATUS,
  isValidSkillName,
  missingRequiredSections,
  type AgentSkill,
  type AgentSkillDraftInput,
  type SkillGate,
  type SkillIssue,
  type SkillTool,
} from '@/domain/models/agentSkill'
import {
  useAgentSkillDocumentQuery,
  useAgentSkillMutations,
  useAgentSkillVersionsQuery,
  skillErrorMessage,
} from '@/application/agent/use-agent-skills'
import { skillIssuesFromError } from '@/infrastructure/api/agentSkillApi'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

import { AGENT_SKILLS_COPY, SKILL_ERROR_CODE_COPY, SKILL_ISSUE_FIELD_ANCHOR } from '../constants'
import { formatSkillTime } from './agent-skill-list'
import { SkillGatePanel } from './skill-gate-panel'
import { SkillIssueList } from './skill-issue-list'

type SkillEditorDialogProps = {
  open: boolean
  /** null = 新建草稿 */
  skill: AgentSkill | null
  /** 新建草稿预填（对话沉淀建议入口） */
  prefill?: { name?: string; description?: string } | null
  tools: SkillTool[]
  onOpenChange: (open: boolean) => void
  /** 保存 / 发布成功后回传最新 Skill（列表刷新由调用方处理） */
  onSaved: (skill: AgentSkill) => void
}

type EditorForm = {
  name: string
  description: string
  allowedTools: string
  permissions: string
  body: string
}

function formFromSkill(
  skill: AgentSkill | null,
  prefill?: { name?: string; description?: string } | null
): EditorForm {
  if (!skill) {
    return {
      name: prefill?.name ?? '',
      description: prefill?.description ?? '',
      allowedTools: '',
      permissions: '',
      body: SKILL_BODY_TEMPLATE,
    }
  }
  return {
    name: skill.name,
    description: skill.description,
    allowedTools: skill.allowedTools.join('\n'),
    permissions: skill.permissions.join('\n'),
    body: '',
  }
}

/** 多行文本 → 去空行的列表 */
function toLines(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

/** 由领域对象取 frontmatter 契约字段（name / description 另列，不重复） */
function buildFrontmatter(
  base: AgentSkill | null,
  allowedTools: string[],
  permissions: string[]
): Record<string, unknown> {
  const frontmatter: Record<string, unknown> = {
    'allowed-tools': allowedTools,
    permissions,
  }
  if (base && Object.keys(base.budgets).length > 0) {
    frontmatter.budgets = { ...base.budgets }
  }
  if (base?.owner) frontmatter.owner = base.owner
  return frontmatter
}

export function SkillEditorDialog({
  open,
  skill,
  prefill = null,
  tools,
  onOpenChange,
  onSaved,
}: SkillEditorDialogProps) {
  const { create, update, publish, invalidateSkill } = useAgentSkillMutations()

  const [current, setCurrent] = useState<AgentSkill | null>(skill)
  const [form, setForm] = useState<EditorForm>(() =>
    formFromSkill(skill, prefill)
  )
  const [issues, setIssues] = useState<SkillIssue[]>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({})
  const [gate, setGate] = useState<SkillGate | null>(null)
  const [docRequested, setDocRequested] = useState(false)
  const [docLoaded, setDocLoaded] = useState(false)
  /** 最近一次保存结果：成功且只剩 WARNING 时汇总文案不能再说「未保存」 */
  const [saveState, setSaveState] = useState<'idle' | 'saved' | 'failed'>('idle')
  // 只在「打开 / 切换到另一个 Skill」时重置；列表刷新回传新对象不重置表单
  const loadedSkillId = useRef<string | null>(null)
  const wasOpen = useRef(false)
  const requestedId = skill?.id ?? null

  const documentQuery = useAgentSkillDocumentQuery(
    current?.id ?? null,
    open && docRequested && Boolean(current?.id)
  )
  const versionsQuery = useAgentSkillVersionsQuery(
    open && current ? current.id : null
  )

  // 打开 / 切换 skill 时重置表单与门控状态
  useEffect(() => {
    if (!open) {
      wasOpen.current = false
      return
    }
    const justOpened = !wasOpen.current
    wasOpen.current = true
    if (!justOpened && loadedSkillId.current === requestedId) return
    setCurrent(skill)
    setForm(formFromSkill(skill, prefill))
    setIssues([])
    setErrorMessage(null)
    setLocalErrors({})
    setGate(null)
    setSaveState('idle')
    setDocLoaded(!skill)
    setDocRequested(Boolean(skill?.id))
    loadedSkillId.current = requestedId
    // skill 仅在打开 / 换 id 时消费；列表刷新回传的新对象不触发重置
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, requestedId])

  // 载入正文（导出包里的 SKILL.md）；同一 skill 只覆盖一次，保存后不再回灌
  useEffect(() => {
    if (!open || docLoaded) return
    const data = documentQuery.data
    if (!data) return
    setForm((previous) => ({ ...previous, body: data.body }))
    setDocLoaded(true)
    setDocRequested(false)
  }, [documentQuery.data, docLoaded, open])

  const pending = create.isPending || update.isPending
  const publishing = publish.isPending
  const unmet = gate !== null && !gate.passed
  /** 保存失败 / 校验有 ERROR 才说「未保存」；只剩 WARNING 时是成功态提示 */
  const errorIssues = issues.filter(
    (issue) => issue.severity === SKILL_ISSUE_SEVERITY.ERROR
  )
  const issueBlocked = errorIssues.length > 0 || Boolean(errorMessage)

  const setField = (field: keyof EditorForm, value: string) => {
    setForm((previous) => ({ ...previous, [field]: value }))
  }

  const appendTool = (tool: string) => {
    setForm((previous) => {
      const lines = toLines(previous.allowedTools)
      if (lines.includes(tool)) return previous
      return {
        ...previous,
        allowedTools: [...lines, tool].join('\n'),
      }
    })
  }

  const validate = (): boolean => {
    const errors: Record<string, string> = {}
    if (!form.name.trim()) errors.name = AGENT_SKILLS_COPY.invalidNameRequired
    else if (!isValidSkillName(form.name)) errors.name = AGENT_SKILLS_COPY.invalidName
    if (!form.description.trim()) {
      errors.description = AGENT_SKILLS_COPY.invalidDescription
    }
    if (!form.body.trim()) errors.body = AGENT_SKILLS_COPY.invalidBody
    setLocalErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSave = async () => {
    setErrorMessage(null)
    setSaveState('idle')
    if (!validate()) return
    const allowedTools = toLines(form.allowedTools)
    const permissions = toLines(form.permissions)
    const input: AgentSkillDraftInput = {
      name: form.name.trim(),
      description: form.description.trim(),
      frontmatter: buildFrontmatter(current, allowedTools, permissions),
      body: form.body,
    }
    try {
      const saved = current
        ? await update.mutateAsync({ id: current.id, input })
        : await create.mutateAsync(input)
      setCurrent(saved)
      setIssues(saved.issues.filter(
        (issue) => issue.severity === SKILL_ISSUE_SEVERITY.WARNING
      ))
      setGate(null)
      setDocLoaded(true)
      setDocRequested(false)
      setSaveState('saved')
      onSaved(saved)
    } catch (error) {
      const found = skillIssuesFromError(error)
      setIssues(found)
      setSaveState('failed')
      setErrorMessage(
        found.length > 0
          ? null
          : skillErrorMessage(error, '保存失败', SKILL_ERROR_CODE_COPY)
      )
    }
  }

  const handlePublish = async () => {
    if (!current) return
    setErrorMessage(null)
    setIssues([])
    setSaveState('idle')
    try {
      const result = await publish.mutateAsync(current.id)
      setGate(result.gate)
      setCurrent(result.skill)
      if (result.gate.passed) {
        onSaved(result.skill)
      } else {
        invalidateSkill(current.id)
      }
    } catch (error) {
      const found = skillIssuesFromError(error)
      setIssues(found)
      setErrorMessage(
        found.length > 0
          ? null
          : skillErrorMessage(error, '发布失败', SKILL_ERROR_CODE_COPY)
      )
    }
  }

  const locateField = (field: string) => {
    const anchor = SKILL_ISSUE_FIELD_ANCHOR[field]
    if (!anchor) return
    const element = document.getElementById(anchor)
    if (!element) return
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    ;(element as HTMLElement).focus?.()
  }

  const fieldError = (field: string) =>
    localErrors[field] ??
    issues.find(
      (issue) =>
        issue.field === field && issue.severity === SKILL_ISSUE_SEVERITY.ERROR
    )?.message

  const docLoading = Boolean(current?.id) && docRequested && documentQuery.isPending
  const docError = documentQuery.isError && docRequested

  const missingSections = missingRequiredSections(form.body)
  const bodyLines = form.body ? form.body.split('\n').length : 0
  const status = current?.status ?? SKILL_STATUS.DRAFT
  const publishable = status === SKILL_STATUS.DRAFT && Boolean(current)

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className='max-h-[92vh] gap-0 overflow-hidden p-0 sm:max-w-5xl'>
        <div className='max-h-[92vh] overflow-y-auto px-5 py-4'>
          <DialogHeader>
            <DialogTitle>
              {current ? AGENT_SKILLS_COPY.editTitle : AGENT_SKILLS_COPY.createTitle}
            </DialogTitle>
            <DialogDescription>
              {AGENT_SKILLS_COPY.editorDescription}
            </DialogDescription>
          </DialogHeader>

          {docLoading && (
            <div
              className='text-muted-foreground flex items-center gap-2 py-6 text-sm'
              role='status'
            >
              <Spinner className='size-4' />
              {AGENT_SKILLS_COPY.loadingDocument}
            </div>
          )}

          {docError && (
            <div className='flex flex-col items-start gap-2 py-4'>
              <p className='text-destructive text-sm'>
                {AGENT_SKILLS_COPY.loadDocumentErrorTitle}
              </p>
              <Button
                data-testid='skill-doc-retry'
                onClick={() => void documentQuery.refetch()}
                size='sm'
                type='button'
                variant='outline'
              >
                <RefreshCw aria-hidden='true' className='size-3.5' />
                {AGENT_SKILLS_COPY.retry}
              </Button>
            </div>
          )}

          {!docLoading && !docError && (
            <div className='mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]'>
              <div className='grid min-w-0 gap-4'>
                {(issues.length > 0 || errorMessage) && (
                  <div
                    className={cn(
                      'grid gap-2 rounded-xl border p-3',
                      issueBlocked
                        ? 'border-destructive/30 bg-destructive/5'
                        : 'border-warning/40 bg-warning/10'
                    )}
                    data-testid='skill-editor-issues'
                  >
                    <p
                      className={cn(
                        'text-xs font-medium',
                        issueBlocked ? 'text-destructive' : 'text-warning'
                      )}
                    >
                      {issueBlocked
                        ? (saveState === 'failed'
                            ? AGENT_SKILLS_COPY.issueSummary
                            : AGENT_SKILLS_COPY.issueBlockedSummary
                          ).replace(
                            '{count}',
                            String(errorIssues.length || issues.length)
                          )
                        : AGENT_SKILLS_COPY.issueWarningSummary.replace(
                            '{count}',
                            String(issues.length)
                          )}
                    </p>
                    <SkillIssueList
                      issues={issues}
                      onLocate={locateField}
                      showSummary
                    />
                    {errorMessage && (
                      <p className='text-destructive text-xs'>{errorMessage}</p>
                    )}
                  </div>
                )}

                {saveState === 'saved' && issues.length === 0 && (
                  <p
                    className='text-success text-xs'
                    data-testid='skill-editor-saved'
                  >
                    {AGENT_SKILLS_COPY.saveSuccessHint}
                  </p>
                )}

                <div className='grid gap-1.5'>
                  <Label htmlFor='agent-skill-name'>
                    {AGENT_SKILLS_COPY.fieldName}
                  </Label>
                  <Input
                    aria-invalid={Boolean(fieldError('name'))}
                    autoComplete='off'
                    id='agent-skill-name'
                    onChange={(event) => setField('name', event.target.value)}
                    placeholder='task-diagnose-copy'
                    value={form.name}
                  />
                  <p className='text-muted-foreground text-xs'>
                    {AGENT_SKILLS_COPY.fieldNameHint}
                  </p>
                  {fieldError('name') && (
                    <p className='text-destructive text-xs'>{fieldError('name')}</p>
                  )}
                </div>

                <div className='grid gap-1.5'>
                  <Label htmlFor='agent-skill-description'>
                    {AGENT_SKILLS_COPY.fieldDescription}
                  </Label>
                  <Textarea
                    aria-invalid={Boolean(fieldError('description'))}
                    className='min-h-24'
                    id='agent-skill-description'
                    onChange={(event) =>
                      setField('description', event.target.value)
                    }
                    placeholder='描述这个 Skill 做什么、何时触发、不适用什么场景。'
                    value={form.description}
                  />
                  <p className='text-muted-foreground text-xs'>
                    {AGENT_SKILLS_COPY.fieldDescriptionHint}
                  </p>
                  {fieldError('description') && (
                    <p className='text-destructive text-xs'>
                      {fieldError('description')}
                    </p>
                  )}
                </div>

                <div className='grid gap-4 sm:grid-cols-2'>
                  <div className='grid gap-1.5'>
                    <Label htmlFor='agent-skill-allowed-tools'>
                      {AGENT_SKILLS_COPY.fieldAllowedTools}
                    </Label>
                    <Textarea
                      aria-invalid={Boolean(fieldError('allowed-tools'))}
                      className='min-h-28 font-mono text-xs'
                      id='agent-skill-allowed-tools'
                      onChange={(event) =>
                        setField('allowedTools', event.target.value)
                      }
                      value={form.allowedTools}
                    />
                    <p className='text-muted-foreground text-xs'>
                      {AGENT_SKILLS_COPY.fieldAllowedToolsHint}
                    </p>
                    {fieldError('allowed-tools') && (
                      <p className='text-destructive text-xs'>
                        {fieldError('allowed-tools')}
                      </p>
                    )}
                  </div>

                  <div className='grid gap-1.5'>
                    <Label htmlFor='agent-skill-permissions'>
                      {AGENT_SKILLS_COPY.fieldPermissions}
                    </Label>
                    <Textarea
                      aria-invalid={Boolean(fieldError('permissions'))}
                      className='min-h-28 font-mono text-xs'
                      id='agent-skill-permissions'
                      onChange={(event) =>
                        setField('permissions', event.target.value)
                      }
                      value={form.permissions}
                    />
                    <p className='text-muted-foreground text-xs'>
                      {AGENT_SKILLS_COPY.fieldPermissionsHint}
                    </p>
                    {fieldError('permissions') && (
                      <p className='text-destructive text-xs'>
                        {fieldError('permissions')}
                      </p>
                    )}
                  </div>
                </div>

                {tools.length > 0 && (
                  <div className='grid gap-1.5'>
                    <p className='text-muted-foreground text-xs'>
                      {AGENT_SKILLS_COPY.availableTools}
                    </p>
                    <div className='flex flex-wrap gap-1'>
                      {tools.map((tool) => (
                        <button
                          className={cn(
                            'border-border/70 hover:border-primary/60 hover:text-primary rounded-md border px-1.5 py-0.5 font-mono text-[11px] transition-colors',
                            tool.enabled
                              ? 'text-foreground'
                              : 'text-muted-foreground'
                          )}
                          key={tool.name}
                          onClick={() => appendTool(tool.name)}
                          title={tool.description}
                          type='button'
                        >
                          {tool.name}
                          {!tool.enabled && '（未启用）'}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className='grid gap-1.5'>
                  <div className='flex flex-wrap items-center justify-between gap-2'>
                    <Label htmlFor='agent-skill-body'>
                      {AGENT_SKILLS_COPY.fieldBody}
                    </Label>
                    <span className='text-muted-foreground font-mono text-[11px]'>
                      {bodyLines} 行
                    </span>
                  </div>
                  <Textarea
                    aria-invalid={Boolean(fieldError('body'))}
                    className='min-h-72 font-mono text-xs leading-5'
                    id='agent-skill-body'
                    onChange={(event) => setField('body', event.target.value)}
                    spellCheck={false}
                    value={form.body}
                  />
                  <p className='text-muted-foreground text-xs'>
                    {AGENT_SKILLS_COPY.fieldBodyHint}
                  </p>
                  {missingSections.length > 0 && (
                    <p className='text-warning text-xs'>
                      缺少小节：
                      {missingSections.map((section) => `## ${section}`).join('、')}
                    </p>
                  )}
                  {fieldError('body') && (
                    <p className='text-destructive text-xs'>{fieldError('body')}</p>
                  )}
                </div>
              </div>

              <aside className='grid content-start gap-3'>
                <div className='border-border/60 rounded-xl border p-3'>
                  <h3 className='flex items-center gap-1.5 text-sm font-semibold'>
                    <BookOpen aria-hidden='true' className='size-4' />
                    {AGENT_SKILLS_COPY.versionsTitle}
                  </h3>
                  {versionsQuery.isPending && current ? (
                    <div className='text-muted-foreground mt-2 flex items-center gap-2 text-xs' role='status'>
                      <Spinner className='size-3' />
                      读取版本…
                    </div>
                  ) : versionsQuery.data && versionsQuery.data.length > 0 ? (
                    <ul className='mt-2 grid gap-1.5' data-testid='skill-version-list'>
                      {versionsQuery.data.map((version) => (
                        <li
                          className='flex items-center justify-between gap-2 text-xs'
                          key={version.version}
                        >
                          <span className='font-mono'>v{version.version}</span>
                          <span className='text-muted-foreground font-mono text-[11px]'>
                            {version.contentHash.slice(0, 8) || '—'}
                          </span>
                          <span className='text-muted-foreground text-[11px]'>
                            {formatSkillTime(version.createdAt)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className='text-muted-foreground mt-2 text-xs'>
                      {current
                        ? AGENT_SKILLS_COPY.versionsEmpty
                        : '保存后生成版本记录'}
                    </p>
                  )}
                </div>

                <div className='flex items-center justify-between gap-2'>
                  <Badge variant='outline'>
                    {current ? `v${current.version || '—'}` : '新草稿'}
                  </Badge>
                  {current && (
                    <span className='text-muted-foreground text-[11px]'>
                      {formatSkillTime(current.updatedAt)}
                    </span>
                  )}
                </div>

                {current && status !== SKILL_STATUS.ACTIVE && (
                  <SkillGatePanel
                    errorMessage={errorMessage}
                    gate={gate}
                    onPublish={() => void handlePublish()}
                    pending={publishing}
                    publishable={publishable}
                    unmet={unmet}
                  />
                )}
              </aside>
            </div>
          )}

          <DialogFooter className='mt-4'>
            <Button
              disabled={pending || publishing}
              onClick={() => onOpenChange(false)}
              type='button'
              variant='outline'
            >
              {AGENT_SKILLS_COPY.cancel}
            </Button>
            <Button
              disabled={pending || docLoading || docError}
              onClick={() => void handleSave()}
              type='button'
            >
              {pending && <Spinner className='size-3.5' />}
              {pending ? AGENT_SKILLS_COPY.saving : AGENT_SKILLS_COPY.save}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  )
}
