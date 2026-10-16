/**
 * 物理域 SPL 映射数据表（§4.2；DataTablePage 对位——列=ID/映射名称/关联播放设备/设备类型/
 * 测量距离/目标声压级/测试频率/校准点数/校准状态/更新时间/操作）。
 * 桌面表格 + 移动卡片同源列定义（§2.1 口径）；校准曲线收进详情弹窗（§6.8）。
 */
import { AudioWaveform } from 'lucide-react'

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
import type { SplMapping } from '@/domain/models/splMapping'
import { DEVICE_TYPE_OPTIONS } from '@/features/spl-mapping/constants'
import {
  formatDateTime,
  formatDistance,
  formatTargetSpl,
  formatTestFrequency,
} from '@/features/spl-mapping/lib/format'
import { DeviceSplRowActions } from '@/features/spl-mapping/components/device-spl-row-actions'

export type DeviceSplTableProps = {
  rows: SplMapping[]
  loading: boolean
  searchKeyword: string
  canRead: boolean
  canUpdate: boolean
  canCreate: boolean
  canDelete: boolean
  onEmptyCreate: () => void
  onDetail: (mapping: SplMapping) => void
  onEdit: (mapping: SplMapping) => void
  onCalibrate: (mapping: SplMapping) => void
  onHistory: (mapping: SplMapping) => void
  onDelete: (mapping: SplMapping) => void
}

/** 校准状态徽章（§4.2：calibrated=success「已校准」/uncalibrated=warning「未校准」） */
function CalibrationStatusBadge({ status }: { status: SplMapping['calibrationStatus'] }) {
  if (status === 'calibrated') {
    return <StatusBadge variant='success' label='已校准' />
  }
  return <StatusBadge variant={status === 'uncalibrated' ? 'warning' : 'neutral'} label='未校准' />
}

/** 设备类型徽章（§4.2 dry/noise→干声/噪声） */
function DeviceTypeBadge({ deviceType }: { deviceType: SplMapping['deviceType'] }) {
  if (!deviceType) return <span className='text-muted-foreground'>—</span>
  const option = DEVICE_TYPE_OPTIONS.find((o) => o.value === deviceType)
  return (
    <Badge variant='outline' className='rounded-md px-1.5 font-normal'>
      {option?.label ?? deviceType}
    </Badge>
  )
}

export function DeviceSplTable(props: DeviceSplTableProps) {
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
            <AudioWaveform aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>
              {props.searchKeyword ? '未找到匹配的映射' : '暂无增益映射'}
            </EmptyTitle>
            <EmptyDescription>
              {props.searchKeyword
                ? '换个关键词或清除筛选条件试试'
                : '点击右上角「添加增益映射」创建第一条映射，或「导入映射数据」批量导入'}
            </EmptyDescription>
          </EmptyHeader>
          {!props.searchKeyword && (
            <EmptyContent>
              <Button variant='outline' size='sm' onClick={props.onEmptyCreate}>
                <AudioWaveform aria-hidden='true' className='size-3.5' />
                添加增益映射
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
        <table className='w-full min-w-[960px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              <th className='px-3 py-2 text-left font-medium'>ID</th>
              <th className='px-3 py-2 text-left font-medium'>映射名称</th>
              <th className='px-3 py-2 text-left font-medium'>关联播放设备</th>
              <th className='px-3 py-2 text-left font-medium'>设备类型</th>
              <th className='px-3 py-2 text-right font-medium'>测量距离</th>
              <th className='px-3 py-2 text-right font-medium'>目标声压级</th>
              <th className='px-3 py-2 text-right font-medium'>测试频率</th>
              <th className='px-3 py-2 text-right font-medium'>校准点数</th>
              <th className='px-3 py-2 text-left font-medium'>校准状态</th>
              <th className='px-3 py-2 text-left font-medium'>更新时间</th>
              <th className='w-14 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => (
              <tr key={row.id} className='hover:bg-muted/40 border-border/50 border-b last:border-b-0'>
                <td className='px-3 py-2'>
                  <span className='font-mono text-xs text-muted-foreground tabular-nums'>
                    #{row.id}
                  </span>
                </td>
                <td className='max-w-56 px-3 py-2'>
                  <span className='min-w-0 block truncate font-medium' title={row.name}>
                    {row.name}
                  </span>
                  {row.description && (
                    <span className='text-muted-foreground min-w-0 block truncate text-xs'>
                      {row.description}
                    </span>
                  )}
                </td>
                <td className='max-w-40 px-3 py-2'>
                  {row.deviceName ? (
                    <span className='min-w-0 block truncate'>
                      {row.deviceName}
                      {row.deviceModel && (
                        <span className='text-muted-foreground'>{`（${row.deviceModel}）`}</span>
                      )}
                    </span>
                  ) : (
                    <span className='text-muted-foreground'>未关联</span>
                  )}
                </td>
                <td className='px-3 py-2'>
                  <DeviceTypeBadge deviceType={row.deviceType} />
                </td>
                <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                  {formatDistance(row.distance)}
                </td>
                <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                  {formatTargetSpl(row.targetSpl)}
                </td>
                <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                  {formatTestFrequency(row.testFrequency)}
                </td>
                <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                  {row.calibrationData?.points.length ?? 0}
                </td>
                <td className='px-3 py-2'>
                  <CalibrationStatusBadge status={row.calibrationStatus} />
                </td>
                <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                  {formatDateTime(row.updatedAt)}
                </td>
                <td className='px-3 py-2'>
                  <div className='flex items-center justify-end gap-0.5'>
                    <DeviceSplRowActions
                      mapping={row}
                      canRead={props.canRead}
                      canUpdate={props.canUpdate}
                      canCreate={props.canCreate}
                      canDelete={props.canDelete}
                      onDetail={() => props.onDetail(row)}
                      onEdit={() => props.onEdit(row)}
                      onCalibrate={() => props.onCalibrate(row)}
                      onHistory={() => props.onHistory(row)}
                      onDelete={() => props.onDelete(row)}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
