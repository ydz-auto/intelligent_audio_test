/**
 * 设备评估映射表（设备「参数配置」弹窗内嵌；设备输出 → 评估参数）。
 *
 * 与算法编辑模态窗的「评估参数映射」共用同一套视图（`mapping-view`）：
 * 来源固定「设备输出」，目标维度分组视图（主/子徽章 + 折叠 + 组尾添加）、
 * 搜索 / 来源维度-转换筛选 / 平铺-维度视图 / 分页；写操作恒落本设备覆盖行。
 */
import { useQuery } from '@tanstack/react-query'
import { Fragment, useMemo, useState } from 'react'

import { useDeviceScopeMappings } from '@/application/devices/use-device-scope-mappings'
import { useEvaluationCategories } from '@/application/evaluation/use-dimensions'
import { usePermissions } from '@/application/hooks/use-permissions'
import type { AlgorithmApiParam } from '@/domain/models/apiConfig'
import type { Dimension } from '@/domain/models/evaluationDimension'
import { TRANSFORM_TYPE_OPTIONS } from '@/features/algorithm-config/constants'
import { DimensionSelect } from '@/features/algorithm-config/mutate/dimension-select'
import {
  evalGroupKey,
  evalGroupName,
  EvaluationMappingRowView,
  GroupAddRow,
  GroupHeaderButton,
  mainBadge,
  MappingAddButton,
  MappingBadgeFilter,
  MappingPagination,
  MappingSearch,
  MappingTableFrame,
  MappingToolbar,
  MappingViewToggle,
  subBadge,
  useDimensionParamsMap,
  useMappingViewState,
} from '@/features/algorithm-config/mutate/mapping-view'
import { Badge } from '@/components/ui/badge'
import {
  fetchDeviceMappingCaseParams,
  fetchDeviceMappingReferenceParams,
  fetchDeviceScopeParams,
} from '@/infrastructure/api/device-param-api'
import { fetchEvaluationDimensions } from '@/infrastructure/api/evaluation-api'

const COLUMNS = [
  { label: '来源' },
  { label: '源参数代码' },
  { label: '源参数名称' },
  { label: '目标评估维度' },
  { label: '目标参数' },
  { label: '转换' },
  { label: '操作', className: 'w-10 px-3 py-2 text-right font-medium' },
] as const

const DEVICE_SOURCE_OPTIONS = [{ value: 'device', label: '设备输出' }] as const

/** 算法级打底 + 本设备覆盖（同 code 覆盖） */
function effectiveDeviceParams(
  rows: AlgorithmApiParam[],
  deviceId: number
): AlgorithmApiParam[] {
  const map = new Map<string, AlgorithmApiParam>()
  for (const row of rows) {
    if (row.deviceId == null) map.set(row.paramCode, row)
  }
  for (const row of rows) {
    if (row.deviceId === deviceId) map.set(row.paramCode, row)
  }
  return [...map.values()]
}

export function DeviceEvaluationMappingTable({
  open,
  algorithmType,
  deviceId,
}: {
  open: boolean
  algorithmType: string
  deviceId: number
}) {
  const { hasPermission } = usePermissions()
  const canEdit = hasPermission('algorithm:definition_manage')
  const view = useMappingViewState<'flat' | 'dimension'>('dimension')
  const [dimensionFilter, setDimensionFilter] = useState('all')

  const { rows, isLoading, isError, patchRow, addRow, removeRow } = useDeviceScopeMappings({
    algorithmType,
    deviceId,
    source: 'device',
    enabled: open,
  })

  const caseParamsQuery = useQuery({
    queryKey: ['devices', 'mapping-case-params', algorithmType],
    queryFn: () => fetchDeviceMappingCaseParams(algorithmType),
    enabled: open && Boolean(algorithmType),
    staleTime: 60_000,
    retry: false,
  })
  const referenceParamsQuery = useQuery({
    queryKey: ['devices', 'mapping-reference-params', algorithmType],
    queryFn: () => fetchDeviceMappingReferenceParams(algorithmType),
    enabled: open && Boolean(algorithmType),
    staleTime: 60_000,
    retry: false,
  })
  const deviceParamsQuery = useQuery({
    queryKey: ['devices', 'device-params', algorithmType],
    queryFn: () => fetchDeviceScopeParams(algorithmType),
    enabled: open && Boolean(algorithmType),
    staleTime: 0,
    retry: false,
  })
  const dimensionsQuery = useQuery({
    queryKey: ['evaluation', 'dimensions'],
    queryFn: () => fetchEvaluationDimensions(),
    enabled: open,
    staleTime: 60_000,
    retry: false,
  })
  const categoriesQuery = useEvaluationCategories()

  const caseParams = useMemo(() => caseParamsQuery.data ?? [], [caseParamsQuery.data])
  const referenceParams = useMemo(
    () => referenceParamsQuery.data ?? [],
    [referenceParamsQuery.data]
  )
  const deviceParams = useMemo(
    () => effectiveDeviceParams(deviceParamsQuery.data ?? [], deviceId),
    [deviceParamsQuery.data, deviceId]
  )
  const dimensions = useMemo<Dimension[]>(
    () => dimensionsQuery.data ?? [],
    [dimensionsQuery.data]
  )

  const dimensionIds = useMemo(
    () => rows.map((row) => (row.dimensionId ? String(row.dimensionId) : '')),
    [rows]
  )
  const dimensionParamsMap = useDimensionParamsMap(dimensionIds)

  const dimById = useMemo(
    () => new Map(dimensions.map((dimension) => [String(dimension.id), dimension])),
    [dimensions]
  )
  /** 已删除维度的组名兜底（行内维度的 id 仍在，名称查不到时显示「维度(id)」） */
  const dimensionNameById = useMemo(() => new Map<string, string>(), [])

  const categories = useMemo(() => categoriesQuery.data ?? [], [categoriesQuery.data])

  /** 字典外筛选选项：「未指定维度」+ 已删除维度存量行（分类节之外兜底） */
  const extraDimensionFilterOptions = useMemo(() => {
    const known = new Set(dimensions.map((dimension) => String(dimension.id)))
    const seen = new Set<string>(['__none__'])
    const options: Array<{ value: string; label: string }> = [
      { value: '__none__', label: '未指定维度' },
    ]
    for (const row of rows) {
      const key = row.dimensionId ? String(row.dimensionId) : '__none__'
      if (known.has(key) || seen.has(key)) continue
      seen.add(key)
      options.push({ value: key, label: `维度(${key})` })
    }
    return options
  }, [dimensions, rows])

  const filtered = useMemo(() => {
    const kw = view.keyword.trim().toLowerCase()
    return rows.filter((row) => {
      if (dimensionFilter !== 'all') {
        const key = row.dimensionId ? String(row.dimensionId) : '__none__'
        if (key !== dimensionFilter) return false
      }
      if (view.transformFilter !== 'all' && row.transformType !== view.transformFilter) {
        return false
      }
      if (!kw) return true
      const dimName = row.dimensionId
        ? dimById.get(String(row.dimensionId))?.name ?? ''
        : ''
      return (
        row.sourceParam.toLowerCase().includes(kw) ||
        (row.paramName ?? '').toLowerCase().includes(kw) ||
        row.targetParam.toLowerCase().includes(kw) ||
        (row.targetParamName ?? '').toLowerCase().includes(kw) ||
        dimName.toLowerCase().includes(kw)
      )
    })
  }, [rows, view.keyword, view.transformFilter, dimensionFilter, dimById])

  const groups = useMemo(() => {
    if (view.viewMode !== 'dimension') return []
    const map = new Map<string, typeof rows>()
    for (const row of filtered) {
      const key = evalGroupKey({
        dimensionId: row.dimensionId ? String(row.dimensionId) : '',
        dimensionName: null,
      })
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(row)
    }
    return Array.from(map.entries()).sort(([a], [b]) =>
      evalGroupName(a, dimensions, dimensionNameById).localeCompare(
        evalGroupName(b, dimensions, dimensionNameById),
        'zh-Hans-CN'
      )
    )
  }, [view.viewMode, filtered, dimensions, dimensionNameById])

  const pageRows = useMemo(() => {
    if (view.viewMode === 'dimension') return []
    const start = (view.page - 1) * view.pageSize
    return filtered.slice(start, start + view.pageSize)
  }, [view.viewMode, filtered, view.page, view.pageSize])

  const renderRow = (row: (typeof rows)[number]) => (
    <EvaluationMappingRowView
      key={row.key}
      value={{
        source: 'device',
        sourceParam: row.sourceParam,
        dimensionId: row.dimensionId ? String(row.dimensionId) : '',
        targetParam: row.targetParam,
        transformType: row.transformType,
        paramName: row.paramName,
        targetParamName: row.targetParamName,
      }}
      caseParams={caseParams}
      referenceParams={referenceParams}
      deviceParams={deviceParams}
      dimensions={dimensions}
      categories={[]}
      dimensionParams={row.dimensionId ? dimensionParamsMap[String(row.dimensionId)] ?? [] : []}
      transformOptions={TRANSFORM_TYPE_OPTIONS}
      sourceOptions={DEVICE_SOURCE_OPTIONS}
      sourceDisabled
      sourceBadge={
        <Badge variant={row.scoped ? 'default' : 'secondary'} className='text-[10px]'>
          {row.scoped ? '本设备' : '算法级'}
        </Badge>
      }
      onChange={(patch) => {
        if (!canEdit) return
        if (patch.sourceParam !== undefined) patchRow(row.key, { sourceParam: patch.sourceParam })
        if (patch.dimensionId !== undefined) {
          // 换维度：维度内目标参数不通用，先清空（齐备后才落库）
          patchRow(row.key, {
            dimensionId: patch.dimensionId ? Number(patch.dimensionId) : null,
            targetParam: '',
          })
        }
        if (patch.targetParam !== undefined) patchRow(row.key, { targetParam: patch.targetParam })
        if (patch.transformType !== undefined) {
          patchRow(row.key, { transformType: patch.transformType })
        }
      }}
      onRemove={row.scoped && canEdit ? () => void removeRow(row.key) : undefined}
      disabled={!canEdit}
    />
  )

  return (
    <div className='space-y-2'>
      <MappingToolbar>
        <MappingSearch value={view.keyword} onChange={view.setKeyword} />
        {/* 评估维度筛选：分类 → 主维度 → 子维度（与算法编辑/用例 facet 同口径） */}
        <DimensionSelect
          dimensions={dimensions}
          categories={categories}
          value={dimensionFilter === 'all' ? '' : dimensionFilter}
          onValueChange={(value) => setDimensionFilter(value || 'all')}
          valueOf={(dimension) => String(dimension.id)}
          clearLabel='全部维度'
          triggerLabel='评估维度'
          placeholder='全部维度'
          ariaLabel='评估维度筛选'
          triggerClassName='h-8 w-auto gap-1.5 rounded-lg px-2.5 font-normal'
          extraOptions={extraDimensionFilterOptions}
        />
        <MappingBadgeFilter
          title='转换'
          options={TRANSFORM_TYPE_OPTIONS}
          value={view.transformFilter}
          onValueChange={view.setTransformFilter}
          allLabel='全部转换'
        />
        <MappingViewToggle
          value={view.viewMode}
          ariaLabel='设备评估映射视图'
          options={[
            { value: 'flat', label: '平铺视图' },
            { value: 'dimension', label: '评估维度视图' },
          ]}
          onValueChange={view.setViewMode}
        />
        <MappingAddButton onClick={addRow} disabled={!canEdit} />
      </MappingToolbar>

      {!canEdit && (
        <p className='text-destructive text-xs'>
          当前账号缺少 algorithm:definition_manage 权限，设备映射只读。
        </p>
      )}
      {isError && (
        <p className='text-destructive text-xs'>设备映射读取失败，请稍后重试。</p>
      )}

      <MappingTableFrame
        columns={COLUMNS}
        colSpan={7}
        isEmpty={rows.length === 0 && !isLoading}
        isFilteredEmpty={filtered.length === 0}
        emptyText={isLoading ? '正在读取设备映射…' : '该设备还没有输出映射；可添加设备输出 → 评估参数的映射。'}
      >
        {view.viewMode === 'flat'
          ? pageRows.map(renderRow)
          : groups.map(([key, groupRows]) => {
              const isCollapsed = view.collapsed.has(key)
              const dimId = !key.startsWith('name:') && key !== '__none__' ? key : ''
              const dim = dimById.get(dimId)
              const parentName = dim?.parentDimensionId
                ? dimensions.find(
                    (item) => String(item.id) === String(dim.parentDimensionId)
                  )?.name
                : undefined
              return (
                <Fragment key={key}>
                  <tr className='bg-muted/40 border-border/50 border-b'>
                    <td colSpan={7} className='px-0 py-0'>
                      <GroupHeaderButton
                        name={evalGroupName(key, dimensions, dimensionNameById)}
                        count={groupRows.length}
                        collapsed={isCollapsed}
                        onToggle={() => view.toggleCollapsed(key)}
                        badge={
                          dim ? (
                            dim.parentDimensionId ? (
                              <>
                                <span className={subBadge}>子</span>
                                {parentName ? (
                                  <span className='text-muted-foreground/70 text-[11px] font-normal'>
                                    （{parentName}）
                                  </span>
                                ) : null}
                              </>
                            ) : (
                              <span className={mainBadge}>主</span>
                            )
                          ) : key === '__none__' ? (
                            <span className='text-muted-foreground text-[11px] font-normal'>
                              （未指定）
                            </span>
                          ) : null
                        }
                      />
                    </td>
                  </tr>
                  {!isCollapsed && groupRows.map(renderRow)}
                  {!isCollapsed && canEdit && (
                    <GroupAddRow colSpan={7} onClick={addRow} />
                  )}
                </Fragment>
              )
            })}
      </MappingTableFrame>

      {view.viewMode === 'flat' && filtered.length > view.pageSize && (
        <MappingPagination
          total={filtered.length}
          page={view.page}
          pageSize={view.pageSize}
          onPageChange={view.setPage}
          onPageSizeChange={view.setPageSize}
        />
      )}
    </div>
  )
}
