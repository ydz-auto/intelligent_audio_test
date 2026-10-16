/**
 * 评估维度导出工具（features/evaluation；11_用例域.md §4.1 导入/导出下拉）。
 * 导出维度（JSON/Excel 二选一下拉项），文件名 `evaluation-dimensions-{YYYY-MM-DD}.{ext}`
 * 照现 downloadBlob 命名。mock 阶段无后端导出，JSON 直接序列化，Excel 用 HTML 表格语法
 * （.xls 前缀 BOM，Excel 原生打开中文不乱码）；接线后替换为真实导出接口。
 */
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import { getAlgorithmLabel } from '@/features/evaluation/constants'

/** 转义 HTML（Excel 表格导出单元格防注入） */
function escapeHtml(value: unknown): string {
  const str = String(value ?? '')
  return str
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

/** 分类 id → 分类名（导出列展示用） */
function categoryNameOf(
  dimension: Dimension,
  categories: EvaluationCategory[]
): string {
  if (dimension.categoryId == null) return '未分类'
  return (
    categories.find((c) => c.id === dimension.categoryId)?.name ?? '未分类'
  )
}

/** Excel 导出（HTML 表格语法 .xls；行=维度，列=表头九列与页面表格同构） */
export function buildDimensionExcelHtml(
  dimensions: Dimension[],
  categories: EvaluationCategory[]
): string {
  const algorithmText = (dimension: Dimension): string =>
    (dimension.associatedAlgorithms ?? [])
      .map((a) => getAlgorithmLabel(a.algorithmType))
      .join('、')
  const header = `<tr><th>ID</th><th>维度名称</th><th>维度类型</th><th>分类</th><th>关联算法</th><th>权重</th><th>API状态</th><th>状态</th></tr>`
  const body = dimensions
    .map((dimension) => {
      const cells = [
        dimension.id,
        dimension.name,
        dimension.dimensionType === 'sub' ? '子维度' : '主维度',
        categoryNameOf(dimension, categories),
        algorithmText(dimension),
        dimension.weight ?? '',
        dimension.apiStatus === 'offline' ? '离线' : '在线',
        dimension.status ? '启用' : '禁用',
      ]
        .map(escapeHtml)
        .map((cell) => `<td>${cell}</td>`)
        .join('')
      return `<tr>${cells}</tr>`
    })
    .join('')
  return `<html><head><meta charset="utf-8"></head><body><table><thead>${header}</thead><tbody>${body}</tbody></table></body></html>`
}

/** 触发浏览器下载（Blob → <a download> 统一走；ext 决定 MIME） */
export function downloadBlob(
  content: string | Blob,
  filename: string,
  mime: string,
  withBom = false
): void {
  const blob =
    typeof content === 'string'
      ? new Blob([withBom ? '﻿' : '', content], { type: mime })
      : content
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
