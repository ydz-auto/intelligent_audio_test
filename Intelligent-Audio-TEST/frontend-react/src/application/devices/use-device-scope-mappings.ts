/**
 * 设备级参数映射（`param_mappings.device_id`）读写编排（Application 层）。
 *
 * 语义（与算法编辑模态窗的映射视图共用一套行模型）：
 * - 读：`GET /algorithm/mappings?...&device_id=Y` 返回算法级打底 + 本设备覆盖行；
 *   本层按映射键合并——设备行覆盖同键算法级行（`scoped` 标记行作用域）；
 * - 写：只落**本设备覆盖行**——编辑算法级行等价于「新增本设备覆盖」，
 *   编辑本设备行即更新；删除本设备行回落到算法级；
 * - 新增行先作为草稿展示，字段齐备（源参数 + 目标参数；评估映射还要维度）才落库，
 *   避免「改维度清空目标参数」这类中间态打服务端校验。
 *
 * snake_case 只在 infrastructure 层出现，这里只见 camelCase Domain 模型。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import type { ParamMapping } from '@/domain/models/algorithmConfig'
import {
  createDeviceScopeMapping,
  deleteDeviceScopeMapping,
  fetchDeviceScopeMappings,
  updateDeviceScopeMapping,
  type DeviceMappingBucket,
  type DeviceMappingSource,
} from '@/infrastructure/api/device-param-api'

export interface DeviceScopeMappingRow {
  /** 稳定行键（合并/草稿/React key 共用） */
  key: string
  /** 本设备覆盖行 id；null = 算法级行或未落库草稿 */
  id: number | null
  /** true = 本设备覆盖行 */
  scoped: boolean
  source: DeviceMappingSource
  sourceParam: string
  /** 目标评估维度（source=device 必填） */
  dimensionId: number | null
  targetParam: string
  transformType: string
  paramName: string | null
  targetParamName: string | null
}

export type DeviceScopeMappingPatch = Partial<
  Pick<DeviceScopeMappingRow, 'sourceParam' | 'dimensionId' | 'targetParam' | 'transformType'>
>

/** 设备映射查询键（按缓存桶区分：设备映射=case，评估映射=evaluation） */
export function deviceMappingsQueryKey(
  algorithmType: string,
  deviceId: number,
  bucket: DeviceMappingBucket
) {
  return ['devices', 'device-mappings', algorithmType, deviceId, bucket] as const
}

/** 映射来源 → 后端缓存桶（对齐 `_serialize_mappings` 分桶） */
export function deviceMappingBucketOf(source: DeviceMappingSource): DeviceMappingBucket {
  return source === 'device' ? 'evaluation' : 'case'
}

/** 合并键：设备映射 = 源参数；评估映射 = 源参数 + 目标维度 */
export function deviceScopeRowKey(
  source: DeviceMappingSource,
  sourceParam: string,
  dimensionId: number | null
): string {
  return `${source}|${sourceParam}|${source === 'device' ? (dimensionId ?? '') : ''}`
}

/** 字段齐备才落库（评估映射缺维度/目标参数时不提交） */
function isCompleteRow(row: DeviceScopeMappingRow): boolean {
  if (!row.sourceParam || !row.targetParam) return false
  if (row.source === 'device' && row.dimensionId == null) return false
  return true
}

function toRow(mapping: ParamMapping, deviceId: number): DeviceScopeMappingRow {
  const source: DeviceMappingSource = mapping.source === 'device' ? 'device' : 'case'
  const scoped = mapping.deviceId != null && mapping.deviceId === deviceId
  return {
    key: deviceScopeRowKey(source, mapping.sourceParam, mapping.dimensionId),
    id: scoped ? mapping.id : null,
    scoped,
    source,
    sourceParam: mapping.sourceParam,
    dimensionId: mapping.dimensionId,
    targetParam: mapping.targetParam,
    transformType: mapping.transformType ?? 'none',
    paramName: mapping.paramName,
    targetParamName: mapping.targetParamName,
  }
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function useDeviceScopeMappings(options: {
  algorithmType: string
  deviceId: number
  /** 本节维护的映射来源（设备映射=case，评估映射=device） */
  source: DeviceMappingSource
  enabled: boolean
}) {
  const { algorithmType, deviceId, source, enabled } = options
  const queryClient = useQueryClient()
  const [drafts, setDrafts] = useState<Record<string, DeviceScopeMappingPatch>>({})
  const [draftRows, setDraftRows] = useState<DeviceScopeMappingRow[]>([])
  const [pending, setPending] = useState(0)

  const bucket = deviceMappingBucketOf(source)

  const query = useQuery({
    queryKey: deviceMappingsQueryKey(algorithmType, deviceId, bucket),
    queryFn: () => fetchDeviceScopeMappings(algorithmType, deviceId, bucket),
    enabled: enabled && Boolean(algorithmType),
    staleTime: 0,
    retry: false,
  })

  /** 生效行：算法级打底 → 本设备覆盖同键覆盖 → 新增草稿 → 本地改动 */
  const rows = (() => {
    const base = new Map<string, DeviceScopeMappingRow>()
    const scoped = new Map<string, DeviceScopeMappingRow>()
    for (const mapping of query.data ?? []) {
      // 同一桶里可能混有其它来源的行（如评估桶的 case 行），按本分节来源分流
      if (mapping.source !== source) continue
      const row = toRow(mapping, deviceId)
      if (row.scoped) scoped.set(row.key, row)
      else if (!base.has(row.key)) base.set(row.key, row)
    }
    for (const [key, row] of scoped) base.set(key, row)
    for (const row of draftRows) base.set(row.key, row)
    return [...base.values()].map((row) =>
      drafts[row.key] ? { ...row, ...drafts[row.key] } : row
    )
  })()

  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: deviceMappingsQueryKey(algorithmType, deviceId, bucket),
    })

  const persist = async (row: DeviceScopeMappingRow) => {
    if (!isCompleteRow(row)) return
    setPending((count) => count + 1)
    try {
      const input = {
        algorithmType,
        deviceId,
        source: row.source,
        sourceParam: row.sourceParam,
        sourceDirection: row.source === 'case' ? ('input' as const) : ('output' as const),
        dimensionId: row.source === 'device' ? row.dimensionId : null,
        targetParam: row.targetParam,
        transformType: row.transformType || 'none',
      }
      if (row.id != null) await updateDeviceScopeMapping(row.id, input)
      else await createDeviceScopeMapping(input)
      await invalidate()
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[row.key]
        return next
      })
      setDraftRows((prev) => prev.filter((item) => item.key !== row.key))
      toast.success('设备映射已保存')
    } catch (error) {
      toast.error(`保存失败：${errorText(error)}`)
      // 已落库行的改动失败：丢弃本地改动并回读，避免界面与服务端不一致
      if (row.id != null) {
        setDrafts((prev) => {
          const next = { ...prev }
          delete next[row.key]
          return next
        })
        await invalidate()
      }
    } finally {
      setPending((count) => count - 1)
    }
  }

  /** 就地改动一行：先本地生效，字段齐备即落库（设备级覆盖） */
  const patchRow = (key: string, patch: DeviceScopeMappingPatch) => {
    const current = rows.find((row) => row.key === key)
    if (!current) return
    setDrafts((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }))
    void persist({ ...current, ...patch })
  }

  /** 新增草稿行（齐备后自动落设备级覆盖行） */
  const addRow = () => {
    const key = `draft-${source}-${Date.now()}`
    setDraftRows((prev) => [
      ...prev,
      {
        key,
        id: null,
        scoped: true,
        source,
        sourceParam: '',
        dimensionId: null,
        targetParam: '',
        transformType: 'none',
        paramName: null,
        targetParamName: null,
      },
    ])
  }

  /** 删除本设备覆盖行（算法级行不可删，回落由覆盖关系保证） */
  const removeRow = async (key: string) => {
    const current = rows.find((row) => row.key === key)
    if (!current) return
    if (current.id == null) {
      // 未落库草稿：仅本地移除
      setDraftRows((prev) => prev.filter((row) => row.key !== key))
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
      return
    }
    setPending((count) => count + 1)
    try {
      await deleteDeviceScopeMapping(current.id)
      await invalidate()
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
      toast.success('设备映射已删除，回落到算法级映射')
    } catch (error) {
      toast.error(`删除失败：${errorText(error)}`)
    } finally {
      setPending((count) => count - 1)
    }
  }

  return {
    rows,
    isLoading: query.isLoading,
    isError: query.isError,
    isFetching: query.isFetching,
    isSaving: pending > 0,
    patchRow,
    addRow,
    removeRow,
  }
}
