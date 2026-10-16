/**
 * 物理域增益映射详情（§6.8；Dialog sm:max-w-3xl）。
 * 标题「增益映射详情」+ 状态 StatusBadge；基本信息分节 + 校准曲线（vChart，SPL↔增益散点/折线，
 * 深浅色 use-chart-theme；未校准显空态「尚无校准数据」）+ 校准点明细（StaticDataTable：增益/SPL）
 * + 「查看校准历史」操作钮（→§6.9）。
 */
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { VChart } from '@visactor/react-vchart'
import type { ISpec } from '@visactor/vchart'
import { History } from 'lucide-react'
import { useMemo } from 'react'

import type { SplMapping } from '@/domain/models/splMapping'
import { DEVICE_TYPE_OPTIONS } from '@/features/spl-mapping/constants'
import {
  formatDateTime,
  formatDistance,
  formatTargetSpl,
  formatTestFrequency,
} from '@/features/spl-mapping/lib/format'
import { buildCalibrationCurveSpec } from '@/features/spl-mapping/lib/charts'
import {
  useChartTheme,
  useThemePresetKey,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'

export type SplMappingDetailDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mapping: SplMapping | null
  onViewHistory: (mapping: SplMapping) => void
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className='grid grid-cols-[110px_1fr] gap-2 text-sm'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='min-w-0 break-words'>{value ?? '—'}</span>
    </div>
  )
}

/** 校准曲线（§6.8；vChart，key 含 themeKey/presetKey 整图重建） */
function CalibrationCurveChart({
  mapping,
}: {
  mapping: SplMapping
}) {
  const { themeReady, themeKey } = useChartTheme()
  const presetKey = useThemePresetKey()

  const spec = useMemo(() => {
    const points =
      mapping.calibrationData?.points
        ?.filter((p) => p.spl != null && p.gainOffset != null)
        .map((p) => ({ x: p.gainOffset as number, y: p.spl as number })) ?? []
    return buildCalibrationCurveSpec(points)
  }, [mapping.calibrationData])

  if (!themeReady) {
    return <Skeleton className='h-56 w-full' />
  }

  return (
    <VChart
      key={[spec.type, themeKey, presetKey, mapping.id].join('-')}
      spec={{ ...spec, theme: themeKey, background: 'transparent' } as ISpec}
      options={VCHART_OPTION}
    />
  )
}

export function SplMappingDetailDialog(props: SplMappingDetailDialogProps) {
  const mapping = props.mapping

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        {mapping && (
          <>
            <DialogHeader>
              <DialogTitle className='flex flex-wrap items-center gap-2'>
                增益映射详情
                {mapping.calibrationStatus === 'calibrated' ? (
                  <StatusBadge variant='success' label='已校准' />
                ) : (
                  <StatusBadge
                    variant={mapping.calibrationStatus === 'uncalibrated' ? 'warning' : 'neutral'}
                    label='未校准'
                  />
                )}
              </DialogTitle>
              <DialogDescription>
                {mapping.name} —— 设备 SPL（E2E 物理域）增益映射只读详情
              </DialogDescription>
            </DialogHeader>

            <div className='space-y-5'>
              <section aria-labelledby='spl-basic-title'>
                <h3 id='spl-basic-title' className='mb-2 text-sm font-medium'>基本信息</h3>
                <div className='space-y-2'>
                  <FieldRow label='映射名称' value={mapping.name} />
                  {mapping.description && <FieldRow label='描述' value={mapping.description} />}
                  <FieldRow
                    label='关联播放设备'
                    value={
                      mapping.deviceName
                        ? mapping.deviceModel
                          ? `${mapping.deviceName}（${mapping.deviceModel}）`
                          : mapping.deviceName
                        : '未关联'
                    }
                  />
                  <FieldRow
                    label='设备类型'
                    value={
                      mapping.deviceType
                        ? DEVICE_TYPE_OPTIONS.find((o) => o.value === mapping.deviceType)?.label
                        : '—'
                    }
                  />
                  <FieldRow label='测量距离' value={formatDistance(mapping.distance)} />
                  <FieldRow label='目标声压级' value={formatTargetSpl(mapping.targetSpl)} />
                  <FieldRow label='数字增益' value={mapping.digitalGain != null ? `${mapping.digitalGain} dB` : '—'} />
                  <FieldRow label='测试频率' value={formatTestFrequency(mapping.testFrequency)} />
                  <FieldRow
                    label='校准点数'
                    value={mapping.calibrationData?.points.length ?? 0}
                  />
                  <FieldRow label='创建时间' value={formatDateTime(mapping.createdAt)} />
                  <FieldRow label='更新时间' value={formatDateTime(mapping.updatedAt)} />
                </div>
              </section>

              <section aria-labelledby='spl-curve-title'>
                <h3 id='spl-curve-title' className='mb-2 text-sm font-medium'>校准曲线</h3>
                <div className='bg-card ring-foreground/10 rounded-lg p-2 ring-1'>
                  <div className='h-56'>
                    <CalibrationCurveChart mapping={mapping} />
                  </div>
                </div>
              </section>

              <section aria-labelledby='spl-points-title'>
                <h3 id='spl-points-title' className='mb-2 text-sm font-medium'>校准点明细</h3>
                {mapping.calibrationData?.points.length ? (
                  <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
                    <div className='overflow-x-auto'>
                      <table className='w-full min-w-0 text-[13px]'>
                        <thead>
                          <tr className='bg-[var(--table-header)] text-xs'>
                            <th className='px-3 py-2 text-right font-medium'>增益偏移</th>
                            <th className='px-3 py-2 text-right font-medium'>数字增益</th>
                            <th className='px-3 py-2 text-right font-medium'>基础电平</th>
                            <th className='px-3 py-2 text-right font-medium'>最终电平</th>
                            <th className='px-3 py-2 text-right font-medium'>实测 SPL</th>
                          </tr>
                        </thead>
                        <tbody>
                          {mapping.calibrationData.points.map((point, index) => (
                            <tr
                              key={index}
                              className='border-border/50 border-b last:border-b-0'
                            >
                              <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                                {point.gainOffset != null ? `${point.gainOffset} dB` : '—'}
                              </td>
                              <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                                {point.digitalGain != null ? `${point.digitalGain} dB` : '—'}
                              </td>
                              <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                                {point.baseLevel != null ? `${point.baseLevel} dBFS` : '—'}
                              </td>
                              <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                                {point.finalLevel != null ? `${point.finalLevel} dBFS` : '—'}
                              </td>
                              <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                                {point.spl != null ? `${point.spl} dB` : '—'}
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

            <DialogFooter>
              <Button
                variant='outline'
                size='sm'
                onClick={() => props.onViewHistory(mapping)}
              >
                <History aria-hidden='true' className='size-3.5' />
                查看校准历史
              </Button>
              <Button size='sm' onClick={() => props.onOpenChange(false)}>
                关闭
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
