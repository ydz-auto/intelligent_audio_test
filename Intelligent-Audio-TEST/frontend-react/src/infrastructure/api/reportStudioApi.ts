/**
 * Report Studio API（infrastructure 层；INT-1766 D8 接线，后端 INT-1763 D5 / INT-1764 D6）。
 * 对照 api_gateway/routes/report_studio_bp.py 实测契约（前缀 /api/v1/report-studio）：
 *   GET  /documents                 文档列表（report_id / source_type / parent_doc_id / limit / offset）
 *   GET  /documents/{id}            单文档（含 markdown_content）
 *   POST /import                    文件型独立报告导入（multipart：file + title + task_id + format）
 *   PUT  /documents/{id}            编辑（expected_version 乐观锁，不一致 409）
 *   GET  /documents/{id}/versions   版本链
 *   POST /documents/{id}/restore    版本恢复（产生新版本，不覆盖）
 *   GET  /documents/{id}/source     上传件（html/pptx）鉴权下载：附件语义 + nosniff + 沙箱 CSP
 * 请求一律经 client.ts；页面层只见 camelCase Domain。
 * 已知后端缺口：报告包无预检端点（D6 只交付 import/export），3a 的预检由前端读包内
 * manifest.json 完成（features/reports/lib/report-package.ts）。
 */
import type {
  ReportPackageImportReceipt,
  StudioDocument,
  StudioDocumentCreateInput,
  StudioDocumentList,
  StudioDocumentListQuery,
  StudioDocumentUpdateInput,
  StudioDocumentVersion,
  StudioExportFormat,
  StudioExportJob,
  StudioUploadInput,
} from '@/domain/models/report-studio'
import { apiClient } from '@/infrastructure/api/client'
import {
  toReportPackageImportReceipt,
  toStudioDocument,
  toStudioDocumentList,
  toStudioDocumentVersion,
  toStudioExportJob,
  type ReportPackageImportReceiptDto,
  type StudioDocumentDto,
  type StudioDocumentListDto,
  type StudioExportJobDto,
  type StudioVersionDto,
  type StudioVersionListDto,
} from '@/infrastructure/dto/report-studio.dto'

/** 文档列表（source_type 由调用方显式给出，平台报告与独立文档库不混） */
export async function listStudioDocuments(
  query: StudioDocumentListQuery = {}
): Promise<StudioDocumentList> {
  const dto = await apiClient.get<StudioDocumentListDto>(
    '/report-studio/documents',
    {
      params: {
        report_id: query.reportId,
        source_type: query.sourceType,
        parent_doc_id: query.parentDocId,
        limit: query.limit,
        offset: query.offset,
      },
    }
  )
  return toStudioDocumentList(dto)
}

/** 单文档（含正文） */
export async function getStudioDocument(docId: string): Promise<StudioDocument> {
  const dto = await apiClient.get<StudioDocumentDto>(
    `/report-studio/documents/${encodeURIComponent(docId)}`
  )
  return toStudioDocument(dto)
}

/**
 * 起草文档（POST /documents）：绑定平台报告生成新草稿（current_version=1）。
 * 对话式工作台「起草」入口；AI 起草时带 agentSessionId，快照原因落 ai_edit。
 */
export async function createStudioDocument(
  input: StudioDocumentCreateInput
): Promise<StudioDocument> {
  const dto = await apiClient.post<StudioDocumentDto>('/report-studio/documents', {
    report_id: input.reportId,
    title: input.title,
    markdown_content: input.markdownContent,
    agent_session_id: input.agentSessionId ?? undefined,
  })
  return toStudioDocument(dto)
}

/** 文件型独立报告导入（3b）：md 进正文，html/pptx 落 OSS 走预览/下载 */
export async function importStudioDocument(
  input: StudioUploadInput
): Promise<StudioDocument> {
  const formData = new FormData()
  formData.append('file', input.file)
  formData.append('title', input.title)
  formData.append('format', input.format)
  if (input.taskId !== undefined) formData.append('task_id', String(input.taskId))
  const dto = await apiClient.post<StudioDocumentDto>(
    '/report-studio/import',
    formData
  )
  return toStudioDocument(dto)
}

/** 编辑正文（乐观锁） */
export async function updateStudioDocument(
  input: StudioDocumentUpdateInput
): Promise<StudioDocument> {
  const dto = await apiClient.put<StudioDocumentDto>(
    `/report-studio/documents/${encodeURIComponent(input.docId)}`,
    {
      expected_version: input.expectedVersion,
      markdown_content: input.markdownContent,
      chart_refs: input.chartRefs,
    }
  )
  return toStudioDocument(dto)
}

/** 版本链（snake_case → camelCase 只在 DTO 层） */
export async function listStudioDocumentVersions(
  docId: string
): Promise<StudioDocumentVersion[]> {
  const data = await apiClient.get<StudioVersionListDto | StudioVersionDto[]>(
    `/report-studio/documents/${encodeURIComponent(docId)}/versions`
  )
  const items = Array.isArray(data) ? data : (data?.items ?? [])
  return items.map(toStudioDocumentVersion)
}

/**
 * 恢复历史版本（乐观锁）：后端按该版本正文生成**新版本**（不覆盖 history），
 * 返回最新文档；`expected_version` 与 current_version 不一致时 409。
 */
export async function restoreStudioDocumentVersion(
  docId: string,
  version: number,
  expectedVersion: number
): Promise<StudioDocument> {
  const dto = await apiClient.post<StudioDocumentDto>(
    `/report-studio/documents/${encodeURIComponent(docId)}/restore`,
    { version, expected_version: expectedVersion }
  )
  return toStudioDocument(dto)
}

/**
 * 上传件（html/pptx）源文件：鉴权下载为 Blob，前端以沙箱 iframe 或下载使用。
 * 后端统一带 Content-Disposition: attachment + nosniff + 沙箱 CSP（设计 §6.2）。
 */
export async function fetchStudioSourceBlob(docId: string): Promise<Blob> {
  return apiClient.get<Blob>(
    `/report-studio/documents/${encodeURIComponent(docId)}/source`,
    { responseType: 'blob', unwrapResponse: false }
  )
}

/**
 * 创建导出作业（POST /documents/{id}/exports，固定文档版本 + 格式）。
 * 返回作业快照（pending 起步），进度由页面轮询 GET /exports/{id}。
 */
export async function createStudioExportJob(
  docId: string,
  version: number,
  format: StudioExportFormat
): Promise<StudioExportJob> {
  const dto = await apiClient.post<StudioExportJobDto>(
    `/report-studio/documents/${encodeURIComponent(docId)}/exports`,
    { version, format }
  )
  return toStudioExportJob(dto)
}

/** 导出作业快照（轮询状态 / 进度 / 失败原因） */
export async function getStudioExportJob(exportId: string): Promise<StudioExportJob> {
  const dto = await apiClient.get<StudioExportJobDto>(
    `/report-studio/exports/${encodeURIComponent(exportId)}`
  )
  return toStudioExportJob(dto)
}

/** 导出产物鉴权下载（二进制；文件名由页面按文档标题 + 版本生成） */
export async function downloadStudioExportBlob(
  exportId: string
): Promise<Blob> {
  return apiClient.get<Blob>(
    `/report-studio/exports/${encodeURIComponent(exportId)}/download`,
    { responseType: 'blob', unwrapResponse: false }
  )
}

// ---------------------------------------------------------------------------
// 报告包（链路 3a/3c，data_transfer_bp.py /report/import）
// ---------------------------------------------------------------------------

/** 导入报告包（multipart ZIP）：平台报告原地替换 + Studio 文档拓扑序落库 */
export async function importReportPackage(
  file: File,
  options: { targetReportId?: number; batchId?: string } = {}
): Promise<ReportPackageImportReceipt> {
  const formData = new FormData()
  formData.append('file', file)
  if (options.targetReportId !== undefined) {
    formData.append('targetReportId', String(options.targetReportId))
  }
  if (options.batchId) formData.append('batchId', options.batchId)
  const dto = await apiClient.post<ReportPackageImportReceiptDto>(
    '/data-transfer/report/import',
    formData
  )
  return toReportPackageImportReceipt(dto)
}
