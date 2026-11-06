/**
 * 挑选合并容器行操作菜单（18_挑选合并交互重设计.md §2.2/§7.5，INT-1277 接线）。
 * 行操作（查看详情/查看报告/生成报告（手动）/发布/收藏/重命名/删除）接真实接口：
 * - 查看详情 → 任务详情页（既有入口）
 * - 查看报告 → 跳 /report/:reportId（容器 reports 摘要；无报告禁用）
 * - 生成报告（手动）→ 报告域 generateTaskReport + SSE 等待后跳报告页（对齐日常任务重新生成流程）
 * - 发布 → PublishTaskDialog（任务域既有入口）
 * - 收藏 → POST/DELETE /tasks/{id}/favorite（INT-1277）
 * - 重命名 → PUT /tasks/{id}（INT-1277）
 * - 删除 → DELETE /tasks/{id} 软删→回收站（ConfirmDialog 确认后发请求）
 * 成功统一失效 ['tasks'] 前缀（含容器列表 query）→ 列表刷新。
 */
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTaskActions } from '@/application/tasks/use-task-actions'
import { waitForReportGenerated } from '@/application/reports/use-report-compare'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/components/confirm-dialog'
import type { CherryPickContainer } from '@/domain/models/cherryPick'
import { generateTaskReport, regenerateReport } from '@/infrastructure/api/reports-api'
import { ContainerRenameDialog } from '@/features/tasks/cherry-pick/components/container-rename-dialog'
import { PublishTaskDialog } from '@/features/tasks/components/publish-task-dialog'

export function ContainerRowActions({
  container,
  onQuickView,
}: {
  container: CherryPickContainer
  onQuickView: (container: CherryPickContainer) => void
}) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const actions = useTaskActions()

  /** 删除确认（INT-1277：确认后才发 DELETE /tasks/{id}，取消不发请求） */
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deletePending, setDeletePending] = useState(false)
  /** 重命名弹窗（PUT /tasks/{id}） */
  const [renameOpen, setRenameOpen] = useState(false)
  /** 发布弹窗（任务域既有入口） */
  const [publishOpen, setPublishOpen] = useState(false)
  /** 重新生成报告覆盖确认（容器已有报告 → 确认后 regenerate → 跳报告页） */
  const [regenConfirm, setRegenConfirm] = useState<{
    container: CherryPickContainer
    reportId: number
  } | null>(null)
  const [regenPending, setRegenPending] = useState(false)

  const reportId = container.reports?.reports[0]?.id ?? undefined

  const mutating =
    [actions.remove, actions.favorite, actions.unfavorite, actions.rename].some(
      (m) => m.isPending
    ) || deletePending || regenPending

  /** 查看报告：跳 /report/:reportId（无报告禁用并标注原因） */
  const goReport = () => {
    if (reportId == null) return
    void navigate({ to: '/report/$reportId', params: { reportId: String(reportId) } })
  }

  /**
   * 生成报告（手动）（对齐日常任务「重新生成报告」INT-967 流程）：
   * 先订阅 report_generated、等 SSE open 再 POST（防 <1s 快速失败竞态）；
   * 任务已有报告（status='exists'）→ 弹覆盖确认；无旧报告 → 等 SSE 回传后跳报告页。
   */
  const handleGenerateReport = async (target: CherryPickContainer) => {
    const controller = new AbortController()
    let sseOpened: (() => void) | undefined
    const sseReady = new Promise<void>((resolve) => {
      sseOpened = resolve
    })
    const waitPromise = waitForReportGenerated(
      { taskId: target.id },
      { signal: controller.signal, onOpen: () => sseOpened?.() }
    )
    // 交接前先挂 no-op catch，避免取消/超时成为 unhandled rejection
    void waitPromise.catch(() => undefined)
    try {
      // 等 SSE 连接建立（≤2s 兜底）再提交，杜绝 <1s 快速失败事件早于订阅到达的竞态
      await Promise.race([sseReady, new Promise((r) => setTimeout(r, 2_000))])
      const result = await generateTaskReport({
        task_id: target.id,
        name: `${target.name || `任务${target.id}`} - 测试报告`,
        description: target.description ?? undefined,
      })
      if (result.status === 'exists' && result.id !== undefined) {
        // 任务已有报告 → 取消本次预订阅（未发起生成），弹「将删除当前报告并重新生成」确认
        controller.abort()
        setRegenConfirm({ container: target, reportId: result.id })
        return
      }
      // 无旧报告 → 异步生成中：loading toast + 等 SSE report_generated 回传真实 report_id 后跳报告页
      const loadingId = toast.loading('正在生成报告，请稍候...')
      try {
        const newReportId = await waitPromise
        toast.dismiss(loadingId)
        toast.success('报告生成成功')
        void navigate({ to: '/report/$reportId', params: { reportId: String(newReportId) } })
      } catch (waitError) {
        toast.dismiss(loadingId)
        toast.error(waitError instanceof Error ? waitError.message : '报告生成失败，请稍后重试')
      }
    } catch (error) {
      controller.abort()
      toast.error(error instanceof Error ? error.message : '报告生成失败，请稍后重试')
    }
  }

  /** 重新生成报告覆盖确认（确认后 POST /reports/{id}/regenerate → 等 SSE → 跳报告页） */
  const handleRegenConfirm = async () => {
    if (!regenConfirm) return
    setRegenPending(true)
    const { container: target, reportId: existingReportId } = regenConfirm
    const controller = new AbortController()
    let sseOpened: (() => void) | undefined
    const sseReady = new Promise<void>((resolve) => {
      sseOpened = resolve
    })
    const waitPromise = waitForReportGenerated(
      { taskId: target.id },
      { signal: controller.signal, onOpen: () => sseOpened?.() }
    )
    void waitPromise.catch(() => undefined)
    try {
      await Promise.race([sseReady, new Promise((r) => setTimeout(r, 2_000))])
      await regenerateReport(existingReportId)
      const loadingId = toast.loading('正在重新生成报告，请稍候...')
      try {
        const newReportId = await waitPromise
        toast.dismiss(loadingId)
        toast.success('报告重新生成成功')
        setRegenConfirm(null)
        void navigate({ to: '/report/$reportId', params: { reportId: String(newReportId) } })
      } catch (waitError) {
        toast.dismiss(loadingId)
        toast.error(waitError instanceof Error ? waitError.message : '报告重新生成失败，请稍后重试')
      }
    } catch (error) {
      controller.abort()
      toast.error(error instanceof Error ? error.message : '报告重新生成失败，请稍后重试')
    } finally {
      setRegenPending(false)
    }
  }

  /** 删除确认后发请求（INT-1277：DELETE /tasks/{id} 软删→回收站，取消不发请求） */
  const handleDelete = async () => {
    setDeletePending(true)
    try {
      await actions.remove.mutateAsync(container.id)
      setConfirmDelete(false)
    } catch {
      // mutation onError 已 toast，弹窗保留可重试
    } finally {
      setDeletePending(false)
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant='ghost'
              size='icon-sm'
              aria-label='挑选合并任务操作'
              disabled={mutating}
            />
          }
        >
          <span className='text-lg leading-none'>⋯</span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align='end' className='w-44'>
          <DropdownMenuGroup>
            <DropdownMenuLabel className='truncate'>{container.name}</DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => onQuickView(container)}>查看详情</DropdownMenuItem>
          {hasPermission('report:read') && (
            <DropdownMenuItem disabled={reportId == null} onSelect={goReport}>
              查看报告
            </DropdownMenuItem>
          )}
          {hasPermission('report:create') && (
            <DropdownMenuItem onSelect={() => void handleGenerateReport(container)}>
              生成报告（手动）
            </DropdownMenuItem>
          )}
          {hasPermission('task:publish') && (
            <DropdownMenuItem onSelect={() => setPublishOpen(true)}>发布</DropdownMenuItem>
          )}
          {hasPermission('task:read') && (
            <DropdownMenuItem
              onSelect={() =>
                container.isFavorite
                  ? actions.unfavorite.mutate(container.id)
                  : actions.favorite.mutate(container.id)
              }
            >
              {container.isFavorite ? '取消收藏' : '收藏'}
            </DropdownMenuItem>
          )}
          {hasPermission('task:update') && (
            <DropdownMenuItem onSelect={() => setRenameOpen(true)}>重命名</DropdownMenuItem>
          )}
          {hasPermission('task:delete') && (
            <DropdownMenuItem
              data-variant='destructive'
              onSelect={() => setConfirmDelete(true)}
            >
              删除
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* 删除确认（INT-1277：软删→回收站；取消不发请求） */}
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(false)}
        title='删除任务'
        desc='将把 1 个任务移入回收站，可在回收站恢复。'
        confirmText='删除'
        destructive
        isLoading={deletePending}
        handleConfirm={() => void handleDelete()}
      />

      {/* 重命名（PUT /tasks/{id}） */}
      <ContainerRenameDialog
        open={renameOpen}
        onOpenChange={setRenameOpen}
        container={container}
        onConfirm={(patch) => actions.rename.mutate({ taskId: container.id, patch })}
      />

      {/* 发布（任务域既有入口） */}
      <PublishTaskDialog
        key={container.id}
        open={publishOpen}
        onOpenChange={setPublishOpen}
        task={{ id: container.id, name: container.name }}
      />

      {/* 重新生成报告覆盖确认（对齐日常任务 INT-967 口径） */}
      <ConfirmDialog
        open={regenConfirm != null}
        onOpenChange={(open) => {
          if (!open && regenConfirm && !regenPending) {
            const oldReportId = regenConfirm.reportId
            setRegenConfirm(null)
            void navigate({ to: '/report/$reportId', params: { reportId: String(oldReportId) } })
          }
        }}
        title='重新生成报告'
        desc='将删除当前报告并重新生成，旧报告数据将被覆盖。是否继续？'
        confirmText='重新生成'
        cancelBtnText='查看旧报告'
        isLoading={regenPending}
        handleConfirm={() => void handleRegenConfirm()}
      />
    </>
  )
}
