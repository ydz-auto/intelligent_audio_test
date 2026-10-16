/**
 * 数字域 RMS-SPL 映射数据表（§4.3；DataTablePage 对位——列=映射名称/关联 API/协议/供应商/
 * 参考基准/校准点数/增益限幅/校准状态/默认/操作）。
 * 保留现状 10 列表格形态；「默认」列由 apis.rmsSplMappingId 指针命中判定（§4.3）。
 */
import { Star, Waves } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { ApiConfigRef, ApiRmsSplMapping } from '@/domain/models/digitalSpl'
import { DIGITAL_PROTOCOL_OPTIONS } from '@/features/spl-mapping/constants'
import {
  formatGainClamp,
  formatReferenceBase,
} from '@/features/spl-mapping/lib/format'
import { DigitalSplRowActions } from '@/features/spl-mapping/components/digital-spl-row-actions'

export type DigitalSplTableProps = {
  rows: ApiRmsSplMapping[]
  apis: ApiConfigRef[]
  loading: boolean
  searchKeyword: string
  canRead: boolean
  canUpdate: boolean
  canCreate: boolean
  canDelete: boolean
  onEmptyCreate: () => void
  onDetail: (mapping: ApiRmsSplMapping) => void
  onEdit: (mapping: ApiRmsSplMapping) => void
  onCalibrate: (mapping: ApiRmsSplMapping) => void
  onToggleDefault: (mapping: ApiRmsSplMapping) => void
  onDelete: (mapping: ApiRmsSplMapping) => void
}

/** 关联 API 名（apiId → apis.name；缺省「API #{apiId}」） */
function resolveApiName(apis: ApiConfigRef[], apiId: number): string {
  const api = apis.find((a) => a.id === apiId)
  return api?.name ?? `API #${apiId}`
}

/** 默认指针命中（apis.rmsSplMappingId === mapping.id） */
function isDefaultMapping(apis: ApiConfigRef[], mapping: ApiRmsSplMapping): boolean {
  const api = apis.find((a) => a.id === mapping.apiId)
  return api?.rmsSplMappingId != null && api.rmsSplMappingId === mapping.id
}

/** 协议徽章（§4.3 websocket→WebSocket/HTTP） */
function ProtocolBadge({ protocol }: { protocol: ApiRmsSplMapping['protocol'] }) {
  if (!protocol) return <span className='text-muted-foreground'>—</span>
  const option = DIGITAL_PROTOCOL_OPTIONS.find((o) => o.value === protocol)
  return (
    <Badge variant='outline' className='rounded-md px-1.5 font-normal'>
      {option?.label ?? protocol}
    </Badge>
  )
}

export function DigitalSplTable(props: DigitalSplTableProps) {
  const isEmpty = !props.loading && props.rows.length === 0

  if (props.loading) {
    return (
      <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  if (isEmpty) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl ring-1'>
        <Empty className='h-80'>
          <EmptyMedia variant='icon'>
            <Waves aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>
              {props.searchKeyword ? '未找到匹配的映射' : '暂无 RMS-SPL 映射'}
            </EmptyTitle>
            <EmptyDescription>
              {props.searchKeyword
                ? '换个关键词或清除筛选条件试试'
                : '点击右上角「添加 RMS-SPL 映射」为被测 API 配置数字域灵敏度'}
            </EmptyDescription>
          </EmptyHeader>
          {!props.searchKeyword && (
            <EmptyContent>
              <Button variant='outline' size='sm' onClick={props.onEmptyCreate}>
                <Waves aria-hidden='true' className='size-3.5' />
                添加 RMS-SPL 映射
              </Button>
            </EmptyContent>
          )}
        </Empty>
      </div>
    )
  }

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[1000px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              <th className='px-3 py-2 text-left font-medium'>映射名称</th>
              <th className='px-3 py-2 text-left font-medium'>关联 API</th>
              <th className='px-3 py-2 text-left font-medium'>协议</th>
              <th className='px-3 py-2 text-left font-medium'>供应商</th>
              <th className='px-3 py-2 text-right font-medium'>参考基准</th>
              <th className='px-3 py-2 text-right font-medium'>校准点数</th>
              <th className='px-3 py-2 text-right font-medium'>增益限幅</th>
              <th className='px-3 py-2 text-left font-medium'>校准状态</th>
              <th className='px-3 py-2 text-left font-medium'>默认</th>
              <th className='w-14 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => {
              const isDefault = isDefaultMapping(props.apis, row)
              return (
                <tr key={row.id} className='hover:bg-muted/40 border-border/50 border-b last:border-b-0'>
                  <td className='max-w-56 px-3 py-2'>
                    <span className='min-w-0 block truncate font-medium'>
                      {row.name || `映射 #${row.id}`}
                    </span>
                    {row.description && (
                      <span className='text-muted-foreground min-w-0 block truncate text-xs'>
                        {row.description}
                      </span>
                    )}
                  </td>
                  <td className='max-w-40 px-3 py-2'>
                    <span className='min-w-0 block truncate'>
                      {resolveApiName(props.apis, row.apiId)}
                    </span>
                  </td>
                  <td className='px-3 py-2'>
                    <ProtocolBadge protocol={row.protocol} />
                  </td>
                  <td className='max-w-28 px-3 py-2'>
                    {row.vendor ? (
                      <span className='min-w-0 block truncate'>{row.vendor}</span>
                    ) : (
                      <span className='text-muted-foreground'>-</span>
                    )}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                    {formatReferenceBase(row.referenceSpl, row.referenceGainLinear)}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                    {row.calibrationPoints.length}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                    {formatGainClamp(row.minGainLinear, row.maxGainLinear)}
                  </td>
                  <td className='px-3 py-2'>
                    {row.calibrationStatus === 'calibrated' ? (
                      <StatusBadge variant='success' label='已校准' />
                    ) : (
                      <StatusBadge
                        variant={row.calibrationStatus === 'uncalibrated' ? 'warning' : 'neutral'}
                        label='未校准'
                      />
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    {isDefault ? (
                      <Badge variant='outline' className='gap-1 rounded-md px-1.5 font-normal'>
                        <Star aria-hidden='true' className='size-3 fill-[var(--warning)] text-[var(--warning)]' />
                        默认
                      </Badge>
                    ) : (
                      <span className='text-muted-foreground'>-</span>
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    <div className='flex items-center justify-end gap-0.5'>
                      <DigitalSplRowActions
                        mapping={row}
                        isDefault={isDefault}
                        canRead={props.canRead}
                        canUpdate={props.canUpdate}
                        canCreate={props.canCreate}
                        canDelete={props.canDelete}
                        onDetail={() => props.onDetail(row)}
                        onEdit={() => props.onEdit(row)}
                        onCalibrate={() => props.onCalibrate(row)}
                        onToggleDefault={() => props.onToggleDefault(row)}
                        onDelete={() => props.onDelete(row)}
                      />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
