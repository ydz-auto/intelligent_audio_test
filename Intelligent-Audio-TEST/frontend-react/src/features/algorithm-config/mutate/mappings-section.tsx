/**
 * §6.5 参数映射分节（mutate sheet 高级配置折叠区）。
 * INT-1160 返工（负责人 2026-10-21「设备/评估参数映射照 V9.7.10 重做」）：
 * - 设备 6 列「源参数代码 / 源参数名称 / 目标参数代码 / 目标参数名称 / 转换 / 操作」；
 *   评估 7 列「来源 / 源参数代码 / 源参数名称 / 目标评估维度 / 目标参数 / 转换 / 操作」。
 * - 公共工具栏：搜索映射 + 转换徽章筛选 + 平铺/分组视图切换 + 分页（平铺 >10 条）；
 *   评估另加 来源 / 评估维度 徽章筛选。
 * - 分组视图：设备按源参数集合（用例参数·通用/API/E2E + 参考参数）、评估按目标维度
 *   （组头折叠 + 主/子徽章 + 计数 + 组尾「添加映射」预填维度；空行归「未指定维度」）。
 * - 数据模型补齐 id/source/sourceDirection/paramName/dimensionId/dimensionName/targetParamName
 *   （INT-1160 范围 1），评估来源可选 用例参数/用例配置/参考参数/设备输出，
 *   目标参数经 /algorithm/dimension-params 拉维度内参数。
 * 行值一律经 useWatch 读 form 值（useFieldArray.fields 不随 setValue 更新，只作 key/增删锚点）。
 *
 * 视图层（工具栏/表格框/分组/分页/行组件）已抽到 `mapping-view`，与设备「参数配置」弹窗共用。
 */
import { Fragment, useEffect, useMemo, useState } from 'react'
import { type FieldPath, type UseFormReturn } from 'react-hook-form'
import { useFieldArray, useWatch } from 'react-hook-form'

import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import type { AlgorithmFormValues, MappingRow } from '@/features/algorithm-config/types'
import { TRANSFORM_TYPE_OPTIONS } from '@/features/algorithm-config/constants'
import {
  buildSourceOptions,
  DEVICE_API_GROUP_LABEL,
  DEVICE_API_GROUP_ORDER,
  deviceApiGroupKey,
  DeviceMappingRowView,
  EVALUATION_SOURCE_OPTIONS,
  evalGroupKey,
  evalGroupName,
  evalSourceParamName,
  EvaluationMappingRowView,
  findDuplicateIndex,
  GroupAddRow,
  GroupHeaderButton,
  mainBadge,
  MappingAddButton,
  MappingBadgeFilter,
  MappingCollapsible,
  MappingPagination,
  MappingSearch,
  MappingTableFrame,
  MappingToolbar,
  MappingViewToggle,
  paramNameByCode,
  subBadge,
  useDimensionParamsMap,
  warnDuplicate,
} from './mapping-view'
import { DimensionSelect } from './dimension-select'

/* ───────────────────────── 设备参数映射分节 ───────────────────────── */

const DEVICE_COLUMNS = [
  { label: '源参数代码' },
  { label: '源参数名称' },
  { label: '目标参数代码' },
  { label: '目标参数名称' },
  { label: '转换' },
  { label: '操作', className: 'w-10 px-3 py-2 text-right font-medium' },
] as const

function DeviceMappingSection({
  form,
  caseParams,
  referenceParams,
  targetParams,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  /** 用例参数（源参数选项 + 分组键 scope） */
  caseParams: Array<{ paramCode: string; paramName?: string; scope: string }>
  /** 参考参数（源参数选项 + 分组键） */
  referenceParams: Array<{ code: string; name?: string }>
  /** 目标参数（设备参数） */
  targetParams: Array<{ paramCode: string; paramName?: string }>
}) {
  const arrayName = 'mappings.device' as const
  const sectionLabel = '设备'
  const transformOptions = TRANSFORM_TYPE_OPTIONS
  const mappings = useFieldArray({ control: form.control, name: arrayName })
  /** 行实时值（setValue 后可读；fields 只作 key/增删锚点） */
  const liveRows = useWatch({ control: form.control, name: arrayName }) as MappingRow[] | undefined
  const rows = liveRows ?? []
  const [keyword, setKeyword] = useState('')
  const [transformFilter, setTransformFilter] = useState('all')
  const [viewMode, setViewMode] = useState<'flat' | 'group'>('flat')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const sourceOptions = useMemo(
    () => buildSourceOptions(caseParams, referenceParams),
    [caseParams, referenceParams]
  )
  const targetOptions = useMemo(
    () =>
      targetParams
        .map((param) => ({
          value: param.paramCode,
          label: `${param.paramCode} · ${param.paramName || '（未填名称）'}`,
        }))
        .filter((option) => option.value),
    [targetParams]
  )

  /** 源参数名（按 code 查 用例/参考；查不到回退 paramName 存量值） */
  const sourceName = (row: MappingRow) =>
    paramNameByCode(caseParams, row.sourceParam) ||
    paramNameByCode(referenceParams, row.sourceParam) ||
    row.paramName ||
    ''
  /** 目标参数名（按 code 查目标参数表；查不到回退 targetParamName 存量值） */
  const targetName = (row: MappingRow) =>
    paramNameByCode(targetParams, row.targetParam) || row.targetParamName || ''

  const section = 'device' as const

  const addEmpty = () =>
    mappings.append({
      key: `${arrayName}-${Date.now()}-${rows.length}`,
      source: 'case',
      sourceDirection: 'output',
      sourceParam: '',
      paramName: '',
      targetParam: '',
      targetParamName: '',
      transformType: 'none',
    })

  const toggleCollapsed = (key: string) => {
    const next = new Set(collapsed)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setCollapsed(next)
  }

  /**
   * 源参数变更：写入 sourceParam + 回填 paramName + 判重提示（V9.7.10 handleSourceChange 口径）。
   * 判重读 form.getValues() 实时值——setValue 后 useWatch 快照要到下轮渲染才更新，
   * 用快照判重会漏掉「编辑存量完备行 sourceParam 制造重复」的变更（INT-1160 返工 P2）。
   */
  const handleSourceChange = (index: number, value: string) => {
    form.setValue(`${arrayName}.${index}.sourceParam` as FieldPath<AlgorithmFormValues>, value ?? '')
    const name =
      paramNameByCode(caseParams, value ?? '') || paramNameByCode(referenceParams, value ?? '')
    form.setValue(`${arrayName}.${index}.paramName` as FieldPath<AlgorithmFormValues>, name)
    const liveRows = (form.getValues(arrayName) ?? []) as MappingRow[]
    const dupIndex = findDuplicateIndex(liveRows, index, section)
    if (dupIndex >= 0) warnDuplicate(sectionLabel, value || '', '')
  }

  /** 目标参数变更（V9.7.10 handleTargetChange 口径：判重提示不阻塞；同样读实时值） */
  const handleTargetChange = (index: number, value: string) => {
    form.setValue(`${arrayName}.${index}.targetParam` as FieldPath<AlgorithmFormValues>, value ?? '')
    form.setValue(
      `${arrayName}.${index}.targetParamName` as FieldPath<AlgorithmFormValues>,
      paramNameByCode(targetParams, value ?? '')
    )
    const liveRows = (form.getValues(arrayName) ?? []) as MappingRow[]
    const dupIndex = findDuplicateIndex(liveRows, index, section)
    if (dupIndex >= 0) warnDuplicate(sectionLabel, liveRows[index]?.sourceParam || '', '')
  }

  /** 搜索 + 转换筛选后的行 */
  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return rows.filter((row) => {
      if (transformFilter !== 'all' && row.transformType !== transformFilter) return false
      if (!kw) return true
      return (
        (row.sourceParam || '').toLowerCase().includes(kw) ||
        (sourceName(row) || '').toLowerCase().includes(kw) ||
        (row.targetParam || '').toLowerCase().includes(kw) ||
        (targetName(row) || '').toLowerCase().includes(kw)
      )
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, keyword, transformFilter, caseParams, referenceParams, targetParams])

  /** 分组视图：按源参数集合分组（组序固定）；平铺视图：过滤 + 分页切片 */
  const groups = useMemo(() => {
    if (viewMode !== 'group') return []
    const map = new Map<string, MappingRow[]>()
    DEVICE_API_GROUP_ORDER.forEach((key) => map.set(key, []))
    for (const row of filtered) {
      const key = deviceApiGroupKey(row.sourceParam, caseParams, referenceParams)
      map.get(key)!.push(row)
    }
    return Array.from(map.entries()).filter(([, groupRows]) => groupRows.length > 0)
  }, [viewMode, filtered, caseParams, referenceParams])

  const pageRows = useMemo(() => {
    if (viewMode === 'group') return []
    const start = (page - 1) * pageSize
    return filtered.slice(start, start + pageSize)
  }, [viewMode, filtered, page, pageSize])

  // 过滤条件/视图切换回到第一页
  useEffect(() => {
    setPage(1)
  }, [keyword, transformFilter, viewMode])

  const colspan = 6
  /** 行索引锚点（fields 为 key 真源，rows 实时值同序） */
  const indexOf = (key: string) => mappings.fields.findIndex((f) => f.key === key)

  const renderRow = (row: MappingRow) => {
    const index = indexOf(row.key)
    return (
      <DeviceMappingRowView
        key={row.key}
        value={row}
        sourceOptions={sourceOptions}
        targetOptions={targetOptions}
        transformOptions={transformOptions}
        sourceName={sourceName(row)}
        targetName={targetName(row)}
        onChange={(patch) => {
          if (patch.sourceParam !== undefined) handleSourceChange(index, patch.sourceParam)
          if (patch.targetParam !== undefined) handleTargetChange(index, patch.targetParam)
          if (patch.transformType !== undefined) {
            form.setValue(
              `${arrayName}.${index}.transformType` as FieldPath<AlgorithmFormValues>,
              patch.transformType ?? 'none'
            )
          }
        }}
        onRemove={() => mappings.remove(index)}
      />
    )
  }

  return (
    <div className='space-y-2'>
      {/* 公共工具栏：搜索 + 转换徽章筛选 + 平铺/分组切换 + 添加 */}
      <MappingToolbar>
        <MappingSearch value={keyword} onChange={setKeyword} />
        <MappingBadgeFilter
          title='转换'
          options={transformOptions}
          value={transformFilter}
          onValueChange={setTransformFilter}
          allLabel='全部转换'
        />
        <MappingViewToggle
          value={viewMode}
          ariaLabel='映射视图'
          options={[
            { value: 'flat', label: '平铺视图' },
            { value: 'group', label: '分组视图' },
          ]}
          onValueChange={setViewMode}
        />
        <MappingAddButton onClick={addEmpty} />
      </MappingToolbar>

      <MappingTableFrame
        columns={DEVICE_COLUMNS}
        colSpan={colspan}
        isEmpty={rows.length === 0}
        isFilteredEmpty={filtered.length === 0}
      >
        {viewMode === 'flat'
          ? pageRows.map(renderRow)
          : groups.map(([key, groupRows]) => {
              const isCollapsed = collapsed.has(key)
              return (
                <Fragment key={key}>
                  <tr className='bg-muted/40 border-border/50 border-b'>
                    <td colSpan={colspan} className='px-0 py-0'>
                      <GroupHeaderButton
                        name={DEVICE_API_GROUP_LABEL[key as keyof typeof DEVICE_API_GROUP_LABEL]}
                        count={groupRows.length}
                        collapsed={isCollapsed}
                        onToggle={() => toggleCollapsed(key)}
                      />
                    </td>
                  </tr>
                  {!isCollapsed && groupRows.map(renderRow)}
                  {!isCollapsed && <GroupAddRow colSpan={colspan} onClick={addEmpty} />}
                </Fragment>
              )
            })}
      </MappingTableFrame>

      {viewMode === 'flat' && filtered.length > pageSize && (
        <MappingPagination
          total={filtered.length}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      )}
    </div>
  )
}

/* ───────────────────────── 评估参数映射分节 ───────────────────────── */

const EVALUATION_COLUMNS = [
  { label: '来源' },
  { label: '源参数代码' },
  { label: '源参数名称' },
  { label: '目标评估维度' },
  { label: '目标参数' },
  { label: '转换' },
  { label: '操作', className: 'w-10 px-3 py-2 text-right font-medium' },
] as const

function EvaluationMappingSection({
  form,
  dimensions,
  categories = [],
}: {
  form: UseFormReturn<AlgorithmFormValues>
  dimensions: Dimension[]
  categories?: EvaluationCategory[]
}) {
  const mappings = useFieldArray({ control: form.control, name: 'mappings.evaluation' })
  const liveRows = useWatch({ control: form.control, name: 'mappings.evaluation' }) as
    | MappingRow[]
    | undefined
  const rows = liveRows ?? []
  const caseParams = useWatch({ control: form.control, name: 'caseParams' })
  const referenceParams = useWatch({ control: form.control, name: 'referenceParams' })
  const deviceParams = useWatch({ control: form.control, name: 'deviceParams' })

  const [keyword, setKeyword] = useState('')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [dimensionFilter, setDimensionFilter] = useState('all')
  const [transformFilter, setTransformFilter] = useState('all')
  const [viewMode, setViewMode] = useState<'flat' | 'dimension'>('dimension')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  /** 当前行引用的维度 id 集（预加载维度参数） */
  const dimensionIds = useMemo(() => rows.map((row) => row.dimensionId || ''), [rows])
  const dimensionParamsMap = useDimensionParamsMap(dimensionIds)

  /** 维度 id → 维度（组头主/子徽章、子维度父名） */
  const dimById = useMemo(
    () => new Map(dimensions.map((d) => [String(d.id), d])),
    [dimensions]
  )
  /** 行内 dimensionName 兜底（存量/已删除维度） */
  const dimensionNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const row of rows) {
      if (row.dimensionId && row.dimensionName && !map.has(String(row.dimensionId))) {
        map.set(String(row.dimensionId), row.dimensionName)
      }
    }
    return map
  }, [rows])

  /** 字典外存量维度的筛选选项（已删除维度：行内仍有 id/名称，字典查不到） */
  const orphanDimensionFilterOptions = useMemo(() => {
    const known = new Set(dimensions.map((dim) => String(dim.id)))
    const seen = new Set<string>()
    const options: Array<{ value: string; label: string }> = []
    for (const row of rows) {
      const key = row.dimensionId ? String(row.dimensionId) : ''
      if (!key || known.has(key) || seen.has(key)) continue
      seen.add(key)
      options.push({ value: key, label: row.dimensionName || `维度(${key})` })
    }
    return options
  }, [dimensions, rows])

  const addEmpty = (dimensionId = '', dimensionName = '') =>
    mappings.append({
      key: `mappings.evaluation-${Date.now()}-${rows.length}`,
      source: 'case',
      sourceDirection: 'output',
      sourceParam: '',
      paramName: '',
      dimensionId,
      dimensionName,
      targetParam: '',
      targetParamName: '',
      transformType: 'none',
    })

  const toggleCollapsed = (key: string) => {
    const next = new Set(collapsed)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setCollapsed(next)
  }

  /** 来源变更（V9.7.10 handleSourceTypeChange：清 source_param/param_name；case/case_config 清维度） */
  const handleSourceChange = (index: number, value: string) => {
    form.setValue(`mappings.evaluation.${index}.source` as FieldPath<AlgorithmFormValues>, value ?? 'case')
    form.setValue(`mappings.evaluation.${index}.sourceParam` as FieldPath<AlgorithmFormValues>, '')
    form.setValue(`mappings.evaluation.${index}.paramName` as FieldPath<AlgorithmFormValues>, '')
    if (value === 'case' || value === 'case_config') {
      form.setValue(`mappings.evaluation.${index}.dimensionId` as FieldPath<AlgorithmFormValues>, '')
      form.setValue(`mappings.evaluation.${index}.dimensionName` as FieldPath<AlgorithmFormValues>, '')
      form.setValue(`mappings.evaluation.${index}.targetParam` as FieldPath<AlgorithmFormValues>, '')
      form.setValue(`mappings.evaluation.${index}.targetParamName` as FieldPath<AlgorithmFormValues>, '')
    }
  }

  /** 源参数变更：回填 paramName + 判重提示（判重读实时值，INT-1160 返工 P2） */
  const handleSourceParamChange = (index: number, value: string) => {
    form.setValue(`mappings.evaluation.${index}.sourceParam` as FieldPath<AlgorithmFormValues>, value ?? '')
    const liveRows = (form.getValues('mappings.evaluation') ?? []) as MappingRow[]
    const source = liveRows[index]?.source || 'case'
    const name = evalSourceParamName(source, value ?? '', caseParams, referenceParams, deviceParams)
    form.setValue(`mappings.evaluation.${index}.paramName` as FieldPath<AlgorithmFormValues>, name)
    checkDup(index)
  }

  /** 维度变更：写 dimensionId/dimensionName、清维度内目标参数 + 判重 */
  const handleDimensionChange = (index: number, dimId: string) => {
    const id = dimId || ''
    const dim = dimensions.find((d) => String(d.id) === id)
    form.setValue(`mappings.evaluation.${index}.dimensionId` as FieldPath<AlgorithmFormValues>, id)
    form.setValue(`mappings.evaluation.${index}.dimensionName` as FieldPath<AlgorithmFormValues>, dim?.name ?? '')
    form.setValue(`mappings.evaluation.${index}.targetParam` as FieldPath<AlgorithmFormValues>, '')
    form.setValue(`mappings.evaluation.${index}.targetParamName` as FieldPath<AlgorithmFormValues>, '')
    checkDup(index)
  }

  /** 维度内目标参数变更：回填名称 + 判重（维度 id 读实时值，INT-1160 返工 P2） */
  const handleTargetChange = (index: number, value: string) => {
    form.setValue(`mappings.evaluation.${index}.targetParam` as FieldPath<AlgorithmFormValues>, value ?? '')
    const liveRows = (form.getValues('mappings.evaluation') ?? []) as MappingRow[]
    const dimId = liveRows[index]?.dimensionId || ''
    const params = dimensionParamsMap[dimId] ?? []
    const param = params.find((p) => p.code === value)
    form.setValue(
      `mappings.evaluation.${index}.targetParamName` as FieldPath<AlgorithmFormValues>,
      param?.name ?? ''
    )
    checkDup(index)
  }

  /**
   * 判重（评估 = source + sourceParam + dimensionId；V9.7.10 checkDuplicateMapping）。
   * 行值一律读 form.getValues() 实时快照：handler 内 setValue 后 useWatch 快照尚未更新，
   * 用渲染快照判重会漏报（INT-1160 返工 P2：编辑存量完备行 sourceParam/dimensionId
   * 制造重复时不弹 toast → 发布 schema 兜底拦截前必须先在交互层报出）。
   */
  const checkDup = (index: number) => {
    const liveRows = (form.getValues('mappings.evaluation') ?? []) as MappingRow[]
    const dupIndex = findDuplicateIndex(liveRows, index, 'evaluation')
    if (dupIndex < 0) return
    const row = liveRows[index]
    const dimId = row?.dimensionId || ''
    const dimName = dimId ? dimById.get(dimId)?.name || row?.dimensionName || dimId : ''
    const sourceLabel =
      EVALUATION_SOURCE_OPTIONS.find((o) => o.value === (row?.source || 'case'))?.label ?? '用例参数'
    warnDuplicate(sourceLabel, row?.sourceParam || '', dimName)
  }

  /** 过滤后的行（keyword/source/dimension/transform） */
  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return rows.filter((row) => {
      if (sourceFilter !== 'all' && (row.source || 'case') !== sourceFilter) return false
      if (dimensionFilter !== 'all') {
        const key = row.dimensionId ? String(row.dimensionId) : '__none__'
        if (key !== dimensionFilter) return false
      }
      if (transformFilter !== 'all' && row.transformType !== transformFilter) return false
      if (!kw) return true
      const dimName = row.dimensionId
        ? dimById.get(String(row.dimensionId))?.name || row.dimensionName || ''
        : ''
      return (
        (row.sourceParam || '').toLowerCase().includes(kw) ||
        (row.paramName || '').toLowerCase().includes(kw) ||
        (row.targetParam || '').toLowerCase().includes(kw) ||
        (row.targetParamName || '').toLowerCase().includes(kw) ||
        dimName.toLowerCase().includes(kw)
      )
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, keyword, sourceFilter, dimensionFilter, transformFilter, dimById])

  /** 评估维度视图：按 dimensionId 分组（组序按维度名中文排序，空行归「未指定维度」） */
  const groups = useMemo(() => {
    if (viewMode !== 'dimension') return []
    const map = new Map<string, MappingRow[]>()
    for (const row of filtered) {
      const key = evalGroupKey(row)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(row)
    }
    return Array.from(map.entries()).sort(([a], [b]) =>
      evalGroupName(a, dimensions, dimensionNameById).localeCompare(
        evalGroupName(b, dimensions, dimensionNameById),
        'zh-Hans-CN'
      )
    )
  }, [viewMode, filtered, dimensions, dimensionNameById])

  const pageRows = useMemo(() => {
    if (viewMode === 'dimension') return []
    const start = (page - 1) * pageSize
    return filtered.slice(start, start + pageSize)
  }, [viewMode, filtered, page, pageSize])

  useEffect(() => {
    setPage(1)
  }, [keyword, sourceFilter, dimensionFilter, transformFilter, viewMode])

  const colspan = 7
  const indexOf = (key: string) => mappings.fields.findIndex((f) => f.key === key)

  const renderRow = (row: MappingRow) => {
    const index = indexOf(row.key)
    return (
      <EvaluationMappingRowView
        key={row.key}
        value={{
          source: row.source || 'case',
          sourceParam: row.sourceParam,
          dimensionId: row.dimensionId || '',
          targetParam: row.targetParam,
          transformType: row.transformType,
          paramName: row.paramName,
          targetParamName: row.targetParamName,
        }}
        caseParams={caseParams}
        referenceParams={referenceParams}
        deviceParams={deviceParams}
        dimensions={dimensions}
        categories={categories}
        dimensionParams={dimensionParamsMap[row.dimensionId || ''] ?? []}
        transformOptions={TRANSFORM_TYPE_OPTIONS}
        onChange={(patch) => {
          if (patch.source !== undefined) handleSourceChange(index, patch.source)
          if (patch.sourceParam !== undefined) handleSourceParamChange(index, patch.sourceParam)
          if (patch.dimensionId !== undefined) handleDimensionChange(index, patch.dimensionId)
          if (patch.targetParam !== undefined) handleTargetChange(index, patch.targetParam)
          if (patch.transformType !== undefined) {
            form.setValue(
              `mappings.evaluation.${index}.transformType` as FieldPath<AlgorithmFormValues>,
              patch.transformType ?? 'none'
            )
          }
        }}
        onRemove={() => mappings.remove(index)}
      />
    )
  }

  return (
    <div className='space-y-2'>
      {/* 工具栏：搜索 + 来源 + 评估维度 + 转换徽章筛选 + 视图切换 + 添加 */}
      <MappingToolbar>
        <MappingSearch value={keyword} onChange={setKeyword} />
        <MappingBadgeFilter
          title='来源'
          options={EVALUATION_SOURCE_OPTIONS}
          value={sourceFilter}
          onValueChange={setSourceFilter}
          allLabel='全部来源'
        />
        {/* 评估维度筛选：分类 → 主维度 → 子维度（与用例 facet / 行内维度选择同口径） */}
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
          extraOptions={orphanDimensionFilterOptions}
        />
        <MappingBadgeFilter
          title='转换'
          options={TRANSFORM_TYPE_OPTIONS}
          value={transformFilter}
          onValueChange={setTransformFilter}
          allLabel='全部转换'
        />
        <MappingViewToggle
          value={viewMode}
          ariaLabel='评估映射视图'
          options={[
            { value: 'flat', label: '平铺视图' },
            { value: 'dimension', label: '评估维度视图' },
          ]}
          onValueChange={setViewMode}
        />
        <MappingAddButton onClick={() => addEmpty()} />
      </MappingToolbar>

      <MappingTableFrame
        columns={EVALUATION_COLUMNS}
        colSpan={colspan}
        isEmpty={rows.length === 0}
        isFilteredEmpty={filtered.length === 0}
      >
        {viewMode === 'flat'
          ? pageRows.map(renderRow)
          : groups.map(([key, groupRows]) => {
              const isCollapsed = collapsed.has(key)
              const dimId = !key.startsWith('name:') && key !== '__none__' ? key : ''
              const dim = dimById.get(dimId)
              const parentName = dim?.parentDimensionId
                ? dimensions.find((d) => String(d.id) === String(dim.parentDimensionId))?.name
                : undefined
              return (
                <Fragment key={key}>
                  <tr className='bg-muted/40 border-border/50 border-b'>
                    <td colSpan={colspan} className='px-0 py-0'>
                      <GroupHeaderButton
                        name={evalGroupName(key, dimensions, dimensionNameById)}
                        count={groupRows.length}
                        collapsed={isCollapsed}
                        onToggle={() => toggleCollapsed(key)}
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
                  {!isCollapsed && (
                    <GroupAddRow
                      colSpan={colspan}
                      onClick={() =>
                        addEmpty(
                          dimId,
                          dimId ? dimById.get(dimId)?.name ?? dimensionNameById.get(dimId) ?? '' : ''
                        )
                      }
                    />
                  )}
                </Fragment>
              )
            })}
      </MappingTableFrame>

      {viewMode === 'flat' && filtered.length > pageSize && (
        <MappingPagination
          total={filtered.length}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      )}
    </div>
  )
}

/* ───────────────────────── 两折叠分区外壳 ───────────────────────── */

export function MappingsSection({
  form,
  dimensions,
  categories = [],
}: {
  form: UseFormReturn<AlgorithmFormValues>
  /** 评估维度全量（含子维度；评估映射 target 按 分组/主维度/子维度 展示） */
  dimensions: Dimension[]
  /** 评估维度分类（分类分组组头） */
  categories?: EvaluationCategory[]
}) {
  const caseParams = useWatch({ control: form.control, name: 'caseParams' })
  const referenceParams = useWatch({ control: form.control, name: 'referenceParams' })
  const deviceParams = useWatch({ control: form.control, name: 'deviceParams' })

  const deviceCount = useWatch({ control: form.control, name: 'mappings.device' }).length
  const evaluationCount = useWatch({ control: form.control, name: 'mappings.evaluation' }).length

  return (
    <div className='space-y-3'>
      <MappingCollapsible
        defaultOpen
        title='设备参数映射'
        subtitle='用例参数 → 设备参数'
        count={deviceCount}
      >
        <DeviceMappingSection
          form={form}
          caseParams={caseParams}
          referenceParams={referenceParams}
          targetParams={deviceParams}
        />
      </MappingCollapsible>

      <MappingCollapsible
        title='评估参数映射'
        subtitle='用例参数/设备输出 → 评估维度'
        count={evaluationCount}
      >
        <EvaluationMappingSection
          form={form}
          dimensions={dimensions}
          categories={categories}
        />
      </MappingCollapsible>
    </div>
  )
}
