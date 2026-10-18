/**
 * 日志维护/归档 query/mutations（application 层，INT-729 接线后）：
 * 归档状态 GET（log:read）、立即归档 POST + 删除 DELETE + 立即清理 POST
 * （log:manage）；toast「归档完成」「归档已删除」+ invalidate 联动。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  ARCHIVE_LIST_QUERY_KEY,
  ARCHIVE_STATUS_QUERY_KEY,
  archiveLogsNow,
  clearLogs,
  deleteArchive,
  downloadArchive,
  getArchiveItems,
  getArchiveStatus,
} from '@/infrastructure/api/logsApi'

export function useArchiveStatusQuery() {
  return useQuery({
    queryKey: [...ARCHIVE_STATUS_QUERY_KEY],
    queryFn: getArchiveStatus,
    staleTime: 30_000,
  })
}

export function useArchiveItemsQuery() {
  return useQuery({
    queryKey: [...ARCHIVE_LIST_QUERY_KEY],
    queryFn: getArchiveItems,
    staleTime: 30_000,
  })
}

export function useLogArchiveMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ARCHIVE_STATUS_QUERY_KEY })
    void queryClient.invalidateQueries({ queryKey: ARCHIVE_LIST_QUERY_KEY })
  }

  const archiveNow = useMutation({
    mutationFn: () => archiveLogsNow(false),
    onSuccess: () => {
      toast.success('归档完成')
      invalidate()
    },
    onError: () => toast.error('归档失败，请稍后重试'),
  })

  const deleteArchiveMutation = useMutation({
    mutationFn: (filename: string) => deleteArchive(filename),
    onSuccess: () => {
      toast.success('归档已删除')
      invalidate()
    },
    onError: () => toast.error('删除失败，请稍后重试'),
  })

  const clearLogsMutation = useMutation({
    mutationFn: (beforeDatetime?: string) => clearLogs(beforeDatetime),
    onSuccess: () => {
      toast.success('日志已清理')
      invalidate()
    },
    onError: () => toast.error('清理失败，请稍后重试'),
  })

  const downloadArchiveMutation = useMutation({
    mutationFn: (filename: string) => downloadArchive(filename),
    onSuccess: (blob, filename) => {
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      anchor.click()
      URL.revokeObjectURL(url)
    },
    onError: () => toast.error('下载失败，请稍后重试'),
  })

  return {
    archiveNow,
    deleteArchive: deleteArchiveMutation,
    clearLogs: clearLogsMutation,
    downloadArchive: downloadArchiveMutation,
  }
}
