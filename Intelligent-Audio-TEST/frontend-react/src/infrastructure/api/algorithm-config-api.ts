/**
 * 算法配置 API 桩（infrastructure 层；17_配置运维.md §11 组件树落位）。
 * 红线④：全部返回 mock 常量（algorithm-config-mock），接线时替换为真实请求：
 *   GET    /api/v1/algorithm/definitions            列表（全量返回，前端分页，§12-4）
 *   GET    /api/v1/algorithm/definitions/{type}     详情（编辑/复制预填，§6.1）
 *   POST   /api/v1/algorithm/definitions            新建（参数/映射/维度随定义聚合落库）
 *   PUT    /api/v1/algorithm/definitions/{type}     编辑
 *   DELETE /api/v1/algorithm/definitions/{type}     删除
 *   GET    /api/v1/algorithm/groups                 分组列表
 *   POST   /api/v1/algorithm/groups                 新建分组
 *   PUT    /api/v1/algorithm/groups/{id}            编辑分组
 *   DELETE /api/v1/algorithm/groups/{id}            删除分组
 *   POST   /api/v1/algorithm/import                 导入（JSON 数组）
 *   POST   /api/v1/algorithm/reload                 重载配置缓存
 *   POST   /api/v1/algorithm/bulk-delete            批量删除
 */
import type {
  AlgorithmDefinition,
  AlgorithmGroup,
  AlgorithmMappings,
  CaseParam,
  DeviceApiParam,
  ParamMapping,
  DimensionRelation,
  ReferenceParam,
} from '@/domain/models/algorithmConfig'
import {
  MOCK_ALGORITHM_DEFINITIONS,
  MOCK_ALGORITHM_GROUPS,
} from '../mock/algorithm-config-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T, ms = 180): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

/** 生成新 id（mock 阶段自增；接线后走后端自增） */
let nextId = 1000
let nextGroupId = 500

function freshId(): number {
  nextId += 1
  return nextId
}

/** mock 内存库（页面内增删改操作在运行时可变） */
let definitionsStore: AlgorithmDefinition[] = [...MOCK_ALGORITHM_DEFINITIONS]
let groupsStore: AlgorithmGroup[] = [...MOCK_ALGORITHM_GROUPS]

function syncGroupCounts(): void {
  groupsStore = groupsStore.map((group) => ({
    ...group,
    algorithmCount: definitionsStore.filter(
      (d) => d.groupId === group.id
    ).length,
  }))
}

/** 算法列表全量（§3.2 现接口无分页参数，前端分页） */
export async function fetchAlgorithmDefinitions(): Promise<AlgorithmDefinition[]> {
  // TODO(API 接线): GET /api/v1/algorithm/definitions
  return mockLatency(definitionsStore)
}

/** 算法详情（§6.1 编辑/复制预填） */
export async function fetchAlgorithmDetail(
  type: string
): Promise<AlgorithmDefinition | undefined> {
  // TODO(API 接线): GET /api/v1/algorithm/definitions/{type}
  return mockLatency(definitionsStore.find((d) => d.type === type))
}

/** 分组列表（facet 选项 + §7.1 分组管理 + 编辑 Sheet 所属分组 Select 共用） */
export async function fetchAlgorithmGroups(): Promise<AlgorithmGroup[]> {
  // TODO(API 接线): GET /api/v1/algorithm/groups
  syncGroupCounts()
  return mockLatency(groupsStore)
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

/** 表单行 → 域模型（mock 阶段补行级 id；接线后走后端字段契约） */
function rowsToDomain(
  rows: Array<Record<string, unknown>>,
  kind: 'device' | 'api' | 'case' | 'reference'
): unknown[] {
  let paramCounter = 20000
  return rows.map((row) => {
    paramCounter += 1
    const base: Record<string, unknown> = { id: paramCounter }
    if (kind === 'device' || kind === 'api') {
      base.paramCode = row.paramCode
      base.paramName = row.paramName || null
      base.label = row.paramName || null
      base.paramType = row.paramType
      base.direction = row.direction
      base.required = Boolean(row.required)
      base.defaultValue = null
      base.helpText = row.helpText || null
      base.uiOrder = paramCounter
      base.hidden = false
    } else if (kind === 'case') {
      base.paramCode = row.paramCode
      base.paramName = row.paramName || null
      base.label = row.paramName || null
      base.paramType = row.paramType
      base.required = Boolean(row.required)
      base.defaultValue = row.defaultValue || null
      base.helpText = row.helpText || null
      base.uiOrder = paramCounter
      base.hidden = false
      base.scope = row.scope ?? 'common'
      base.minValue = row.minValue ? Number(row.minValue) : null
      base.maxValue = row.maxValue ? Number(row.maxValue) : null
      base.step = row.step ? Number(row.step) : null
      base.unit = row.unit || null
      base.annotationCode = row.annotationCode || null
      base.fieldPath = row.fieldPath || null
    } else {
      base.code = row.code
      base.name = row.name
      base.type = row.type
      base.annotationCode = row.annotationCode || null
      base.annotationFormat = row.annotationFormat || null
      base.fieldPath = row.fieldPath || null
      base.mergeMode = row.mergeMode || null
      base.helpText = row.helpText || null
    }
    return base
  })
}

/** 映射行 → 域模型 */
function mappingsToDomain(mappings: {
  device: unknown[]
  api: unknown[]
  evaluation: unknown[]
}): AlgorithmMappings {
  let counter = 30000
  const map = (rows: unknown[]): ParamMapping[] =>
    rows.map((row) => {
      counter += 1
      const r = row as Record<string, unknown>
      return {
        id: counter,
        sourceParam: String(r.sourceParam ?? ''),
        targetParam: String(r.targetParam ?? ''),
        transformType: (r.transformType ?? 'none') as ParamMapping['transformType'],
      }
    })
  return {
    device: map(mappings.device),
    api: map(mappings.api),
    evaluation: map(mappings.evaluation),
  }
}

/** 维度关联行 → 域模型 */
function dimensionsToDomain(
  rows: Array<Record<string, unknown>>
): DimensionRelation[] {
  let counter = 40000
  return rows.map((row) => {
    counter += 1
    return {
      id: counter,
      dimensionId: Number(row.dimensionId),
      dimensionName: String(row.dimensionName ?? ''),
      weight: row.weight ? Number(row.weight) : 1,
      isDefault: Boolean(row.isDefault),
    }
  })
}

/** 新建算法（§6.1 create；聚合提交） */
export async function createAlgorithm(
  input: SaveAlgorithmInput
): Promise<AlgorithmDefinition> {
  // TODO(API 接线): POST /api/v1/algorithm/definitions
  const group = groupsStore.find((g) => g.id === input.groupId)
  const definition: AlgorithmDefinition = {
    id: input.id ?? freshId(),
    type: input.type,
    name: input.name,
    groupId: input.groupId,
    groupName: group?.name ?? null,
    category: null,
    description: input.description || null,
    status: input.status,
    icon: null,
    displayOrder: input.displayOrder,
    deviceParams: rowsToDomain(input.deviceParams, 'device') as DeviceApiParam[],
    apiParams: rowsToDomain(input.apiParams, 'api') as DeviceApiParam[],
    caseParams: rowsToDomain(input.caseParams, 'case') as CaseParam[],
    referenceParams: rowsToDomain(input.referenceParams, 'reference') as ReferenceParam[],
    mappings: mappingsToDomain(input.mappings),
    associatedDimensions: dimensionsToDomain(input.associatedDimensions),
    caseCount: 0,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }
  definitionsStore = [...definitionsStore, definition]
  syncGroupCounts()
  return mockLatency(definition, 120)
}

/** 编辑算法（§6.1 edit；聚合提交） */
export async function updateAlgorithm(
  type: string,
  input: SaveAlgorithmInput
): Promise<AlgorithmDefinition> {
  // TODO(API 接线): PUT /api/v1/algorithm/definitions/{type}
  const existing = definitionsStore.find((d) => d.type === type)
  const group = groupsStore.find((g) => g.id === input.groupId)
  const updated: AlgorithmDefinition = existing
    ? {
        ...existing,
        name: input.name,
        groupId: input.groupId,
        groupName: group?.name ?? null,
        description: input.description || null,
        status: input.status,
        displayOrder: input.displayOrder,
        deviceParams: rowsToDomain(input.deviceParams, 'device') as DeviceApiParam[],
        apiParams: rowsToDomain(input.apiParams, 'api') as DeviceApiParam[],
        caseParams: rowsToDomain(input.caseParams, 'case') as CaseParam[],
        referenceParams: rowsToDomain(input.referenceParams, 'reference') as ReferenceParam[],
        mappings: mappingsToDomain(input.mappings),
        associatedDimensions: dimensionsToDomain(input.associatedDimensions),
        updatedAt: new Date().toISOString(),
      }
    : {
        id: freshId(),
        type,
        name: input.name,
        groupId: input.groupId,
        groupName: group?.name ?? null,
        category: null,
        description: input.description || null,
        status: input.status,
        icon: null,
        displayOrder: input.displayOrder,
        deviceParams: rowsToDomain(input.deviceParams, 'device') as DeviceApiParam[],
        apiParams: rowsToDomain(input.apiParams, 'api') as DeviceApiParam[],
        caseParams: rowsToDomain(input.caseParams, 'case') as CaseParam[],
        referenceParams: rowsToDomain(input.referenceParams, 'reference') as ReferenceParam[],
        mappings: mappingsToDomain(input.mappings),
        associatedDimensions: dimensionsToDomain(input.associatedDimensions),
        caseCount: 0,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }
  definitionsStore = definitionsStore.map((d) =>
    d.type === type ? updated : d
  )
  syncGroupCounts()
  return mockLatency(updated, 120)
}

/** 删除算法（§7.5；后端引用中算法返回 400/409） */
export async function deleteAlgorithm(
  type: string
): Promise<{ success: boolean; message?: string }> {
  // TODO(API 接线): DELETE /api/v1/algorithm/definitions/{type}
  const target = definitionsStore.find((d) => d.type === type)
  if (!target) return mockLatency({ success: false, message: '算法不存在' }, 80)
  if (target.caseCount > 0) {
    return mockLatency(
      { success: false, message: '该算法已被测试任务/用例引用，无法删除' },
      80
    )
  }
  definitionsStore = definitionsStore.filter((d) => d.type !== type)
  syncGroupCounts()
  return mockLatency({ success: true }, 80)
}

/** 批量删除（§7.8；POST /algorithm/bulk-delete） */
export async function bulkDeleteAlgorithms(types: string[]): Promise<{
  successCount: number
  failedCount: number
}> {
  // TODO(API 接线): POST /api/v1/algorithm/bulk-delete
  let successCount = 0
  let failedCount = 0
  for (const type of types) {
    const target = definitionsStore.find((d) => d.type === type)
    if (target && target.caseCount === 0) {
      definitionsStore = definitionsStore.filter((d) => d.type !== type)
      successCount += 1
    } else {
      failedCount += 1
    }
  }
  syncGroupCounts()
  return mockLatency({ successCount, failedCount }, 100)
}

/** 重载配置（§7.7；POST /algorithm/reload） */
export async function reloadAlgorithmConfig(): Promise<{
  success: boolean
  reloadTime: string
}> {
  // TODO(API 接线): POST /api/v1/algorithm/reload
  return mockLatency(
    { success: true, reloadTime: new Date().toISOString() },
    260
  )
}

/** 导入算法（§7.6；POST /algorithm/import） */
export async function importAlgorithms(
  algorithms: unknown[]
): Promise<{ importedCount: number }> {
  // TODO(API 接线): POST /api/v1/algorithm/import
  // mock 阶段：按导出契约（AlgorithmDefinition 形态）校验后追加入库，返回实际导入数（type 主键去重）
  const existingTypes = new Set(definitionsStore.map((d) => d.type))
  const imported: AlgorithmDefinition[] = algorithms
    .filter(
      (row): row is AlgorithmDefinition =>
        typeof row === 'object' &&
        row !== null &&
        typeof (row as AlgorithmDefinition).type === 'string' &&
        (row as AlgorithmDefinition).type.trim() !== '' &&
        !existingTypes.has((row as AlgorithmDefinition).type)
    )
    .map((row, index) => {
      const group = groupsStore.find((g) => g.id === row.groupId)
      return {
        ...row,
        id: freshId(),
        type: row.type.trim(),
        name: row.name || row.type,
        groupId: row.groupId ?? null,
        groupName: group?.name ?? null,
        status: row.status === 'offline' ? 'offline' : 'online',
        displayOrder:
          typeof row.displayOrder === 'number' ? row.displayOrder : index + 1,
        deviceParams: Array.isArray(row.deviceParams) ? row.deviceParams : [],
        apiParams: Array.isArray(row.apiParams) ? row.apiParams : [],
        caseParams: Array.isArray(row.caseParams) ? row.caseParams : [],
        referenceParams: Array.isArray(row.referenceParams)
          ? row.referenceParams
          : [],
        mappings: row.mappings ?? { device: [], api: [], evaluation: [] },
        associatedDimensions: Array.isArray(row.associatedDimensions)
          ? row.associatedDimensions
          : [],
        caseCount: typeof row.caseCount === 'number' ? row.caseCount : 0,
        createdAt: row.createdAt ?? new Date().toISOString(),
        updatedAt: row.updatedAt ?? new Date().toISOString(),
      }
    })
  definitionsStore = [...definitionsStore, ...imported]
  syncGroupCounts()
  return mockLatency({ importedCount: imported.length }, 260)
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
  // TODO(API 接线): POST /api/v1/algorithm/groups
  const group: AlgorithmGroup = {
    id: freshGroupId(),
    name: input.name,
    description: input.description || null,
    icon: input.icon || null,
    displayOrder: input.displayOrder,
    algorithmCount: 0,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }
  groupsStore = [...groupsStore, group]
  return mockLatency(group, 100)
}

/** 编辑分组 */
export async function updateAlgorithmGroup(
  id: number,
  input: SaveGroupInput
): Promise<AlgorithmGroup> {
  // TODO(API 接线): PUT /api/v1/algorithm/groups/{id}
  const existing = groupsStore.find((g) => g.id === id)
  if (!existing) return mockLatency({ ...(input as unknown as AlgorithmGroup) }, 80)
  const updated: AlgorithmGroup = {
    ...existing,
    name: input.name,
    description: input.description || null,
    icon: input.icon || null,
    displayOrder: input.displayOrder,
    updatedAt: new Date().toISOString(),
  }
  groupsStore = groupsStore.map((g) => (g.id === id ? updated : g))
  return mockLatency(updated, 100)
}

/** 删除分组（§3.6 cascade 语义：删分组、其下算法保留并变未分组） */
export async function deleteAlgorithmGroup(
  id: number
): Promise<{ success: boolean; message?: string }> {
  // TODO(API 接线): DELETE /api/v1/algorithm/groups/{id}
  const group = groupsStore.find((g) => g.id === id)
  if (!group) return mockLatency({ success: false, message: '分组不存在' }, 80)
  // 对齐后端契约（algorithm_handlers.handle_delete_group → soft_delete，无算法存在性检查）
  // 与 §3.6 cascade 语义：删除分组，其下算法保留并置为未分组（groupId/groupName 置空）。
  groupsStore = groupsStore.filter((g) => g.id !== id)
  definitionsStore = definitionsStore.map((d) =>
    d.groupId === id ? { ...d, groupId: null, groupName: null } : d
  )
  syncGroupCounts()
  return mockLatency({ success: true }, 80)
}

function freshGroupId(): number {
  nextGroupId += 1
  return nextGroupId
}

/** 供测试清理内存库（vitest 用例内独立初始化） */
export function __resetAlgorithmMock(): void {
  definitionsStore = [...MOCK_ALGORITHM_DEFINITIONS]
  groupsStore = [...MOCK_ALGORITHM_GROUPS]
  nextId = 1000
  nextGroupId = 500
  __resetAlgorithmDraftMock()
}

/** 当前 mock 内存库（供 feature 内读取导出/复制用；接线后删除） */
export function peekAlgorithmDefinitions(): AlgorithmDefinition[] {
  return definitionsStore
}

/* ───────────────────────── INT-591 草稿/发布 RPC（§6.2/§12-10，mock 形态） ─────────────────────────
 * 后端「算法定义全量保存事务 RPC」（主项目后端卡，草稿分支 + 发布事务 + 乐观锁 revision/force + has_draft）
 * 落定后按契约平移；落定前以下按 §6.2 UI 契约出 mock 形态，供前端走查验收。
 * 乐观锁冲突：revision 条件更新，不匹配抛 AlgorithmConflictError（409 语义，携带服务端最新版本）。
 */

/** 草稿保存成功结果（footer「上次保存 HH:mm:ss」时间戳 + 乐观锁版本号） */
export type DraftSaveResult = {
  revision: number
  savedAt: string
}

/** 乐观锁冲突错误（§6.2a：409 + 服务端最新版本；发布冲突与草稿冲突共用） */
export class AlgorithmConflictError extends Error {
  status = 409
  latestRevision: number
  constructor(latestRevision: number) {
    super('算法定义已被他人修改')
    this.name = 'AlgorithmConflictError'
    this.latestRevision = latestRevision
  }
}

/** mock 冲突演示开关：'none' 正常 / 'draft' 草稿保存恒冲突 / 'publish' 发布恒冲突（接线后删除） */
let algorithmConflictMode: 'none' | 'draft' | 'publish' = 'none'

export function __setAlgorithmConflictMode(
  mode: 'none' | 'draft' | 'publish'
): void {
  algorithmConflictMode = mode
}

/** mock 草稿内存库（key=算法 type；revision 自增） */
const draftRevisionMap = new Map<string, number>()
/** mock 发布版乐观锁版本号（key=算法 type；每次发布递增） */
const publishRevisionMap = new Map<string, number>()

/** 取当前发布版乐观锁版本号（无记录默认 0） */
function currentPublishedRevision(type: string): number {
  return publishRevisionMap.get(type) ?? 0
}

/** 草稿保存（§6.2 draft 分支；宽松结构校验由前端 schema 把关，此处 mock 落库 + 冲突模拟） */
export async function saveAlgorithmDraft(
  input: SaveAlgorithmInput,
  revision?: number
): Promise<DraftSaveResult> {
  // TODO(API 接线): 后端定义全量保存 RPC draft 分支
  const type = input.type.trim() || '__new__'
  if (algorithmConflictMode === 'draft') {
    await mockLatency(undefined, 120)
    throw new AlgorithmConflictError(Math.max(currentPublishedRevision(type), 1))
  }
  // 乐观锁：请求 revision 落后于发布版 → 409 冲突（§6.2a 草稿已过期）
  const published = currentPublishedRevision(type)
  if (revision != null && revision < published) {
    await mockLatency(undefined, 120)
    throw new AlgorithmConflictError(published)
  }
  const next = (draftRevisionMap.get(type) ?? 0) + 1
  draftRevisionMap.set(type, next)
  return mockLatency({ revision: next, savedAt: new Date().toISOString() }, 120)
}

/** 发布（§6.2 发布事务；全量校验由前端 schema 把关，此处执行聚合落库 + 乐观锁冲突模拟） */
export async function publishAlgorithm(
  input: SaveAlgorithmInput,
  revision?: number
): Promise<AlgorithmDefinition> {
  // TODO(API 接线): 后端定义全量保存 RPC 发布事务（草稿分支 + 乐观锁 + has_draft 回写）
  const isNew = !definitionsStore.some((d) => d.type === input.type)
  if (isNew && input.type.trim() === '') {
    await mockLatency(undefined, 120)
    throw new Error('算法代码已存在')
  }
  if (isNew && definitionsStore.some((d) => d.type === input.type)) {
    // 后端 409「算法代码已存在」（§6.6 错误态）
    await mockLatency(undefined, 120)
    const err = new Error('算法代码已存在')
    Object.assign(err, { status: 409 })
    throw err
  }
  if (algorithmConflictMode === 'publish') {
    await mockLatency(undefined, 120)
    throw new AlgorithmConflictError(
      Math.max(currentPublishedRevision(input.type), 1)
    )
  }
  const published = currentPublishedRevision(input.type)
  if (revision != null && revision < published) {
    await mockLatency(undefined, 120)
    throw new AlgorithmConflictError(published)
  }
  const definition = isNew
    ? await createAlgorithm(input)
    : await updateAlgorithm(input.type, input)
  publishRevisionMap.set(input.type, currentPublishedRevision(input.type) + 1)
  draftRevisionMap.delete(input.type)
  return definition
}

/** 供测试重置草稿/发布内存态 */
export function __resetAlgorithmDraftMock(): void {
  draftRevisionMap.clear()
  publishRevisionMap.clear()
  algorithmConflictMode = 'none'
}

/* 演示/走查钩子：mock 阶段暴露冲突模式开关（window.__iatpAlgo.setConflictMode），
 * 供浏览器走查驱动「发布冲突/草稿已过期」UI；接线后随 mock 一并删除。 */
if (typeof window !== 'undefined') {
  ;(window as unknown as Record<string, unknown>).__iatpAlgo = {
    setConflictMode: (mode: 'none' | 'draft' | 'publish') =>
      __setAlgorithmConflictMode(mode),
  }
}
