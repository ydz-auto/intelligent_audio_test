/**
 * 日志写操作 mutation（application 层；17_配置运维.md §7.9-7.10 + §4.5，INT-693 接线）。
 * 标记 PUT /logs/mark、清除 POST /logs/clear、导出 POST /logs/export（Blob 下载）；
 * 成功后 invalidate 列表/统计缓存联动 + toast 中文文案（§10 文案源）。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { LogClearInput, LogExportInput, LogMarkInput, LogQuery } from '@/domain/models/log'
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

export function useLogMutations() {
  const queryClient = useQueryClient()

  const invalidateLogs = () => {
    void queryClient.invalidateQueries({ queryKey: LOG_LIST_QUERY_KEY })
    void queryClient.invalidateQueries({ queryKey: LOG_STATS_QUERY_KEY })
  }

  const mark = useMutation({
    mutationFn: (input: LogMarkInput) => markLogs(input),
    // mark:'' 是清除（V9.7.10 同色二次点击 / 批量「清除标记」），文案不能报「已标记」
    onSuccess: (_data, variables) => {
      toast.success(variables.mark ? '日志已标记' : '已清除标记')
      invalidateLogs()
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
