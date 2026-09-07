/**
 * DTO 层 —— snake_case，与后端 api_gateway/schemas 一一对应
 *
 * 规则：
 * - 字段名与后端 JSON 输出完全一致（snake_case）
 * - 本层类型仅被 adapters/ 和 api/ 使用，禁止泄漏到 views/composables
 */

/** 对应后端 PaginatedData[T]（api_gateway/schemas/common.py） */
export interface PaginatedDto<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}
