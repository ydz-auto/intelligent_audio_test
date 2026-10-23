/**
 * 算法详情弹窗（§7.2；Dialog sm:max-w-3xl + DetailSection 分节）。
 * 基本信息 + 参数定义（设备/API/用例三页签静态表）+ 参数映射（设备/API/评估三页签静态表）。
 * 权限 algorithm:read（tester 只读查看恢复入口，§12-2）。
 */
import { useMemo } from 'react'

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
import type { AlgorithmDefinition, DeviceApiParam } from '@/domain/models/algorithmConfig'
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
  if (dimensionName) return dimensionName
  if (dimensionId == null || dimensionId === '') return '—'
  const name = dimensions.find((d) => String(d.id) === String(dimensionId))?.name
  return name || `已删除维度 #${dimensionId}`
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

  const paramTotal = useMemo(
    () =>
      algorithm
        ? algorithm.deviceParams.length +
          algorithm.apiParams.length +
          algorithm.caseParams.length
        : 0,
    [algorithm]
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
                    <MappingRows mappings={algorithm.mappings.evaluation} empty='无评估参数映射' evaluation dimensions={props.dimensions} />
                  </TabsContent>
                </Tabs>
              </section>

              {algorithm.associatedDimensions.length > 0 && (
                <section aria-labelledby='algorithm-dimensions-title'>
                  <h3 id='algorithm-dimensions-title' className='mb-2 text-sm font-medium'>
                    评估维度关联
                  </h3>
                  <StaticTable headers={['评估维度', '权重', '默认']}>
                    {algorithm.associatedDimensions.map((relation) => (
                      <tr key={relation.id} className='border-border/50 border-b last:border-b-0'>
                        <td className='px-3 py-2'>
                          {resolveDimensionName(
                            props.dimensions ?? [],
                            relation.dimensionId,
                            relation.dimensionName
                          )}
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
                    ))}
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

function MappingRows({
  mappings,
  empty,
  evaluation = false,
  dimensions = [],
}: {
  mappings: AlgorithmDefinition['mappings']['device']
  empty: string
  /** evaluation 行带 来源/目标评估维度/维度内目标参数 列（INT-1160 列口径对齐 V9.7.10） */
  evaluation?: boolean
  /** 评估维度全量（evaluation 列 dimension_id → 名称解析；缺省显示 维度(id) 兜底） */
  dimensions?: Dimension[]
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
      headers={
        evaluation
          ? ['来源', '源参数代码', '源参数名称', '目标评估维度', '目标参数', '转换']
          : ['源参数代码', '源参数名称', '目标参数代码', '目标参数名称', '转换']
      }
    >
      {mappings.map((mapping) => {
        const dimName =
          mapping.dimensionName ||
          (mapping.dimensionId != null
            ? resolveDimensionName(dimensions, mapping.dimensionId)
            : '')
        return (
          <tr key={mapping.id || `${mapping.source}-${mapping.sourceParam}-${mapping.targetParam}-${mapping.dimensionId ?? ''}`} className='border-border/50 border-b last:border-b-0'>
            {evaluation && (
              <td className='px-3 py-2 text-xs'>
                {labelOf(
                  [
                    { value: 'case', label: '用例参数' },
                    { value: 'case_config', label: '用例配置' },
                    { value: 'reference', label: '参考参数' },
                    { value: 'device', label: '设备输出' },
                    { value: 'api', label: 'API输出' },
                  ],
                  mapping.source ?? 'case'
                )}
              </td>
            )}
            <td className='px-3 py-2 font-mono text-xs'>{mapping.sourceParam || '—'}</td>
            <td className='px-3 py-2 text-xs'>{mapping.paramName || '—'}</td>
            {evaluation && (
              <>
                <td className='px-3 py-2 text-xs'>{dimName || '—'}</td>
                <td className='px-3 py-2 font-mono text-xs'>{mapping.targetParam || '—'}</td>
              </>
            )}
            {!evaluation && (
              <td className='px-3 py-2 font-mono text-xs'>{mapping.targetParam || '—'}</td>
            )}
            {!evaluation && (
              <td className='px-3 py-2 text-xs'>{mapping.targetParamName || '—'}</td>
            )}
            <td className='px-3 py-2 text-xs'>
              {labelOf(TRANSFORM_TYPE_OPTIONS, mapping.transformType)}
            </td>
          </tr>
        )
      })}
    </StaticTable>
  )
}
