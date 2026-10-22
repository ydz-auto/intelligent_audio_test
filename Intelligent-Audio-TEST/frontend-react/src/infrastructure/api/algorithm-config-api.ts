/**
 * 算法配置 API（infrastructure 层；17_配置运维.md §11 组件树落位）。
 * INT-647 接线：infra mock→api，全部真实端点经 client.ts 统一 fetch 封装（INT-605 基座），
 * snake_case 契约仅存在于 infrastructure/dto/algorithm-config.dto.ts（唯一转换层）。
 *
 * 端点契约（api_gateway/routes/algorithm_bp.py）：
 *   GET    /api/v1/algorithm/definitions            列表（INT-297 信封 {items,total,...}）
 *   GET    /api/v1/algorithm/definitions/{type}     详情（编辑/复制预填，§6.1）
 *   POST   /api/v1/algorithm/definitions            新建（参数/映射/维度随定义聚合落库）
 *   PUT    /api/v1/algorithm/definitions/{type}     编辑
 *   DELETE /api/v1/algorithm/definitions/{type}     删除
 *   GET    /api/v1/algorithm/groups                 分组列表（INT-297 信封）
 *   POST   /api/v1/algorithm/groups                 新建分组
 *   PUT    /api/v1/algorithm/groups/{id}            编辑分组
 *   DELETE /api/v1/algorithm/groups/{id}            删除分组
 *   POST   /api/v1/algorithm/import                 导入（{ algorithms: [...] }）
 *   POST   /api/v1/algorithm/reload                 重载配置缓存
 *   POST   /api/v1/algorithm/bulk-delete            批量删除（{ algorithm_types: [...] }）
 *   PUT    /api/v1/algorithm/definitions/draft      草稿保存（完整定义快照 + algorithm_type，§6.2/INT-589）
 *   GET    /api/v1/algorithm/definitions/draft/{type}  草稿恢复（空 {} = 无草稿）
 *   GET    /api/v1/evaluation/dimensions/options    评估维度选项（关联维度 Select 数据源）
 *   GET    /api/v1/testcases                        用例引用聚合兜底（§154：后端未返回
 *                                                   case_count 时按用例 algorithm_type 计数）
 */
import type {
  AlgorithmDefinition,
  AlgorithmGroup,
  DimensionParam,
} from '@/domain/models/algorithmConfig'
import { request } from '@/infrastructure/api/client'
import { ApiError } from '@/infrastructure/api/api-error'
import { fetchEvaluationDimensions } from '@/infrastructure/api/evaluation-api'
import { fetchTestCases } from '@/infrastructure/api/testcases-api'
import {
  toAlgorithmDefinition,
  toAlgorithmDefinitionList,
  toAlgorithmDefinitionDto,
  toAlgorithmGroup,
  toAlgorithmGroupList,
  toAlgorithmGroupDto,
  toBulkDeleteDto,
  toDimensionParam,
  toImportDto,
  toImportResult,
  toReloadConfigResult,
  type AlgorithmBulkDeleteResultDto,
  type AlgorithmDefinitionDto,
  type AlgorithmDefinitionListDto,
  type AlgorithmDraftSaveResultDto,
  type AlgorithmGroupDto,
  type AlgorithmGroupListDto,
  type AlgorithmImportResultDto,
  type DimensionParamDto,
  type ReloadConfigDto,
} from '@/infrastructure/dto/algorithm-config.dto'

/** 算法列表全量（§3.2 现接口无分页参数，前端分页） */
export async function fetchAlgorithmDefinitions(): Promise<AlgorithmDefinition[]> {
  const dto = await request<AlgorithmDefinitionListDto>(
    'GET',
    '/algorithm/definitions',
    undefined,
    {
      // INT-1225：/rankings 公开页算法卡片网格同源消费本端点（useRankingAlgorithm，
      // 14_benchmark排行.md §4.5），匿名 401 不触发 sessionExpired 整页跳登录——
      // 页面按只读降级条/「算法详情暂不可用」降级。
      skipAuthRedirect: true,
    }
  )
  // P3-1（INT-1319）：后端列表项无 case_count 时不再在这里逐算法用例聚合兜底——
  // 那会让整表等 8-15s 才渲染；改由 useAlgorithmCaseCounts 经
  // fetchCaseCountByAlgorithmType 异步补齐「关联用例」列，列表首屏先渲染 definitions。
  return toAlgorithmDefinitionList(dto)
}

/** 用例引用聚合兜底（§154/P3-1（INT-1319））：按算法 type 逐个经 testcases 的
 *  algorithm_type 筛选读 total 计数，返回 type → count Map；由
 *  useAlgorithmCaseCounts 异步消费，单类型计数失败不影响其余（该类型保持 null/0）。 */
export async function fetchCaseCountByAlgorithmType(
  types: string[]
): Promise<Map<string, number>> {
  const counts = new Map<string, number>()
  await Promise.all(
    [...new Set(types.filter(Boolean))].map(async (type) => {
      try {
        const { total } = await fetchTestCases({
          page: 1,
          perPage: 1,
          algorithmType: type,
        })
        counts.set(type, total)
      } catch {
        // 单类型计数失败不影响其余；用例端不可达时该类型不落表
      }
    })
  )
  return counts
}

/** 算法详情（§6.1 编辑/复制预填） */
export async function fetchAlgorithmDetail(
  type: string
): Promise<AlgorithmDefinition | undefined> {
  const dto = await request<AlgorithmDefinitionDto>(
    'GET',
    `/algorithm/definitions/${encodeURIComponent(type)}`
  )
  return toAlgorithmDefinition(dto)
}

/** 分组列表（facet 选项 + §7.1 分组管理 + 编辑 Sheet 所属分组 Select 共用） */
export async function fetchAlgorithmGroups(): Promise<AlgorithmGroup[]> {
  const dto = await request<AlgorithmGroupListDto>('GET', '/algorithm/groups')
  return toAlgorithmGroupList(dto)
}

export type SaveAlgorithmInput = {
  id?: number
  type: string
  name: string
  groupId: number | null
  displayOrder: number
  status: 'online' | 'offline'
  description: string
  deviceParams: Array<Record<string, unknown>>
  apiParams: Array<Record<string, unknown>>
  caseParams: Array<Record<string, unknown>>
  referenceParams: Array<Record<string, unknown>>
  mappings: { device: unknown[]; api: unknown[]; evaluation: unknown[] }
  associatedDimensions: Array<Record<string, unknown>>
}

/** 评估维度参数（evaluation 映射「目标参数」下拉数据源；GET /algorithm/dimension-params/{id}） */
export async function fetchDimensionParams(
  dimensionId: number
): Promise<DimensionParam[]> {
  const dto = await request<{ params?: DimensionParamDto[] }>(
    'GET',
    `/algorithm/dimension-params/${dimensionId}`
  )
  return (Array.isArray(dto?.params) ? dto.params : []).map(toDimensionParam)
}

/* ───────── 评估维度名 → id 解析（写侧 evaluation 映射的 dimension_id 对账） ───────── */

let dimensionOptionsCache: Map<string, number> | null = null
let dimensionOptionsCachedAt = 0
const DIMENSION_OPTIONS_TTL_MS = 5 * 60_000

/**
 * 评估维度名 → id 映射（短 TTL 缓存；失败返回 null 由调用方按空表兜底）。
 * INT-1030：评估映射 target 改分组/主维度/子维度可选择，名→id 解析必须覆盖子维度
 * （/evaluation/dimensions/options 仅主维度，换 /evaluation/dimensions 全量）。
 */
async function resolveDimensionIdByName(): Promise<Map<string, number>> {
  const now = Date.now()
  if (dimensionOptionsCache && now - dimensionOptionsCachedAt < DIMENSION_OPTIONS_TTL_MS) {
    return dimensionOptionsCache
  }
  try {
    const dimensions = await fetchEvaluationDimensions()
    const map = new Map(dimensions.map((d) => [d.name, Number(d.id)]))
    dimensionOptionsCache = map
    dimensionOptionsCachedAt = now
    return map
  } catch {
    // 维度选项不可达时按空表兜底：evaluation 映射降级为仅提交 target_param，不阻断保存
    return new Map()
  }
}

/** 保存请求体（snake_case；evaluation 映射 targetParam=维度名 → dimension_id 解析） */
async function buildDefinitionDto(input: SaveAlgorithmInput): Promise<Record<string, unknown>> {
  const dimensionIdByName = await resolveDimensionIdByName()
  const asRows = (rows: unknown[]): Array<Record<string, unknown>> =>
    (rows ?? []) as Array<Record<string, unknown>>
  return toAlgorithmDefinitionDto(
    {
      type: input.type,
      name: input.name,
      groupId: input.groupId,
      displayOrder: input.displayOrder,
      status: input.status,
      description: input.description,
      deviceParams: input.deviceParams,
      apiParams: input.apiParams,
      caseParams: input.caseParams,
      referenceParams: input.referenceParams,
      mappings: {
        device: asRows(input.mappings.device),
        api: asRows(input.mappings.api),
        evaluation: asRows(input.mappings.evaluation),
      },
      associatedDimensions: input.associatedDimensions,
    },
    dimensionIdByName
  )
}

/** 新建算法（§6.1 create；聚合提交 POST /algorithm/definitions）
 *  INT-1317：后端 create 走 draft 语义（无论提交 online/offline 都落库 status="draft"，
 *  见 INT-1253 走查证据），发布后如后端返回 status 与表单所选不一致，立即补一次 PUT
 *  应用所选 status（PUT 走 update 语义落库正常）；后端 FEAT 修复后此条件不触发、零额外请求。 */
export async function createAlgorithm(
  input: SaveAlgorithmInput
): Promise<AlgorithmDefinition> {
  const body = await buildDefinitionDto(input)
  const dto = await request<AlgorithmDefinitionDto>('POST', '/algorithm/definitions', body)
  // INT-1317：create 落 draft / 状态丢失 → 用表单所选 status 补一次 PUT，避免列表徽章误显「上线」
  if (typeof dto?.status === 'string' && dto.status !== input.status) {
    const patched = await request<AlgorithmDefinitionDto>(
      'PUT',
      `/algorithm/definitions/${encodeURIComponent(input.type)}`,
      body
    )
    return toAlgorithmDefinition(patched)
  }
  return toAlgorithmDefinition(dto)
}

/** 编辑算法（§6.1 edit；聚合提交 PUT /algorithm/definitions/{type}） */
export async function updateAlgorithm(
  type: string,
  input: SaveAlgorithmInput
): Promise<AlgorithmDefinition> {
  const body = await buildDefinitionDto(input)
  const dto = await request<AlgorithmDefinitionDto>(
    'PUT',
    `/algorithm/definitions/${encodeURIComponent(type)}`,
    body
  )
  return toAlgorithmDefinition(dto)
}

/** 删除算法（§7.5；后端软删除，引用校验由后端契约把关，失败走 ApiError 抛错） */
export async function deleteAlgorithm(
  type: string
): Promise<{ success: boolean; message?: string }> {
  await request('DELETE', `/algorithm/definitions/${encodeURIComponent(type)}`)
  return { success: true }
}

/** 批量删除（§7.8；POST /algorithm/bulk-delete，deleted_types 对账计数）。
 * INT-1316：真实栈 bulk-delete 后端 soft_delete 未生效（报成功但记录残留，单删正常），
 * 批量后逐类型复核详情，仍存在的记录回退单条删除，计数以实际落删为准。 */
export async function bulkDeleteAlgorithms(types: string[]): Promise<{
  successCount: number
  failedCount: number
}> {
  const requested = [...new Set(types.filter(Boolean))]
  if (requested.length === 0) return { successCount: 0, failedCount: 0 }

  // 1) 批量软删（后端正常时一次完成）
  await request<AlgorithmBulkDeleteResultDto>(
    'POST',
    '/algorithm/bulk-delete',
    toBulkDeleteDto(requested)
  )

  // 2) INT-1316 复核：deleted_types 不可信（真实栈批量软删未生效），逐类型查详情，
  //    仍存在的类型回退单条删除（单删可靠），计数以实际落删为准
  const existsFlags = await Promise.all(
    requested.map((type) => algorithmStillExists(type))
  )
  const stillPresent = requested.filter((_, index) => existsFlags[index])

  const fallbackResults = await Promise.all(
    stillPresent.map(async (type) => {
      try {
        await deleteAlgorithm(type)
        return true
      } catch {
        return false
      }
    })
  )
  const failedCount = fallbackResults.filter((ok) => !ok).length
  return { successCount: requested.length - failedCount, failedCount }
}

/** 算法是否仍存在（detail 200 且 type 非空 → 存在；404/400-not-found → 已删） */
async function algorithmStillExists(type: string): Promise<boolean> {
  try {
    const detail = await fetchAlgorithmDetail(type)
    return detail != null && detail.type !== ''
  } catch (error) {
    if (isAlgorithmNotFound(error)) return false
    throw error
  }
}

/** 重载配置（§7.7；POST /algorithm/reload） */
export async function reloadAlgorithmConfig(): Promise<{
  success: boolean
  reloadTime: string
}> {
  const dto = await request<ReloadConfigDto>('POST', '/algorithm/reload')
  return toReloadConfigResult(dto)
}

/** 导入算法（§7.6；POST /algorithm/import，返回实际导入数） */
export async function importAlgorithms(
  algorithms: unknown[]
): Promise<{ importedCount: number }> {
  const dto = await request<AlgorithmImportResultDto>(
    'POST',
    '/algorithm/import',
    toImportDto(algorithms)
  )
  return toImportResult(dto)
}

/* ───────────────────────── 分组 CRUD（§7.1） ───────────────────────── */

export type SaveGroupInput = {
  name: string
  description: string
  icon: string
  displayOrder: number
}

/** 新建分组 */
export async function createAlgorithmGroup(
  input: SaveGroupInput
): Promise<AlgorithmGroup> {
  const dto = await request<AlgorithmGroupDto>(
    'POST',
    '/algorithm/groups',
    toAlgorithmGroupDto(input)
  )
  return toAlgorithmGroup(dto)
}

/** 编辑分组 */
export async function updateAlgorithmGroup(
  id: number,
  input: SaveGroupInput
): Promise<AlgorithmGroup> {
  const dto = await request<AlgorithmGroupDto>(
    'PUT',
    `/algorithm/groups/${id}`,
    toAlgorithmGroupDto(input)
  )
  return toAlgorithmGroup(dto)
}

/** 删除分组（§3.6 cascade 语义：删分组、其下算法保留并变未分组，后端 soft_delete） */
export async function deleteAlgorithmGroup(
  id: number
): Promise<{ success: boolean; message?: string }> {
  await request('DELETE', `/algorithm/groups/${id}`)
  return { success: true }
}

/* ───────────────────────── INT-591/INT-589 草稿（§6.2，后端草稿 RPC 已落定） ─────────────────────────
 * 草稿保存 = PUT /algorithm/definitions/draft（完整定义快照 + algorithm_type，不落正式六表）；
 * 草稿恢复 = GET /algorithm/definitions/draft/{type}（空 {} = 无草稿）。发布走 create/update，
 * 后端发布事务成功时清除草稿快照（clear_snapshot）。乐观锁冲突 UI（AlgorithmConflictError）
 * 等待后端提供 revision 条件更新与 409 语义后启用；缺口证据见 INT-647 交付评论。
 */

/** 草稿保存成功结果（footer「上次保存 HH:mm:ss」时间戳 + 乐观锁版本号） */
export type DraftSaveResult = {
  revision: number
  savedAt: string
}

/** 乐观锁冲突错误（§6.2a：409 + 服务端最新版本；发布冲突与草稿冲突共用，后端 RPC 落定后启用） */
export class AlgorithmConflictError extends Error {
  status = 409
  latestRevision: number
  constructor(latestRevision: number) {
    super('算法定义已被他人修改')
    this.name = 'AlgorithmConflictError'
    this.latestRevision = latestRevision
  }
}

/** 草稿恢复（§6.2 编辑态打开先读草稿；空 {} = 无草稿，返回 undefined） */
export async function fetchAlgorithmDraft(
  type: string
): Promise<AlgorithmDefinition | undefined> {
  const dto = await request<AlgorithmDefinitionDto>(
    'GET',
    `/algorithm/definitions/draft/${encodeURIComponent(type)}`
  )
  // 后端无草稿返回 data:{}（空对象）；有草稿返回完整快照（snake_case，type 键可经 toAlgorithmDefinition 还原）
  if (!dto || typeof dto !== 'object' || Object.keys(dto).length === 0) {
    return undefined
  }
  return toAlgorithmDefinition(dto)
}

/** 草稿保存（§6.2 draft 分支；PUT /algorithm/definitions/draft，快照落库 + 服务端 saved_at 回执） */
export async function saveAlgorithmDraft(
  input: SaveAlgorithmInput,
  _revision?: number
): Promise<DraftSaveResult> {
  const body = await buildDefinitionDto(input)
  // 草稿快照归属键：后端 SaveAlgorithmDefinitionDraft 按 algorithm_type 落 PO（type 兼容读）
  body.algorithm_type = input.type
  const data = await request<AlgorithmDraftSaveResultDto>(
    'PUT',
    '/algorithm/definitions/draft',
    body
  )
  return {
    // 后端草稿保存仅回 success（无版本号），revision 恒 0；saved_at 服务端时间，缺省取本端
    revision: 0,
    savedAt: data?.saved_at ?? new Date().toISOString(),
  }
}

/** 发布（§6.2 发布事务；后端 RPC 未落定前 = 真实 create/update，revision 条件更新待后端） */
export async function publishAlgorithm(
  input: SaveAlgorithmInput,
  _revision?: number
): Promise<AlgorithmDefinition> {
  // 探测存量：GET detail「不存在」→ 新建。后端网关对缺失算法实际返回 400 + 「not found」
  // （wrap_grpc_response 将 gRPC 404 映射为 HTTP 400），故 404/400-not-found 均判新；其他错误原样抛出
  let isNew = false
  try {
    isNew = !(await fetchAlgorithmDetail(input.type))
  } catch (error) {
    if (isAlgorithmNotFound(error)) {
      isNew = true
    } else {
      throw error
    }
  }
  return isNew
    ? createAlgorithm(input)
    : updateAlgorithm(input.type, input)
}

/** 算法不存在的错误判定（网关缺失算法 = HTTP 400 + 「Algorithm not found」/ 404） */
function isAlgorithmNotFound(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  if (error.httpStatus === 404) return true
  if (error.httpStatus === 400) {
    const message = error.serverMessage ?? ''
    return /not found|不存在|未找到/i.test(message)
  }
  return false
}
