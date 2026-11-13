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
  StudioDocumentCreateInput,
  StudioDocumentListQuery,
  StudioDocumentUpdateInput,
  StudioExportFormat,
  StudioUploadInput,
} from '@/domain/models/report-studio'
import { isStudioExportActive } from '@/domain/models/report-studio'
import {
  createStudioDocument,
  createStudioExportJob,
  getStudioDocument,
  getStudioExportJob,
  importReportPackage,
  importStudioDocument,
  listStudioDocumentVersions,
  listStudioDocuments,
  restoreStudioDocumentVersion,
  updateStudioDocument,
} from '@/infrastructure/api/reportStudioApi'
import { fetchReportIdByTask } from '@/infrastructure/api/reports-api'

export const studioDocumentKeys = {
  all: ['report-studio'] as const,
  lists: () => [...studioDocumentKeys.all, 'documents'] as const,
  list: (query: StudioDocumentListQuery) =>
    [...studioDocumentKeys.lists(), query] as const,
  detail: (docId: string) => [...studioDocumentKeys.all, 'document', docId] as const,
  versions: (docId: string) =>
    [...studioDocumentKeys.all, 'versions', docId] as const,
  exportJob: (exportId: string) =>
    [...studioDocumentKeys.all, 'export', exportId] as const,
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

/**
 * 任务 → 该任务的报告 id（任务详情页文档区的取数入口）。
 *
 * 后端 `import_document` 只把上传时的 task_id 落成「该任务最新未删除报告」的 report_id
 * （report_service `_report_id_by_task`，无可见报告时 404、不建无主文档），所以任务详情按
 * 同一个口径先取报告 id，再按 `report_id` 列出关联文档；口径不一致会漏掉上传件。
 */
export function useTaskReportId(taskId: number) {
  return useQuery({
    queryKey: ['reports', 'by-task', taskId],
    queryFn: () => fetchReportIdByTask(taskId),
    enabled: Number.isFinite(taskId) && taskId > 0,
    staleTime: 30_000,
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

/**
 * 起草：绑定平台报告创建 Studio 草稿（对话式工作台「起草」入口）。
 * 成功后文档列表与详情一起失效，工作台右栏直接切到新草稿。
 */
export function useCreateStudioDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: StudioDocumentCreateInput) => createStudioDocument(input),
    onSuccess: (doc) => {
      void queryClient.invalidateQueries({ queryKey: studioDocumentKeys.all })
      void queryClient.invalidateQueries({
        queryKey: studioDocumentKeys.detail(doc.docId),
      })
    },
  })
}

// ---------------------------------------------------------------------------
// 导出作业（取数 → 起草 → 版本 → 导出 的最后一环）
// ---------------------------------------------------------------------------

/** 导出作业轮询间隔（ms）：pending/running 时拉取进度，终态停止 */
export const STUDIO_EXPORT_POLL_INTERVAL_MS = 1_000

/** 创建导出作业（固定文档版本 + 格式）；按钮防重复由 mutation isPending 把关 */
export function useCreateStudioExportJob() {
  return useMutation({
    mutationFn: (input: {
      docId: string
      version: number
      format: StudioExportFormat
    }) => createStudioExportJob(input.docId, input.version, input.format),
  })
}

/**
 * 导出作业进度（轮询）：pending/running 每秒刷新，done/failed 停止。
 * enabled 为 false（尚未创建作业）时不发请求。
 */
export function useStudioExportJob(exportId: string | null) {
  return useQuery({
    queryKey: studioDocumentKeys.exportJob(exportId ?? ''),
    queryFn: () => getStudioExportJob(exportId as string),
    enabled: Boolean(exportId),
    staleTime: 0,
    refetchInterval: (query) =>
      isStudioExportActive(query.state.data ?? null)
        ? STUDIO_EXPORT_POLL_INTERVAL_MS
        : false,
  })
}
