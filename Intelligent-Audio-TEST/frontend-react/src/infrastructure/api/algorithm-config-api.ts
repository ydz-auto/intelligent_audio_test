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
 *   GET    /api/v1/evaluation/dimensions/options    评估维度选项（关联维度 Select 数据源）
 *   GET    /api/v1/testcases                        用例引用聚合兜底（§154：后端未返回
 *                                                   case_count 时按用例 algorithm_type 计数）
 */
import type {
  AlgorithmDefinition,
  AlgorithmGroup,
} from '@/domain/models/algorithmConfig'
import { request } from '@/infrastructure/api/client'
import { ApiError } from '@/infrastructure/api/api-error'
import { fetchDimensionOptions } from '@/infrastructure/api/evaluation-api'
import { fetchTestCases } from '@/infrastructure/api/testcases-api'
import {
  toAlgorithmDefinition,
  toAlgorithmDefinitionList,
  toAlgorithmDefinitionDto,
  toAlgorithmGroup,
  toAlgorithmGroupList,
  toAlgorithmGroupDto,
  toBulkDeleteDto,
  toBulkDeleteResult,
  toImportDto,
  toImportResult,
  toReloadConfigResult,
  type AlgorithmBulkDeleteResultDto,
  type AlgorithmDefinitionDto,
  type AlgorithmDefinitionListDto,
  type AlgorithmGroupDto,
  type AlgorithmGroupListDto,
  type AlgorithmImportResultDto,
  type ReloadConfigDto,
} from '@/infrastructure/dto/algorithm-config.dto'

/** 算法列表全量（§3.2 现接口无分页参数，前端分页） */
export async function fetchAlgorithmDefinitions(): Promise<AlgorithmDefinition[]> {
  const dto = await request<AlgorithmDefinitionListDto>(
    'GET',
    '/algorithm/definitions'
  )
  const list = toAlgorithmDefinitionList(dto)
  // §3.4/§154：后端返回 case_count 时直接消费；未返回（INT-591 契约未达）时按用例引用聚合兜底，
  // 让「关联用例」列展示真实引用数而非恒 0
  const hasBackendCount = (dto?.items ?? []).some((item) => item.case_count != null)
  if (!hasBackendCount) {
    const counts = await fetchCaseCountByAlgorithmType(list.map((d) => d.type))
    for (const def of list) {
      const count = counts.get(def.type)
      if (count != null) def.caseCount = count
    }
  }
  // 关联维度名补全（后端 associated_dimensions 仅回 dimension_id，照 Vue 从维度选项解析）
  await enrichAssociatedDimensionNames(list)
  return list
}

/** 用例引用聚合兜底（§154）：按算法 type 逐个经 testcases 的 algorithm_type 筛选读 total 计数 */
async function fetchCaseCountByAlgorithmType(
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
        // 单类型计数失败不影响其余；用例端不可达时该类型归 0
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
  const detail = toAlgorithmDefinition(dto)
  await enrichAssociatedDimensionNames([detail])
  return detail
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

/* ───────── 评估维度名 → id 解析（写侧 evaluation 映射的 dimension_id 对账） ───────── */

let dimensionOptionsCache: Map<string, number> | null = null
let dimensionOptionsCachedAt = 0
const DIMENSION_OPTIONS_TTL_MS = 5 * 60_000

/** 评估维度名 → id 映射（短 TTL 缓存；失败返回 null 由调用方按空表兜底） */
async function resolveDimensionIdByName(): Promise<Map<string, number>> {
  const now = Date.now()
  if (dimensionOptionsCache && now - dimensionOptionsCachedAt < DIMENSION_OPTIONS_TTL_MS) {
    return dimensionOptionsCache
  }
  try {
    const options = await fetchDimensionOptions()
    const map = new Map(options.map((d) => [d.name, d.id]))
    dimensionOptionsCache = map
    dimensionOptionsCachedAt = now
    return map
  } catch {
    // 维度选项不可达时按空表兜底：evaluation 映射降级为仅提交 target_param，不阻断保存
    return new Map()
  }
}

/** 评估维度 id → 名 解析（读侧详情/列表「关联维度」展示；后端 associated_dimensions
 *  仅回 dimension_id 不回名称，照 Vue 从维度选项解析口径补名）。 */
async function resolveDimensionNameById(): Promise<Map<number, string>> {
  try {
    const options = await fetchDimensionOptions()
    return new Map(options.map((d) => [d.id, d.name]))
  } catch {
    // 维度选项不可达时按空表兜底：名称保持后端原值（可能为空串），不阻断列表
    return new Map()
  }
}

/** 列表/详情共用的关联维度名称补全（dimensionId → 维度名；后端无 dimension_name 时回填） */
async function enrichAssociatedDimensionNames(
  defs: AlgorithmDefinition[]
): Promise<void> {
  const nameById = await resolveDimensionNameById()
  for (const def of defs) {
    for (const rel of def.associatedDimensions ?? []) {
      if (!rel.dimensionName && nameById.has(rel.dimensionId)) {
        rel.dimensionName = nameById.get(rel.dimensionId) ?? ''
      }
    }
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

/** 新建算法（§6.1 create；聚合提交 POST /algorithm/definitions） */
export async function createAlgorithm(
  input: SaveAlgorithmInput
): Promise<AlgorithmDefinition> {
  const body = await buildDefinitionDto(input)
  const dto = await request<AlgorithmDefinitionDto>('POST', '/algorithm/definitions', body)
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

/** 批量删除（§7.8；POST /algorithm/bulk-delete，deleted_types 对账计数） */
export async function bulkDeleteAlgorithms(types: string[]): Promise<{
  successCount: number
  failedCount: number
}> {
  const dto = await request<AlgorithmBulkDeleteResultDto>(
    'POST',
    '/algorithm/bulk-delete',
    toBulkDeleteDto(types)
  )
  return toBulkDeleteResult(dto, types)
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

/* ───────────────────────── INT-591 草稿/发布（§6.2，后端 RPC 未落定） ─────────────────────────
 * 后端「算法定义全量保存事务 RPC」（主项目后端卡：草稿分支 + 发布事务 + 乐观锁 revision/force +
 * has_draft）落定后按契约平移；落定前 saveAlgorithmDraft 保留 mock 形态（仅回时间戳/版本号），
 * publishAlgorithm 走真实 create/update。乐观锁冲突 UI（AlgorithmConflictError）等待后端 RPC
 * 提供 revision 条件更新与 409 语义后启用；缺口证据见 INT-647 交付评论。
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

/** mock 草稿版本号（后端 RPC 未落定前的本地回执；接线后删除） */
const draftRevisionMap = new Map<string, number>()

/** 草稿保存（§6.2 draft 分支；后端 RPC 落定前按 §6.2 UI 契约出 mock 回执） */
export async function saveAlgorithmDraft(
  input: SaveAlgorithmInput,
  _revision?: number
): Promise<DraftSaveResult> {
  // TODO(API 接线): 后端定义全量保存 RPC draft 分支（草稿落库 + 乐观锁 revision）
  const type = input.type.trim() || '__new__'
  const next = (draftRevisionMap.get(type) ?? 0) + 1
  draftRevisionMap.set(type, next)
  return { revision: next, savedAt: new Date().toISOString() }
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
