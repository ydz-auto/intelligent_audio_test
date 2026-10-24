/**
 * 用例详情弹窗（§5.2；interfaces/features/test-execution/modals；Dialog sm:max-w-4xl，
 * 内滚 contentHeight='min(72dvh,720px)'）。
 * 头：用例名 + 双状态徽章 + 耗时 + 评分徽章 + CaseIdBadge（点击复制）+ 设备名列表。
 * 分节①执行结果与指标——轮次 Tab（第1轮…第N轮 / 整体，单轮不渲染 Tab 栏）+ 指标×设备表
 * （行=指标、列=设备，V9.7.10 currentRoundTableData 同口径）+ ASR/翻译参考文本块 +
 * 结果音频（`result_audios`，按设备分组、**不随轮次 Tab 过滤**，10 §5.2 ① INT-1723 ⑤）+
 * 执行结果音频字段（`algorithm_results` 的 audio_file 项，按当前 Tab 轮次过滤，V9.7.10 结果字段口径）；
 * 试听→INT-356 弹窗复用；换用例时轮次 Tab 复位到第一个有数据的 Tab。
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
import { executionStatusLabel, toAiReviewDimensionIds } from '@/domain/models/review'
import type {
  CaseAlgorithmResult,
  CaseAudioResult,
  CaseResultAudioField,
  CaseRoundTab,
} from '@/domain/models/testExecution'
import { stream, streamByPath } from '@/infrastructure/api/audios-api'
import { fetchCaseExecutionDetail, fetchCaseLogs } from '@/infrastructure/api/test-execution-api'
import { fetchTaskDetail } from '@/infrastructure/api/tasks-list-api'
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
import {
  AudioPlayerModal,
  type AudioItemMeta,
} from '@/features/report-view/components/case-report-detail/audio-player-modal'
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
 * 执行结果音频字段（algorithm_results 的 audio_file 项）按当前 Tab 过滤——
 * V9.7.10 `currentRoundResultTextFields`（TestCaseReportDetail.vue:834-891）同口径：
 * - 单轮「指标」Tab / 无 Tab：全部；
 * - 「整体」Tab：无维度归属（设备/API 执行结果）全部显示，有维度归属只显示 `@overall` 项；
 * - 轮次 Tab：无轮次标记的字段所有 Tab 都显示，有轮次标记的只在本轮（`@overall` 不混入）。
 */
function isAudioFieldVisible(
  field: CaseResultAudioField,
  tab: CaseRoundTab | null
): boolean {
  if (!tab || tab.kind === 'all') return true
  if (tab.kind === 'overall') {
    return field.dimensionName == null ? true : field.overall
  }
  if (field.overall) return false
  if (field.round == null) return true
  return field.round === tab.round
}

/** Tab 是否有评估数据（V9.7.10 tabHasMetricData：有非空值才算） */
function tabHasData(tab: CaseRoundTab): boolean {
  return tab.rows.some((row) =>
    Object.values(row.values).some((value) => value !== '' && value !== '—')
  )
}

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
  // 轮次 Tab 选中态绑定 caseId：换用例即失配 → 复位到第一个有数据的 Tab（P3，V9.7.10 :1317-1328）
  const [tabChoice, setTabChoice] = useState<{ caseId: string; tabKey: string } | null>(null)
  const [playingAudio, setPlayingAudio] = useState<AudioItemMeta | null>(null)
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
  // INT-1064 复核入口准入（10 §5.2：终态任务 + 有执行结果 + task.result.ai_review）
  const taskQuery = useQuery({
    queryKey: ['tasks', 'detail', taskId],
    queryFn: () => fetchTaskDetail(taskId),
    enabled: open && taskId > 0,
    staleTime: 30_000,
  })

  const detail = detailQuery.data
  const logs = logsQuery.data
  // INT-1688：执行结果行随详情一并取回（/results），不再单独查询
  const caseResults: CaseResultForReview[] = detail?.results ?? []
  const taskTerminal = ['completed', 'failed', 'stopped', 'skipped'].includes(
    taskQuery.data?.status ?? ''
  )
  const hasCaseResults = caseResults.length > 0
  // INT-1279 P2：dimension_ids 源（taskQuery.data.cases）异步加载——与 canAiReview 同 gate
  // 在 taskQuery.data 就绪后再计算；taskLoading 期间入口不可见，避免维度静默缺省 → 真实库 400。
  const aiReviewReady = taskQuery.data != null && !taskQuery.isLoading
  // INT-1279：用例评估维度 id（任务用例简报 evaluation_dimensions 溯源；真实库结果无 LLM 判分维度时显式传）
  const aiReviewDimensionIds = toAiReviewDimensionIds(
    taskQuery.data?.cases?.find((c) => c.case_id === caseId)?.evaluation_dimensions
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

  /** 结果/参考音频试听：直出 url → 音频库 id → 静态路径换预签名地址，三种来源统一到 INT-356 弹窗 */
  const playAudio = async (
    audio: {
      url: string | null
      path?: string | null
      audioId?: number | null
      audioName?: string | null
    },
    audioType: 'result' | 'reference'
  ) => {
    try {
      const url =
        audio.url ??
        (audio.audioId != null
          ? await stream(audio.audioId)
          : audio.path
            ? await streamByPath(audio.path)
            : null)
      if (!url) throw new Error('音频地址缺失')
      setPlayingAudio({
        audio_id: audio.audioId ?? audio.audioName ?? '',
        audio_name: audio.audioName ?? undefined,
        audio_type: audioType,
        url,
      })
    } catch {
      toast.error('音频播放地址获取失败')
    }
  }

  const roundTabs = detail?.roundTabs ?? []
  /** 第一个有评估数据的 Tab（V9.7.10 tabHasMetricData + :1317-1328 初始化口径） */
  const firstTabWithDataKey =
    (roundTabs.find(tabHasData) ?? roundTabs[0])?.key ?? null
  /** 换用例或所选 Tab 消失 → 回第一个有数据的 Tab（不再只做越界钳制，P3） */
  const activeTabKey =
    tabChoice &&
    tabChoice.caseId === caseId &&
    roundTabs.some((tab) => tab.key === tabChoice.tabKey)
      ? tabChoice.tabKey
      : firstTabWithDataKey
  const currentTab = roundTabs.find((tab) => tab.key === activeTabKey) ?? null

  /**
   * 参考音频（audio_list，带 roundNumber）按当前 Tab 轮次过滤（现状保留，10 §5.2 本次返工未改口径）：
   * 「整体」Tab 与单轮「指标」Tab 展示全部；轮次 Tab 只留本轮与无轮次信息的音频。
   */
  const audiosForCurrentTab = (audios: CaseAudioResult[]) => {
    if (!currentTab || currentTab.kind !== 'round') return audios
    return audios.filter((audio) => audio.round == null || audio.round === currentTab.round)
  }
  const currentReferenceAudios = detail ? audiosForCurrentTab(detail.referenceAudios) : []

  /**
   * 结果音频（result_audios）不随轮次 Tab 过滤（10 §5.2 ① INT-1723 ⑤）：按设备分组全量展示。
   */
  const resultAudioGroups = (() => {
    const groups: Array<{ deviceName: string; audios: CaseAudioResult[] }> = []
    for (const audio of detail?.resultAudios ?? []) {
      const deviceName = audio.deviceName || '未标注设备'
      const group = groups.find((g) => g.deviceName === deviceName)
      if (group) group.audios.push(audio)
      else groups.push({ deviceName, audios: [audio] })
    }
    return groups
  })()

  /** 执行结果音频字段（algorithm_results 的 audio_file 项）按当前 Tab 过滤 */
  const visibleResultAudioFields = (detail?.resultAudioFields ?? []).filter((field) =>
    isAudioFieldVisible(field, currentTab)
  )

  /** 有真实执行数据才渲染指标×设备表；无结果用例退回结果摘要（空态不回归） */
  const hasDeviceTable =
    (detail?.devices.length ?? 0) > 0 &&
    (caseResults.length > 0 || (detail?.devices ?? []).some((d) => d.metrics.length > 0))

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
                  label={
                    detail.executionStatus === 'completed'
                      ? '执行完成'
                      : executionStatusLabel(detail.executionStatus)
                  }
                  variant={
                    detail.executionStatus === 'completed'
                      ? 'success'
                      : detail.executionStatus === 'failed'
                        ? 'danger'
                        : 'warning'
                  }
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
                    <Badge key={d.deviceName} variant='outline' className='text-[11px]'>
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
              {hasDeviceTable ? (
                <div className='space-y-2'>
                  {/* 轮次 Tab（第1轮…第N轮 + 整体）；单轮「指标」Tab 不渲染 Tab 栏 */}
                  {roundTabs.length > 1 && (
                    <div className='flex flex-wrap gap-1' role='tablist' aria-label='轮次切换'>
                      {roundTabs.map((tab) => (
                        <button
                          key={tab.key}
                          type='button'
                          role='tab'
                          aria-selected={currentTab?.key === tab.key}
                          className={cn(
                            'rounded-md px-2.5 py-1 text-xs transition-colors',
                            currentTab?.key === tab.key
                              ? 'bg-primary text-primary-foreground'
                              : 'text-muted-foreground hover:bg-muted'
                          )}
                          onClick={() => setTabChoice({ caseId, tabKey: tab.key })}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>
                  )}
                  {/* 指标×设备表：行=指标、列=设备（V9.7.10 currentRoundTableData 同口径） */}
                  <div className='overflow-x-auto rounded-lg border'>
                    <table className='w-full text-left text-sm'>
                      <thead className='bg-muted/50 border-b'>
                        <tr className='text-muted-foreground text-xs'>
                          <th className='px-3 py-2 font-medium whitespace-nowrap'>指标</th>
                          {detail.devices.map((device) => (
                            <th
                              key={device.deviceName}
                              className='px-3 py-2 font-medium whitespace-nowrap'
                            >
                              <span className='flex items-center gap-1.5'>
                                {device.deviceName}
                                <StatusBadge
                                  label={
                                    device.executionStatus
                                      ? executionStatusLabel(device.executionStatus)
                                      : '—'
                                  }
                                  variant={
                                    device.executionStatus === 'completed'
                                      ? 'success'
                                      : device.executionStatus === 'failed'
                                        ? 'danger'
                                        : device.executionStatus
                                          ? 'warning'
                                          : 'neutral'
                                  }
                                />
                              </span>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(currentTab?.rows ?? []).map((row) => (
                          <tr
                            key={row.dimension}
                            className='border-b last:border-0 hover:bg-muted/30'
                          >
                            <td className='px-3 py-2 whitespace-nowrap'>{row.dimension}</td>
                            {detail.devices.map((device) => (
                              <td
                                key={device.deviceName}
                                className='px-3 py-2 font-mono text-xs tabular-nums'
                              >
                                {row.values[device.deviceName] ?? '—'}
                              </td>
                            ))}
                          </tr>
                        ))}
                        {(currentTab?.rows.length ?? 0) === 0 && (
                          <tr>
                            <td
                              colSpan={detail.devices.length + 1}
                              className='text-muted-foreground p-4 text-center text-sm'
                            >
                              暂无指标数据
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <ApiCaseResultSummary
                  results={caseResults}
                  algorithmResults={detail.algorithmResults}
                />
              )}

              {/* ASR / 翻译参考文本 */}
              {detail.devices.some((d) => d.asrReference) && (
                <div className='mt-3 grid gap-3 sm:grid-cols-2'>
                  {detail.devices.map((device) => (
                    <div key={`ref-${device.deviceName}`} className='space-y-2'>
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

              {/* 结果音频（INT-1688：detail result_audios，按设备分组；10 §5.2 ①
                  ——**不随轮次 Tab 过滤**，任何 Tab 都显示全部；试听→INT-356 弹窗复用） */}
              {resultAudioGroups.length > 0 && (
                <div className='mt-3 space-y-2'>
                  <p className='text-muted-foreground text-xs'>结果音频</p>
                  {resultAudioGroups.map((group) => (
                    <div key={group.deviceName} className='space-y-1'>
                      <p className='text-xs font-medium'>{group.deviceName}</p>
                      {group.audios.map((audio, index) => (
                        <div
                          key={`${group.deviceName}-${audio.audioName}-${index}`}
                          className='flex items-center gap-2 rounded-lg border px-3 py-2 text-sm'
                        >
                          <span className='font-mono text-xs'>{audio.audioName}</span>
                          <Button
                            variant='ghost'
                            size='sm'
                            className='ml-auto h-6 gap-1 text-xs'
                            onClick={() => void playAudio(audio, 'result')}
                          >
                            <Play aria-hidden='true' className='size-3' />
                            试听
                          </Button>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              {/* 执行结果音频字段（algorithm_results 的 audio_file 项，V9.7.10 视为结果字段）：
                  按当前 Tab 过滤；轮次只在 chip 上出现一次，label 用原始参数名（不含 @round/@overall） */}
              {visibleResultAudioFields.length > 0 && (
                <div className='mt-3 space-y-1'>
                  <p className='text-muted-foreground text-xs'>执行结果音频</p>
                  {visibleResultAudioFields.map((field, index) => (
                    <div
                      key={`${field.paramCode}-${index}`}
                      className='flex items-center gap-2 rounded-lg border px-3 py-2 text-sm'
                    >
                      <span className='font-mono text-xs'>{field.label}</span>
                      {field.round != null && (
                        <span className='bg-muted text-muted-foreground rounded px-1 text-[10px]'>
                          第{field.round}轮
                        </span>
                      )}
                      {field.overall && (
                        <span className='bg-muted text-muted-foreground rounded px-1 text-[10px]'>
                          整体
                        </span>
                      )}
                      {field.deviceName && (
                        <span className='text-muted-foreground text-xs'>{field.deviceName}</span>
                      )}
                      <Button
                        variant='ghost'
                        size='sm'
                        className='ml-auto h-6 gap-1 text-xs'
                        onClick={() =>
                          void playAudio(
                            { url: field.url, path: field.path, audioName: field.label },
                            'result'
                          )
                        }
                      >
                        <Play aria-hidden='true' className='size-3' />
                        试听
                      </Button>
                    </div>
                  ))}
                </div>
              )}

              {/* 参考音频（用例输入音频 audio_list；按当前轮次 Tab 过滤） */}
              {currentReferenceAudios.length > 0 && (
                <div className='mt-3 space-y-1'>
                  <p className='text-muted-foreground text-xs'>参考音频（用例输入）</p>
                  {currentReferenceAudios.map((audio, index) => (
                    <div
                      key={`${audio.audioName}-${index}`}
                      className='flex items-center gap-2 rounded-lg border px-3 py-2 text-sm'
                    >
                      <span className='font-mono text-xs'>{audio.audioName}</span>
                      {audio.round != null && (
                        <span className='bg-muted text-muted-foreground rounded px-1 text-[10px]'>
                          第{audio.round}轮
                        </span>
                      )}
                      <Button
                        variant='ghost'
                        size='sm'
                        className='ml-auto h-6 gap-1 text-xs'
                        onClick={() => void playAudio(audio, 'reference')}
                      >
                        <Play aria-hidden='true' className='size-3' />
                        试听
                      </Button>
                    </div>
                  ))}
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

      {/* 试听弹窗（INT-356 §5 复用件；INT-1688：url 为预签名地址，真实音频流） */}
      <AudioPlayerModal
        open={playingAudio != null}
        onOpenChange={(next) => {
          if (!next) setPlayingAudio(null)
        }}
        audio={playingAudio ?? undefined}
      />

      {/* 分节①区头「人工复核」入口（10 §5.2）→ 19 §3.2 复核弹窗（结果区真实结果行，无执行结果不开放） */}
      <ManualReviewDialog
        open={manualReviewOpen}
        onOpenChange={setManualReviewOpen}
        taskId={taskId}
        taskName={taskQuery.data?.name}
        caseName={detail?.name}
        results={caseResults}
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
