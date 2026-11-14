/**
 * Auto 进度面板（interfaces 层 ai-chat/auto-mode；INT-2474 §9.4 / 场景 19-20）。
 *
 * 会话区内展示本 run 的 Auto 执行状态：
 * - 目标 / 当前计划 / 当前步骤与阶段；
 * - 预算水位（五维：已用 / 上限，最高维度给进度条与百分比）；
 * - 已产出工件（id / kind / uri 摘要）与连续失败次数；
 * - 暂停点（预算到阈值 / 连续工具失败）：说明原因 + 「继续运行」/「结束运行」；
 * - 终态：完成 / 超预算 / 熔断 / 失败 / 已结束分别给明确口径，**不把超预算或
 *   熔断展示成成功**；已完成产物保留。
 *
 * 审批联动：Auto 下写操作仍逐条审批，面板只提示待审批条数并引导到下方审批卡，
 * 不提供「全部自动批准」入口（拍板增补 3）。
 */
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CirclePause,
  CirclePlay,
  Loader2,
  Package,
  ShieldAlert,
  Square,
  TriangleAlert,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  AGENT_AUTO_COPY,
  AGENT_RUN_MODE,
  type AgentAutoPause,
  type AgentAutoProgress,
  type AgentRun,
  type AgentRunPausePolicy,
} from '@/domain/models/agent'
import {
  autoBudgetRows,
  autoMaxRatio,
  autoPhaseText,
  autoTerminalCopy,
  autoTerminalKind,
  formatElapsed,
  formatPercent,
  pauseReasonText,
  type AutoTerminalKind,
} from '@/application/agent/auto-progress'
import { cn } from '@/lib/utils'

const TERMINAL_META: Record<
  AutoTerminalKind,
  { icon: typeof CheckCircle2; tone: string }
> = {
  succeeded: { icon: CheckCircle2, tone: 'text-muted-foreground' },
  budget_exceeded: { icon: TriangleAlert, tone: 'text-destructive' },
  circuit_break: { icon: AlertTriangle, tone: 'text-destructive' },
  failed: { icon: AlertTriangle, tone: 'text-destructive' },
  cancelled: { icon: Square, tone: 'text-muted-foreground' },
}

type AutoProgressPanelProps = {
  run: AgentRun | null
  progress: AgentAutoProgress | null
  pause: AgentAutoPause | null
  pausePolicy?: AgentRunPausePolicy | null
  /** 本 run 的待审批条数（与审批卡同源） */
  pendingApprovalCount?: number
  /** 「继续」请求在途 */
  resuming?: boolean
  /** 结束 / 停止按钮在途（取消阶段） */
  stopping?: boolean
  /** 运行错误（事件流失败 / 发起失败） */
  error?: string | null
  /** 刷新恢复后继续：本页无事件流，正在轮询服务端终态（P2） */
  tracking?: boolean
  onResume?: () => void
  onStop?: () => void
}

/** 单个预算维度的迷你水位条 */
function BudgetRow({
  label,
  text,
  ratio,
}: {
  label: string
  text: string
  ratio?: number
}) {
  const percent = Math.min(100, Math.round((ratio ?? 0) * 100))
  return (
    <div className='min-w-0' data-auto-budget-row={label}>
      <div className='text-muted-foreground flex items-baseline justify-between gap-1 text-[11px] leading-4'>
        <span className='truncate'>{label}</span>
        <span className='shrink-0 font-mono text-[10px]'>{text}</span>
      </div>
      <div className='bg-muted mt-0.5 h-1 overflow-hidden rounded-full'>
        <div
          className={cn(
            'h-full rounded-full transition-[width]',
            percent >= 100 ? 'bg-destructive' : percent >= 80 ? 'bg-warning' : 'bg-primary/70'
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  )
}

export function AutoProgressPanel({
  run,
  progress,
  pause,
  pausePolicy = null,
  pendingApprovalCount = 0,
  resuming = false,
  stopping = false,
  error = null,
  tracking = false,
  onResume,
  onStop,
}: AutoProgressPanelProps) {
  // 只在本 run 是 Auto（或已收到 Auto 事件）时出现
  const isAuto =
    run?.mode === AGENT_RUN_MODE.AUTO ||
    Boolean(progress) ||
    Boolean(pause)
  if (!isAuto) return null

  const terminal = autoTerminalCopy(autoTerminalKind(run))
  const ratio = autoMaxRatio(progress)
  const percent = Math.min(100, Math.round(ratio * 100))
  const budgetRows = progress
    ? autoBudgetRows(progress.usage, progress.limits)
    : []
  const artifacts = progress?.artifacts ?? []
  const paused = Boolean(pause) && !terminal
  const pausedText = pause
    ? pauseReasonText(pause.reason, pause.policy?.consecutiveFailures ?? pausePolicy?.consecutiveFailures)
    : ''

  return (
    <section
      className={cn(
        'border-border/60 bg-background/70 mt-3 rounded-xl border p-3 shadow-xs',
        terminal && autoTerminalKind(run) !== 'succeeded' && autoTerminalKind(run) !== 'cancelled'
          ? 'border-destructive/40'
          : undefined
      )}
      data-auto-progress
      data-auto-terminal={autoTerminalKind(run) ?? ''}
      data-auto-paused={paused ? 'true' : 'false'}
    >
      <div className='flex flex-wrap items-center gap-2'>
        <Activity className='text-muted-foreground size-4' />
        <span className='text-sm font-semibold'>{AGENT_AUTO_COPY.progressTitle}</span>
        <Badge data-auto-mode-badge variant='secondary'>
          {AGENT_AUTO_COPY.autoBadge}
        </Badge>
        {progress && !terminal && (
          <Badge data-auto-step={progress.step} variant='outline'>
            {AGENT_AUTO_COPY.progressStep} {progress.step} {AGENT_AUTO_COPY.progressStepUnit}
            {' · '}
            {autoPhaseText(progress)}
          </Badge>
        )}
        {paused && (
          <Badge variant='warning'>{AGENT_AUTO_COPY.pausedTitle}</Badge>
        )}
        {terminal && (
          <Badge variant={terminalTitleVariant(run)}>{terminal.title}</Badge>
        )}
        {pendingApprovalCount > 0 && (
          <Badge data-auto-approvals-count={pendingApprovalCount} variant='warning'>
            {pendingApprovalCount} {AGENT_AUTO_COPY.approvalsCount}
          </Badge>
        )}
      </div>

      {progress?.goal && (
        <p className='text-muted-foreground mt-2 line-clamp-2 text-xs' data-auto-goal>
          <span className='font-medium'>{AGENT_AUTO_COPY.progressGoal}：</span>
          {progress.goal}
        </p>
      )}
      {progress?.plan && (
        <p className='text-muted-foreground mt-1 line-clamp-3 text-[11px] leading-5'>
          <span className='font-medium'>{AGENT_AUTO_COPY.progressPlan}：</span>
          {progress.plan}
        </p>
      )}

      {!progress && !terminal && !paused && (
        <p className='text-muted-foreground mt-2 flex items-center gap-2 text-xs' role='status'>
          <Loader2 className='size-3.5 animate-spin' />
          {tracking ? AGENT_AUTO_COPY.tracking : '正在收集步骤进度…'}
        </p>
      )}

      {progress && (
        <>
          <div className='mt-2.5'>
            <div className='text-muted-foreground mb-1 flex items-center justify-between text-[11px]'>
              <span>{AGENT_AUTO_COPY.progressBudget}</span>
              <span className='font-mono'>
                已用{' '}
                <span data-auto-ratio={percent}>{formatPercent(ratio)}</span>
                {' · '}剩余 {100 - percent}%
              </span>
            </div>
            <div
              aria-label={AGENT_AUTO_COPY.progressBudget}
              aria-valuemax={100}
              aria-valuemin={0}
              aria-valuenow={percent}
              className='bg-muted h-1.5 overflow-hidden rounded-full'
              role='progressbar'
            >
              <div
                className={cn(
                  'h-full rounded-full transition-[width]',
                  percent >= 100 ? 'bg-destructive' : percent >= 80 ? 'bg-warning' : 'bg-primary'
                )}
                style={{ width: `${percent}%` }}
              />
            </div>
            <div className='mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3 lg:grid-cols-5'>
              {budgetRows.map((row) => (
                <BudgetRow
                  key={row.dimension}
                  label={row.label}
                  ratio={row.ratio}
                  text={row.text}
                />
              ))}
            </div>
          </div>

          <div className='mt-2 flex flex-wrap items-center gap-2 text-[11px]'>
            <span className='text-muted-foreground'>
              已用时长 {formatElapsed(progress.usage.elapsedSeconds)}
            </span>
            <span className='text-muted-foreground'>
              {AGENT_AUTO_COPY.progressConsecutiveFailures}{' '}
              {progress.consecutiveFailures} {AGENT_AUTO_COPY.progressTimes}
            </span>
            {progress.instruction && (
              <Badge
                data-auto-instruction
                title={progress.instruction}
                variant='outline'
              >
                {AGENT_AUTO_COPY.progressInstruction}
              </Badge>
            )}
          </div>

          <div className='mt-2' data-auto-artifacts data-auto-artifact-count={progress.artifactCount}>
            <div className='text-muted-foreground mb-1 flex items-center gap-1.5 text-[11px]'>
              <Package className='size-3' />
              <span className='font-medium'>{AGENT_AUTO_COPY.progressArtifacts}</span>
              <span>
                {progress.artifactCount} {AGENT_AUTO_COPY.progressArtifactCount}
              </span>
            </div>
            {artifacts.length === 0 ? (
              <p className='text-muted-foreground text-[11px]'>
                {AGENT_AUTO_COPY.progressNoArtifacts}
              </p>
            ) : (
              <ul className='grid gap-1'>
                {artifacts.map((artifact) => (
                  <li
                    className='text-muted-foreground truncate font-mono text-[10px] leading-4'
                    data-auto-artifact={artifact.id}
                    key={artifact.id || artifact.uri}
                    title={artifact.uri || artifact.id}
                  >
                    {artifact.kind || 'artifact'} · {artifact.uri || artifact.id}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      {/* 暂停点：原因 + 继续 / 结束（DESTRUCTIVE 审批仍逐条，不在此预授权） */}
      {paused && (
        <div
          className='border-warning/40 bg-warning/8 mt-2.5 rounded-lg border px-2.5 py-2'
          data-auto-pause-reason={pause?.reason ?? 'unknown'}
        >
          <div className='flex items-start gap-1.5'>
            <CirclePause className='text-warning mt-0.5 size-3.5 shrink-0' />
            <div className='min-w-0 flex-1'>
              <p className='text-xs font-medium'>{pausedText}</p>
              {pause?.usage && pause.limits && (
                <p className='text-muted-foreground mt-0.5 text-[11px]'>
                  {AGENT_AUTO_COPY.pausedUsage}：{formatPercent(pause.ratio)}（
                  {autoBudgetRows(pause.usage, pause.limits)
                    .filter((row) => row.limit !== undefined)
                    .map((row) => `${row.label} ${row.text}`)
                    .join(' · ')}）
                </p>
              )}
              {pendingApprovalCount > 0 && (
                <p className='text-muted-foreground mt-1 flex items-center gap-1 text-[11px]'>
                  <ShieldAlert className='text-warning size-3' />
                  {AGENT_AUTO_COPY.approvalsHint}（{AGENT_AUTO_COPY.noBulkApprove}）
                </p>
              )}
              <div className='mt-2 flex flex-wrap items-center gap-2'>
                <Button
                  data-auto-resume
                  disabled={resuming || pendingApprovalCount > 0}
                  onClick={onResume}
                  size='xs'
                  type='button'
                >
                  {resuming ? (
                    <Loader2 className='size-3.5 animate-spin' />
                  ) : (
                    <CirclePlay className='size-3.5' />
                  )}
                  {resuming ? AGENT_AUTO_COPY.resuming : AGENT_AUTO_COPY.resume}
                </Button>
                {onStop && (
                  <Button
                    data-auto-stop
                    disabled={stopping}
                    onClick={onStop}
                    size='xs'
                    type='button'
                    variant='outline'
                  >
                    <Square className='size-3.5' />
                    {AGENT_AUTO_COPY.stop}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 终态：完成 / 超预算 / 熔断 / 失败 / 已结束 分别给明确口径 */}
      {terminal && (
        <div
          className='border-border/50 bg-muted/20 mt-2.5 rounded-lg border px-2.5 py-2'
          data-auto-terminal-message={autoTerminalKind(run) ?? ''}
        >
          <div className='flex items-start gap-1.5'>
            {(() => {
              const kind = autoTerminalKind(run)
              if (!kind) return null
              const meta = TERMINAL_META[kind]
              const Icon = meta.icon
              return <Icon className={cn('mt-0.5 size-3.5 shrink-0', meta.tone)} />
            })()}
            <div className='min-w-0 flex-1'>
              <p className='text-xs font-medium'>{terminal.title}</p>
              {terminal.description && (
                <p className='text-muted-foreground mt-0.5 text-[11px]'>
                  {terminal.description}
                </p>
              )}
              {/* 内部错误码收进「详情」，不直接铺在用户文案里（P3-4） */}
              {run?.error && autoTerminalKind(run) !== 'succeeded' && (
                <details className='mt-1'>
                  <summary className='text-muted-foreground w-fit cursor-pointer text-[10px]'>
                    查看详情
                  </summary>
                  <p
                    className='text-muted-foreground mt-0.5 font-mono text-[10px] break-all'
                    data-auto-error-code
                  >
                    {run.error}
                  </p>
                </details>
              )}
            </div>
          </div>
        </div>
      )}

      {/* run 级错误：终态由终态块统一表达，不再重复同一条提示（P3-4） */}
      {error && !terminal && (
        <p className='text-destructive mt-2 text-xs' role='alert'>
          {error}
        </p>
      )}
    </section>
  )
}

/** 终态徽标配色：成功中性、超预算 / 熔断 / 失败用 destructive */
function terminalTitleVariant(
  run: AgentRun | null
): 'secondary' | 'destructive' | 'warning' {
  const kind = autoTerminalKind(run)
  if (kind === 'budget_exceeded' || kind === 'circuit_break' || kind === 'failed') {
    return 'destructive'
  }
  return 'secondary'
}
