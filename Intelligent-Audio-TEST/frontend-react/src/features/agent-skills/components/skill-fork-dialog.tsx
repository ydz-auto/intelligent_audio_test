/**
 * fork 弹窗（features/agent-skills）：从平台内置 / 可见 Skill 复制出本人草稿。
 *
 * 名称默认 `<name>-copy`（服务端缺省同口径），可改名；内容与资源由服务端复制，
 * 不覆盖原 Skill（§4.4「从内置 fork」）。
 */
import { useEffect, useState } from 'react'

import type { AgentSkill, SkillIssue } from '@/domain/models/agentSkill'
import { useAgentSkillMutations, skillErrorMessage } from '@/application/agent/use-agent-skills'
import { skillIssuesFromError } from '@/infrastructure/api/agentSkillApi'
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
import { Spinner } from '@/components/ui/spinner'

import { AGENT_SKILLS_COPY } from '../constants'
import { SkillIssueList } from './skill-issue-list'

type SkillForkDialogProps = {
  open: boolean
  skill: AgentSkill | null
  onOpenChange: (open: boolean) => void
  onForked: (skill: AgentSkill) => void
}

export function SkillForkDialog({
  open,
  skill,
  onOpenChange,
  onForked,
}: SkillForkDialogProps) {
  const { fork } = useAgentSkillMutations()
  const [name, setName] = useState('')
  const [issues, setIssues] = useState<SkillIssue[]>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !skill) return
    setName(`${skill.name}-copy`)
    setIssues([])
    setErrorMessage(null)
  }, [open, skill])

  const handleSubmit = async () => {
    if (!skill) return
    setErrorMessage(null)
    setIssues([])
    try {
      const created = await fork.mutateAsync({
        id: skill.id,
        input: { name: name.trim() || `${skill.name}-copy` },
      })
      onForked(created)
      onOpenChange(false)
    } catch (error) {
      const found = skillIssuesFromError(error)
      setIssues(found)
      if (found.length === 0) {
        setErrorMessage(skillErrorMessage(error, 'fork Skill 失败'))
      }
    }
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{AGENT_SKILLS_COPY.forkTitle}</DialogTitle>
          <DialogDescription>
            {AGENT_SKILLS_COPY.forkDescription}
          </DialogDescription>
        </DialogHeader>

        <div className='grid gap-1.5'>
          <Label htmlFor='agent-skill-fork-name'>
            {AGENT_SKILLS_COPY.forkName}
          </Label>
          <Input
            autoComplete='off'
            id='agent-skill-fork-name'
            onChange={(event) => setName(event.target.value)}
            value={name}
          />
          <p className='text-muted-foreground text-xs'>
            {AGENT_SKILLS_COPY.fieldNameHint}
          </p>
        </div>

        {issues.length > 0 && <SkillIssueList issues={issues} showSummary />}
        {errorMessage && (
          <p className='text-destructive text-xs'>{errorMessage}</p>
        )}

        <DialogFooter>
          <Button
            disabled={fork.isPending}
            onClick={() => onOpenChange(false)}
            type='button'
            variant='outline'
          >
            {AGENT_SKILLS_COPY.cancel}
          </Button>
          <Button
            disabled={fork.isPending}
            onClick={() => void handleSubmit()}
            type='button'
          >
            {fork.isPending && <Spinner className='size-3.5' />}
            {fork.isPending
              ? AGENT_SKILLS_COPY.forkSubmitting
              : AGENT_SKILLS_COPY.forkButton}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
