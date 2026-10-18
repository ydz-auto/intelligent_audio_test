/**
 * 评估维度导出工具（features/evaluation；11_用例域.md §4.1 导入/导出下拉）。
 * 导出维度（JSON/Excel 二选一下拉项），文件名 `evaluation-dimensions-{YYYY-MM-DD}.{ext}`。
 * 数据源 = GET /evaluation/dimensions/export?format=json|excel 返回的维度行数组
 * （excel 格式行键为中文列名，json 格式行为 camel 键）；前端将行数组落盘为文件。
 */
import { downloadBlob } from './download-blob'

/** 转义 HTML（Excel 表格导出单元格防注入） */
export function escapeHtml(value: unknown): string {
  const str = String(value ?? '')
  return str
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

/** 由后端导出行数组构建 Excel HTML 表格（行键即表头，照 .xls 语法） */
export function buildExportRowsExcelHtml(
  rows: Array<Record<string, unknown>>
): string {
  if (rows.length === 0) {
    return '<html><head><meta charset="utf-8"></head><body><table></table></body></html>'
  }
  const header = Object.keys(rows[0])
    .map((key) => `<th>${escapeHtml(key)}</th>`)
    .join('')
  const body = rows
    .map((row) =>
      header
        ? Object.values(row)
            .map(escapeHtml)
            .map((cell) => `<td>${cell}</td>`)
            .join('')
        : ''
    )
    .map((cells) => `<tr>${cells}</tr>`)
    .join('')
  return `<html><head><meta charset="utf-8"></head><body><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></body></html>`
}
