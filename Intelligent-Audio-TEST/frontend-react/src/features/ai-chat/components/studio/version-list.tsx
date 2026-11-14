/**
 * 历史版本列表（interfaces 层 ai-chat/studio；INT-2473，设计文档 §15.5）。
 * 展示不可变版本链（版本号 / 快照原因 / 创建时间 / 当前版本标记），
 * 可把任一历史版本恢复为新版本（后端不覆盖历史；乐观锁 409 回显）。
 * 只读展示：后端版本列表不返回正文，历史正文只能通过恢复读取。
 */
import { History, Loader2, RotateCcw } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Spinner } from '@/components/ui/spinner'
import {
  STUDIO_SNAPSHOT_REASON_LABEL,
  type StudioDocumentVersion,
} from '@/domain/models/report-studio'
import {
  useRestoreStudioDocumentVersion,
  useStudioDocumentVersions,
} from '@/application/reports/use-report-studio'
import { resolveApiErrorMessage } from '@/features/ai-chat/lib/api-error-message'

type VersionListProps = {
  docId: string
  currentVersion: number
  canRestore: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

function formatTime(value: string | null): string {
  if (!value) return ''
  // 后端时间为 naive UTC 字符串（agent/report 同口径），按 UTC 解析后本地展示
  const iso = /Z$|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function reasonLabel(reason: string): string {
  return STUDIO_SNAPSHOT_REASON_LABEL[reason] ?? (reason || '历史版本')
}

export function VersionList({
  docId,
  currentVersion,
  canRestore,
  open,
  onOpenChange,
}: VersionListProps) {
  const versionsQuery = useStudioDocumentVersions(open ? docId : null)
  const restore = useRestoreStudioDocumentVersion()
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null)

  const versions: StudioDocumentVersion[] = [...(versionsQuery.data ?? [])].sort(
    (a, b) => b.version - a.version
  )

  const handleRestore = async (version: number) => {
    setRestoreError(null)
    setRestoringVersion(version)
    try {
      await restore.mutateAsync({
        docId,
        version,
        expectedVersion: currentVersion,
      })
      onOpenChange(false)
    } catch (error) {
      // 同 document-panel 保存：message 为空的 ApiError 不得让失败提示整块消失（P2-1）
      setRestoreError(
        resolveApiErrorMessage(
          error,
          '恢复失败（版本可能已变化，请重新打开版本列表）'
        )
      )
    } finally {
      setRestoringVersion(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md' data-testid='studio-version-list'>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2 text-base'>
            <History className='size-4' />
            历史版本
          </DialogTitle>
          <DialogDescription>
            每次编辑自动落不可变快照；恢复历史版本会生成一个新版本，不覆盖现有内容。
          </DialogDescription>
        </DialogHeader>

        {versionsQuery.isLoading ? (
          <p className='text-muted-foreground flex items-center gap-2 py-6 text-sm'>
            <Spinner className='size-4' />
            正在加载版本…
          </p>
        ) : versionsQuery.isError ? (
          <div className='flex items-center justify-between gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive'>
            <span>版本列表加载失败</span>
            <Button
              onClick={() => void versionsQuery.refetch()}
              size='sm'
              type='button'
              variant='outline'
            >
              重试
            </Button>
          </div>
        ) : versions.length === 0 ? (
          <p className='text-muted-foreground py-6 text-center text-sm'>
            暂无历史版本
          </p>
        ) : (
          <ul className='max-h-[min(60vh,26rem)] space-y-1.5 overflow-y-auto pr-1'>
            {versions.map((version) => {
              const isCurrent = version.version === currentVersion
              return (
                <li
                  className='flex items-center justify-between gap-3 rounded-md border px-3 py-2'
                  data-version={version.version}
                  key={version.id || version.version}
                >
                  <div className='min-w-0'>
                    <div className='flex items-center gap-2'>
                      <span className='text-sm font-medium tabular-nums'>
                        v{version.version}
                      </span>
                      {isCurrent && <Badge variant='secondary'>当前版本</Badge>}
                      <span className='text-muted-foreground truncate text-xs'>
                        {reasonLabel(version.snapshotReason)}
                      </span>
                    </div>
                    <div className='text-muted-foreground mt-0.5 text-[11px] tabular-nums'>
                      {formatTime(version.createdAt) || '创建时间未知'}
                    </div>
                  </div>
                  {!isCurrent && (
                    <Button
                      aria-label={`恢复版本 v${version.version}`}
                      className='h-7 shrink-0 gap-1 px-2 text-xs'
                      disabled={!canRestore || restoringVersion !== null}
                      onClick={() => void handleRestore(version.version)}
                      size='sm'
                      type='button'
                      variant='outline'
                    >
                      {restoringVersion === version.version ? (
                        <Loader2 className='size-3 animate-spin' />
                      ) : (
                        <RotateCcw className='size-3' />
                      )}
                      恢复
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}

        {!canRestore && (
          <p className='text-muted-foreground text-xs'>
            缺少「版本恢复」权限（report:studio:undo），仅可查看版本记录。
          </p>
        )}

        {restoreError && (
          <p className='rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive'>
            {restoreError}
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
