/**
 * 「沉淀为 Skill」建议卡（interfaces 层 ai-chat/message；INT-2550 卡面「做」第 10 项）。
 *
 * 后端在 run 正常结束且本次调用 ≥2 个工具时下发 skill_draft_suggested 事件
 * （不落库、created=false、requires_confirmation=true）。气泡里渲染为建议卡：
 * 主按钮带 `?name=&description=` 直达 /agent-skills 新建草稿并预填，
 * 创建动作仍由用户在页面确认；事件未到达时不渲染，不伪造建议。
 * 「忽略」只关闭本卡（INT-2584）：不发请求、不落服务端，卡片随既有消息持久化一起消失。
 */
import { Link } from '@tanstack/react-router'
import { Sparkles } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { ChatSkillSuggestion } from '@/domain/models/aiChat'
import { AGENT_SKILLS_ROUTE } from '@/features/agent-skills/constants'
import { SKILL_SUGGESTION_COPY } from '@/features/ai-chat/constants'

type SkillSuggestionCardProps = {
  suggestion: ChatSkillSuggestion
  /** 「忽略」：只关闭本卡（INT-2584），不发请求、不落库；由消息层清理建议字段 */
  onDismiss?: () => void
}

export function SkillSuggestionCard({
  suggestion,
  onDismiss,
}: SkillSuggestionCardProps) {
  const toolCount = suggestion.toolsUsed.length

  return (
    <div
      className='border-primary/30 bg-primary/5 not-prose mb-4 w-full rounded-md border p-3'
      data-suggested-name={suggestion.suggestedName}
      data-testid='skill-suggestion-card'
    >
      <div className='flex flex-wrap items-center gap-2'>
        <Sparkles aria-hidden='true' className='text-primary size-4' />
        <span className='text-sm font-medium'>
          {SKILL_SUGGESTION_COPY.title}
        </span>
        <div className='ml-auto flex items-center gap-1.5'>
          {suggestion.created ? (
            <Badge variant='secondary'>
              {SKILL_SUGGESTION_COPY.createdBadge}
            </Badge>
          ) : (
            <Button
              className='h-6 px-2 text-xs'
              data-testid='skill-suggestion-create'
              render={
                <Link
                  search={{
                    name: suggestion.suggestedName,
                    description: suggestion.description || undefined,
                  }}
                  to={AGENT_SKILLS_ROUTE}
                />
              }
              size='sm'
              type='button'
              variant='outline'
            >
              {SKILL_SUGGESTION_COPY.createAction}
            </Button>
          )}
          {onDismiss && (
            <Button
              className='h-6 px-2 text-xs'
              data-testid='skill-suggestion-dismiss'
              onClick={onDismiss}
              size='sm'
              type='button'
              variant='ghost'
            >
              {SKILL_SUGGESTION_COPY.dismissAction}
            </Button>
          )}
        </div>
      </div>

      <p className='text-muted-foreground mt-2 text-xs leading-5'>
        {SKILL_SUGGESTION_COPY.description.replace('{count}', String(toolCount))}
      </p>

      <div className='mt-2 flex flex-wrap items-center gap-1.5'>
        <span className='text-muted-foreground text-[11px]'>
          {SKILL_SUGGESTION_COPY.suggestedNameLabel}
        </span>
        <span className='font-mono text-[11px]'>{suggestion.suggestedName}</span>
        {suggestion.sourceSkill && (
          <span className='text-muted-foreground text-[11px]'>
            （来自 {suggestion.sourceSkill}）
          </span>
        )}
      </div>

      {toolCount > 0 && (
        <div className='mt-1.5 flex flex-wrap items-center gap-1.5'>
          <span className='text-muted-foreground text-[11px]'>
            {SKILL_SUGGESTION_COPY.toolsLabel}
          </span>
          {suggestion.toolsUsed.map((tool) => (
            <Badge key={tool} variant='outline'>
              <span className='font-mono text-[11px]'>{tool}</span>
            </Badge>
          ))}
        </div>
      )}

      <p className='text-muted-foreground mt-2 text-[11px]'>
        {SKILL_SUGGESTION_COPY.note}
      </p>
    </div>
  )
}
