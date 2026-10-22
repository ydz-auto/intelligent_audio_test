/**
 * 用例详情弹窗（§5.2；interfaces/features/test-execution/modals；Dialog sm:max-w-4xl，
 * 内滚 contentHeight='min(72dvh,720px)'）。
 * 头：用例名 + 双状态徽章 + 耗时 + 评分徽章 + CaseIdBadge（点击复制）+ 设备名列表。
 * 分节①执行结果与指标——设备×维度对比表（多轮维度列带 @round:{n}/@overall 后缀）+
 * ASR/翻译参考文本块 + 结果音频列表（试听→INT-356 弹窗复用）；
 * 分节②执行日志——「加载更多日志」+ 等宽容器 + 分页 100 条/页。
 * 数据源 GET /tasks/{taskId}/cases/{caseId}/detail + /results + GET /logs?task_id&test_case_id。
 * 复核入口（INT-1055/INT-1066，10 §5.2 注记 3）：分节①区头右侧「人工复核」/「AI 复核」两钮
 * （终态任务 + fetchCaseResults 有执行结果时显；无执行结果不开放）——人工复核 → 19 §3.2 弹窗
 * （task.result.review）；AI 复核 → 19 §5 灵犀Agent 复核会话（task.result.ai_review，可追问）。
 * 接线：任务详情路由页（09 §4.4 onCaseSelect）与测试执行步骤四共用本组件。
 */
import { Clipboard, ClipboardCheck, ListChecks, Play, ScrollText, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { CaseResultForReview } from '@/domain/models/review'
import { toAiReviewDimensionIds } from '@/domain/models/review'
import type { CaseAlgorithmResult } from '@/domain/models/testExecution'
import { fetchCaseExecutionDetail, fetchCaseLogs } from '@/infrastructure/api/test-execution-api'
import { fetchTaskDetail } from '@/infrastructure/api/tasks-list-api'
import { fetchCaseResults } from '@/infrastructure/api/reviewApi'
import { usePermissions } from '@/application/hooks/use-permissions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { AudioPlayerModal } from '@/features/report-view/components/case-report-detail/audio-player-modal'
import { formatResultValue } from '@/features/report-view/components/case-report-detail/case-report-utils'
import { AiReviewSessionDialog } from '@/features/ai-review/ai-review-session-dialog'
import { ManualReviewDialog } from '@/features/tasks/components/manual-review-dialog'
import { cn } from '@/lib/utils'

interface CaseDetailDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number
  caseId: string
}

const LOG_PER_PAGE = 100

/**
 * 分节① API/voice_llm 用例结果摘要（INT-1066 返工，10 §5.2 同口径对齐旧 Vue TestCaseDetailModal）：
 * devices 空但 /results 或 /detail.algorithm_results 有结果时展示真实结果，与「人工复核」可用态一致，
 * 不再直接判「暂无执行结果」。两数据源并存时依次展示「执行结果行」（/results）与「算法结果指标」
 * （algorithm_results 扁平项，值经 report 域 formatResultValue 格式化）。
 */
function ApiCaseResultSummary({
  results,
  algorithmResults,
}: {
  results: CaseResultForReview[]
  algorithmResults: CaseAlgorithmResult[]
}) {
  const hasResults = results.length > 0
  const hasAlgorithm = (algorithmResults ?? []).length > 0
  if (!hasResults && !hasAlgorithm) {
    return <p className='text-muted-foreground py-6 text-center text-sm'>暂无执行结果</p>
  }
  return (
    <div className='space-y-3'>
      {hasResults && (
        <div className='overflow-hidden rounded-lg border'>
          <table className='w-full text-left text-sm'>
            <thead className='bg-muted/50 border-b'>
              <tr className='text-muted-foreground text-xs'>
                <th className='px-3 py-2 font-medium'>资源</th>
                <th className='px-3 py-2 font-medium'>结果</th>
                <th className='px-3 py-2 text-end font-medium'>响应</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.id} className='border-b last:border-0 hover:bg-muted/30'>
                  <td className='px-3 py-2'>
                    <span className='font-medium'>
                      {r.deviceName ?? r.apiName ?? `结果 ${r.id}`}
                    </span>
                    {r.errorMessage && (
                      <span className='text-destructive ml-1 text-xs'>{r.errorMessage}</span>
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    <StatusBadge
                      label={r.executionStatus === 'completed' ? '执行完成' : r.executionStatus ?? '—'}
                      variant={
                        r.executionStatus === 'completed'
                          ? 'success'
                          : r.executionStatus === 'failed'
                            ? 'danger'
                            : 'warning'
                      }
                    />
                  </td>
                  <td className='px-3 py-2 text-end font-mono text-xs tabular-nums'>
                    {r.responseTime != null ? `${r.responseTime}ms` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {hasAlgorithm && (
        <div className='overflow-hidden rounded-lg border'>
          <table className='w-full text-left text-sm'>
            <thead className='bg-muted/50 border-b'>
              <tr className='text-muted-foreground text-xs'>
                <th className='px-3 py-2 font-medium'>算法结果指标</th>
                <th className='px-3 py-2 font-medium'>值</th>
              </tr>
            </thead>
            <tbody>
              {(algorithmResults ?? []).map((row, index) => (
                <tr
                  key={row.paramCode ?? index}
                  className='border-b align-top last:border-0 hover:bg-muted/30'
                >
                  <td className='px-3 py-2 font-medium'>{row.label ?? row.paramCode}</td>
                  <td className='px-3 py-2 break-all font-mono text-xs whitespace-pre-wrap tabular-nums'>
                    {formatResultValue(row.value, row.paramType)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function CaseDetailDialog({ open, onOpenChange, taskId, caseId }: CaseDetailDialogProps) {
  const [page, setPage] = useState(1)
  const [playingAudio, setPlayingAudio] = useState<string | null>(null)
  const [manualReviewOpen, setManualReviewOpen] = useState(false)
  const [aiReviewOpen, setAiReviewOpen] = useState(false)
  const { hasPermission } = usePermissions()

  const detailQuery = useQuery({
    queryKey: ['test-execution', 'case-detail', taskId, caseId],
    queryFn: () => fetchCaseExecutionDetail(taskId, caseId),
    enabled: open,
    staleTime: 30_000,
  })
  const logsQuery = useQuery({
    queryKey: ['test-execution', 'case-logs', taskId, caseId, page],
    queryFn: () => fetchCaseLogs(taskId, caseId, page),
    enabled: open,
    staleTime: 15_000,
  })
  // INT-1064 复核入口准入（10 §5.2：终态任务 + fetchCaseResults 有执行结果 + task.result.ai_review）
  const taskQuery = useQuery({
    queryKey: ['tasks', 'detail', taskId],
    queryFn: () => fetchTaskDetail(taskId),
    enabled: open && taskId > 0,
    staleTime: 30_000,
  })
  const resultsQuery = useQuery({
    queryKey: ['tasks', 'cases', taskId, caseId, 'results'],
    queryFn: () => fetchCaseResults(taskId, caseId),
    enabled: open && taskId > 0 && Boolean(caseId),
    staleTime: 15_000,
  })

  const detail = detailQuery.data
  const logs = logsQuery.data
  const taskTerminal = ['completed', 'failed', 'stopped', 'skipped'].includes(
    taskQuery.data?.status ?? ''
  )
  const hasCaseResults = (resultsQuery.data?.results.length ?? 0) > 0
  // INT-1279 P2：dimension_ids 源（taskQuery.data.cases）异步加载——与 canAiReview 同 gate
  // 在 taskQuery.data 就绪后再计算；taskLoading 期间入口不可见，避免维度静默缺省 → 真实库 400。
  const aiReviewReady = taskQuery.data != null && !taskQuery.isLoading
  // INT-1279：用例评估维度 id（任务用例简报 evaluation_dimensions 溯源；真实库结果无 LLM 判分维度时显式传）
  const aiReviewDimensionIds = toAiReviewDimensionIds(
    taskQuery.data?.cases.find((c) => c.case_id === caseId)?.evaluation_dimensions
  )
  // 复核按钮位置以 10 §5.2「分节①区头右侧」收口（注记 3）：终态任务 + 有执行结果 + 权限
  // 人工复核（task.result.review）→ 19 §3.2 弹窗；AI 复核（task.result.ai_review）→ 19 §5 会话
  const canManualReview =
    taskTerminal && hasCaseResults && hasPermission('task.result.review')
  const canAiReview =
    aiReviewReady &&
    taskTerminal &&
    hasCaseResults &&
    hasPermission('task.result.ai_review')

  /** INT-1279 P2：AI 复核发起前等任务详情查询解析（防御性 gate——canAiReview 已要求 taskQuery.data
   *  就绪，此等待兜底极端时序，确保 dimension_ids 可用后再打开会话） */
  const openAiReview = async () => {
    if (taskQuery.isLoading) {
      await taskQuery.refetch()
    }
    setAiReviewOpen(true)
  }

  const copyCaseId = () => {
    void navigator.clipboard?.writeText(caseId)
    toast.success('已复制')
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-4xl' data-slot='case-detail-dialog'>
        <DialogHeader className='text-start'>
          {detail ? (
            <div className='space-y-2'>
              <div className='flex flex-wrap items-center gap-2'>
                <DialogTitle className='text-lg font-semibold'>{detail.name}</DialogTitle>
                <button
                  type='button'
                  onClick={copyCaseId}
                  className='bg-muted text-muted-foreground hover:bg-accent inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-xs'
                  title='点击复制用例 ID'
                >
                  {caseId}
                  <Clipboard aria-hidden='true' className='size-3' />
                </button>
              </div>
              <div className='flex flex-wrap items-center gap-2'>
                <StatusBadge
                  label={detail.executionStatus === 'completed' ? '执行完成' : detail.executionStatus}
                  variant={detail.executionStatus === 'completed' ? 'success' : 'warning'}
                />
                <StatusBadge
                  label={detail.evaluationStatus === 'completed' ? '评估完成' : '评估中'}
                  variant={detail.evaluationStatus === 'completed' ? 'success' : 'neutral'}
                />
                {detail.duration != null && (
                  <span className='text-muted-foreground text-sm'>耗时 {detail.duration}s</span>
                )}
                {detail.score != null && (
                  <StatusBadge
                    label={`评分 ${detail.score}`}
                    variant={detail.score >= 80 ? 'success' : 'warning'}
                  />
                )}
                <span className='flex flex-wrap gap-1'>
                  {detail.devices.map((d) => (
                    <Badge key={d.deviceId} variant='outline' className='text-[11px]'>
                      {d.deviceName}
                    </Badge>
                  ))}
                </span>
              </div>
            </div>
          ) : (
            <DialogTitle>用例详情</DialogTitle>
          )}
        </DialogHeader>

        {detailQuery.isLoading ? (
          <div aria-busy='true' className='space-y-3 py-2'>
            <Skeleton className='h-40 w-full rounded-lg' />
            <Skeleton className='h-52 w-full rounded-lg' />
          </div>
        ) : detailQuery.isError || !detail ? (
          <Alert variant='destructive'>
            <AlertDescription className='text-sm'>
              加载失败，请重试
            </AlertDescription>
          </Alert>
        ) : (
          <div className='max-h-[min(72dvh,720px)] space-y-6 overflow-y-auto pr-1'>
            {/* ①执行结果与指标（区头右侧 = 复核入口，10 §5.2 注记 3） */}
            <section>
              <div className='mb-2 flex items-center justify-between gap-2'>
                <h4 className='flex items-center gap-1.5 text-sm font-semibold'>
                  <ListChecks aria-hidden='true' className='text-muted-foreground size-4' />
                  执行结果与指标
                </h4>
                {canManualReview && (
                  <Button
                    variant='ghost'
                    size='sm'
                    className='text-muted-foreground h-7 gap-1 text-xs'
                    onClick={() => setManualReviewOpen(true)}
                    title='人工复核（改判执行/评估状态 + 备注必填留痕）'
                  >
                    <ClipboardCheck aria-hidden='true' className='size-3' />
                    人工复核
                  </Button>
                )}
                {canAiReview && (
                  <Button
                    variant='ghost'
                    size='sm'
                    className='text-muted-foreground h-7 gap-1 text-xs'
                    onClick={() => void openAiReview()}
                    title='AI 复核（灵犀Agent 对话式复核，可追问；建议层不直接修改统计）'
                  >
                    <Sparkles aria-hidden='true' className='size-3' />
                    AI 复核
                  </Button>
                )}
              </div>
              {detail.devices.length > 0 ? (
                <div className='overflow-hidden rounded-lg border'>
                  <table className='w-full text-left text-sm'>
                    <thead className='bg-muted/50 border-b'>
                      <tr className='text-muted-foreground text-xs'>
                        <th className='px-3 py-2 font-medium'>设备</th>
                        {detail.devices[0].metrics.map((metric) => (
                          <th key={`${metric.dimension}-${metric.round ?? 'overall'}`} className='px-3 py-2 text-end font-medium'>
                            {metric.round != null
                              ? `${metric.dimension}@round:${metric.round}`
                              : `${metric.dimension}@overall`}
                          </th>
                        ))}
                        <th className='px-3 py-2 text-end font-medium'>结果</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.devices.map((device) => (
                        <tr key={device.deviceId} className='border-b last:border-0 hover:bg-muted/30'>
                          <td className='px-3 py-2'>
                            <span className='font-medium'>{device.deviceName}</span>
                          </td>
                          {device.metrics.map((metric, index) => (
                            <td key={index} className='px-3 py-2 text-end font-mono text-xs tabular-nums'>
                              {metric.value}
                            </td>
                          ))}
                          <td className='px-3 py-2 text-end'>
                            <StatusBadge
                              label={device.status === 'pass' ? '通过' : '失败'}
                              variant={device.status === 'pass' ? 'success' : 'danger'}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <ApiCaseResultSummary
                  results={resultsQuery.data?.results ?? []}
                  algorithmResults={detail.algorithmResults}
                />
              )}

              {/* ASR / 翻译参考文本 */}
              {detail.devices.some((d) => d.asrReference) && (
                <div className='mt-3 grid gap-3 sm:grid-cols-2'>
                  {detail.devices.map((device) => (
                    <div key={`ref-${device.deviceId}`} className='space-y-2'>
                      {device.asrReference && (
                        <div className='space-y-1'>
                          <p className='text-muted-foreground text-xs'>ASR 参考文本（{device.deviceName}）</p>
                          <p className='bg-muted/40 rounded-md p-3 font-mono text-xs'>
                            {device.asrReference}
                          </p>
                        </div>
                      )}
                      {device.translationReference && (
                        <div className='space-y-1'>
                          <p className='text-muted-foreground text-xs'>翻译参考文本（{device.deviceName}）</p>
                          <p className='bg-muted/40 rounded-md p-3 font-mono text-xs'>
                            {device.translationReference}
                          </p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* 结果音频列表（试听→INT-356 弹窗复用） */}
              {detail.devices.some((d) => d.audioResults.length > 0) && (
                <div className='mt-3 space-y-1'>
                  <p className='text-muted-foreground text-xs'>结果音频</p>
                  {detail.devices.map((device) =>
                    device.audioResults.map((audio, index) => (
                      <div
                        key={`${device.deviceId}-${audio.audioName}-${index}`}
                        className='flex items-center gap-2 rounded-lg border px-3 py-2 text-sm'
                      >
                        <span className='font-mono text-xs'>{audio.audioName}</span>
                        <span className='text-muted-foreground text-xs tabular-nums'>
                          {device.deviceName} · {audio.duration}s
                        </span>
                        <Button
                          variant='ghost'
                          size='sm'
                          className='ml-auto h-6 gap-1 text-xs'
                          onClick={() => setPlayingAudio(audio.audioName)}
                        >
                          <Play aria-hidden='true' className='size-3' />
                          试听
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              )}
            </section>

            {/* ②执行日志（分页 100 条/页） */}
            <section>
              <div className='mb-2 flex items-center justify-between'>
                <h4 className='flex items-center gap-1.5 text-sm font-semibold'>
                  <ScrollText aria-hidden='true' className='text-muted-foreground size-4' />
                  执行日志
                </h4>
                {logs && (
                  <Button
                    variant='ghost'
                    size='sm'
                    className='text-muted-foreground h-6 text-xs'
                    onClick={() => setPage((p) => p + 1)}
                  >
                    加载更多日志
                  </Button>
                )}
              </div>
              <div className='bg-muted/30 max-h-[400px] overflow-y-auto rounded-lg p-4 font-mono text-xs leading-6'>
                {!logs ? (
                  <p className='text-muted-foreground'>暂无日志信息</p>
                ) : (
                  <>
                    {logs.items.map((entry) => (
                      <div key={entry.id} className='flex items-baseline gap-2'>
                        <span className='text-muted-foreground min-w-[150px] shrink-0 whitespace-nowrap'>
                          {entry.timestamp}
                        </span>
                        <span
                          aria-hidden='true'
                          className={cn(
                            'mt-[7px] size-1.5 shrink-0 rounded-full',
                            entry.level === 'error'
                              ? 'bg-destructive'
                              : entry.level === 'warn'
                                ? 'bg-warning'
                                : 'bg-foreground'
                          )}
                        />
                        <span
                          className={cn(
                            'break-all',
                            entry.level === 'error' && 'text-destructive',
                            entry.level === 'warn' && 'text-warning'
                          )}
                        >
                          {entry.message}
                        </span>
                      </div>
                    ))}
                  </>
                )}
              </div>
              {logs && (
                <p className='text-muted-foreground mt-1.5 text-end text-xs'>
                  显示 {Math.min(page * LOG_PER_PAGE, logs.total)} / 共 {logs.total} 条
                </p>
              )}
            </section>
          </div>
        )}
      </DialogContent>

      {/* 试听弹窗（INT-356 §5 复用件） */}
      <AudioPlayerModal
        open={playingAudio != null}
        onOpenChange={(next) => {
          if (!next) setPlayingAudio(null)
        }}
        audio={
          playingAudio
            ? { audio_id: playingAudio, audio_name: playingAudio, audio_type: 'result' }
            : undefined
        }
      />

      {/* 分节①区头「人工复核」入口（10 §5.2）→ 19 §3.2 复核弹窗（结果区真实结果行，无执行结果不开放） */}
      <ManualReviewDialog
        open={manualReviewOpen}
        onOpenChange={setManualReviewOpen}
        taskId={taskId}
        taskName={taskQuery.data?.name}
        caseName={detail?.name}
        results={resultsQuery.data?.results ?? []}
        evaluationStatus={detail?.evaluationStatus}
      />

      {/* 分节①区头「AI 复核」入口（10 §5.2）→ 灵犀Agent 复核会话（19 §5，可追问） */}
      <AiReviewSessionDialog
        open={aiReviewOpen}
        onOpenChange={setAiReviewOpen}
        taskId={taskId}
        caseId={caseId}
        caseName={detail?.name}
        dimensionIds={aiReviewDimensionIds}
      />
    </Dialog>
  )
}
