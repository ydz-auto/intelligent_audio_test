/**
 * 日志维护/归档 query/mutations（application 层，INT-347 §4.7）：
 * 归档状态/列表 GET（log:read）、立即归档 POST + 删除 DELETE（log:manage）；
 * toast「归档完成」「归档已删除」+ invalidate 联动。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  ARCHIVE_LIST_QUERY_KEY,
  ARCHIVE_STATUS_QUERY_KEY,
  archiveLogsNow,
  deleteMockArchive,
  getArchiveItems,
  getArchiveStatus,
} from '@/infrastructure/api/archive-api'

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
    mutationFn: archiveLogsNow,
    onSuccess: () => {
      toast.success('归档完成')
      invalidate()
    },
    onError: () => toast.error('归档失败，请稍后重试'),
  })

  const deleteArchive = useMutation({
    mutationFn: deleteMockArchive,
    onSuccess: () => {
      toast.success('归档已删除')
      invalidate()
    },
    onError: () => toast.error('删除失败，请稍后重试'),
  })

  return { archiveNow, deleteArchive }
}
