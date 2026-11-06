/**
 * 数字域 RMS-SPL 映射数据表（§4.3 简化口径 INT-1031；DataTablePage 对位——列=映射名称/
 * 关联 API/参考基准/校准点数/增益限幅/校准状态/默认/操作；协议/供应商列隐藏）。
 * 「默认」列由 apis.rmsSplMappingId 指针命中判定（§4.3）。
 */
import { AlertTriangle, RotateCw, Star, Waves } from 'lucide-react'

import { ErrorState } from '@/components/error-state'
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
import {
  formatGainClamp,
  formatReferenceBase,
} from '@/features/spl-mapping/lib/format'
import { DigitalSplRowActions } from '@/features/spl-mapping/components/digital-spl-row-actions'

export type DigitalSplTableProps = {
  rows: ApiRmsSplMapping[]
  apis: ApiConfigRef[]
  loading: boolean
  /** 映射列表查询失败（INT-2331）：失败且无行时显示错误态 + 重试，不得伪装成「暂无 RMS-SPL 映射」 */
  isError?: boolean
  /** 查询失败重试（refetch） */
  onRetry?: () => void
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

export function DigitalSplTable(props: DigitalSplTableProps) {
  // 失败不等于空库（INT-2331，与 INT-1583 音频页同型）：isError 时不得走「暂无 RMS-SPL 映射」空态
  const isEmpty = !props.loading && !props.isError && props.rows.length === 0

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

  // 查询失败且无任何可展示行：显式错误态 + 重试（用户可区分「库里没有映射」与「接口挂了」）
  if (props.isError && props.rows.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl ring-1'>
        <ErrorState
          title='SPL 映射加载失败'
          description='RMS-SPL 映射列表获取失败，请重试'
          onRetry={props.onRetry}
        />
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
      {/* 失败但保留着上一次成功结果：不清空表格，行内提示 + 重试 */}
      {props.isError && (
        <div
          role='alert'
          className='border-destructive/30 bg-destructive/5 text-destructive flex flex-wrap items-center gap-2 border-b px-3 py-2 text-xs'
        >
          <AlertTriangle aria-hidden='true' className='size-3.5 shrink-0' />
          <span className='min-w-0 flex-1'>
            SPL 映射加载失败，当前显示的是上一次加载的数据
          </span>
          {props.onRetry && (
            <Button
              variant='outline'
              size='sm'
              className='h-7 gap-1'
              onClick={props.onRetry}
            >
              <RotateCw aria-hidden='true' className='size-3' />
              重试
            </Button>
          )}
        </div>
      )}
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[860px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              <th className='px-3 py-2 text-left font-medium'>映射名称</th>
              <th className='px-3 py-2 text-left font-medium'>关联 API</th>
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
