/**
 * 测试执行域 API（infrastructure/api 层；10_测试执行.md §9）。
 * 已接线（INT-646）：全部经 client.ts 统一 fetch 封装走真实后端，端点对照
 * api_gateway/routes 实测（testcase_bp / group_bp / task_bp / execution_bp / log_bp /
 * api_bp / algorithm_bp / report_bp）：
 *   GET /testcases（TestCaseListQuery；执行选择列表，per_page=1000 全量）
 *   POST /testcases/ids（按筛选条件圈定全量 id）
 *   GET /testcases/tags（TagListData → string[]）
 *   GET /groups（GroupListData → {value,label}[]）
 *   GET /test-devices（DeviceListData；device:read）
 *   GET /apis（ApiListData；无后端门槛）
 *   POST /apis/{id}/health（api_config:read）
 *   POST/PUT/DELETE /apis、/apis/{id}（api_config:create/update/delete）
 *   POST /apis/{id}/stop-test（api_config:test）
 *   POST /tasks + POST /tasks/{id}/start（task:create/execute）
 *   POST /reports/generate-task + POST /reports/export（report:create/read）
 *   GET /tasks/{taskId}/cases/{caseId}/detail（task:read）
 *   GET /logs?task_id&test_case_id（log:read）
 *   GET /reports/{id}（report:read；15_报告域 domain 模型即后端 snake_case 同构）
 * snake_case 契约只在 infrastructure/dto/ 出现，本层与 domain 只见 camelCase。
 */
import type { CaseExecutionDetail, TaskLaunchInput } from '@/domain/models/testExecution'
import type { ApiConfig, ApiHealthCheckResult } from '@/domain/models/apiConfig'
import type { Device } from '@/domain/models/device'
import type { TestCase, EvaluationDimension } from '@/domain/models/testCase'
import type { TestAlgorithmOption } from '@/domain/models/algorithm'
import type { ReportDetailData } from '@/domain/models/report'
import { request } from '@/infrastructure/api/client'
import { apiConfigFromDto, apiHealthFromDto } from '@/infrastructure/adapters/apiConfigAdapter'
import { deviceFromDto } from '@/infrastructure/adapters/deviceAdapter'
import { caseDetailFromDto, testCaseFromDto } from '@/infrastructure/adapters/testCaseAdapter'
import type { CaseDetailDto, TestCaseListItemDto } from '@/infrastructure/dto/testcase.dto'
import type { ApiHealthCheckDataDto, ApiItemDto } from '@/infrastructure/dto/apis.dto'
import type { DeviceItemDto } from '@/infrastructure/dto/device.dto'
import {
  type GroupListDataDto,
  type LogListDataDto,
  type TaskStartDataDto,
  type TestCaseIdsResultDto,
  type TestCaseTagListDataDto,
  toGroupFacetOptions,
  toLogItems,
} from '@/infrastructure/dto/test-execution.dto'

export interface TestCaseFilter {
  keyword?: string
  groupId?: string | null
  tags?: string[]
  dimensionId?: number | null
  type?: 'e2e' | 'api' | null
  algorithmType?: string | null
}

/** 用例选择列表查询参数（camelCase → snake_case；INT-193 执行口径 type 由后端派生） */
function toTestCaseQuery(filter: TestCaseFilter): Record<string, unknown> {
  return {
    keyword: filter.keyword?.trim() || undefined,
    group_id: filter.groupId || undefined,
    tag: filter.tags?.length ? filter.tags[0] : undefined,
    dimension_id: filter.dimensionId ?? undefined,
    type: filter.type ?? undefined,
    algorithm_type: filter.algorithmType || undefined,
  }
}

/** 用例列表（步骤二；GET /testcases，per_page=1000 全量拉取由前端过滤语义保留） */
export async function fetchTestCases(filter: TestCaseFilter): Promise<TestCase[]> {
  const dto = await request<{ items: TestCaseListItemDto[] }>('GET', '/testcases', undefined, {
    params: { ...toTestCaseQuery(filter), per_page: 1000 },
  })
  return (dto?.items ?? []).map(testCaseFromDto)
}

/** 算法选项（步骤一算法联动 + API 弹窗关联算法；GET /algorithm/options，algorithm:read，与评测域同端点） */
export async function fetchTestAlgorithmOptions(): Promise<TestAlgorithmOption[]> {
  const dto = await request<{ algorithms: Array<{ value: string; name: string }> }>(
    'GET',
    '/algorithm/options'
  )
  return (dto?.algorithms ?? []).map((item) => ({
    id: item.value ?? '',
    name: item.name ?? item.value ?? '',
  }))
}

/** 全量圈定（步骤二「全选结果」；POST /testcases/ids 按筛选条件圈定全量 id） */
export async function fetchCaseIdsByFilter(
  filter: TestCaseFilter
): Promise<{ ids: string[]; total: number }> {
  const dto = await request<TestCaseIdsResultDto>('POST', '/testcases/ids', toTestCaseQuery(filter))
  return { ids: dto?.ids ?? [], total: dto?.total ?? (dto?.ids ?? []).length }
}

/** 用例分组 facet（GET /groups，per_page=100） */
export async function fetchCaseGroups(): Promise<{ value: string; label: string }[]> {
  const dto = await request<GroupListDataDto>('GET', '/groups', undefined, {
    params: { per_page: 100 },
  })
  return toGroupFacetOptions(dto)
}

/** 标签 facet（GET /testcases/tags；TagNameListQuery 平移） */
export async function fetchCaseTags(): Promise<string[]> {
  const dto = await request<TestCaseTagListDataDto>('GET', '/testcases/tags', undefined, {
    params: { per_page: 100 },
  })
  return dto?.items ?? []
}

/** 评估维度 facet（GET /evaluation/dimensions，per_page=1000；TestCaseDimensionBrief 主/子平铺） */
export async function fetchEvaluationDimensions(): Promise<EvaluationDimension[]> {
  const dto = await request<{ items: Array<{ id: number; name: string; dimension_type: string | null }> }>(
    'GET',
    '/evaluation/dimensions',
    undefined,
    { params: { per_page: 1000 } }
  )
  return (dto?.items ?? []).map((item) => ({
    id: item.id,
    name: item.name ?? '',
    type: item.dimension_type ?? null,
  }))
}

/** 设备列表（步骤三；GET /test-devices，device:read） */
export async function fetchDevices(): Promise<Device[]> {
  const dto = await request<{ items: DeviceItemDto[] }>('GET', '/test-devices', undefined, {
    params: { per_page: 1000 },
  })
  return (dto?.items ?? []).map(deviceFromDto)
}

/** 被测 API 列表（步骤三；GET /apis 实测无后端门槛，前端 api_config:read 判定） */
export async function fetchApis(): Promise<ApiConfig[]> {
  const dto = await request<{ items: ApiItemDto[] }>('GET', '/apis', undefined, {
    params: { per_page: 1000 },
  })
  return (dto?.items ?? []).map(apiConfigFromDto)
}

/** API 连接测试（§5.4；POST /apis/{id}/health，api_config:test） */
export async function fetchApiHealth(apiId: number): Promise<ApiHealthCheckResult> {
  const dto = await request<ApiHealthCheckDataDto>('POST', `/apis/${apiId}/health`)
  return apiHealthFromDto({ ...(dto ?? {}), id: dto?.id ?? apiId })
}

/** 报告详情（步骤五嵌入式装配；GET /reports/{id}；15_报告域 domain 模型即后端 snake_case 同构） */
export async function fetchFlowReport(reportId: number): Promise<ReportDetailData> {
  const data = await request<ReportDetailData>('GET', `/reports/${reportId}`)
  return data
}

/** 创建任务（步骤三开始测试；POST /tasks，task:create；filter-all 口径显性化；INT-604 携带 execution_mode/serial_first） */
export async function createTask(input: TaskLaunchInput): Promise<{ id: number }> {
  const caseIds = input.filterAllMode
    // filter-all：按启动时当前筛选条件全量圈定（INT-646 代码审计 P2——不再是仅算法维度；
    // caseFilter 由 case-selection store 随启动流程传入，未带时回退仅算法口径）
    ? (await fetchCaseIdsByFilter(
        input.caseFilter ?? { algorithmType: input.algorithmType ?? undefined }
      )).ids
    : input.testCaseIds
  const body: Record<string, unknown> = {
    name: input.name,
    algorithm_type: input.algorithmType || undefined,
    case_ids: caseIds,
    device_ids: input.deviceIds,
    api_ids: input.apiIds,
    // INT-604：执行模式（并行/串行）+ 串行优先侧（device/api）——网关 TaskCreateRequest
    // 顶层显式字段（api_gateway/schemas/task.py:250-251 实测），task_service 并入 Task.config。
    execution_mode: input.params.executionMode,
    serial_first: input.params.serialFirst,
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
  const dto = await request<{ id: number }>('POST', '/tasks', body)
  return { id: dto?.id ?? 0 }
}

/** 启动任务（POST /tasks/{id}/start，task:execute） */
export async function startTask(taskId: number): Promise<void> {
  await request<TaskStartDataDto>('POST', `/tasks/${taskId}/start`)
}

/** 报告生成（步骤五；POST /reports/generate-task，report:create） */
export async function generateTaskReport(
  taskId: number
): Promise<{ reportId: number; status: string }> {
  const dto = await request<{ report_id: number; status: string }>(
    'POST',
    '/reports/generate-task',
    { task_id: taskId }
  )
  return { reportId: dto?.report_id ?? 0, status: dto?.status ?? 'generated' }
}

/** 报告导出（步骤五；POST /reports/export，report:read，format csv/excel/pdf/html；blob 下载） */
export async function exportReport(
  reportIds: number[],
  format: string
): Promise<{ filename: string }> {
  const blob = await request<Blob>('POST', '/reports/export', { ids: reportIds, format }, {
    responseType: 'blob',
  })
  const filename = `report-${reportIds[0]}.${format}`
  triggerBlobDownload(blob, filename)
  return { filename }
}

/** 用例执行详情（§5.2；GET /tasks/{taskId}/cases/{caseId}/detail，task:read） */
export async function fetchCaseExecutionDetail(
  taskId: number,
  caseId: string
): Promise<CaseExecutionDetail> {
  const dto = await request<CaseDetailDto>('GET', `/tasks/${taskId}/cases/${caseId}/detail`)
  return caseDetailFromDto(dto ?? ({} as CaseDetailDto))
}

/** 用例日志（§5.2 日志分页；GET /logs?task_id&test_case_id，log:read） */
export async function fetchCaseLogs(
  taskId: number,
  caseId: string,
  page: number
): Promise<{ items: Array<{ id: number; timestamp: string; level: 'info' | 'warn' | 'error'; message: string }>; total: number; page: number }> {
  const dto = await request<LogListDataDto>('GET', '/logs', undefined, {
    params: { task_id: taskId, test_case_id: caseId, page, per_page: 100 },
  })
  return toLogItems(dto)
}

/** 新增/更新 API（§5.3；POST/PUT /apis，api_config:create/update；camelCase→snake_case 本层收敛） */
export async function saveApi(
  input: Partial<ApiConfig> & { name: string }
): Promise<{ id: number }> {
  const body = toApiInputDto(input)
  if (input.id != null) {
    await request('PUT', `/apis/${input.id}`, body)
    return { id: input.id }
  }
  const dto = await request<{ id: number }>('POST', '/apis', body)
  return { id: dto?.id ?? 0 }
}

/** 删除 API（DELETE /apis/{id}；api_config:delete） */
export async function deleteApi(apiId: number): Promise<void> {
  await request('DELETE', `/apis/${apiId}`)
}

/** API 停止测试（POST /apis/{id}/stop-test，api_config:test） */
export async function stopApiTest(apiId: number): Promise<void> {
  await request('POST', `/apis/${apiId}/stop-test`)
}

/** Partial<ApiConfig>（camelCase）→ ApiCreateInput/ApiUpdateInput 请求体 */
function toApiInputDto(input: Partial<ApiConfig> & { name: string }): Record<string, unknown> {
  const result: Record<string, unknown> = { name: input.name }
  if (input.vendor !== undefined) result.vendor = input.vendor
  if (input.apiUrl !== undefined) result.api_url = input.apiUrl
  if (input.description !== undefined) result.description = input.description
  if (input.algorithmType !== undefined) result.algorithm_type = input.algorithmType
  if (input.defaultMaxProcess !== undefined) result.default_max_process = input.defaultMaxProcess
  if (input.defaultMaxTimeout !== undefined) result.default_max_timeout = input.defaultMaxTimeout
  if (input.defaultMaxAudioDuration !== undefined) result.default_max_audio_duration = input.defaultMaxAudioDuration
  if (input.status !== undefined) result.status = input.status
  if (input.endpoints !== undefined) {
    result.endpoints = input.endpoints.map((endpoint) => ({
      endpoint: endpoint.endpoint,
      name: endpoint.name,
      max_process: endpoint.maxProcess,
      max_timeout: endpoint.maxTimeout,
      max_audio_duration: undefined,
      status: endpoint.status,
      priority: undefined,
      description: endpoint.description,
    }))
  }
  if (input.deviceType !== undefined) result.device_type = input.deviceType
  return result
}

/** 触发浏览器下载（Blob → <a download> 统一走；导出响应 Content-Disposition 缺省按默认名） */
function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
