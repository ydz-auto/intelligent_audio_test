/**
 * zip 导入弹窗（features/agent-skills）：文件选择 → 原字节上传 → 逐项结果。
 *
 * 失败不吞错：服务端 issues（code / field / message）逐条展示；列表不新增。
 * 成功进入 DRAFT（服务端返回 SkillView），由调用方 invalidate 列表。
 */
import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'

import type { AgentSkill, SkillIssue } from '@/domain/models/agentSkill'
import {
  skillErrorMessage,
  useAgentSkillMutations,
} from '@/application/agent/use-agent-skills'
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
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'

import {
  AGENT_SKILLS_COPY,
  SKILL_ERROR_CODE_COPY,
  SKILL_UPLOAD_MAX_BYTES,
} from '../constants'
import { SkillIssueList } from './skill-issue-list'

type SkillImportDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onImported: (skill: AgentSkill) => void
}

export function SkillImportDialog({
  open,
  onOpenChange,
  onImported,
}: SkillImportDialogProps) {
  const { importPackage } = useAgentSkillMutations()
  const [file, setFile] = useState<File | null>(null)
  const [issues, setIssues] = useState<SkillIssue[]>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [localError, setLocalError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const reset = () => {
    setFile(null)
    setIssues([])
    setErrorMessage(null)
    setLocalError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

  const handleSubmit = async () => {
    setIssues([])
    setErrorMessage(null)
    setLocalError(null)
    if (!file) {
      setLocalError(AGENT_SKILLS_COPY.invalidFile)
      return
    }
    if (file.size > SKILL_UPLOAD_MAX_BYTES) {
      setLocalError(
        AGENT_SKILLS_COPY.importTooLarge.replace(
          '{mb}',
          String(SKILL_UPLOAD_MAX_BYTES / (1024 * 1024))
        )
      )
      return
    }
    try {
      const created = await importPackage.mutateAsync(file)
      onImported(created)
      handleOpenChange(false)
    } catch (error) {
      const found = skillIssuesFromError(error)
      setIssues(found)
      if (found.length === 0) {
        setErrorMessage(
          skillErrorMessage(
            error,
            AGENT_SKILLS_COPY.importFailed,
            SKILL_ERROR_CODE_COPY
          )
        )
      }
    }
  }

  return (
    <Dialog onOpenChange={handleOpenChange} open={open}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{AGENT_SKILLS_COPY.importTitle}</DialogTitle>
          <DialogDescription>
            {AGENT_SKILLS_COPY.importDescription}
          </DialogDescription>
        </DialogHeader>

        <div className='grid gap-1.5'>
          <Label htmlFor='agent-skill-import-file'>
            {AGENT_SKILLS_COPY.importFile}
          </Label>
          <input
            accept='.zip,application/zip'
            className='border-input file:bg-muted file:text-foreground w-full rounded-lg border px-2.5 py-1.5 text-sm file:mr-3 file:rounded-md file:border-0 file:px-2 file:py-1 file:text-xs'
            id='agent-skill-import-file'
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null)
              setLocalError(null)
              setIssues([])
              setErrorMessage(null)
            }}
            ref={inputRef}
            type='file'
          />
          {localError && <p className='text-destructive text-xs'>{localError}</p>}
        </div>

        {(issues.length > 0 || errorMessage) && (
          <div
            className='border-destructive/30 bg-destructive/5 grid gap-2 rounded-xl border p-3'
            data-testid='skill-import-result'
          >
            <p className='text-destructive text-xs font-medium'>
              {AGENT_SKILLS_COPY.importIssues}
            </p>
            <SkillIssueList issues={issues} showSummary />
            {errorMessage && (
              <p className='text-destructive text-xs'>{errorMessage}</p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button
            disabled={importPackage.isPending}
            onClick={() => handleOpenChange(false)}
            type='button'
            variant='outline'
          >
            {AGENT_SKILLS_COPY.cancel}
          </Button>
          <Button
            disabled={importPackage.isPending}
            onClick={() => void handleSubmit()}
            type='button'
          >
            {importPackage.isPending ? (
              <Spinner className='size-3.5' />
            ) : (
              <Upload aria-hidden='true' className='size-3.5' />
            )}
            {importPackage.isPending
              ? AGENT_SKILLS_COPY.importSubmitting
              : AGENT_SKILLS_COPY.importSubmit}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
