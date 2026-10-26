/**
 * 日志写操作 mutation（application 层；17_配置运维.md §7.9-7.10 + §4.5，INT-693 接线）。
 * 标记 PUT /logs/mark、清除 POST /logs/clear、导出 POST /logs/export（Blob 下载）；
 * 成功后 invalidate 列表/统计缓存联动 + toast 中文文案（§10 文案源）。
 * INT-1945：标记按 updated 判定——文件日志游标行 updated=0，只给不可标记提示，不提示成功。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type {
  LogClearInput,
  LogExportInput,
  LogMarkInput,
  LogMarkResult,
  LogQuery,
} from '@/domain/models/log'
import { isFileLogId } from '@/domain/models/log'
import {
  clearLogs,
  exportLogs,
  LOG_LIST_QUERY_KEY,
  LOG_STATS_QUERY_KEY,
  markLogs,
} from '@/infrastructure/api/logsApi'
import { formatLogsExportFilename } from '@/application/logs/log-export-filename'

/** 导出 mutation 入参（input + 当前筛选 query，见页面 handleExport/handleExportSelected） */
export type LogExportMutationInput = {
  input: LogExportInput
  query?: LogQuery
}

/** 触发 Blob 下载（导出文件名 logs_{本地日期}.{format}，见 log-export-filename） */
function downloadBlob(blob: Blob, format: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = formatLogsExportFilename(new Date(), format)
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

/**
 * 标记结果提示（INT-1945：文件日志不可标记，不得提示成功）。
 * 后端对纯文件游标批次返回 200 + updated=0 + 专用文案，200 不等于成功。
 * 判定同时兼顾两种后端：带 data.updated 的（INT-1903 起）用实数；未返 data 的旧包
 * 按请求行里的历史库行数推定——文件日志由 id ≥ LOG_FILE_CURSOR_FLOOR 判定（同一契约）。
 */
export const LOG_MARK_FILE_ONLY_HINT = '所选为文件日志，不支持标记'

/** 实际落库条数：后端 updated 优先，缺失时按请求里的历史库行数推定 */
export function resolveMarkedCount(
  result: LogMarkResult,
  logIds: Array<string | number>
): number {
  if (result.updated !== null) return result.updated
  return logIds.filter((id) => !isFileLogId(id)).length
}

export function logMarkResultToast(
  logIds: Array<string | number>,
  updated: number | null
): { level: 'warning' | 'success' | 'error'; message: string } {
  const fileCount = logIds.filter((id) => isFileLogId(id)).length
  const marked = resolveMarkedCount({ updated }, logIds)
  if (marked <= 0) {
    return fileCount > 0
      ? { level: 'warning', message: LOG_MARK_FILE_ONLY_HINT }
      : { level: 'error', message: '未标记任何日志，请刷新后重试' }
  }
  if (fileCount > 0) {
    return {
      level: 'warning',
      message: `已标记 ${marked} 条；${fileCount} 条为文件日志，不支持标记`,
    }
  }
  return { level: 'success', message: '日志已标记' }
}

export function useLogMutations() {
  const queryClient = useQueryClient()

  const invalidateLogs = () => {
    void queryClient.invalidateQueries({ queryKey: LOG_LIST_QUERY_KEY })
    void queryClient.invalidateQueries({ queryKey: LOG_STATS_QUERY_KEY })
  }

  const mark = useMutation({
    mutationFn: (input: LogMarkInput) => markLogs(input),
    // INT-1947：mark:'' 是清除（同色二次点击 / 批量「清除标记」），文案不能报「已标记」
    // INT-1945：文件日志游标行只读，后端 200 不等于成功——按实际落库条数分档提示，
    // 未落库（updated=0）不刷新列表
    onSuccess: (data, variables) => {
      if (!variables.mark) {
        toast.success('已清除标记')
        invalidateLogs()
        return
      }
      const hint = logMarkResultToast(variables.logIds, data.updated)
      if (hint.level === 'success') toast.success(hint.message)
      else if (hint.level === 'warning') toast.warning(hint.message)
      else toast.error(hint.message)
      // 未落库（updated=0）不刷新列表：没有可显示的变化，避免无谓重取
      if (resolveMarkedCount(data, variables.logIds) > 0) invalidateLogs()
    },
    onError: (_error, variables) =>
      toast.error(variables.mark ? '标记失败，请稍后重试' : '清除标记失败，请稍后重试'),
  })

  const clear = useMutation({
    mutationFn: (input: LogClearInput) => clearLogs(input),
    onSuccess: (data) => {
      toast.success(`已清除 ${data.deletedCount} 条日志`)
      invalidateLogs()
    },
    onError: () => toast.error('清除失败，请稍后重试'),
  })

  const exportLogsMutation = useMutation({
    mutationFn: ({ input, query }: LogExportMutationInput) => exportLogs(input, query),
    onSuccess: ({ blob, format }) => {
      downloadBlob(blob, format)
      toast.success('日志已导出')
    },
    onError: () => toast.error('导出失败，请稍后重试'),
  })

  return { mark, clear, exportLogs: exportLogsMutation }
}
