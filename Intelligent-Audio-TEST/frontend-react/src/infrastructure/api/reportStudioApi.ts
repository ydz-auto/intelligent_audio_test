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
  StudioDocumentList,
  StudioDocumentListQuery,
  StudioDocumentUpdateInput,
  StudioUploadInput,
} from '@/domain/models/report-studio'
import { apiClient } from '@/infrastructure/api/client'
import {
  toReportPackageImportReceipt,
  toStudioDocument,
  toStudioDocumentList,
  type ReportPackageImportReceiptDto,
  type StudioDocumentDto,
  type StudioDocumentListDto,
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

export interface StudioDocumentVersion {
  id: number
  docId: string
  version: number
  markdownContent: string
  parentVersion: number | null
  snapshotReason: string
  createdAt: string | null
}

interface StudioVersionDto {
  id?: number
  doc_id?: string
  version?: number
  markdown_content?: string
  parent_version?: number | null
  snapshot_reason?: string
  created_at?: string | null
}

function toVersion(dto: StudioVersionDto): StudioDocumentVersion {
  return {
    id: dto.id ?? 0,
    docId: dto.doc_id ?? '',
    version: dto.version ?? 0,
    markdownContent: dto.markdown_content ?? '',
    parentVersion: dto.parent_version ?? null,
    snapshotReason: dto.snapshot_reason ?? '',
    createdAt: dto.created_at ?? null,
  }
}

/** 版本链 */
export async function listStudioDocumentVersions(
  docId: string
): Promise<StudioDocumentVersion[]> {
  const data = await apiClient.get<{ items?: StudioVersionDto[] } | StudioVersionDto[]>(
    `/report-studio/documents/${encodeURIComponent(docId)}/versions`
  )
  const items = Array.isArray(data) ? data : (data?.items ?? [])
  return items.map(toVersion)
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
