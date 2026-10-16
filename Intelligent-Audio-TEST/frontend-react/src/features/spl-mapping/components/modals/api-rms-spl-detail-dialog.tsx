/**
 * 数字域 RMS-SPL 映射详情（§6.11；Dialog sm:max-w-3xl）。
 * DetailSection：基本信息（名称/API名/协议/供应商/参考声压级/参考线性增益/增益限幅/校准状态/
 * 是否默认/校准点数）；校准点明细（StaticDataTable：目标SPL→线性增益(→dB)→实测RMS dBFS，升序）。
 */
import { Star } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { ApiConfigRef, ApiRmsSplMapping } from '@/domain/models/digitalSpl'
import { DIGITAL_PROTOCOL_OPTIONS } from '@/features/spl-mapping/constants'
import {
  formatDateTime,
  formatGainClamp,
  formatReferenceBase,
  gainToDb,
} from '@/features/spl-mapping/lib/format'

export type ApiRmsSplDetailDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mapping: ApiRmsSplMapping | null
  apis: ApiConfigRef[]
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className='grid grid-cols-[130px_1fr] gap-2 text-sm'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='min-w-0 break-words'>{value ?? '—'}</span>
    </div>
  )
}

export function ApiRmsSplDetailDialog(props: ApiRmsSplDetailDialogProps) {
  const mapping = props.mapping

  const api = props.apis.find((a) => a.id === mapping?.apiId)
  const isDefault =
    mapping != null && api?.rmsSplMappingId != null && api.rmsSplMappingId === mapping.id

  const sortedPoints = mapping
    ? [...mapping.calibrationPoints].sort((a, b) => a.targetSpl - b.targetSpl)
    : []

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        {mapping && (
          <>
            <DialogHeader>
              <DialogTitle className='flex flex-wrap items-center gap-2'>
                RMS-SPL 映射详情
                {mapping.calibrationStatus === 'calibrated' ? (
                  <StatusBadge variant='success' label='已校准' />
                ) : (
                  <StatusBadge
                    variant={mapping.calibrationStatus === 'uncalibrated' ? 'warning' : 'neutral'}
                    label='未校准'
                  />
                )}
                {isDefault && (
                  <Badge variant='outline' className='gap-1 rounded-md px-1.5 font-normal'>
                    <Star aria-hidden='true' className='size-3 fill-[var(--warning)] text-[var(--warning)]' />
                    默认
                  </Badge>
                )}
              </DialogTitle>
              <DialogDescription>
                {mapping.name || `映射 #${mapping.id}`} —— API/Realtime 数字域 RMS 映射只读详情
              </DialogDescription>
            </DialogHeader>

            <div className='space-y-5'>
              <section aria-labelledby='digital-basic-title'>
                <h3 id='digital-basic-title' className='mb-2 text-sm font-medium'>基本信息</h3>
                <div className='space-y-2'>
                  <FieldRow label='映射名称' value={mapping.name || `映射 #${mapping.id}`} />
                  {mapping.description && <FieldRow label='描述' value={mapping.description} />}
                  <FieldRow label='关联 API' value={api?.name ?? `API #${mapping.apiId}`} />
                  <FieldRow
                    label='协议'
                    value={
                      mapping.protocol
                        ? DIGITAL_PROTOCOL_OPTIONS.find((o) => o.value === mapping.protocol)?.label
                        : '—'
                    }
                  />
                  <FieldRow label='供应商' value={mapping.vendor || '-'} />
                  <FieldRow
                    label='参考基准'
                    value={formatReferenceBase(mapping.referenceSpl, mapping.referenceGainLinear)}
                  />
                  <FieldRow
                    label='增益限幅'
                    value={formatGainClamp(mapping.minGainLinear, mapping.maxGainLinear)}
                  />
                  <FieldRow label='是否默认' value={isDefault ? '默认' : '-'} />
                  <FieldRow label='校准点数' value={mapping.calibrationPoints.length} />
                  <FieldRow label='创建时间' value={formatDateTime(mapping.createdAt)} />
                  <FieldRow label='更新时间' value={formatDateTime(mapping.updatedAt)} />
                </div>
              </section>

              <section aria-labelledby='digital-points-title'>
                <h3 id='digital-points-title' className='mb-2 text-sm font-medium'>校准点明细</h3>
                {sortedPoints.length ? (
                  <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
                    <div className='overflow-x-auto'>
                      <table className='w-full min-w-0 text-[13px]'>
                        <thead>
                          <tr className='bg-[var(--table-header)] text-xs'>
                            <th className='px-3 py-2 text-right font-medium'>目标 SPL</th>
                            <th className='px-3 py-2 text-right font-medium'>线性增益</th>
                            <th className='px-3 py-2 text-right font-medium'>增益（dB）</th>
                            <th className='px-3 py-2 text-right font-medium'>实测 RMS</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sortedPoints.map((point, index) => (
                            <tr key={index} className='border-border/50 border-b last:border-b-0'>
                              <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                                {point.targetSpl} dB
                              </td>
                              <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                                {point.gainLinear}
                              </td>
                              <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                                {gainToDb(point.gainLinear)}
                              </td>
                              <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                                {point.rmsDbfs != null ? `${point.rmsDbfs} dBFS` : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className='bg-card ring-foreground/10 text-muted-foreground rounded-lg px-3 py-4 text-center text-xs ring-1'>
                    尚无校准数据
                  </div>
                )}
              </section>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
