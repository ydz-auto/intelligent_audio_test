/**
 * TestCase DTO —— snake_case
 * 与后端 api_gateway/schemas/testcase.py 一一对应（serialize_by_alias=False 输出 snake_case）。
 */

/**
 * 透传的用例配置。
 *
 * 注意：后端 TestCaseConfig 内键名前后端一致（数据结构而非 API 字段名），
 * 不做 snake/camel 转换；类型上收紧为 Record<string, unknown>，
 * 具体形状由 Domain 侧 TestCaseConfig 类型约束。
 */
export type TestCaseConfigRaw = Record<string, unknown>

/** 用例列表行（TestCaseListItem） */
export interface TestCaseDto {
  id: string | number
  name: string
  description?: string | null
  group_id?: string | null
  group_name?: string | null
  type?: string | null
  tags: string[]
  config?: TestCaseConfigRaw
  algorithm_params?: unknown
  reference_params?: unknown
  algorithm_type?: string | null
  created_at?: string | null
  updated_at?: string | null
  total_duration?: number | null
}

/** 用例分组（GroupListItem） */
export interface TestCaseGroupDto {
  id: string | number
  name: string
  description?: string | null
  algorithm_type?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** 用例创建/更新请求体（宽松可选；config 为透传结构） */
export interface TestCaseUpsertDto {
  name?: string
  description?: string
  type?: string
  test_type?: 'api' | 'e2e'
  group_id?: string | number | null
  tags?: string[]
  config?: TestCaseConfigRaw
  algorithm_params?: unknown
  reference_params?: unknown
  algorithm_type?: string
}
