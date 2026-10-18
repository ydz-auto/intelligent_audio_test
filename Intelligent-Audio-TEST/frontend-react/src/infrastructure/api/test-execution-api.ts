/**
 * 测试执行域 API 桩（infrastructure/api 层；红线④：不接真实后端）。
 * 全部函数 TODO(API 接线) 标注对应真实端点；当前返回 mock 常量（经 adapters 产出 domain）。
 * 端点对照：POST /tasks（task:create）+ POST /tasks/{id}/start（task:execute）；
 * POST /testcases/ids（全量圈定）；GET /logs?task_id&test_case_id；
 * POST /reports/generate-task（report:create）；GET /apis（无后端门槛，前端 api_config:read 判定）。
 */
import { request } from '@/infrastructure/api/client'
import type { TaskLaunchInput } from '@/domain/models/testExecution'
import type { ApiConfig, ApiHealthCheckResult } from '@/domain/models/apiConfig'
import type { Device } from '@/domain/models/device'
import type { TestCase, EvaluationDimension } from '@/domain/models/testCase'
import {
  MOCK_APIS,
  MOCK_CASE_EXECUTION_DETAIL,
  MOCK_CASE_GROUPS,
  MOCK_CASE_TAGS,
  MOCK_DEVICES,
  MOCK_EVAL_DIMENSIONS,
  MOCK_FLOW_REPORT,
  MOCK_TEST_ALGORITHMS,
  MOCK_TESTCASES,
} from '@/infrastructure/mock/test-execution-mock'
import type { TestAlgorithmOption } from '@/infrastructure/mock/test-execution-mock'

function mockLatency<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 120))
}

export interface TestCaseFilter {
  keyword?: string
  groupId?: string | null
  tags?: string[]
  dimensionId?: number | null
  type?: 'e2e' | 'api' | null
  algorithmType?: string | null
}

function filterTestCases(filter: TestCaseFilter): TestCase[] {
  const keyword = filter.keyword?.trim().toLowerCase()
  return MOCK_TESTCASES.filter((item) => {
    if (filter.type && item.type !== filter.type) return false
    if (filter.groupId === 'ungrouped') {
      if (item.groupId != null) return false
    } else if (filter.groupId && item.groupId !== filter.groupId) return false
    if (filter.algorithmType && item.algorithmType !== filter.algorithmType) return false
    if (filter.tags?.length && !filter.tags.every((t) => item.tags.includes(t))) return false
    if (keyword) {
      const haystack = `${item.name} ${item.description ?? ''}`.toLowerCase()
      if (!haystack.includes(keyword)) return false
    }
    return true
  })
}

/** 算法选择项（步骤一；GET /algorithm/options 平移，algorithm:read） */
export async function fetchAlgorithmOptions(): Promise<TestAlgorithmOption[]> {
  // TODO(API 接线): GET /algorithm/options（algorithm_bp.py:165-167 = algorithm:read）
  return mockLatency(MOCK_TEST_ALGORITHMS)
}

/** 用例列表（步骤二；POST /testcases 平移） */
export async function fetchTestCases(filter: TestCaseFilter): Promise<TestCase[]> {
  // TODO(API 接线): GET /testcases（TestCaseListQuery：page/per_page/keyword/tag/group_id/algorithm_type/type/dimension_id）
  return mockLatency(filterTestCases(filter))
}

/** 全量圈定（步骤二「全选结果」；POST /testcases/ids 平移，testcase_bp.py:72-75） */
export async function fetchCaseIdsByFilter(
  filter: TestCaseFilter
): Promise<{ ids: string[]; total: number }> {
  // TODO(API 接线): POST /testcases/ids（按筛选条件圈定全量 id）
  const all = filterTestCases(filter)
  return mockLatency({ ids: all.map((c) => c.id), total: all.length })
}

/** 用例分组 facet */
export async function fetchCaseGroups(): Promise<{ value: string; label: string }[]> {
  return mockLatency(MOCK_CASE_GROUPS)
}

/** 标签 facet（TagNameListQuery 平移） */
export async function fetchCaseTags(): Promise<string[]> {
  return mockLatency(MOCK_CASE_TAGS)
}

/** 评估维度 facet（TestCaseDimensionBrief 列表） */
export async function fetchEvaluationDimensions(): Promise<EvaluationDimension[]> {
  return mockLatency(MOCK_EVAL_DIMENSIONS)
}

/** 设备列表（E2E 步骤三；GET /devices 平移，device:read） */
export async function fetchDevices(): Promise<Device[]> {
  // TODO(API 接线): GET /devices（DeviceListQuery：keyword/status/type/algorithm_type）
  return mockLatency(MOCK_DEVICES)
}

/** 被测 API 列表（API 步骤三；GET /apis 实测无后端门槛，前端 api_config:read 判定） */
export async function fetchApis(): Promise<ApiConfig[]> {
  // TODO(API 接线): GET /apis（ApiListQuery）
  return mockLatency(MOCK_APIS)
}

/** API 连接测试（§5.4；POST /apis/{id}/health 平移，api_config:test） */
export async function fetchApiHealth(apiId: number): Promise<ApiHealthCheckResult> {
  // TODO(API 接线): POST /apis/{id}/health
  return mockLatency({
    id: apiId,
    status: 'online',
    healthScore: 92,
    apiUrlStatus: 'online',
    endpointsStatus: 'online',
    statusCode: 200,
    responseTime: '214ms',
    error: null,
    warning: null,
  })
}

/** 报告详情（步骤五嵌入式装配；15_报告域 domain 模型，本地 mock 源） */
export async function fetchFlowReport(_reportId: number): Promise<typeof MOCK_FLOW_REPORT> {
  // TODO(API 接线): GET /reports/{id}（report.py ReportDetailData）
  return mockLatency(MOCK_FLOW_REPORT)
}

/** 创建任务（步骤三开始测试；POST /tasks，task:create，task_bp.py TaskCreateRequest 契约） */
export async function createTask(input: TaskLaunchInput): Promise<{ id: number }> {
  const body: Record<string, unknown> = {
    name: input.name,
    case_ids: input.testCaseIds,
    device_ids: input.deviceIds,
    api_ids: input.apiIds,
    algorithm_type: input.algorithmType,
    config: {
      rounds: input.params.rounds,
      timeout: input.params.timeout,
      retries: input.params.retries,
      concurrency: input.params.concurrency,
      network: input.params.network,
      report_template: input.params.reportTemplate,
      include_charts: input.params.includeCharts,
      include_detailed_logs: input.params.includeDetailedLogs,
      include_reference_params: input.params.includeReferenceParams,
    },
  }
  const dto = await request<{ id?: number }>('POST', '/tasks', body)
  return { id: dto?.id ?? 0 }
}

/** 启动任务（POST /tasks/{id}/start，task:execute，task_bp.py TaskStartData 契约） */
export async function startTask(taskId: number): Promise<void> {
  await request<{ task_id?: number }>('POST', `/tasks/${taskId}/start`)
}

/** 报告生成（步骤五；POST /reports/generate-task，report:create） */
export async function generateTaskReport(
  _taskId: number
): Promise<{ reportId: number; status: string }> {
  // TODO(API 接线): POST /reports/generate-task
  return mockLatency({ reportId: 1205, status: 'generated' })
}

/** 报告导出（步骤五；POST /reports/export，report:read，format csv/excel/pdf/html） */
export async function exportReport(
  reportIds: number[],
  format: string
): Promise<{ filename: string }> {
  // TODO(API 接线): POST /reports/export（ReportExportRequestDto；zip_base64→Blob 下载）
  return mockLatency({ filename: `report-${reportIds[0]}.${format}` })
}

/** 用例执行详情（§5.2；GET /tasks/{taskId}/cases/{caseId}/detail + /results） */
export async function fetchCaseExecutionDetail(
  _taskId: number,
  _caseId: string
): Promise<typeof MOCK_CASE_EXECUTION_DETAIL> {
  // TODO(API 接线): GET /tasks/{taskId}/cases/{caseId}/detail + /results（task_bp.py:32-39）
  return mockLatency(MOCK_CASE_EXECUTION_DETAIL)
}

/** 用例日志（§5.2 日志分页 100 条/页；GET /logs?task_id&test_case_id） */
export async function fetchCaseLogs(
  _taskId: number,
  _caseId: string,
  page: number
): Promise<{ items: Array<{ id: number; timestamp: string; level: 'info' | 'warn' | 'error'; message: string }>; total: number; page: number }> {
  // TODO(API 接线): GET /logs?task_id&test_case_id（log_bp.py 查询字段实测）
  const perPage = 100
  const total = 100
  const start = (page - 1) * perPage
  const items = Array.from({ length: total }, (_, i) => {
    const id = total - start - i
    return {
      id,
      timestamp: `10-15 09:${String(Math.floor(i / 60)).padStart(2, '0')}:${String(i % 60).padStart(2, '0')}.${String((id * 7) % 999).padStart(3, '0')}`,
      level: (i % 5 === 2 ? 'warn' : i % 7 === 3 ? 'error' : 'info') as 'info' | 'warn' | 'error',
      message:
        i === 0
          ? '[评估] 用例 c-001 评估完成，综合得分 94.2'
          : i % 4 === 0
            ? `[执行器] 用例 c-001 第 ${i / 4 + 1} 轮执行中，当前并发 4/4`
            : `[音频] round ${(i % 3) + 1} 播放完成，设备返回码 200`,
    }
  })
  return mockLatency({ items, total, page })
}

/** 新增/更新 API（§5.3；POST/PUT /apis，api_config:create/update） */
export async function saveApi(
  _input: Partial<ApiConfig> & { name: string }
): Promise<{ id: number }> {
  // TODO(API 接线): POST/PUT /apis（ApiCreateInput/ApiUpdateInput）
  return mockLatency({ id: 99 })
}

/** 删除 API（api_config:delete） */
export async function deleteApi(_apiId: number): Promise<void> {
  // TODO(API 接线): DELETE /apis/{id}
  return mockLatency(undefined)
}

/** API 停止测试（api_config:test，api_bp.py stop-test 实测） */
export async function stopApiTest(_apiId: number): Promise<void> {
  // TODO(API 接线): POST /apis/{id}/stop-test
  return mockLatency(undefined)
}
