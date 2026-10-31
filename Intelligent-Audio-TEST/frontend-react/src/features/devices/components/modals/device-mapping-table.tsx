/**
 * 设备映射表（设备「参数配置」弹窗内嵌；用例参数 → 设备输入）。
 *
 * 视图与算法编辑模态窗同源（`mapping-view`）：搜索 / 转换筛选 / 平铺-分组视图 /
 * 分页 / 分组折叠与组尾添加；行内联编辑，写操作恒落**本设备覆盖行**（device_id），
 * 算法级行只读（编辑即新增覆盖），设备行可删除回落。
 */
import { useQuery } from '@tanstack/react-query'
import { Fragment, useMemo } from 'react'

import { useDeviceScopeMappings } from '@/application/devices/use-device-scope-mappings'
import { usePermissions } from '@/application/hooks/use-permissions'
import type { AlgorithmApiParam } from '@/domain/models/apiConfig'
import { TRANSFORM_TYPE_OPTIONS } from '@/features/algorithm-config/constants'
import {
  buildSourceOptions,
  DEVICE_API_GROUP_LABEL,
  DEVICE_API_GROUP_ORDER,
  deviceApiGroupKey,
  DeviceMappingRowView,
  GroupAddRow,
  GroupHeaderButton,
  MappingAddButton,
  MappingBadgeFilter,
  MappingPagination,
  MappingSearch,
  MappingTableFrame,
  MappingToolbar,
  MappingViewToggle,
  paramNameByCode,
  useMappingViewState,
} from '@/features/algorithm-config/mutate/mapping-view'
import { Badge } from '@/components/ui/badge'
import {
  fetchDeviceMappingCaseParams,
  fetchDeviceMappingReferenceParams,
  fetchDeviceScopeParams,
} from '@/infrastructure/api/device-param-api'

const COLUMNS = [
  { label: '源参数代码' },
  { label: '源参数名称' },
  { label: '目标参数代码' },
  { label: '目标参数名称' },
  { label: '转换' },
  { label: '操作', className: 'w-10 px-3 py-2 text-right font-medium' },
] as const

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

export function DeviceMappingTable({
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
  const view = useMappingViewState<'flat' | 'group'>('flat')

  const { rows, isLoading, isError, patchRow, addRow, removeRow } = useDeviceScopeMappings({
    algorithmType,
    deviceId,
    source: 'case',
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

  const caseParams = useMemo(() => caseParamsQuery.data ?? [], [caseParamsQuery.data])
  const referenceParams = useMemo(
    () => referenceParamsQuery.data ?? [],
    [referenceParamsQuery.data]
  )
  const deviceParams = useMemo(
    () => effectiveDeviceParams(deviceParamsQuery.data ?? [], deviceId),
    [deviceParamsQuery.data, deviceId]
  )

  const sourceOptions = useMemo(
    () => buildSourceOptions(caseParams, referenceParams),
    [caseParams, referenceParams]
  )
  const targetOptions = useMemo(
    () =>
      deviceParams
        .map((param) => ({
          value: param.paramCode,
          label: `${param.paramCode} · ${param.paramName || '（未填名称）'}`,
        }))
        .filter((option) => option.value),
    [deviceParams]
  )

  const sourceName = (sourceParam: string, fallback: string | null) =>
    paramNameByCode(caseParams, sourceParam) ||
    paramNameByCode(referenceParams, sourceParam) ||
    fallback ||
    ''
  const targetName = (targetParam: string, fallback: string | null) =>
    paramNameByCode(deviceParams, targetParam) || fallback || ''

  const filtered = useMemo(() => {
    const kw = view.keyword.trim().toLowerCase()
    return rows.filter((row) => {
      if (view.transformFilter !== 'all' && row.transformType !== view.transformFilter) {
        return false
      }
      if (!kw) return true
      return (
        row.sourceParam.toLowerCase().includes(kw) ||
        sourceName(row.sourceParam, row.paramName).toLowerCase().includes(kw) ||
        row.targetParam.toLowerCase().includes(kw) ||
        targetName(row.targetParam, row.targetParamName).toLowerCase().includes(kw)
      )
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, view.keyword, view.transformFilter, caseParams, referenceParams, deviceParams])

  const groups = useMemo(() => {
    if (view.viewMode !== 'group') return []
    const map = new Map<string, typeof rows>()
    DEVICE_API_GROUP_ORDER.forEach((key) => map.set(key, []))
    for (const row of filtered) {
      const key = deviceApiGroupKey(row.sourceParam, caseParams, referenceParams)
      map.get(key)!.push(row)
    }
    return Array.from(map.entries()).filter(([, groupRows]) => groupRows.length > 0)
  }, [view.viewMode, filtered, caseParams, referenceParams])

  const pageRows = useMemo(() => {
    if (view.viewMode === 'group') return []
    const start = (view.page - 1) * view.pageSize
    return filtered.slice(start, start + view.pageSize)
  }, [view.viewMode, filtered, view.page, view.pageSize])

  const renderRow = (row: (typeof rows)[number]) => (
    <DeviceMappingRowView
      key={row.key}
      value={row}
      sourceOptions={sourceOptions}
      targetOptions={targetOptions}
      transformOptions={TRANSFORM_TYPE_OPTIONS}
      sourceName={sourceName(row.sourceParam, row.paramName)}
      targetName={targetName(row.targetParam, row.targetParamName)}
      sourceBadge={
        <Badge variant={row.scoped ? 'default' : 'secondary'} className='text-[10px]'>
          {row.scoped ? '本设备' : '算法级'}
        </Badge>
      }
      onChange={(patch) => {
        if (!canEdit) return
        patchRow(row.key, patch)
      }}
      onRemove={row.scoped && canEdit ? () => void removeRow(row.key) : undefined}
      disabled={!canEdit}
    />
  )

  return (
    <div className='space-y-2'>
      <MappingToolbar>
        <MappingSearch value={view.keyword} onChange={view.setKeyword} />
        <MappingBadgeFilter
          title='转换'
          options={TRANSFORM_TYPE_OPTIONS}
          value={view.transformFilter}
          onValueChange={view.setTransformFilter}
          allLabel='全部转换'
        />
        <MappingViewToggle
          value={view.viewMode}
          ariaLabel='设备映射视图'
          options={[
            { value: 'flat', label: '平铺视图' },
            { value: 'group', label: '分组视图' },
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
        colSpan={6}
        isEmpty={rows.length === 0 && !isLoading}
        isFilteredEmpty={filtered.length === 0}
        emptyText={isLoading ? '正在读取设备映射…' : '该算法还没有设备映射；可直接添加本设备的映射。'}
      >
        {view.viewMode === 'flat'
          ? pageRows.map(renderRow)
          : groups.map(([key, groupRows]) => {
              const isCollapsed = view.collapsed.has(key)
              return (
                <Fragment key={key}>
                  <tr className='bg-muted/40 border-border/50 border-b'>
                    <td colSpan={6} className='px-0 py-0'>
                      <GroupHeaderButton
                        name={DEVICE_API_GROUP_LABEL[key as keyof typeof DEVICE_API_GROUP_LABEL]}
                        count={groupRows.length}
                        collapsed={isCollapsed}
                        onToggle={() => view.toggleCollapsed(key)}
                      />
                    </td>
                  </tr>
                  {!isCollapsed && groupRows.map(renderRow)}
                  {!isCollapsed && canEdit && (
                    <GroupAddRow colSpan={6} onClick={addRow} />
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
