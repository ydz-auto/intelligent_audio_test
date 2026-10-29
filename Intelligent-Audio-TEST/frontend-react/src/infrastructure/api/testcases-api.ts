/**
 * 用例列表 API（infrastructure/api 层；接线 INT-639，经统一 client.ts）。
 * 对照后端 api_gateway/routes/testcase_bp.py + schemas/testcase.py TestCaseListQuery：
 *   GET /api/v1/testcases?page&per_page&keyword&tag&group_id&algorithm_type&
 *       favorite&only_deleted&dimension_id&type（INT-486 口径：前端不再发送 type）
 * 普通视图返回 TestCaseListData（PaginatedData 内 TestCaseListItem snake_case）；
 * view=tag 为后端契约保留项（Vue 端用），本前端标签视图由平铺行按 tag 客户端聚合
 * （11_用例域.md §3.6），故一律走普通列表（不传 view）。
 * snake→camel 转换收敛在 adapters/dto；application/domain 层只见 camelCase Domain。
 */
import { apiClient } from './client'
import type {
  PreviewPlaybackMode,
  TestCaseDuplicateStrategy,
  TestCaseImportPreview,
  TestCaseImportResult,
  TestCaseListItem,
  TestCasePreview,
} from '@/domain/models/testCase'
import {
  testCaseImportPreviewFromDto,
  testCaseImportResultFromDto,
  testCaseListItemFromDto,
  testCasePreviewFromDto,
} from '@/infrastructure/adapters/testCaseAdapter'
import type {
  TestCaseImportPreviewDto,
  TestCaseImportResultDto,
  TestCaseListDataDto,
  TestCasePreviewDto,
} from '@/infrastructure/dto/testcase.dto'

export interface TestCaseListQuery {
  page?: number
  perPage?: number
  search?: string
  groupId?: string | null
  /**
   * 分组**名**（仅 POST /testcases/ids 消费：后端 fetch_case_ids 只认 group 名，
   * INT-1267 审计 P1；GET /testcases 是 group_id，此键在 fetchTestCases 显式参数构建中不生效）
   */
  group?: string | null
  /** 标签筛选（INT-592 单选：后端 tag 参数为单值） */
  tag?: string | null
  dimensionId?: number | null
  algorithmType?: string | null
  favorite?: boolean
  trash?: boolean
  /** 分组聚合 / 标签聚合视图（前端拍平；后端 view=tag 契约不消费，见文件头） */
  view?: string | null
}

export interface TestCaseListResult {
  items: TestCaseListItem[]
  total: number
  /** 后端分页信封（INT-1284 分组内懒加载「加载更多」翻页判定；非分页消费方忽略） */
  page?: number
  pages?: number
  perPage?: number
}

/** 列表页当前为客户端懒加载分页（§3.3「已显示 n / 总 条 · 加载更多」），拉大页供前端切分 */
const LIST_PAGE_SIZE = 100

/**
 * 用例列表（真实 GET /testcases）。
 * 未分组虚拟组（INT-249）：后端 group_id 为精确匹配、无 '__ungrouped__' 哨兵，
 * 照 Vue fetchCasesByGroup('__ungrouped__') 口径——不携带 group_id 拉大页后前端过滤；
 * 收藏/回收站互斥守卫：trash 时仅 only_deleted（favorite 清空，INT-215/320 口径）。
 */
export async function fetchTestCases(
  query: TestCaseListQuery
): Promise<TestCaseListResult> {
  const ungrouped = query.groupId === '__ungrouped__'
  const dto = await apiClient.get<TestCaseListDataDto>('/testcases', {
    params: {
      page: query.page ?? 1,
      per_page: query.perPage ?? LIST_PAGE_SIZE,
      keyword: query.search,
      group_id: ungrouped ? undefined : query.groupId,
      tag: query.tag,
      dimension_id: query.dimensionId,
      algorithm_type: query.algorithmType,
      favorite: query.favorite && !query.trash ? true : undefined,
      only_deleted: query.trash ? true : undefined,
    },
  })
  let items = (dto.items ?? []).map(testCaseListItemFromDto)
  if (ungrouped) items = items.filter((c) => c.groupId === null)
  return {
    items,
    total: dto.total,
    page: dto.page,
    pages: dto.pages,
    perPage: dto.per_page,
  }
}

/** 组内懒加载每页条数（V9.7.10 testCaseStore DEFAULT_GROUP_PAGE_SIZE=20 语义平移，INT-1267） */
export const GROUP_PAGE_SIZE = 20

/**
 * 组内用例按 group_id 懒加载（Vue testCaseStore.fetchCasesByGroup 对位，INT-1267）。
 * 分组卡头计数以 /groups testCaseCount 为准；组内用例展开时才按组拉取，
 * 「加载更多」页续（page/per_page 走 fetchTestCases 契约）。
 */
export async function fetchTestCasesByGroup(
  groupId: string,
  filters: Omit<TestCaseListQuery, 'groupId' | 'page' | 'perPage' | 'view'>,
  page = 1,
  perPage = GROUP_PAGE_SIZE
): Promise<TestCaseListResult> {
  const result = await fetchTestCases({ ...filters, groupId, page, perPage })
  // 未分组虚拟组契约：fetchTestCases 不携带 group_id 拉大页后前端过滤，total 是全部用例数而非未分组数。
  // INT-1267 兜底——/groups 无「未分组」真实条目时，虚拟组计数以已加载未分组条数为准（不显示错误的全库总数）。
  return groupId === '__ungrouped__'
    ? { items: result.items, total: result.items.length }
    : result
}

/** 分组视图数据（grouped-case-list 消费：分组卡 + 组内用例卡；客户端按 groupId 聚合） */
export async function fetchGroupedTestCases(
  query: TestCaseListQuery
): Promise<TestCaseListResult> {
  return fetchTestCases(query)
}

/** 标签视图数据（tag-case-list 消费：前端按 tag 聚合为标签卡；后端 view=tag 契约不消费） */
export async function fetchTagGroupedTestCases(
  query: TestCaseListQuery
): Promise<TestCaseListResult> {
  return fetchTestCases(query)
}

/** 全量圈定每页条数（导出范围翻页；后端 per_page 无上限，此值兼顾响应体量与请求数） */
const ID_SCAN_PAGE_SIZE = 200
/** 翻页硬上限（防后端 pages 异常导致死循环；200×100=2 万条远超单库用例量） */
const ID_SCAN_MAX_PAGES = 100

/**
 * 「当前筛选」全量 id 圈定（INT-1642 导出范围；与列表同端点同口径）。
 * 逐页翻完 GET /testcases 直到最后一页，返回全部命中 id——收藏（favorite）、回收站
 * （only_deleted）、分组（group_id，含未分组哨兵的前端过滤）、标签、维度、算法全部生效，
 * 不退化成「全库」（POST /testcases/ids 后端 fetch_case_ids 不认 favorite，会静默返回全库，
 * 代码审计 P2）也不退化成「仅当前页」。
 */
export async function fetchAllTestCaseIdsByFilter(
  query: TestCaseListQuery
): Promise<string[]> {
  const ids: string[] = []
  for (let page = 1; page <= ID_SCAN_MAX_PAGES; page += 1) {
    const result = await fetchTestCases({
      ...query,
      page,
      perPage: ID_SCAN_PAGE_SIZE,
    })
    ids.push(...result.items.map((c) => c.id))
    // 未分组哨兵在 fetchTestCases 内前端过滤：items 可能少于本页行数，但 pages/total
    // 仍是未过滤集合的分页信息，按 pages 判终止才对。
    const totalPages =
      result.pages ??
      Math.max(1, Math.ceil((result.total || 0) / ID_SCAN_PAGE_SIZE))
    if (page >= totalPages) return ids
  }
  throw new Error('用例数量超出导出范围上限，请缩小筛选条件后重试')
}

/**
 * 用例保存载荷（camelCase Domain 写侧；对照 api_gateway/schemas/testcase.py
 * TestCaseCreateSchema/TestCaseUpdateSchema，Vue testcasesApi.create/update 口径）。
 * config/algorithmParams/referenceParams 值内动态结构原样透传（snake_case 契约，
 * 与 batch API「顶层映射、值内 Dict 透传」一致）。
 */
export interface TestCaseMutatePayload {
  name: string
  description?: string | null
  /** 分组 id（新建「+ 新建分组」时缺省，改走 group 字段） */
  groupId?: string | null
  /** 新建分组名（group_id 缺省时后端按名建组） */
  group?: string | null
  tags?: string[]
  algorithmType?: string | null
  config?: Record<string, unknown> | null
  algorithmParams?: unknown
  referenceParams?: unknown
  /** INT-590：评估策略引用（写时物化；后端契约：显式空字符串 '' 清引用，null/缺省沿用既有引用） */
  strategyId?: string | null
  strategyOverrides?: Record<string, unknown> | null
}

/** 写侧 camelCase → snake_case 顶层映射（值内动态结构原样透传，Vue convertTestCaseFormData 口径） */
const MUTATE_KEY_MAP: Record<string, string> = {
  groupId: 'group_id',
  algorithmType: 'algorithm_type',
  algorithmParams: 'algorithm_params',
  referenceParams: 'reference_params',
  strategyId: 'strategy_id',
  strategyOverrides: 'strategy_overrides',
}

function toTestCaseMutateDto(
  payload: TestCaseMutatePayload
): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(payload)) {
    if (value === undefined) continue
    const snakeKey = MUTATE_KEY_MAP[key] ?? key
    body[snakeKey] = value
  }
  return body
}

/** 创建测试用例（POST /testcases；对照 Vue testcasesApi.create → StringIdData） */
export async function createTestCase(
  payload: TestCaseMutatePayload
): Promise<{ id: string }> {
  const dto = await apiClient.post<{ id?: string | number }>(
    '/testcases',
    toTestCaseMutateDto(payload)
  )
  return { id: String(dto?.id ?? '') }
}

/** 更新测试用例（PUT /testcases/{id}；对照 Vue testcasesApi.update） */
export async function updateTestCase(
  id: string,
  payload: TestCaseMutatePayload
): Promise<void> {
  await apiClient.put(`/testcases/${id}`, toTestCaseMutateDto(payload))
}

/**
 * 删除测试用例（DELETE /testcases/{id}；逻辑删除 → 回收站，Vue testcasesApi.delete）。
 * 若该用例正被活跃任务引用，后端返回错误码 201。
 */
export async function deleteTestCase(id: string): Promise<void> {
  await apiClient.delete(`/testcases/${id}`)
}

/** 复制测试用例（POST /testcases/{id}/copy；深度克隆，新名称默认为「原名称_copy」，返回新用例 id） */
export async function copyTestCase(id: string): Promise<string> {
  const dto = await apiClient.post<{ id?: string | number }>(`/testcases/${id}/copy`)
  return dto?.id != null ? String(dto.id) : ''
}

/** 恢复单个测试用例（POST /testcases/{id}/restore；favorite_trash_bp INT-141） */
export async function restoreTestCase(id: string): Promise<void> {
  await apiClient.post(`/testcases/${id}/restore`)
}

/**
 * 试听测试用例（POST /testcases/{id}/preview；11_用例域.md §5.2 试听三件套接线）。
 * 载荷对照 api_gateway/schemas/testcase.py TestCasePreviewRequest：
 *   { offset（秒）, preview_type, playback_mode }（后端默认 backend，APIModel 同时收 camelCase）；
 * 响应 TestCasePreviewData：frontend 模式回音频流 URL（多轮 audio_stream_urls），
 * backend 模式由网关经播放编排在用例配置设备上放音、只回时长。
 * 失败（未配置音频 / 有待执行 E2E 任务 / 音频引擎不可用）由 client 抛 ApiError，
 * 文案直接取 userMessage（§8「音频试听失败: {err}」）。
 */
export async function previewTestCase(
  id: string,
  payload: {
    offset?: number
    previewType: PreviewPlaybackMode
    playbackMode: PreviewPlaybackMode
  }
): Promise<TestCasePreview> {
  const dto = await apiClient.post<TestCasePreviewDto>(
    `/testcases/${id}/preview`,
    {
      offset: Number.isFinite(payload.offset) ? Number(payload.offset) : 0,
      preview_type: payload.previewType,
      playback_mode: payload.playbackMode,
    }
  )
  return testCasePreviewFromDto(dto)
}

/** 停止试听（POST /testcases/{id}/stop_preview；§5.2 启停语义，随播放器停止/关闭触发） */
export async function stopTestCasePreview(id: string): Promise<void> {
  await apiClient.post(`/testcases/${id}/stop_preview`)
}

/** 彻底删除单个测试用例（DELETE /testcases/{id}/purge；admin/owner 由服务端按 metadata 校验） */
export async function purgeTestCase(id: string): Promise<void> {
  await apiClient.delete(`/testcases/${id}/purge`)
}

/** 收藏 / 取消收藏（POST/DELETE /testcases/{id}/favorite；INT-141 per-user，需带 Bearer 身份；
 *  testcase:read 幂等）。开始测试用例选择行内收藏（INT-1138）：调用后由调用方就地回写列表缓存，
 *  不整表重拉。 */
export async function setTestCaseFavorite(
  id: string,
  favorite: boolean
): Promise<void> {
  if (favorite) await apiClient.post(`/testcases/${id}/favorite`)
  else await apiClient.delete(`/testcases/${id}/favorite`)
}

/** 批量恢复（POST /testcases/restore，{ids}，testcase:delete；返回 restored_count） */
export async function restoreTestCases(ids: string[]): Promise<number> {
  const dto = await apiClient.post<{ restored_count?: number }>(
    '/testcases/restore',
    { ids }
  )
  return dto?.restored_count ?? 0
}

/** 批量彻底删除（POST /testcases/purge，{ids}，testcase:delete；返回 purged_count） */
export async function purgeTestCases(ids: string[]): Promise<number> {
  const dto = await apiClient.post<{ purged_count?: number }>(
    '/testcases/purge',
    { ids }
  )
  return dto?.purged_count ?? 0
}

/** 单轮参考参数文件内容（GET|PUT /testcases/{id}/rounds/{n}/ref-params 实测 data 结构） */
export interface RoundRefParams {
  roundNumber: number
  /** 真实存储路径（config.rounds[].referenceParamsPath，后端回填） */
  referenceParamsPath: string
  /** 文件内容（结构随算法参考参数定义） */
  referenceParams: unknown
}

interface RoundRefParamsDto {
  roundNumber?: number
  referenceParamsPath?: string
  referenceParams?: unknown
}

function toRoundRefParams(
  dto: RoundRefParamsDto | null,
  roundNumber: number
): RoundRefParams {
  return {
    roundNumber: dto?.roundNumber ?? roundNumber,
    referenceParamsPath: dto?.referenceParamsPath ?? '',
    referenceParams: dto?.referenceParams ?? null,
  }
}

/**
 * 读取指定用例指定轮的参考参数文件内容（11_用例域.md §5.1「参考参数」步骤 +
 * §3.3.2 行菜单；testcase_bp.py get_ref_params → task_service get_testcase_ref_params）。
 * 未生成 / 路径不存在时后端 404（调用方按「未生成」空态处理，不作错误）。
 */
export async function fetchRoundRefParams(
  id: string,
  roundNumber: number
): Promise<RoundRefParams> {
  const dto = await apiClient.get<RoundRefParamsDto>(
    `/testcases/${id}/rounds/${roundNumber}/ref-params`
  )
  return toRoundRefParams(dto, roundNumber)
}

/**
 * 写入指定用例指定轮的参考参数文件（PUT .../ref-params，testcase:update）。
 * body 顶层 `referenceParams`（task_service update_ref_params 只认此键）；
 * 成功返回 { roundNumber, referenceParamsPath, referenceParams }（保存后的实际内容）。
 */
export async function updateRoundRefParams(
  id: string,
  roundNumber: number,
  referenceParams: unknown
): Promise<RoundRefParams> {
  const dto = await apiClient.put<RoundRefParamsDto>(
    `/testcases/${id}/rounds/${roundNumber}/ref-params`,
    { referenceParams }
  )
  return toRoundRefParams(dto, roundNumber)
}

/**
 * 导出格式：
 * - zip：后端打包（manifest + testcases.json + 可选参考参数文件），与任务数据导出口径一致；
 * - xlsx：后端直接回 xlsx 字节流；
 * - json：后端返回 JSON 数据信封，前端序列化为 .json 文件下载。
 */
export type TestCaseExportFormat = 'zip' | 'json' | 'xlsx'

export interface TestCaseExportOptions {
  /** ZIP 数据包是否包含参考参数文件（默认包含） */
  includeReferenceParams?: boolean
}

export interface TestCaseExportResult {
  blob: Blob
  filename: string
}

/** 导出文件名时间戳（yyyyMMdd_HHmmss，与后端 download_name 同口径） */
function exportTimestamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

/**
 * 导出用例（POST /testcases/export，testcase:import_export）。
 * format=zip 走 ZIP 数据包（含参考参数文件开关）；format=xlsx 走 xlsx 字节流；
 * format=json 走 success_response（数据在信封 data，结构 {test_cases, exported_at,
 * total_count}，与导入端往返一致），前端序列化落文件。
 * 空 ids 后端 400「未指定要导出的用例ID」由 client 抛 ApiError。
 */
export async function exportTestCases(
  ids: string[],
  format: TestCaseExportFormat,
  options: TestCaseExportOptions = {}
): Promise<TestCaseExportResult> {
  const extension = format === 'json' ? 'json' : format
  const filename = `testcases_export_${exportTimestamp()}.${extension}`
  if (format === 'zip' || format === 'xlsx') {
    const body: Record<string, unknown> = { ids, format }
    if (format === 'zip') {
      body.include_reference_params = options.includeReferenceParams ?? true
    }
    const blob = await apiClient.post<Blob>('/testcases/export', body, {
      responseType: 'blob',
    })
    return { blob, filename }
  }
  const data = await apiClient.post<unknown>('/testcases/export', { ids, format: 'json' })
  return {
    blob: new Blob([JSON.stringify(data ?? {}, null, 2)], {
      type: 'application/json',
    }),
    filename,
  }
}

/**
 * 用例导入预览（POST /testcases/import/preview，multipart，testcase:import_export）。
 * 支持 JSON/CSV/Excel/ZIP 用例包；返回总行数 + 重复用例清单（ID 或同分组同名命中），
 * 供导入弹窗展示并选择覆盖/跳过/另存副本。
 */
export async function previewTestCasesImport(
  file: File
): Promise<TestCaseImportPreview> {
  const formData = new FormData()
  formData.append('file', file)
  const dto = await apiClient.post<TestCaseImportPreviewDto>(
    '/testcases/import/preview',
    formData
  )
  return testCaseImportPreviewFromDto(dto)
}

/**
 * 执行用例导入（POST /testcases/import，multipart，testcase:import_export）。
 * `on_duplicate`：skip（默认）/ overwrite / copy；回执含新增/覆盖/跳过/副本计数与逐行错误。
 */
export async function importTestCases(
  file: File,
  onDuplicate: TestCaseDuplicateStrategy
): Promise<TestCaseImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('on_duplicate', onDuplicate)
  const dto = await apiClient.post<TestCaseImportResultDto>(
    '/testcases/import',
    formData
  )
  return testCaseImportResultFromDto(dto)
}

/** 模板下载文件名（与后端 Content-Disposition 同名口径：testcase_template_YYYYmmdd_HHMMSS.xlsx） */
export function buildTestCaseTemplateFilename(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `testcase_template_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.xlsx`
}

export interface TestCaseTemplateResult {
  blob: Blob
  filename: string
}

/**
 * 下载导入模板（GET /testcases/template/download，testcase:import_export；
 * 11_用例域.md §5.7.3 + testcase_bp.py 实测挂码）。
 * 后端回 xlsx 附件字节流（Content-Type application/vnd.openxmlformats-…sheet，
 * Content-Disposition attachment；文件名由前端按同口径生成），不走 JSON 信封。
 */
export async function downloadTestCaseTemplate(): Promise<TestCaseTemplateResult> {
  const blob = await apiClient.get<Blob>('/testcases/template/download', {
    responseType: 'blob',
  })
  return { blob, filename: buildTestCaseTemplateFilename() }
}
