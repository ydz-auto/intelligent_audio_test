/**
 * Report Studio 文档领域模型（domain 层；INT-1766 D8）。
 * 契约来源：report_service `_doc_dict`（INT-1763 D5）与 data_transfer 报告包回执（INT-1764 D6）。
 * 页面只读 camelCase；snake_case 转换只在 infrastructure/dto。
 */

/** 文档来源（后端 ReportStudioSourceType，禁止裸字符串比较） */
export const StudioSourceType = {
  PLATFORM_REPORT: 'platform_report',
  UPLOADED_FILE: 'uploaded_file',
  AGENT_SUMMARY: 'agent_summary',
} as const

export type StudioSourceTypeValue =
  (typeof StudioSourceType)[keyof typeof StudioSourceType]

export const STUDIO_SOURCE_TYPE_LABEL: Record<StudioSourceTypeValue, string> = {
  [StudioSourceType.PLATFORM_REPORT]: '平台报告文档',
  [StudioSourceType.UPLOADED_FILE]: '上传文档',
  [StudioSourceType.AGENT_SUMMARY]: 'Agent 总结',
}

/** 独立报告上传白名单（后端 _STUDIO_UPLOAD_TYPES 同口径） */
export const STUDIO_UPLOAD_FORMATS = ['md', 'html', 'pptx'] as const
export type StudioUploadFormat = (typeof STUDIO_UPLOAD_FORMATS)[number]

/** 上传大小上限默认值（后端 REPORT_STUDIO_UPLOAD_MAX_MB 默认 50，超限 413） */
export const STUDIO_UPLOAD_MAX_MB = 50

export interface StudioDocument {
  docId: string
  /** 平台报告文档 / 源为平台报告的 Agent 总结才有；上传文档与孤儿总结为空 */
  reportId: number | null
  title: string
  /** 列表接口不返回正文（include_content=false） */
  markdownContent: string
  currentVersion: number
  etag: string
  chartRefs: string[]
  stylePrefs: Record<string, unknown>
  /** 搬运后一律置空：A 侧无法续接 B 侧 DSH 会话（设计 §6.3-1） */
  agentSessionId: string | null
  parentDocId: string | null
  sourceType: StudioSourceTypeValue
  sourceFormat: string | null
  sourceFileSize: number | null
  sourceFilePath: string | null
  /** 上传件鉴权下载引用（html/pptx），前端按沙箱 iframe/下载打开 */
  sourceDownloadRef: string | null
  createdBy: number | null
  createdAt: string | null
  updatedAt: string | null
}

export interface StudioDocumentList {
  items: StudioDocument[]
  total: number
  limit: number
  offset: number
}

export interface StudioDocumentListQuery {
  reportId?: number
  sourceType?: StudioSourceTypeValue
  parentDocId?: string
  limit?: number
  offset?: number
}

export interface StudioUploadInput {
  file: File
  title: string
  /** 可选关联任务；为空即独立文档库 */
  taskId?: number
  format: StudioUploadFormat
}

export interface StudioDocumentUpdateInput {
  docId: string
  /** 乐观锁：与 currentVersion 不一致时后端 409 */
  expectedVersion: number
  markdownContent?: string
  chartRefs?: string[]
}

/** 报告包导入回执（D6 网关 success_response(result.data)） */
export interface ReportPackageImportReceipt {
  reportId: number | null
  targetResolvedBy: string | null
  batchId: string | null
  deletedCounts: Record<string, number>
  insertedCounts: Record<string, number>
  documentIdMapping: Record<string, string>
  chartIdMapping: Record<string, string>
  agentSessionDropped: number
  warnings: string[]
  rollbackAvailable: boolean
}

/** 报告包 manifest（包内 manifest.json，由前端预检读取） */
export interface ReportPackageManifestSummary {
  kind: string
  version: string | null
  exportedAt: string | null
  /** B 侧原任务（A 侧按它匹配本地任务） */
  sourceTaskId: number | null
  sourceTaskName: string | null
  sourceTaskCaseSetHash: string | null
  entities: string[]
  docVersionScope: string | null
  stats: Record<string, number>
}

/** 上传文档的「无法预览/未绑定」类降级判定（图表需重新绑定报告，设计 §6.3-5） */
export function needsChartRebind(doc: StudioDocument): boolean {
  return doc.chartRefs.length > 0 && doc.reportId === null
}

// ---------------------------------------------------------------------------
// 对话式工作台：起草 / 版本 / 导出（INT-2473，设计文档 §15.5）
// ---------------------------------------------------------------------------

/**
 * 版本快照原因（后端 StudioSnapshotReason 同口径）。
 * 页面按枚举出中文标签，禁止直接比较后端字符串。
 */
export const StudioSnapshotReason = {
  AI_EDIT: 'ai_edit',
  MANUAL_EDIT: 'manual_edit',
  RESTORE: 'restore',
  IMPORT: 'import',
} as const

export type StudioSnapshotReasonValue =
  (typeof StudioSnapshotReason)[keyof typeof StudioSnapshotReason]

export const STUDIO_SNAPSHOT_REASON_LABEL: Record<string, string> = {
  [StudioSnapshotReason.AI_EDIT]: 'AI 起草',
  [StudioSnapshotReason.MANUAL_EDIT]: '人工编辑',
  [StudioSnapshotReason.RESTORE]: '版本恢复',
  [StudioSnapshotReason.IMPORT]: '文件导入',
}

/**
 * 历史版本快照（GET /documents/{id}/versions 单项）。
 * 后端 `_version_dict` 不返回正文，`markdownContent` 恒为空串——历史正文只能
 * 通过恢复版本读取（恢复生成新版本并返回最新文档），页面不得把空串当正文展示。
 */
export interface StudioDocumentVersion {
  id: number
  docId: string
  version: number
  markdownContent: string
  parentVersion: number | null
  snapshotReason: string
  createdAt: string | null
  createdBy: number | null
}

/** 起草文档入参（POST /documents：绑定平台报告生成新草稿） */
export interface StudioDocumentCreateInput {
  reportId: number
  title?: string
  markdownContent?: string
  /** 关联的 Agent 会话（AI 起草时由后端落版本快照原因 ai_edit） */
  agentSessionId?: string | null
}

/** 导出格式（后端 StudioExportFormat；PDF/PPTX 依赖渲染器，未部署时返回失败态） */
export const STUDIO_EXPORT_FORMATS = ['pdf', 'pptx', 'html', 'md'] as const
export type StudioExportFormat = (typeof STUDIO_EXPORT_FORMATS)[number]

export const STUDIO_EXPORT_FORMAT_LABEL: Record<StudioExportFormat, string> = {
  pdf: 'PDF',
  pptx: 'PPTX',
  html: 'HTML',
  md: 'Markdown',
}

/** 导出作业状态（后端 StudioExportStatus） */
export const StudioExportStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  DONE: 'done',
  FAILED: 'failed',
} as const

export type StudioExportStatusValue =
  (typeof StudioExportStatus)[keyof typeof StudioExportStatus]

/** 导出作业（POST /documents/{id}/exports 与 GET /exports/{id}） */
export interface StudioExportJob {
  exportId: string
  docId: string
  version: number
  format: string
  theme: string
  status: StudioExportStatusValue
  /** 0~100；pending 0 / running 10+ / 终态 100 */
  progress: number
  error: string | null
  createdAt: string | null
  updatedAt: string | null
  /** 网关鉴权下载引用（完成后可下载） */
  downloadRef: string | null
}

/** 导出是否处于在途状态（按钮防重复 + 轮询区间） */
export function isStudioExportActive(job: StudioExportJob | null): boolean {
  return (
    job?.status === StudioExportStatus.PENDING ||
    job?.status === StudioExportStatus.RUNNING
  )
}

/** 导出作业状态 → 中文文案 */
export const STUDIO_EXPORT_STATUS_LABEL: Record<StudioExportStatusValue, string> = {
  [StudioExportStatus.PENDING]: '排队中',
  [StudioExportStatus.RUNNING]: '导出中',
  [StudioExportStatus.DONE]: '已完成',
  [StudioExportStatus.FAILED]: '导出失败',
}
