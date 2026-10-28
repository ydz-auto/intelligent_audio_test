/**
 * 算法详情弹窗（§7.2；Dialog sm:max-w-3xl + DetailSection 分节）。
 * 基本信息 + 参数定义（设备/API/用例三页签静态表）+ 参数映射（设备/API/评估三页签）。
 * 权限 algorithm:read（tester 只读查看恢复入口，§12-2）。
 *
 * INT-1644（对齐编辑模态窗评估维度视图，只读）：
 * - 参数映射 → 评估参数：按目标维度分组（组头 维度名 + 主/子徽章 + 父维度名 + 条数，可折叠，
 *   默认展开；空维度「未指定维度」，查不到「已删除维度 #id」），不再是一张几百行平铺长表。
 * - 评估维度关联：主维度与其子维度成组相邻、子维度带「子」徽章 + 父维度名；
 *   已删除维度统一排末尾按 id 升序，仍显示「已删除维度 #id」。
 */
import { Fragment, memo, useCallback, useMemo, useState } from 'react'
import { ChevronDown, Folder } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type {
  AlgorithmDefinition,
  DeviceApiParam,
  DimensionRelation,
  ParamMapping,
} from '@/domain/models/algorithmConfig'
import type { Dimension } from '@/domain/models/evaluationDimension'
import { AlgorithmStatusBadge } from '@/features/algorithm-config/components/algorithm-status-badge'
import {
  CASE_PARAM_TYPE_OPTIONS,
  DEVICE_PARAM_TYPE_OPTIONS,
  PARAM_DIRECTION_OPTIONS,
  TRANSFORM_TYPE_OPTIONS,
} from '@/features/algorithm-config/constants'

export type AlgorithmDetailDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  algorithm: AlgorithmDefinition | null
  /** 评估维度全量（§7.2 静态表 evaluation 列解析 dimension_id → 名称，避免裸 id） */
  dimensions?: Dimension[]
}

function labelOf(
  options: ReadonlyArray<{ value: string; label: string }>,
  value: string
): string {
  return options.find((o) => o.value === value)?.label ?? value
}

/** 维度 id → 维度索引（INT-2119：一次建表，替代每行 `dimensions.find` 线性扫描） */
export type DimensionIndex = Map<string, Dimension>

export function buildDimensionIndex(dimensions: Dimension[]): DimensionIndex {
  return new Map(dimensions.map((d) => [String(d.id), d]))
}

/**
 * 维度 id → 名称解析（INT-1558）：
 * 后端 associated_dimensions 只回 dimension_id 不回 dimension_name，名称由前端
 * dimensionOptions（evaluation/dimensions）补；查不到的（已删除 / 接口未返回）兜底
 * `已删除维度 #<id>`，不留空白单元格。
 */
export function resolveDimensionName(
  dimensions: Dimension[],
  dimensionId: number | string | null | undefined,
  dimensionName?: string | null
): string {
  return resolveDimensionNameByIndex(
    buildDimensionIndex(dimensions),
    dimensionId,
    dimensionName
  )
}

/** 索引版解析（渲染热路径用，避免逐行建索引） */
export function resolveDimensionNameByIndex(
  index: DimensionIndex,
  dimensionId: number | string | null | undefined,
  dimensionName?: string | null
): string {
  if (dimensionName) return dimensionName
  if (dimensionId == null || dimensionId === '') return '—'
  const name = index.get(String(dimensionId))?.name
  return name || `已删除维度 #${dimensionId}`
}

/**
 * 评估映射行/分组维度名（详情只读口径，INT-1644）：以 dimensions 全量为准，
 * 查不到的一律 `已删除维度 #<id>`（行内 dimensionName 是存量快照，已删维度不采信）；
 * 维度列表尚未加载（空）时退回行内 dimensionName，避免加载瞬间整表被误标为已删除。
 */
export function resolveMappingDimensionName(
  dimensions: Dimension[],
  dimensionId: number | string | null | undefined,
  dimensionName?: string | null
): string {
  return resolveMappingDimensionNameByIndex(
    buildDimensionIndex(dimensions),
    dimensionId,
    dimensionName
  )
}

export function resolveMappingDimensionNameByIndex(
  index: DimensionIndex,
  dimensionId: number | string | null | undefined,
  dimensionName?: string | null
): string {
  if (dimensionId == null || dimensionId === '') return ''
  const name = index.get(String(dimensionId))?.name
  if (name) return name
  if (index.size === 0 && dimensionName) return dimensionName
  return `已删除维度 #${dimensionId}`
}

/** 主/子维度徽章样式（与编辑模态窗 mappings-section 同款） */
const mainBadge =
  'bg-primary/20 text-primary inline-flex size-3.5 items-center justify-center rounded-[3px] text-[9px] font-semibold'
const subBadge =
  'bg-muted text-muted-foreground border-border inline-flex size-3.5 items-center justify-center rounded-[3px] border text-[9px] font-semibold'

/** 组头折叠按钮（照编辑模态窗 GroupHeaderButton，去掉可编辑内容） */
function GroupHeaderButton({
  name,
  badge,
  hint,
  count,
  collapsed,
  onToggle,
}: {
  name: string
  badge?: React.ReactNode
  hint?: string
  count: number
  collapsed: boolean
  onToggle: () => void
}) {
  return (
    <button
      type='button'
      onClick={onToggle}
      aria-expanded={!collapsed}
      className='hover:bg-muted/60 flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-medium transition-colors'
    >
      <ChevronDown
        aria-hidden='true'
        className={cn('size-3.5 shrink-0 transition-transform', collapsed && '-rotate-90')}
      />
      <Folder aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
      <span className='truncate'>{name}</span>
      {badge}
      {hint && <span className='text-muted-foreground/70 text-[11px] font-normal'>{hint}</span>}
      <span className='bg-muted text-muted-foreground ml-auto shrink-0 rounded-full px-1.5 text-[10px] tabular-nums'>
        {count} 条
      </span>
    </button>
  )
}

export type EvaluationMappingGroup = {
  /** 分组键：dimensionId 字符串，空维度 `__none__` */
  key: string
  /** 组头显示名（维度名 / 未指定维度 / 已删除维度 #id） */
  name: string
  /** dimensions 中命中的维度（组头主/子徽章用；已删除/未指定为 undefined） */
  dimension?: Dimension
  rows: ParamMapping[]
}

/**
 * 评估映射按目标维度分组（INT-1644 A）：组序按维度名中文排序，
 * 组内保持接口返回顺序；空维度归「未指定维度」。
 */
export function groupEvaluationMappings(
  mappings: ParamMapping[],
  dimensions: Dimension[]
): EvaluationMappingGroup[] {
  const dimById = buildDimensionIndex(dimensions)
  const map = new Map<string, ParamMapping[]>()
  for (const mapping of mappings) {
    const key =
      mapping.dimensionId == null || String(mapping.dimensionId) === ''
        ? '__none__'
        : String(mapping.dimensionId)
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(mapping)
  }
  return Array.from(map.entries())
    .map(([key, rows]) => ({
      key,
      name:
        key === '__none__'
          ? '未指定维度'
          : resolveMappingDimensionNameByIndex(dimById, key, rows[0]?.dimensionName),
      dimension: dimById.get(key),
      rows,
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN'))
}

/** 评估维度关联行（主维度 + 紧随其后的子维度，已删除维度排末尾） */
export type OrderedDimensionRelation = {
  relation: DimensionRelation
  /** dimensions 中命中的维度（已删除为 undefined） */
  dimension: Dimension | undefined
}

/**
 * 评估维度关联排序（INT-1644 B）：主维度行在前、其子维度紧随其后；
 * 父维度不在 dimensions 的按「已删除维度 #<父id>」兜底（渲染时解析）；
 * 已删除维度统一排末尾，按 dimensionId 升序。
 */
export function orderAssociatedDimensions(
  relations: DimensionRelation[],
  dimensions: Dimension[]
): OrderedDimensionRelation[] {
  const dimById = new Map(dimensions.map((d) => [String(d.id), d]))
  const resolved = relations
    .map((relation) => ({ relation, dimension: dimById.get(String(relation.dimensionId)) }))
    .filter((item): item is OrderedDimensionRelation => item.dimension !== undefined)
  const deleted = relations
    .filter((relation) => !dimById.has(String(relation.dimensionId)))
    .sort((a, b) => Number(a.dimensionId) - Number(b.dimensionId))

  const isSub = (item: OrderedDimensionRelation) => item.dimension?.parentDimensionId != null
  const mains = resolved.filter((item) => !isSub(item))
  const subs = resolved.filter(isSub)

  const ordered: OrderedDimensionRelation[] = []
  const seen = new Set<number>()
  const push = (item: OrderedDimensionRelation) => {
    if (seen.has(item.relation.id)) return
    seen.add(item.relation.id)
    ordered.push(item)
  }
  for (const main of mains) {
    push(main)
    for (const sub of subs) {
      if (
        String(sub.dimension?.parentDimensionId ?? '') === String(main.relation.dimensionId)
      ) {
        push(sub)
      }
    }
  }
  // 父维度未关联到本算法的子维度：原序补在主维度块之后，避免丢行
  for (const sub of subs) push(sub)

  return [...ordered, ...deleted.map((relation) => ({ relation, dimension: undefined }))]
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className='grid grid-cols-[100px_1fr] gap-2 text-sm'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='min-w-0 break-words'>{value ?? '—'}</span>
    </div>
  )
}

function StaticTable({
  headers,
  children,
}: {
  headers: string[]
  children: React.ReactNode
}) {
  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-0 text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              {headers.map((header) => (
                <th key={header} className='px-3 py-2 text-left font-medium'>
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </div>
  )
}

function DeviceParamRows({ params }: { params: DeviceApiParam[] }) {
  if (params.length === 0) {
    return (
      <tr>
        <td colSpan={7} className='text-muted-foreground px-3 py-4 text-center'>
          无设备参数
        </td>
      </tr>
    )
  }
  return params.map((param) => (
    <tr
      key={param.id}
      className='border-border/50 border-b last:border-b-0'
    >
      <td className='px-3 py-2 font-mono text-xs'>{param.paramCode}</td>
      <td className='px-3 py-2'>{param.paramName ?? '—'}</td>
      <td className='px-3 py-2 text-xs'>
        {labelOf(DEVICE_PARAM_TYPE_OPTIONS, param.paramType)}
      </td>
      <td className='px-3 py-2 text-xs'>
        {labelOf(PARAM_DIRECTION_OPTIONS, param.direction)}
      </td>
      <td className='px-3 py-2'>{param.required ? '是' : '否'}</td>
      <td className='px-3 py-2 font-mono text-xs'>{param.defaultValue || '—'}</td>
      <td className='text-muted-foreground max-w-56 truncate px-3 py-2 text-xs' title={param.helpText ?? ''}>
        {param.helpText || '—'}
      </td>
    </tr>
  ))
}

export function AlgorithmDetailDialog(props: AlgorithmDetailDialogProps) {
  const algorithm = props.algorithm
  const dimensions = props.dimensions

  const paramTotal = useMemo(
    () =>
      algorithm
        ? algorithm.deviceParams.length +
          algorithm.apiParams.length +
          algorithm.caseParams.length
        : 0,
    [algorithm]
  )

  /** INT-2119：维度索引与关联行排序结果 memo 化，避免每次渲染重建 / 逐行线性扫描 */
  const dimensionIndex = useMemo(
    () => buildDimensionIndex(dimensions ?? []),
    [dimensions]
  )

  const associatedDimensions = algorithm?.associatedDimensions
  const orderedRelations = useMemo(
    () =>
      associatedDimensions && associatedDimensions.length > 0
        ? orderAssociatedDimensions(associatedDimensions, dimensions ?? [])
        : [],
    [associatedDimensions, dimensions]
  )

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        {algorithm && (
          <>
            <DialogHeader>
              <DialogTitle className='flex flex-wrap items-center gap-2'>
                {algorithm.name}
                <AlgorithmStatusBadge status={algorithm.status} />
              </DialogTitle>
              <DialogDescription>
                算法定义与参数映射只读详情
              </DialogDescription>
            </DialogHeader>

            <div className='space-y-5'>
              <section aria-labelledby='algorithm-basic-title'>
                <h3
                  id='algorithm-basic-title'
                  className='mb-2 text-sm font-medium'
                >
                  基本信息
                </h3>
                <div className='space-y-2'>
                  <FieldRow label='算法类型' value={algorithm.type} />
                  <FieldRow label='显示名称' value={algorithm.name} />
                  <FieldRow label='所属分组' value={algorithm.groupName ?? '未分组'} />
                  <FieldRow label='状态' value={algorithm.status === 'online' ? '上线' : '下线'} />
                  <FieldRow label='排序' value={algorithm.displayOrder} />
                  <FieldRow label='参数数量' value={paramTotal} />
                  <FieldRow label='创建时间' value={new Date(algorithm.createdAt).toLocaleString()} />
                  <FieldRow label='更新时间' value={new Date(algorithm.updatedAt).toLocaleString()} />
                  {algorithm.description && (
                    <FieldRow label='描述' value={algorithm.description} />
                  )}
                </div>
              </section>

              <section aria-labelledby='algorithm-params-title'>
                <h3 id='algorithm-params-title' className='mb-2 text-sm font-medium'>
                  参数定义
                </h3>
                <Tabs defaultValue='device'>
                  <TabsList variant='line' className='w-full justify-start'>
                    <TabsTrigger value='device'>设备参数（{algorithm.deviceParams.length}）</TabsTrigger>
                    <TabsTrigger value='api'>API参数（{algorithm.apiParams.length}）</TabsTrigger>
                    <TabsTrigger value='case'>用例参数（{algorithm.caseParams.length}）</TabsTrigger>
                  </TabsList>
                  <TabsContent value='device' className='pt-2'>
                    <StaticTable headers={['参数代码', '参数名称', '类型', '方向', '必填', '默认值', '帮助文本']}>
                      <DeviceParamRows params={algorithm.deviceParams} />
                    </StaticTable>
                  </TabsContent>
                  <TabsContent value='api' className='pt-2'>
                    <StaticTable headers={['参数代码', '参数名称', '类型', '方向', '必填', '默认值', '帮助文本']}>
                      <DeviceParamRows params={algorithm.apiParams} />
                    </StaticTable>
                  </TabsContent>
                  <TabsContent value='case' className='pt-2'>
                    <StaticTable headers={['参数代码', '参数名称', '类型', '适用范围', '必填', '默认值']}>
                      {algorithm.caseParams.length === 0 ? (
                        <tr>
                          <td colSpan={6} className='text-muted-foreground px-3 py-4 text-center'>
                            无用例参数
                          </td>
                        </tr>
                      ) : (
                        algorithm.caseParams.map((param) => (
                          <tr key={param.id} className='border-border/50 border-b last:border-b-0'>
                            <td className='px-3 py-2 font-mono text-xs'>{param.paramCode}</td>
                            <td className='px-3 py-2'>{param.paramName ?? '—'}</td>
                            <td className='px-3 py-2 text-xs'>
                              {labelOf(CASE_PARAM_TYPE_OPTIONS, param.paramType)}
                            </td>
                            <td className='px-3 py-2 text-xs'>
                              {labelOf(
                                [
                                  { value: 'common', label: '通用' },
                                  { value: 'api', label: 'API' },
                                  { value: 'e2e', label: 'E2E' },
                                ],
                                param.scope
                              )}
                            </td>
                            <td className='px-3 py-2'>{param.required ? '是' : '否'}</td>
                            <td className='px-3 py-2 font-mono text-xs'>{param.defaultValue ?? '—'}</td>
                          </tr>
                        ))
                      )}
                    </StaticTable>
                  </TabsContent>
                </Tabs>
              </section>

              <section aria-labelledby='algorithm-mappings-title'>
                <h3 id='algorithm-mappings-title' className='mb-2 text-sm font-medium'>
                  参数映射
                </h3>
                <Tabs defaultValue='device'>
                  <TabsList variant='line' className='w-full justify-start'>
                    <TabsTrigger value='device'>设备参数（{algorithm.mappings.device.length}）</TabsTrigger>
                    <TabsTrigger value='api'>API参数（{algorithm.mappings.api.length}）</TabsTrigger>
                    <TabsTrigger value='evaluation'>评估参数（{algorithm.mappings.evaluation.length}）</TabsTrigger>
                  </TabsList>
                  <TabsContent value='device' className='pt-2'>
                    <MappingRows mappings={algorithm.mappings.device} empty='无设备参数映射' />
                  </TabsContent>
                  <TabsContent value='api' className='pt-2'>
                    <MappingRows mappings={algorithm.mappings.api} empty='无 API 参数映射' />
                  </TabsContent>
                  <TabsContent value='evaluation' className='pt-2'>
                    <EvaluationMappingRows
                      mappings={algorithm.mappings.evaluation}
                      dimensions={dimensions}
                    />
                  </TabsContent>
                </Tabs>
              </section>

              {orderedRelations.length > 0 && (
                <section aria-labelledby='algorithm-dimensions-title'>
                  <h3 id='algorithm-dimensions-title' className='mb-2 text-sm font-medium'>
                    评估维度关联
                  </h3>
                  <StaticTable headers={['评估维度', '权重', '默认']}>
                    {orderedRelations.map(({ relation, dimension }) => {
                      const isSub = dimension?.parentDimensionId != null
                      return (
                        <tr key={relation.id} className='border-border/50 border-b last:border-b-0'>
                          <td className='px-3 py-2'>
                            <span className='inline-flex flex-wrap items-center gap-1.5'>
                              <span>
                                {resolveDimensionNameByIndex(
                                  dimensionIndex,
                                  relation.dimensionId,
                                  relation.dimensionName
                                )}
                              </span>
                              {dimension &&
                                (isSub ? (
                                  <>
                                    <span className={subBadge}>子</span>
                                    <span className='text-muted-foreground/70 text-[11px]'>
                                      （
                                      {resolveDimensionNameByIndex(
                                        dimensionIndex,
                                        dimension.parentDimensionId
                                      )}
                                      ）
                                    </span>
                                  </>
                                ) : (
                                  <span className={mainBadge}>主</span>
                                ))}
                            </span>
                          </td>
                          <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                            {relation.weight}
                          </td>
                          <td className='px-3 py-2'>
                            <Badge
                              variant={relation.isDefault ? 'default' : 'outline'}
                              className={cn('px-1.5 text-[11px] font-normal', !relation.isDefault && 'text-muted-foreground')}
                            >
                              {relation.isDefault ? '默认' : '—'}
                            </Badge>
                          </td>
                        </tr>
                      )
                    })}
                  </StaticTable>
                </section>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** 设备 / API 参数映射（平铺 5 列，INT-1160 列口径） */
function MappingRows({
  mappings,
  empty,
}: {
  mappings: AlgorithmDefinition['mappings']['device']
  empty: string
}) {
  if (mappings.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 text-muted-foreground rounded-lg px-3 py-4 text-center text-xs ring-1'>
        {empty}
      </div>
    )
  }
  return (
    <StaticTable
      headers={['源参数代码', '源参数名称', '目标参数代码', '目标参数名称', '转换']}
    >
      {mappings.map((mapping) => (
        <tr key={mapping.id || `${mapping.source}-${mapping.sourceParam}-${mapping.targetParam}-${mapping.dimensionId ?? ''}`} className='border-border/50 border-b last:border-b-0'>
          <td className='px-3 py-2 font-mono text-xs'>{mapping.sourceParam || '—'}</td>
          <td className='px-3 py-2 text-xs'>{mapping.paramName || '—'}</td>
          <td className='px-3 py-2 font-mono text-xs'>{mapping.targetParam || '—'}</td>
          <td className='px-3 py-2 text-xs'>{mapping.targetParamName || '—'}</td>
          <td className='px-3 py-2 text-xs'>
            {labelOf(TRANSFORM_TYPE_OPTIONS, mapping.transformType)}
          </td>
        </tr>
      ))}
    </StaticTable>
  )
}

/** 评估映射来源列选项（与编辑模态窗同口径） */
const EVALUATION_SOURCE_LABELS = [
  { value: 'case', label: '用例参数' },
  { value: 'case_config', label: '用例配置' },
  { value: 'reference', label: '参考参数' },
  { value: 'device', label: '设备输出' },
  { value: 'api', label: 'API输出' },
] as const

/**
 * 评估参数映射（INT-1644 A）：只读「评估维度分组视图」，照编辑模态窗
 * EvaluationMappingSection 评估维度视图。组头可折叠，默认全部展开。
 *
 * INT-2119：分组结果、维度索引 useMemo 化；每组（组头 + 组内行）单独 memo，
 * 折叠/展开只重渲染被点的组，不再整表 reconcile（实测见交付评论）。
 */
function EvaluationMappingRows({
  mappings,
  dimensions,
}: {
  mappings: ParamMapping[]
  dimensions?: Dimension[]
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const dimensionIndex = useMemo(
    () => buildDimensionIndex(dimensions ?? []),
    [dimensions]
  )
  const groups = useMemo(
    () => groupEvaluationMappings(mappings, dimensions ?? []),
    [mappings, dimensions]
  )
  const toggleCollapsed = useCallback((key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  if (mappings.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 text-muted-foreground rounded-lg px-3 py-4 text-center text-xs ring-1'>
        无评估参数映射
      </div>
    )
  }

  return (
    <StaticTable
      headers={['来源', '源参数代码', '源参数名称', '目标评估维度', '目标参数', '转换']}
    >
      {groups.map((group) => (
        <EvaluationMappingGroupRows
          key={group.key}
          group={group}
          collapsed={collapsed.has(group.key)}
          dimensionIndex={dimensionIndex}
          onToggle={toggleCollapsed}
        />
      ))}
    </StaticTable>
  )
}

/** 单个维度分组（组头 + 组内行）；props 稳定时折叠别的组不触发本组重渲染 */
const EvaluationMappingGroupRows = memo(function EvaluationMappingGroupRows({
  group,
  collapsed,
  dimensionIndex,
  onToggle,
}: {
  group: EvaluationMappingGroup
  collapsed: boolean
  dimensionIndex: DimensionIndex
  onToggle: (key: string) => void
}) {
  const isSub = group.dimension?.parentDimensionId != null
  const parentName = isSub
    ? resolveDimensionNameByIndex(dimensionIndex, group.dimension?.parentDimensionId)
    : ''
  return (
    <Fragment>
      <tr className='bg-muted/40 border-border/50 border-b'>
        <td colSpan={6} className='px-0 py-0'>
          <GroupHeaderButton
            name={group.name}
            count={group.rows.length}
            collapsed={collapsed}
            onToggle={() => onToggle(group.key)}
            badge={
              group.dimension ? (
                isSub ? (
                  <span className={subBadge}>子</span>
                ) : (
                  <span className={mainBadge}>主</span>
                )
              ) : undefined
            }
            hint={parentName ? `（${parentName}）` : undefined}
          />
        </td>
      </tr>
      {!collapsed &&
        group.rows.map((mapping) => (
          <tr
            key={mapping.id || `${mapping.source}-${mapping.sourceParam}-${mapping.targetParam}-${mapping.dimensionId ?? ''}`}
            className='border-border/50 border-b last:border-b-0'
          >
            <td className='px-3 py-2 text-xs'>
              {labelOf(EVALUATION_SOURCE_LABELS, mapping.source ?? 'case')}
            </td>
            <td className='px-3 py-2 font-mono text-xs'>{mapping.sourceParam || '—'}</td>
            <td className='px-3 py-2 text-xs'>{mapping.paramName || '—'}</td>
            <td className='px-3 py-2 text-xs'>{group.name || '—'}</td>
            <td className='px-3 py-2 font-mono text-xs'>{mapping.targetParam || '—'}</td>
            <td className='px-3 py-2 text-xs'>
              {labelOf(TRANSFORM_TYPE_OPTIONS, mapping.transformType)}
            </td>
          </tr>
        ))}
    </Fragment>
  )
})
