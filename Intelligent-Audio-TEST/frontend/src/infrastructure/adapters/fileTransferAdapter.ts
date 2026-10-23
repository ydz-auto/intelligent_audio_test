/**
 * 文件导入导出 Adapter —— 三资源（test-devices / playback-devices / apis）INT-816 端点共用
 *
 * - 导出响应是后端 FileResponse 原始文件流，文件名在 Content-Disposition；
 *   request 层把响应头以非枚举属性 `__responseHeaders` 挂到 Blob 上（见 http/client.ts），
 *   本层解析后对业务层只暴露 camelCase 的 { blob, filename }。
 * - 导入响应 { imported_count, updated_count, skipped_count, errors } → ImportReport（camelCase）。
 */
import type { ExportFile, ImportReport } from '../../domain/model/common'
import type { ImportReportDto, ResourceExportQueryDto } from '../dto/common'

/** 三资源导出参数（Domain camelCase）：format 仅 json/excel；ids 为空表示全部 */
export interface ResourceExportParams {
  format?: 'json' | 'excel'
  ids?: (string | number)[]
}

/** Content-Disposition 中的文件名（兼容 filename= / filename*=UTF-8'' 两种写法） */
const FILENAME_PATTERN = /filename\*?=(?:UTF-8'')?["']?([^"';\r\n]+)["']?/i

/** 从 Blob 附带响应头读取 Content-Disposition 文件名（读不到返回 null） */
export function readContentDispositionFilename(blob: Blob): string | null {
  const headers = (blob as any)?.__responseHeaders as Record<string, string> | undefined
  if (!headers) return null
  const disposition = headers['content-disposition'] || headers['Content-Disposition'] || ''
  const matched = disposition.match(FILENAME_PATTERN)
  const raw = matched?.[1]?.trim()
  if (!raw) return null
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
}

/** 本地时间戳 yyyyMMdd_HHmmss（后端缺 Content-Disposition 时的兜底文件名） */
function buildTimestamp(date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
}

/** 兜底文件名（与后端命名口径一致：<前缀>_<时间戳>.<扩展名>） */
export function buildFallbackExportFilename(prefix: string, format: string | undefined): string {
  const extension = (format || 'json').toLowerCase() === 'excel' ? 'xlsx' : (format || 'json').toLowerCase()
  return `${prefix}_${buildTimestamp()}.${extension}`
}

/** Blob + 后端响应头 → ExportFile（文件名优先 Content-Disposition） */
export function toExportFile(blob: Blob, fallbackFilename: string): ExportFile {
  return {
    blob,
    filename: readContentDispositionFilename(blob) || fallbackFilename,
  }
}

/** 导出参数（Domain camelCase）→ 后端 ResourceExportQuery（ids 拼 CSV） */
export function toResourceExportQueryDto(ids?: (string | number)[], format?: string): ResourceExportQueryDto {
  const query: ResourceExportQueryDto = { format: format || 'json' }
  const normalizedIds = (ids || []).map((id) => String(id).trim()).filter((id) => id.length > 0)
  if (normalizedIds.length > 0) query.ids = normalizedIds.join(',')
  return query
}

/** 导入计数 DTO → ImportReport（snake_case → camelCase，缺失按 0/空数组） */
export function toImportReport(dto: ImportReportDto | null | undefined): ImportReport {
  const toCount = (value: unknown): number => {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
  }
  return {
    importedCount: toCount(dto?.imported_count),
    updatedCount: toCount(dto?.updated_count),
    skippedCount: toCount(dto?.skipped_count),
    errors: Array.isArray(dto?.errors) ? dto!.errors!.map((item) => String(item)) : [],
  }
}
