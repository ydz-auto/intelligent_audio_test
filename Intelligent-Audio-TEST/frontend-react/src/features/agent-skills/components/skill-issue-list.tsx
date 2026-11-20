/**
 * 逐项校验明细（features/agent-skills）。
 *
 * 服务端 issues[{code, severity, field, message}] 原样展示：code 查表出中文名，
 * 带 field 的条目可点击定位到对应输入项；field 缺失的归到顶部汇总区，不静默
 * 丢弃（方案 §4.4 逐项校验反馈）。
 */
import { AlertCircle, ArrowUpRight } from 'lucide-react'

import {
  SKILL_ISSUE_SEVERITY,
  type SkillIssue,
} from '@/domain/models/agentSkill'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import { AGENT_SKILLS_COPY, SKILL_ISSUE_CODE_COPY } from '../constants'

type SkillIssueListProps = {
  issues: SkillIssue[]
  /** 点击带 field 的条目时定位（由编辑器提供锚点滚动） */
  onLocate?: (field: string) => void
  className?: string
  /** 顶部汇总（导入弹窗等无字段定位场景） */
  showSummary?: boolean
}

export function SkillIssueList({
  issues,
  onLocate,
  className,
  showSummary = false,
}: SkillIssueListProps) {
  if (issues.length === 0) return null
  const unlocated = issues.filter((issue) => !issue.field)

  return (
    <div className={cn('grid gap-2', className)} data-testid='skill-issue-list'>
      {showSummary && unlocated.length > 0 && (
        <p className='text-muted-foreground text-xs'>
          {AGENT_SKILLS_COPY.issueSummaryTop}
        </p>
      )}
      <ul className='grid gap-1.5'>
        {issues.map((issue, index) => {
          const codeCopy = SKILL_ISSUE_CODE_COPY[issue.code]
          const isError = issue.severity === SKILL_ISSUE_SEVERITY.ERROR
          const clickable = Boolean(issue.field && onLocate)
          return (
            <li
              className={cn(
                'flex items-start gap-2 rounded-lg border px-2.5 py-2 text-xs',
                isError
                  ? 'border-destructive/30 bg-destructive/5'
                  : 'border-warning/40 bg-warning/10'
              )}
              data-testid='skill-issue-item'
              key={`${issue.code}-${issue.field}-${index}`}
            >
              <AlertCircle
                aria-hidden='true'
                className={cn(
                  'mt-0.5 size-3.5 shrink-0',
                  isError ? 'text-destructive' : 'text-warning'
                )}
              />
              <div className='min-w-0 flex-1'>
                <p className='flex flex-wrap items-center gap-1.5'>
                  <Badge variant={isError ? 'destructive' : 'secondary'}>
                    {isError ? '错误' : '告警'}
                  </Badge>
                  <span className='font-mono text-[11px]'>{issue.code}</span>
                  {codeCopy && (
                    <span className='text-muted-foreground'>{codeCopy}</span>
                  )}
                  {issue.field ? (
                    <span className='text-muted-foreground font-mono text-[11px]'>
                      @{issue.field}
                    </span>
                  ) : (
                    <span className='text-muted-foreground text-[11px]'>
                      {AGENT_SKILLS_COPY.issueUnlocated}
                    </span>
                  )}
                </p>
                <p className='text-foreground/90 mt-0.5 leading-5 break-words'>
                  {issue.message}
                </p>
              </div>
              {clickable && (
                <button
                  className='text-primary inline-flex shrink-0 items-center gap-0.5 text-[11px] hover:underline'
                  onClick={() => onLocate?.(issue.field)}
                  type='button'
                >
                  定位
                  <ArrowUpRight aria-hidden='true' className='size-3' />
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
