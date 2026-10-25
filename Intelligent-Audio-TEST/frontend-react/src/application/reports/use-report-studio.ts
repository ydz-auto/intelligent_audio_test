/**
 * Report Studio / 报告包 application 层（INT-1766 D8）。
 * - 文档列表 / 单文档 / 版本链：react-query 缓存，按 report_id + source_type 分键，
 *   平台报告文档与独立文档库不会互相污染；
 * - 上传独立报告（3b）与导入报告包（3a）成功后统一失效文档列表 + 报告列表/计数，
 *   满足卡面「新建后立即出现，无需手动刷新」「导入后列表与计数刷新」。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import type {
  StudioDocumentListQuery,
  StudioDocumentUpdateInput,
  StudioUploadInput,
} from '@/domain/models/report-studio'
import {
  getStudioDocument,
  importReportPackage,
  importStudioDocument,
  listStudioDocumentVersions,
  listStudioDocuments,
  restoreStudioDocumentVersion,
  updateStudioDocument,
} from '@/infrastructure/api/reportStudioApi'

export const studioDocumentKeys = {
  all: ['report-studio'] as const,
  lists: () => [...studioDocumentKeys.all, 'documents'] as const,
  list: (query: StudioDocumentListQuery) =>
    [...studioDocumentKeys.lists(), query] as const,
  detail: (docId: string) => [...studioDocumentKeys.all, 'document', docId] as const,
  versions: (docId: string) =>
    [...studioDocumentKeys.all, 'versions', docId] as const,
}

export function useStudioDocuments(
  query: StudioDocumentListQuery,
  options: { enabled?: boolean } = {}
) {
  return useQuery({
    queryKey: studioDocumentKeys.list(query),
    queryFn: () => listStudioDocuments(query),
    enabled: options.enabled ?? true,
    staleTime: 15_000,
  })
}

export function useStudioDocument(docId: string | null) {
  return useQuery({
    queryKey: studioDocumentKeys.detail(docId ?? ''),
    queryFn: () => getStudioDocument(docId as string),
    enabled: Boolean(docId),
    staleTime: 0,
  })
}

export function useStudioDocumentVersions(docId: string | null) {
  return useQuery({
    queryKey: studioDocumentKeys.versions(docId ?? ''),
    queryFn: () => listStudioDocumentVersions(docId as string),
    enabled: Boolean(docId),
    staleTime: 10_000,
  })
}

/** 文档相关缓存统一失效（上传/编辑后列表与详情都刷新） */
function useInvalidateStudio() {
  const queryClient = useQueryClient()
  return useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: studioDocumentKeys.all })
  }, [queryClient])
}

/** 3b：上传独立报告（md / html / pptx） */
export function useImportStudioDocument() {
  const invalidate = useInvalidateStudio()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: StudioUploadInput) => importStudioDocument(input),
    onSuccess: () => {
      invalidate()
      // 关联任务时任务详情/报告列表口径同步
      void queryClient.invalidateQueries({ queryKey: ['reports'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}

/** 编辑文档正文（乐观锁；409 由 ApiError 透出） */
export function useUpdateStudioDocument() {
  const invalidate = useInvalidateStudio()
  return useMutation({
    mutationFn: (input: StudioDocumentUpdateInput) => updateStudioDocument(input),
    onSuccess: () => {
      invalidate()
    },
  })
}

/**
 * 3c：切换/恢复历史版本。恢复后后端生成新版本，详情、版本链与列表一起失效，
 * 避免版本号与正文显示陈旧。
 */
export function useRestoreStudioDocumentVersion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: {
      docId: string
      version: number
      expectedVersion: number
    }) =>
      restoreStudioDocumentVersion(
        input.docId,
        input.version,
        input.expectedVersion
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: studioDocumentKeys.all })
    },
  })
}

/**
 * 3a/3c：导入报告包。成功后报告列表、计数、统计卡片与 Studio 文档全部失效，
 * 卡片/表格随之刷新（旧报告子表被原地替换，报告 id 不变）。
 */
export function useImportReportPackage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { file: File; targetReportId?: number }) =>
      importReportPackage(input.file, { targetReportId: input.targetReportId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reports'] })
      void queryClient.invalidateQueries({ queryKey: ['reports', 'counts'] })
      void queryClient.invalidateQueries({ queryKey: ['report-statistics'] })
      void queryClient.invalidateQueries({ queryKey: ['report-studio'] })
    },
  })
}
