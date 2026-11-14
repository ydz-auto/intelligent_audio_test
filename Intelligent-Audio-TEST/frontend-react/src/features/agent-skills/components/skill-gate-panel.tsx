/**
 * 发布门槛面板（features/agent-skills；方案 §4.4「发布门槛」）。
 *
 * 服务端没有独立的门槛只读接口：发布动作本身即门槛检查（门槛未达标返回 200 +
 * gate + 仍 DRAFT）。面板展示最近一次检查结果：golden tasks 条数、触发判定、
 * 未达标原因；未达标时发布按钮禁用并说明「只能留作草稿，不参与自动触发」
 * （再次保存会清空本次门槛结果，按钮随之恢复）。
 */
import { CheckCircle2, ShieldAlert, ShieldCheck } from 'lucide-react'

import type { SkillGate } from '@/domain/models/agentSkill'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'

import { AGENT_SKILLS_COPY } from '../constants'

type SkillGatePanelProps = {
  gate: SkillGate | null
  /** 发布动作进行中 */
  pending: boolean
  /** 服务端返回的发布错误（含逐项 issues 之外的错误码文案） */
  errorMessage?: string | null
  onPublish: () => void
  /** 是否允许发起发布（只有 DRAFT 可发布） */
  publishable: boolean
  /** 页面已知道门槛未达标（发布按钮禁用，只能留作草稿） */
  unmet: boolean
}

export function SkillGatePanel({
  gate,
  pending,
  errorMessage,
  onPublish,
  publishable,
  unmet,
}: SkillGatePanelProps) {
  return (
    <div
      className='border-border/60 grid gap-2 rounded-xl border p-3'
      data-testid='skill-gate-panel'
    >
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <h3 className='flex items-center gap-1.5 text-sm font-semibold'>
          {gate?.passed ? (
            <ShieldCheck aria-hidden='true' className='size-4 text-emerald-600' />
          ) : (
            <ShieldAlert aria-hidden='true' className='text-warning size-4' />
          )}
          {AGENT_SKILLS_COPY.gateTitle}
        </h3>
        {publishable && (
          <Button
            data-testid='skill-publish-button'
            disabled={pending || unmet}
            onClick={onPublish}
            size='sm'
            type='button'
            variant='default'
          >
            {pending && <Spinner className='size-3.5' />}
            {AGENT_SKILLS_COPY.publishButton}
          </Button>
        )}
      </div>

      {!gate && (
        <p className='text-muted-foreground text-xs'>
          {AGENT_SKILLS_COPY.gateNotChecked}
        </p>
      )}

      {gate && (
        <dl className='grid gap-1.5 text-xs sm:grid-cols-2'>
          <div className='flex items-baseline justify-between gap-2'>
            <dt className='text-muted-foreground'>
              {AGENT_SKILLS_COPY.gateGoldenTasks}
            </dt>
            <dd className='flex items-center gap-1 font-mono'>
              {gate.goldenTasks}
              <CheckCircle2
                aria-hidden='true'
                className={
                  gate.goldenTasks >= 3
                    ? 'size-3.5 text-emerald-600'
                    : 'text-muted-foreground size-3.5'
                }
              />
            </dd>
          </div>
          <div className='flex items-baseline justify-between gap-2'>
            <dt className='text-muted-foreground'>
              {AGENT_SKILLS_COPY.gateTrigger}
            </dt>
            <dd>
              <Badge variant={gate.passed ? 'default' : 'destructive'}>
                {gate.passed
                  ? AGENT_SKILLS_COPY.gatePassed
                  : AGENT_SKILLS_COPY.gateFailed}
              </Badge>
            </dd>
          </div>

          {gate.failures.length > 0 && (
            <div className='grid gap-1 sm:col-span-2'>
              <dt className='text-muted-foreground'>
                {AGENT_SKILLS_COPY.gateFailures}
              </dt>
              <dd>
                <ul className='m-0 list-inside list-disc'>
                  {gate.failures.map((failure) => (
                    <li className='text-foreground/90 leading-5' key={failure}>
                      {failure}
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          )}

          {gate.note && (
            <div className='flex items-baseline gap-2 sm:col-span-2'>
              <dt className='text-muted-foreground shrink-0'>
                {AGENT_SKILLS_COPY.gateNote}
              </dt>
              <dd className='text-foreground/80'>{gate.note}</dd>
            </div>
          )}
        </dl>
      )}

      {unmet ? (
        <p
          className='border-warning/40 bg-warning/10 text-warning rounded-lg border px-2.5 py-2 text-xs'
          data-testid='skill-gate-unmet'
        >
          {AGENT_SKILLS_COPY.gateUnmetHint}
        </p>
      ) : (
        gate?.passed && (
          <p className='text-xs text-emerald-600' data-testid='skill-gate-met'>
            {AGENT_SKILLS_COPY.gateMetHint}
          </p>
        )
      )}

      {errorMessage && (
        <p className='text-destructive text-xs'>{errorMessage}</p>
      )}
    </div>
  )
}
