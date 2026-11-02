/**
 * 参数变更历史 / 回滚对话框（Presentation；设备参数弹窗与 API 参数页签共用）。
 *
 * - 读：`GET /algorithm/param-history?scope=&scope_id=&algorithm_type=`；
 * - 写：`POST /algorithm/param-history/{id}/restore`（把覆盖行整份恢复到该版本）；
 * - 回滚成功后由调用方失效自己的读侧查询（onRestored）。
 *
 * 降级：缺 `algorithm:read` → 列表报错提示；缺 `algorithm:param_manage` → 回滚禁用。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/infrastructure/api/api-error'
import {
  fetchParamHistory,
  restoreParamHistory,
} from '@/infrastructure/api/param-history-api'
import {
  PARAM_HISTORY_ACTION_LABEL,
  type ParamHistoryRestoreResult,
  type ParamHistoryScope,
  type ParamHistoryVersion,
} from '@/domain/models/paramHistory'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const HISTORY_QUERY_ROOT = ['algorithm', 'param-history'] as const

function historyQueryKey(
  scope: ParamHistoryScope,
  scopeId: number,
  algorithmType: string
) {
  return [...HISTORY_QUERY_ROOT, scope, scopeId, algorithmType] as const
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.userMessage
  return error instanceof Error && error.message ? error.message : '操作失败，请重试'
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

/**
 * 回滚回执 → toast 文案（INT-2341）。
 *
 * 后端两种口径都要认：
 * - API 作用域整份回滚只回 `paramsRestored / mappingsRestored`（无增删改拆分）——
 *   只读 created/updated 会误报「无变化」；
 * - 设备作用域回 `paramsCreated/Updated/Deleted + mappings*`。
 */
export function restoreSummary(result: ParamHistoryRestoreResult): string {
  // API 作用域：只有恢复总数（快照整份写回），0 也要显示——
  // 快照为空时「恢复参数 0」比「无变化」更准确；有值时即本卡要展示的实际恢复条数
  const restored: string[] = []
  if (typeof result.paramsRestored === 'number') {
    restored.push(`恢复参数 ${result.paramsRestored}`)
  }
  if (typeof result.mappingsRestored === 'number') {
    restored.push(`恢复映射 ${result.mappingsRestored}`)
  }
  if (restored.length > 0) return restored.join('，')

  // 设备作用域：按增删改计数，只列真正发生的动作
  const parts = [
    ['新增参数', result.paramsCreated],
    ['更新参数', result.paramsUpdated],
    ['删除参数', result.paramsDeleted],
    ['新增映射', result.mappingsCreated],
    ['更新映射', result.mappingsUpdated],
    ['删除映射', result.mappingsDeleted],
  ]
    .filter(([, value]) => typeof value === 'number' && value > 0)
    .map(([label, value]) => `${label} ${value}`)
  return parts.length > 0 ? parts.join('，') : '无变化'
}

export interface ParamHistoryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  scope: ParamHistoryScope
  scopeId: number | null
  algorithmType: string
  /** `algorithm:param_manage` */
  canRestore: boolean
  /** 回滚成功（调用方失效参数 / 映射读侧查询） */
  onRestored?: () => void
}

export function ParamHistoryDialog({
  open,
  onOpenChange,
  scope,
  scopeId,
  algorithmType,
  canRestore,
  onRestored,
}: ParamHistoryDialogProps) {
  const queryClient = useQueryClient()
  const [confirmTarget, setConfirmTarget] = useState<ParamHistoryVersion | null>(null)

  const enabled = open && scopeId != null && Boolean(algorithmType)
  const query = useQuery({
    queryKey: historyQueryKey(scope, scopeId ?? 0, algorithmType),
    queryFn: () => fetchParamHistory(scope, scopeId as number, algorithmType),
    enabled,
    staleTime: 0,
    retry: false,
  })

  const restoreMutation = useMutation({
    mutationFn: (version: ParamHistoryVersion) => restoreParamHistory(version.id),
    onSuccess: (result) => {
      toast.success(`已回滚到所选版本（${restoreSummary(result)}）`)
      setConfirmTarget(null)
      void queryClient.invalidateQueries({
        queryKey: historyQueryKey(scope, scopeId ?? 0, algorithmType),
      })
      onRestored?.()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const versions = query.data ?? []

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className='max-h-[85vh] overflow-y-auto sm:max-w-3xl'>
          <DialogHeader>
            <DialogTitle className='flex items-center gap-2'>
              <History aria-hidden='true' className='size-4' />
              参数变更历史
            </DialogTitle>
            <DialogDescription>
              每个版本只记录该作用域的覆盖行（算法级与策略层不在此列）。回滚会把覆盖行整份恢复成所选版本。
            </DialogDescription>
          </DialogHeader>

          {!enabled ? (
            <p className='text-muted-foreground py-8 text-center text-xs'>
              请先选择算法并完成一次保存。
            </p>
          ) : query.isLoading ? (
            <div className='text-muted-foreground flex items-center justify-center gap-2 py-12 text-xs'>
              <Spinner className='size-4' />
              正在读取历史…
            </div>
          ) : query.isError ? (
            <p className='text-destructive py-8 text-center text-xs'>
              历史读取失败（可能需要 algorithm:read 权限）。
            </p>
          ) : versions.length === 0 ? (
            <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed py-8 text-center text-xs'>
              还没有变更历史；保存一次参数或映射后即可在这里查看与回滚。
            </p>
          ) : (
            <div className='border-border/60 overflow-x-auto rounded-lg border'>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className='w-20 text-xs'>版本</TableHead>
                    <TableHead className='text-xs'>时间</TableHead>
                    <TableHead className='w-20 text-xs'>动作</TableHead>
                    <TableHead className='w-20 text-xs'>参数</TableHead>
                    <TableHead className='w-20 text-xs'>映射</TableHead>
                    <TableHead className='w-28 text-xs'>操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {versions.map((version) => (
                    <TableRow key={version.id}>
                      <TableCell className='text-xs tabular-nums'>v{version.version}</TableCell>
                      <TableCell className='text-xs'>{formatTime(version.createdAt)}</TableCell>
                      <TableCell>
                        <Badge variant={version.action === 'restore' ? 'outline' : 'secondary'}>
                          {PARAM_HISTORY_ACTION_LABEL[version.action]}
                        </Badge>
                      </TableCell>
                      <TableCell className='text-xs tabular-nums'>{version.paramCount}</TableCell>
                      <TableCell className='text-xs tabular-nums'>{version.mappingCount}</TableCell>
                      <TableCell>
                        <Button
                          type='button'
                          variant='ghost'
                          size='sm'
                          className='h-7 gap-1 px-2 text-xs'
                          disabled={!canRestore || restoreMutation.isPending}
                          onClick={() => setConfirmTarget(version)}
                        >
                          <RotateCcw aria-hidden='true' className='size-3.5' />
                          回滚
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => onOpenChange(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={confirmTarget != null}
        onOpenChange={(next) => !next && setConfirmTarget(null)}
      >
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>回滚到 v{confirmTarget?.version}</DialogTitle>
            <DialogDescription>
              当前覆盖行会被整份替换为该版本的快照（{confirmTarget?.paramCount ?? 0} 个参数、
              {confirmTarget?.mappingCount ?? 0} 条映射）。策略绑定不受影响。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => setConfirmTarget(null)}>
              取消
            </Button>
            <Button
              type='button'
              disabled={restoreMutation.isPending}
              onClick={() => confirmTarget && restoreMutation.mutate(confirmTarget)}
            >
              {restoreMutation.isPending ? '回滚中…' : '确认回滚'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
