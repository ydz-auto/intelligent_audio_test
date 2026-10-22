/**
 * 已发布任务表格（09_任务域.md §3.7：表格 + 展开版本链详情行）。
 * 列：版本/名称·说明/状态/类型/Benchmark/版本数/发布人·发布时间/操作（行内按钮组）。
 * 展开行五个 DetailSection（照 log-detail-layout 键值行）：版本历史 / Benchmark 标记 /
 * 任务详情（发布时冻结）/ 冻结报告 / 执行记录。
 * 「查看冻结任务详情」→ TaskSnapshotDialog（§5.13）；「查看冻结报告」→ ReportSnapshotDialog（§5.13）。
 * 数据源：列表 fetchPublishedTaskList（GET /published-tasks）；展开版本链行
 * fetchPublishedTaskDetail（GET /published-tasks/{id}）真实详情。
 */
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { ChevronDown, ChevronRight, Package, RefreshCw, Trophy } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { fetchPublishedTaskDetail } from '@/infrastructure/api/tasks-list-api'
import type { PublishedTaskDetail, PublishedTaskItem } from '@/domain/models/task'
import { readReportSnapshot, readReportSummary, readTaskSnapshot } from '@/domain/models/task'
import { formatDateTime, getTaskTypeLabel } from '@/features/tasks/constants'
import { TaskSnapshotDialog } from '@/features/tasks/components/task-snapshot-dialog'
import { ReportSnapshotDialog } from '@/features/tasks/components/report-snapshot-dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
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
import { ApiError } from '@/infrastructure/api/api-error'
import {
  archivePublishedTask,
  createPublishedTaskVersion,
  executePublishedTask,
  renamePublishedTask,
} from '@/infrastructure/api/tasks-published-actions-api'

const STATUS_META: Record<string, { label: string; variant: 'success' | 'neutral' }> = {
  published: { label: '已发布', variant: 'success' },
  archived: { label: '已归档', variant: 'neutral' },
}

/** 版本链展开行（§3.7 五节键值行） */
function PublishedExpandRow({
  detail,
  onOpenSnapshot,
  onOpenReport,
}: {
  detail: PublishedTaskDetail
  onOpenSnapshot: () => void
  onOpenReport: () => void
}) {
  const [versionsOpen, setVersionsOpen] = useState(true)
  const [legacy] = useState(!detail.has_task_snapshot)
  const reportSummary = readReportSummary(readReportSnapshot(detail.report_snapshot))

  return (
    <div className='bg-muted/20 px-4 py-3'>
      <div className='grid gap-3 sm:grid-cols-2'>
        {/* ① 版本历史 */}
        <section className='rounded-lg border p-3'>
          <button
            type='button'
            className='flex items-center gap-1 text-sm font-medium'
            onClick={() => setVersionsOpen((v) => !v)}
          >
            <ChevronDown
              aria-hidden='true'
              className={cn('size-4 transition-transform', !versionsOpen && '-rotate-90')}
            />
            版本历史（共 {detail.versions.length} 个版本）
          </button>
          {versionsOpen && (
            <div className='mt-2 flex flex-col gap-1.5'>
              {detail.versions.map((version) => (
                <div
                  key={version.id}
                  className='flex items-center gap-2 text-xs tabular-nums'
                >
                  <span className='font-mono font-medium'>v{version.version}</span>
                  <StatusBadge
                    label={STATUS_META[version.status]?.label ?? version.status}
                    variant={STATUS_META[version.status]?.variant ?? 'neutral'}
                  />
                  {version.is_current && (
                    <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                      当前
                    </Badge>
                  )}
                  <span className='text-muted-foreground'>
                    {formatDateTime(version.published_at)}
                  </span>
                  <span className='text-muted-foreground ml-auto'>
                    来源任务 #{version.source_task_id ?? '—'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ② Benchmark 标记 */}
        <section className='rounded-lg border p-3'>
          <p className='text-sm font-medium'>Benchmark 标记（发布时冻结）</p>
          {detail.benchmark ? (
            <div className='mt-2 flex flex-col gap-1 text-xs'>
              <span>测试集：{String(detail.snapshot_config.benchmarkSuite ?? '—')}</span>
              <span>被测类别：{String(detail.snapshot_config.benchmarkCategory ?? '—')}</span>
            </div>
          ) : (
            <p className='text-muted-foreground mt-2 text-xs'>该版本未参与 Benchmark 排行</p>
          )}
        </section>
      </div>

      {/* ③ 任务详情（发布时冻结） */}
      <section className='mt-3 rounded-lg border p-3'>
        <p className='text-sm font-medium'>任务详情（发布时冻结 · 不可变）</p>
        {legacy ? (
          <div className='mt-2 rounded-lg border border-warning/40 bg-warning/10 p-2.5 text-xs'>
            历史版本（发布时未冻结任务详情）：任务详情按来源任务当前数据展示，源用例被编辑/删除后可能失真；执行按引用轨还原（源用例需存在）。
          </div>
        ) : (
          <div className='mt-2 flex flex-wrap items-center gap-2 text-xs'>
            <span className='text-muted-foreground'>来源任务：</span>
            <span className='font-medium'>{detail.source_task_name ?? '—'}</span>
            <Badge variant='outline' className='rounded-md px-1.5'>
              {getTaskTypeLabel(detail.versions[0]?.type ?? null)}
            </Badge>
            <span className='text-muted-foreground'>
              用例 {detail.source_task_completed_cases ?? 0}/{detail.source_task_total_cases ?? 0}
            </span>
            <Button
              size='sm'
              variant='outline'
              className='ml-auto h-7'
              onClick={onOpenSnapshot}
            >
              查看冻结任务详情
            </Button>
          </div>
        )}
      </section>

      {/* ④ 冻结报告 */}
      <section className='mt-3 rounded-lg border p-3'>
        <p className='text-sm font-medium'>冻结报告（发布时快照 · 不可变）</p>
        {detail.has_report_snapshot ? (
          <div className='mt-2 flex flex-wrap items-center gap-2 text-xs'>
            <span className='font-medium'>
              {String(readReportSnapshot(detail.report_snapshot)?.name ?? '冻结报告')}
            </span>
            <span className='text-muted-foreground'>
              用例 {reportSummary.caseCount ?? '—'} · 通过率 {reportSummary.passRate ?? '—'}%
            </span>
            <Button
              size='sm'
              variant='outline'
              className='ml-auto h-7'
              onClick={onOpenReport}
            >
              查看冻结报告
            </Button>
          </div>
        ) : (
          <p className='text-muted-foreground mt-2 text-xs'>
            该版本无冻结报告（发布时源任务无已完成报告）
          </p>
        )}
      </section>

      {/* ⑤ 执行记录 */}
      <section className='mt-3 rounded-lg border p-3'>
        <p className='text-sm font-medium'>执行记录（按冻结快照执行生成的日常任务）</p>
        {detail.execution_history.length > 0 ? (
          <div className='mt-2 flex flex-col gap-1.5 text-xs'>
            {detail.execution_history.map((record) => (
              <div key={record.task_id} className='flex items-center gap-2'>
                <span className='font-medium'>{record.task_name}</span>
                <span className='font-mono'>v{record.version}</span>
                <StatusBadge
                  label={record.status === 'completed' ? '已完成' : record.status}
                  variant={record.status === 'completed' ? 'success' : 'neutral'}
                />
                <span className='text-muted-foreground'>
                  用例 {record.completed_cases}/{record.total_cases}
                </span>
                <span className='text-muted-foreground ml-auto'>
                  {formatDateTime(record.created_at)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className='text-muted-foreground mt-2 text-xs'>该版本暂无执行记录</p>
        )}
      </section>
    </div>
  )
}

/** 错误 → 可展示文案（复用 use-task-actions 同款收敛） */
function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.userMessage || error.message || fallback
  return fallback
}

/** 已发布任务单字段命名弹窗（§5.5 新版本 / 重命名共用：Dialog max-w-sm 单 Input） */
function PublishedTaskNameDialog({
  open,
  title,
  label,
  placeholder,
  hint,
  value,
  onChange,
  pending,
  confirmDisabled,
  confirmText,
  onClose,
  onConfirm,
}: {
  open: boolean
  title: string
  label: string
  placeholder?: string
  hint?: string
  value: string
  onChange: (value: string) => void
  pending?: boolean
  confirmDisabled?: boolean
  confirmText?: string
  onClose: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !pending) onClose()
      }}
    >
      <DialogContent className='sm:max-w-sm'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {hint && <DialogDescription>{hint}</DialogDescription>}
        </DialogHeader>
        <div className='flex flex-col gap-1.5'>
          <Label className='text-sm'>{label}</Label>
          <Input
            value={value}
            maxLength={255}
            placeholder={placeholder}
            autoFocus
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !pending && !confirmDisabled) onConfirm()
            }}
          />
        </div>
        <DialogFooter>
          <Button variant='outline' disabled={pending} onClick={onClose}>
            取消
          </Button>
          <Button disabled={pending || confirmDisabled} onClick={() => void onConfirm()}>
            {pending ? '提交中...' : (confirmText ?? '确定')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function PublishedTaskTable({
  tasks,
  loading,
  error,
  onRetry,
}: {
  tasks: PublishedTaskItem[]
  loading: boolean
  /** 列表请求失败（P1-3：错误态 + 重试，不再渲染空态） */
  error?: boolean
  onRetry?: () => void
}) {
  const { hasPermission } = usePermissions()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [snapshotOpen, setSnapshotOpen] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const [detail, setDetail] = useState<PublishedTaskDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  // 已发布任务行操作（INT-1287 接线：执行/新版本/重命名/归档发真实请求 + 确认弹窗）
  const [executeTask, setExecuteTask] = useState<PublishedTaskItem | null>(null)
  const [executing, setExecuting] = useState(false)
  const [versionTask, setVersionTask] = useState<PublishedTaskItem | null>(null)
  const [versionName, setVersionName] = useState('')
  const [creatingVersion, setCreatingVersion] = useState(false)
  const [renameTask, setRenameTask] = useState<PublishedTaskItem | null>(null)
  const [renameName, setRenameName] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [archiveTask, setArchiveTask] = useState<PublishedTaskItem | null>(null)
  const [archiving, setArchiving] = useState(false)

  /** 行操作任一进行中（对齐旧 Vue published.actionLoading 置灰动作钮） */
  const actionLoading = executing || creatingVersion || renaming || archiving

  // 展开版本链：取 GET /published-tasks/{id} 真实详情（版本历史/冻结快照/执行记录）
  useEffect(() => {
    if (expandedId == null) {
      setDetail(null)
      setDetailError(null)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    setDetailError(null)
    fetchPublishedTaskDetail(expandedId)
      .then((d) => {
        if (cancelled) return
        setDetail(d)
        setDetailLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setDetailError(err instanceof Error ? err.message : '已发布任务详情加载失败')
        setDetailLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [expandedId])

  /** 列表/详情前缀统一失效（动作后刷新当前筛选态列表与计数） */
  const invalidateTasks = () => {
    void queryClient.invalidateQueries({ queryKey: ['tasks'] })
  }

  /** §5.4 执行已发布任务：确认 → POST execute → toast + 跳转任务详情 + 刷新 */
  const handleExecuteConfirm = async () => {
    if (!executeTask) return
    setExecuting(true)
    try {
      const result = await executePublishedTask(executeTask.id)
      setExecuteTask(null)
      toast.success(`日常任务已创建（ID: ${result.task_id}），即将前往任务详情`)
      invalidateTasks()
      void navigate({ to: '/tasks/$tab', params: { tab: String(result.task_id) } })
    } catch (error) {
      toast.error(toErrorMessage(error, '创建日常任务失败'))
    } finally {
      setExecuting(false)
    }
  }

  /** §5.5 创建新版本：Dialog 单字段（留空沿用当前名）→ POST versions → toast + 刷新 */
  const handleCreateVersionConfirm = async () => {
    if (!versionTask) return
    setCreatingVersion(true)
    try {
      await createPublishedTaskVersion(versionTask.id, versionName)
      setVersionTask(null)
      setVersionName('')
      toast.success('新版本创建成功')
      invalidateTasks()
    } catch (error) {
      toast.error(toErrorMessage(error, '创建新版本失败'))
    } finally {
      setCreatingVersion(false)
    }
  }

  /** §5.5 重命名（作用于整个版本链）：PUT /published-tasks/{id} → toast + 刷新 */
  const handleRenameConfirm = async () => {
    if (!renameTask) return
    setRenaming(true)
    try {
      await renamePublishedTask(renameTask.id, renameName.trim())
      setRenameTask(null)
      toast.success('任务名称已更新')
      invalidateTasks()
    } catch (error) {
      toast.error(toErrorMessage(error, '重命名失败'))
    } finally {
      setRenaming(false)
    }
  }

  /** 归档已发布任务（对齐旧 Vue 文案）：确认 → POST archive → toast + 刷新 */
  const handleArchiveConfirm = async () => {
    if (!archiveTask) return
    setArchiving(true)
    try {
      await archivePublishedTask(archiveTask.id)
      setArchiveTask(null)
      toast.success('任务已归档')
      invalidateTasks()
    } catch (error) {
      toast.error(toErrorMessage(error, '归档失败'))
    } finally {
      setArchiving(false)
    }
  }

  if (loading) {
    return (
      <div className='rounded-xl border'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  // P1-3：请求失败渲染错误态 + 重试（不再误示为空态）
  if (error) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            <RefreshCw aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>已发布任务列表加载失败</EmptyTitle>
            <EmptyDescription>请检查网络或后端服务后重试</EmptyDescription>
            {onRetry && (
              <EmptyContent>
                <Button variant='outline' size='sm' onClick={onRetry}>
                  重试
                </Button>
              </EmptyContent>
            )}
          </EmptyHeader>
        </Empty>
      </div>
    )
  }

  if (tasks.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            <Package aria-hidden='true' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>暂无已发布任务</EmptyTitle>
            <EmptyDescription>
              从日常任务列表发布，沉淀可复用、可追踪的任务资产
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </div>
    )
  }

  return (
    <>
      <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
        <div className='overflow-x-auto'>
          <table className='w-full min-w-[900px] text-[13px]'>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='w-11 px-3 py-2' />
                <th className='px-3 py-2 text-left font-medium'>版本</th>
                <th className='px-3 py-2 text-left font-medium'>名称/说明</th>
                <th className='px-3 py-2 text-left font-medium'>状态</th>
                <th className='px-3 py-2 text-left font-medium'>类型</th>
                <th className='px-3 py-2 text-left font-medium'>Benchmark</th>
                <th className='px-3 py-2 text-left font-medium'>版本数</th>
                <th className='px-3 py-2 text-left font-medium'>发布人/发布时间</th>
                <th className='px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const meta = STATUS_META[task.status] ?? { label: task.status, variant: 'neutral' as const }
                const expanded = expandedId === task.id
                return (
                  <ExpandedRows
                    key={task.id}
                    task={task}
                    meta={meta}
                    expanded={expanded}
                    onToggle={() => setExpandedId(expanded ? null : task.id)}
                    detail={detail}
                    detailLoading={detailLoading}
                    detailError={detailError}
                    hasPermission={hasPermission}
                    actionLoading={actionLoading}
                    onExecute={() => setExecuteTask(task)}
                    onNewVersion={() => {
                      setVersionName('')
                      setVersionTask(task)
                    }}
                    onRename={() => {
                      setRenameName(task.name)
                      setRenameTask(task)
                    }}
                    onArchive={() => setArchiveTask(task)}
                    onOpenSnapshot={() => setSnapshotOpen(true)}
                    onOpenReport={() => setReportOpen(true)}
                  />
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {detail && (
        <>
          <TaskSnapshotDialog
            open={snapshotOpen}
            onOpenChange={setSnapshotOpen}
            snapshot={readTaskSnapshot(detail.snapshot_config)}
          />
          <ReportSnapshotDialog
            open={reportOpen}
            onOpenChange={setReportOpen}
            report={readReportSnapshot(detail.report_snapshot)}
          />
        </>
      )}

      {/* §5.4 执行确认（已发布）：按冻结快照创建日常任务 → 跳转任务详情 */}
      <ConfirmDialog
        open={executeTask != null}
        onOpenChange={(open) => !open && !executing && setExecuteTask(null)}
        title='执行此版本'
        desc={
          executeTask
            ? `将按版本 v${executeTask.version} 的快照创建新的日常任务「${executeTask.name}」，创建后前往任务详情页。是否继续？`
            : ''
        }
        confirmText='创建日常任务'
        isLoading={executing}
        handleConfirm={() => void handleExecuteConfirm()}
      />
      {/* §5.5 新版本：单字段命名弹窗（留空沿用当前版本名称） */}
      <PublishedTaskNameDialog
        open={versionTask != null}
        title='新版本'
        label='新版本名称'
        placeholder={versionTask?.name}
        hint='留空沿用当前版本名称'
        value={versionName}
        onChange={setVersionName}
        pending={creatingVersion}
        confirmDisabled={false}
        onClose={() => setVersionTask(null)}
        onConfirm={() => void handleCreateVersionConfirm()}
      />
      {/* §5.5 重命名：单字段命名弹窗（作用于整个版本链） */}
      <PublishedTaskNameDialog
        open={renameTask != null}
        title='重命名'
        label='新的任务名称'
        placeholder={renameTask?.name}
        hint='作用于整个版本链'
        value={renameName}
        onChange={setRenameName}
        pending={renaming}
        confirmDisabled={!renameName.trim()}
        onClose={() => setRenameTask(null)}
        onConfirm={() => void handleRenameConfirm()}
      />
      {/* 归档已发布任务（对齐旧 Vue 文案：归档后不可直接执行） */}
      <ConfirmDialog
        open={archiveTask != null}
        onOpenChange={(open) => !open && !archiving && setArchiveTask(null)}
        title='归档已发布任务'
        desc={
          archiveTask
            ? `确定归档「${archiveTask.name}」v${archiveTask.version} 吗？归档后不可直接执行。`
            : ''
        }
        confirmText='归档'
        destructive
        isLoading={archiving}
        handleConfirm={() => void handleArchiveConfirm()}
      />
    </>
  )
}

function ExpandedRows({
  task,
  meta,
  expanded,
  onToggle,
  detail,
  detailLoading,
  detailError,
  hasPermission,
  actionLoading,
  onExecute,
  onNewVersion,
  onRename,
  onArchive,
  onOpenSnapshot,
  onOpenReport,
}: {
  task: PublishedTaskItem
  meta: { label: string; variant: 'success' | 'neutral' }
  expanded: boolean
  onToggle: () => void
  detail: PublishedTaskDetail | null
  detailLoading: boolean
  detailError: string | null
  hasPermission: (permission: string) => boolean
  /** 任一动作提交中：动作钮置灰（对齐旧 Vue published.actionLoading） */
  actionLoading: boolean
  onExecute: () => void
  onNewVersion: () => void
  onRename: () => void
  onArchive: () => void
  onOpenSnapshot: () => void
  onOpenReport: () => void
}) {
  const archived = task.status === 'archived'
  const canExecute = hasPermission('published_task:execute')

  return (
    <>
      <tr
        className={cn(
          'hover:bg-muted/40 border-border/60 border-b transition-colors',
          expanded && 'bg-muted/40'
        )}
      >
        <td className='px-3 py-2'>
          <Button
            variant='ghost'
            size='icon-xs'
            aria-label={expanded ? '收起版本详情' : '展开版本详情'}
            onClick={onToggle}
          >
            <ChevronRight
              aria-hidden='true'
              className={cn('size-4 transition-transform', expanded && 'rotate-90')}
            />
          </Button>
        </td>
        <td className='px-3 py-2'>
          <div className='flex items-center gap-1.5'>
            <Badge className='rounded-md px-1.5'>v{task.version}</Badge>
            {task.is_current && (
              <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                当前
              </Badge>
            )}
          </div>
        </td>
        <td className='max-w-64 px-3 py-2'>
          <span className='block font-medium truncate'>{task.name}</span>
          <span className='text-muted-foreground block truncate'>
            {task.description ?? ''}
          </span>
        </td>
        <td className='px-3 py-2'>
          <StatusBadge label={meta.label} variant={meta.variant} />
        </td>
        <td className='px-3 py-2'>
          <Badge variant='outline' className='rounded-md px-1.5'>
            {getTaskTypeLabel(task.type ?? null)}
          </Badge>
        </td>
        <td className='px-3 py-2'>
          {task.benchmark ? (
            <Tooltip>
              <TooltipTrigger
                render={
                  <span className='inline-flex items-center justify-center'>
                    <Trophy
                      aria-hidden='true'
                      className='text-chart-5 size-4.5 rounded-md bg-chart-5/10 p-0.5'
                    />
                  </span>
                }
              />
              <TooltipContent>参与 Benchmark 排行（实测轨数据源）</TooltipContent>
            </Tooltip>
          ) : (
            <span className='text-muted-foreground'>—</span>
          )}
        </td>
        <td className='px-3 py-2 text-muted-foreground'>
          {(task.version_count ?? 0) > 1 ? `共 ${task.version_count} 个版本` : '—'}
        </td>
        <td className='px-3 py-2'>
          <span className='block whitespace-nowrap'>{task.published_by ?? '—'}</span>
          <span className='text-muted-foreground block whitespace-nowrap text-xs tabular-nums'>
            {formatDateTime(task.published_at)}
          </span>
        </td>
        <td className='px-3 py-2'>
          <div className='flex items-center justify-end gap-1.5'>
            {canExecute && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      size='sm'
                      variant='default'
                      className='h-7'
                      disabled={archived || actionLoading}
                      onClick={onExecute}
                    >
                      执行
                    </Button>
                  }
                />
                <TooltipContent>
                  {archived ? '已归档任务禁止执行，请先创建新版本' : '按当前版本快照创建日常任务'}
                </TooltipContent>
              </Tooltip>
            )}
            <Button size='sm' variant='outline' className='h-7' onClick={onToggle}>
              版本
            </Button>
            {hasPermission('published_task:version') && (
              <Button
                size='sm'
                variant='outline'
                className='h-7'
                disabled={actionLoading}
                onClick={onNewVersion}
              >
                新版本
              </Button>
            )}
            {hasPermission('published_task:read') && (
              <Button
                size='sm'
                variant='ghost'
                className='h-7'
                disabled={actionLoading}
                onClick={onRename}
              >
                重命名
              </Button>
            )}
            {hasPermission('published_task:archive') && (
              <Button
                size='sm'
                variant='ghost'
                className='text-destructive hover:text-destructive h-7'
                disabled={actionLoading}
                onClick={onArchive}
              >
                归档
              </Button>
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className='border-border/60 border-b'>
          <td colSpan={9} className='p-0'>
            {detailLoading ? (
              <div className='bg-muted/20 px-4 py-3'>
                <Skeleton className='h-12 w-full' />
                <Skeleton className='mt-3 h-20 w-full' />
                <Skeleton className='mt-3 h-12 w-full' />
              </div>
            ) : detailError ? (
              <div className='bg-muted/20 px-4 py-3 text-sm text-destructive'>
                {detailError}
              </div>
            ) : detail ? (
              <>
                <PublishedExpandRow
                  detail={{
                    ...detail,
                    id: task.id,
                    versions: [
                      task,
                      ...detail.versions.filter((v) => v.id !== task.id),
                    ],
                  }}
                  onOpenSnapshot={onOpenSnapshot}
                  onOpenReport={onOpenReport}
                />
                <Separator className='mt-1' />
              </>
            ) : null}
          </td>
        </tr>
      )}
    </>
  )
}
