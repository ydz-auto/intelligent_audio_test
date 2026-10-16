/**
 * 数字域 RMS-SPL 校准弹窗（§6.10；Dialog sm:max-w-3xl）。
 * 标题「RMS-SPL 数字校准」+ 顶部说明 info + 参考基准四格 + 校准点集表（目标SPL/线性增益/
 * 增益(dB 只读 gainToDb)/实测RMS/删除；行级校验：SPL 范围/增益正数/限幅/重复 x）+「按参考生成」
 * 钮（已有非空点集两步确认）+ 增益曲线预览（vChart，SPL→gain，≥2 点）+ 互斥提示 info +
 * 底栏「取消｜提交校准」（disabled 无有效点；提交中「校准中...」）。
 * POST /digital-spl/{id}/calibrate（digital_spl:create）；成功 toast 逐字保留；409 互斥提示。
 */
import { Lock, Plus, RefreshCw, Trash2, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { VChart } from '@visactor/react-vchart'
import type { ISpec } from '@visactor/vchart'

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import type { ApiRmsSplMapping } from '@/domain/models/digitalSpl'
import { useDigitalSplMutations } from '@/application/spl/useDigitalSplMappings'
import {
  CALIBRATION_RMS_MAX,
  CALIBRATION_RMS_MIN,
  CALIBRATION_TARGET_SPL_MAX,
  CALIBRATION_TARGET_SPL_MIN,
  DIGITAL_CALIBRATION_INFO_TEXT,
  DIGITAL_CALIBRATION_LOCK_TEXT,
} from '@/features/spl-mapping/constants'
import { gainToDb, formatGainClamp, formatLinearGain } from '@/features/spl-mapping/lib/format'
import { buildDigitalGainCurveSpec } from '@/features/spl-mapping/lib/charts'
import {
  useChartTheme,
  useThemePresetKey,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'

export type ApiRmsSplCalibrationDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mapping: ApiRmsSplMapping | null
}

interface PointDraft {
  targetSpl: string
  gainLinear: string
  rmsDbfs: string
}

/** 行级校验错误（§6.10：SPL 范围/增益正数/限幅） */
interface PointError {
  targetSpl?: string
  gainLinear?: string
}

function validatePoint(
  point: PointDraft,
  minGain: number,
  maxGain: number
): PointError {
  const errors: PointError = {}
  const target = Number(point.targetSpl)
  const gain = Number(point.gainLinear)
  if (point.targetSpl === '' || Number.isNaN(target)) {
    errors.targetSpl = '请输入目标 SPL'
  } else if (target < CALIBRATION_TARGET_SPL_MIN || target > CALIBRATION_TARGET_SPL_MAX) {
    errors.targetSpl = `范围 ${CALIBRATION_TARGET_SPL_MIN}~${CALIBRATION_TARGET_SPL_MAX}`
  }
  if (point.gainLinear === '' || Number.isNaN(gain) || gain <= 0) {
    errors.gainLinear = '请输入正数增益'
  } else if (gain < minGain || gain > maxGain) {
    errors.gainLinear = `限幅 ${minGain}~${maxGain}`
  }
  return errors
}

/** 按参考生成点集（§6.10：以 refSpl 为中心 ±20dB 每 10dB 一点=5 点） */
function generateByReference(refSpl: number, refGain: number): PointDraft[] {
  return [-20, -10, 0, 10, 20].map((offset) => {
    const target = Math.round((refSpl + offset) * 10) / 10
    const gain = refGain * Math.pow(10, offset / 20)
    return {
      targetSpl: String(target),
      gainLinear: gain.toFixed(4),
      rmsDbfs: '',
    }
  })
}

export function ApiRmsSplCalibrationDialog(props: ApiRmsSplCalibrationDialogProps) {
  const mapping = props.mapping
  const { calibrate } = useDigitalSplMutations()
  const { themeReady, themeKey } = useChartTheme()
  const presetKey = useThemePresetKey()

  const [points, setPoints] = useState<PointDraft[]>([])
  const [pending, setPending] = useState(false)
  // 「按参考生成」两步确认（§6.10：已有非空点集时再点一次确认覆盖）
  const [generateConfirmOpen, setGenerateConfirmOpen] = useState(false)

  useEffect(() => {
    if (!props.open || !mapping) return
    setPoints(
      mapping.calibrationPoints.length
        ? mapping.calibrationPoints.map((point) => ({
            targetSpl: String(point.targetSpl),
            gainLinear: String(point.gainLinear),
            rmsDbfs: point.rmsDbfs != null ? String(point.rmsDbfs) : '',
          }))
        : []
    )
    setPending(false)
    setGenerateConfirmOpen(false)
  }, [props.open, mapping])

  const infoText = useMemo(() => {
    const refGain = mapping?.referenceGainLinear ?? 1.0
    const refSpl = mapping?.referenceSpl ?? 65
    return DIGITAL_CALIBRATION_INFO_TEXT
      .replace('{refGain}', String(refGain))
      .replace('{refSpl}', String(refSpl))
  }, [mapping?.referenceGainLinear, mapping?.referenceSpl])

  /** 重复目标 SPL 拦截（§6.10：重复 x 拦截；mapping 空时无点集可校验，恒空集） */
  const duplicateIndexes = useMemo(() => {
    const seen = new Map<string, number[]>()
    points.forEach((point, index) => {
      const target = point.targetSpl.trim()
      if (target === '') return
      const list = seen.get(target) ?? []
      list.push(index)
      seen.set(target, list)
    })
    const duplicated = new Set<number>()
    seen.forEach((indexes) => {
      if (indexes.length > 1) indexes.forEach((i) => duplicated.add(i))
    })
    return duplicated
  }, [points])

  const curveSpec = useMemo(() => {
    const curvePoints = points
      .map((point) => ({
        x: Number(point.targetSpl),
        y: Number(point.gainLinear),
      }))
      .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y) && point.y > 0)
      .map((point) => ({ x: point.x, y: Number(20 * Math.log10(point.y)) }))
    return buildDigitalGainCurveSpec(curvePoints)
  }, [points])

  if (!mapping) return null

  const minGain = mapping.minGainLinear ?? 0.001
  const maxGain = mapping.maxGainLinear ?? 10.0

  const errors = points.map((point) => validatePoint(point, minGain, maxGain))

  const validCount = points.filter((_, index) => {
    const hasError = Object.keys(errors[index]).length > 0
    const isDuplicate = duplicateIndexes.has(index)
    const target = points[index].targetSpl.trim()
    const gain = points[index].gainLinear.trim()
    return !hasError && !isDuplicate && target !== '' && gain !== ''
  }).length

  const addPoint = () => setPoints((prev) => [...prev, { targetSpl: '', gainLinear: '', rmsDbfs: '' }])
  const removePoint = (index: number) =>
    setPoints((prev) => prev.filter((_, i) => i !== index))
  const patchPoint = (index: number, patch: Partial<PointDraft>) =>
    setPoints((prev) => prev.map((point, i) => (i === index ? { ...point, ...patch } : point)))

  const handleGenerate = () => {
    const nonEmpty = points.filter((point) => point.targetSpl.trim() || point.gainLinear.trim()).length
    if (nonEmpty > 0) {
      setGenerateConfirmOpen(true)
      return
    }
    applyGenerated()
  }

  const applyGenerated = () => {
    const refSpl = mapping.referenceSpl ?? 65
    const refGain = mapping.referenceGainLinear ?? 1.0
    setPoints(generateByReference(refSpl, refGain))
    setGenerateConfirmOpen(false)
  }

  const handleSubmit = async () => {
    if (validCount === 0) {
      toast.error('请填写有效的校准点')
      return
    }
    setPending(true)
    try {
      const payload = points
        .filter((_, index) => !duplicateIndexes.has(index))
        .map((point) => ({
          targetSpl: Number(point.targetSpl),
          gainLinear: Number(point.gainLinear),
          rmsDbfs: point.rmsDbfs === '' || Number.isNaN(Number(point.rmsDbfs))
            ? null
            : Number(point.rmsDbfs),
        }))
      await calibrate.mutateAsync({ id: mapping.id, points: payload })
      toast.success('校准完成：校准点已落库并置为已校准')
      props.onOpenChange(false)
    } catch {
      // 409：同 API 并发校准互斥（§6.10；mock 阶段走成功路径，接线后由后端返 409）
      toast.error('校准失败（409）：API 正在执行校准，请稍后重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        <DialogContent className='sm:max-w-3xl'>
          <DialogHeader>
            <DialogTitle>RMS-SPL 数字校准</DialogTitle>
            <DialogDescription>
              {mapping.name || `映射 #${mapping.id}`} —— 数字域点集全量替换
            </DialogDescription>
          </DialogHeader>

          <Alert className='items-start gap-2'>
            <RefreshCw aria-hidden='true' className='size-4 shrink-0' />
            <AlertDescription className='text-xs'>{infoText}</AlertDescription>
          </Alert>

          {/* 参考基准四格（§6.10） */}
          <div className='grid grid-cols-2 gap-3 sm:grid-cols-4'>
            <div className='border-border/60 bg-muted/25 rounded-md border px-2.5 py-2'>
              <div className='text-muted-foreground text-xs'>参考声压级</div>
              <div className='font-mono text-sm font-medium tabular-nums'>
                {mapping.referenceSpl ?? 65} dB SPL
              </div>
            </div>
            <div className='border-border/60 bg-muted/25 rounded-md border px-2.5 py-2'>
              <div className='text-muted-foreground text-xs'>参考线性增益</div>
              <div className='font-mono text-sm font-medium tabular-nums'>
                {mapping.referenceGainLinear != null
                  ? formatLinearGain(mapping.referenceGainLinear)
                  : '1.0'}
              </div>
            </div>
            <div className='border-border/60 bg-muted/25 rounded-md border px-2.5 py-2'>
              <div className='text-muted-foreground text-xs'>增益限幅</div>
              <div className='font-mono text-sm font-medium tabular-nums'>
                {formatGainClamp(minGain, maxGain)}
              </div>
            </div>
            <div className='border-border/60 bg-muted/25 rounded-md border px-2.5 py-2'>
              <div className='text-muted-foreground text-xs'>基准电平</div>
              <div className='font-mono text-sm font-medium tabular-nums'>
                -30 dBFS（RMS 补偿基准）
              </div>
            </div>
          </div>

          {/* 校准点集表（§6.10） */}
          <section aria-labelledby='digital-calibration-points-title'>
            <div className='mb-2 flex flex-wrap items-center justify-between gap-2'>
              <h3 id='digital-calibration-points-title' className='text-sm font-medium'>
                校准点集
              </h3>
              <div className='flex items-center gap-2'>
                <Button variant='outline' size='sm' onClick={handleGenerate}>
                  <RefreshCw aria-hidden='true' className='size-3.5' />
                  按参考生成
                </Button>
                <Button variant='outline' size='sm' onClick={addPoint}>
                  <Plus aria-hidden='true' className='size-3.5' />
                  添加校准点
                </Button>
              </div>
            </div>
            {points.length === 0 ? (
              <div className='bg-card ring-foreground/10 text-muted-foreground rounded-lg px-3 py-4 text-center text-xs ring-1'>
                尚无校准点，可点击「按参考生成」快速生成 5 个基准点
              </div>
            ) : (
              <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
                <div className='overflow-x-auto'>
                  <table className='w-full min-w-0 text-xs'>
                    <thead>
                      <tr className='bg-[var(--table-header)]'>
                        <th className='px-3 py-2 text-left font-medium'>目标 SPL（dB）</th>
                        <th className='px-3 py-2 text-left font-medium'>线性增益</th>
                        <th className='px-3 py-2 text-left font-medium'>增益（dB）</th>
                        <th className='px-3 py-2 text-left font-medium'>实测 RMS（dBFS）</th>
                        <th className='w-10 px-3 py-2' />
                      </tr>
                    </thead>
                    <tbody>
                      {points.map((point, index) => {
                        const error = errors[index]
                        const isDuplicate = duplicateIndexes.has(index)
                        const gain = Number(point.gainLinear)
                        return (
                          <tr key={index} className='border-border/50 border-b last:border-b-0'>
                            <td className='px-3 py-1.5'>
                              <Input
                                type='number'
                                step='0.5'
                                min={CALIBRATION_TARGET_SPL_MIN}
                                max={CALIBRATION_TARGET_SPL_MAX}
                                value={point.targetSpl}
                                onChange={(e) => patchPoint(index, { targetSpl: e.target.value })}
                                aria-label={`第 ${index + 1} 行目标 SPL`}
                                className='h-7 w-24 aria-[invalid=true]:border-destructive'
                              />
                              {(error?.targetSpl || isDuplicate) && (
                                <p className='text-destructive mt-0.5 flex items-center gap-1 text-[10px]'>
                                  {isDuplicate && !error?.targetSpl ? (
                                    <>
                                      <X aria-hidden='true' className='size-2.5' />
                                      重复目标
                                    </>
                                  ) : (
                                    error?.targetSpl
                                  )}
                                </p>
                              )}
                            </td>
                            <td className='px-3 py-1.5'>
                              <Input
                                type='number'
                                step='0.001'
                                value={point.gainLinear}
                                onChange={(e) => patchPoint(index, { gainLinear: e.target.value })}
                                aria-label={`第 ${index + 1} 行线性增益`}
                                className='h-7 w-24'
                              />
                              {error?.gainLinear && (
                                <p className='text-destructive mt-0.5 text-[10px]'>
                                  {error.gainLinear}
                                </p>
                              )}
                            </td>
                            <td className='px-3 py-1.5 font-mono text-xs tabular-nums text-muted-foreground'>
                              {gain > 0 && Number.isFinite(gain) ? gainToDb(gain) : '-'}
                            </td>
                            <td className='px-3 py-1.5'>
                              <Input
                                type='number'
                                step='0.5'
                                min={CALIBRATION_RMS_MIN}
                                max={CALIBRATION_RMS_MAX}
                                value={point.rmsDbfs}
                                onChange={(e) => patchPoint(index, { rmsDbfs: e.target.value })}
                                aria-label={`第 ${index + 1} 行实测 RMS`}
                                placeholder='选填'
                                className='h-7 w-24'
                              />
                            </td>
                            <td className='px-3 py-1.5'>
                              <Button
                                variant='ghost'
                                size='icon-sm'
                                aria-label={`删除第 ${index + 1} 个校准点`}
                                onClick={() => removePoint(index)}
                              >
                                <Trash2 aria-hidden='true' className='size-3.5' />
                              </Button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>

          {/* 增益曲线预览（§6.10；≥2 点显） */}
          {points.filter((point) => point.targetSpl.trim() && point.gainLinear.trim()).length >= 2 && (
            <section aria-labelledby='digital-curve-preview-title'>
              <h3 id='digital-curve-preview-title' className='mb-2 text-sm font-medium'>
                增益曲线预览（SPL→gain，dB）
              </h3>
              <div className='bg-card ring-foreground/10 rounded-lg p-2 ring-1'>
                <div className='h-40'>
                  {themeReady ? (
                    <VChart
                      key={[curveSpec.type, themeKey, presetKey].join('-')}
                      spec={{ ...curveSpec, theme: themeKey, background: 'transparent' } as ISpec}
                      options={VCHART_OPTION}
                    />
                  ) : (
                    <Skeleton className='h-40 w-full' />
                  )}
                </div>
              </div>
            </section>
          )}

          {/* 互斥提示（§6.10） */}
          <Alert className='items-start gap-2'>
            <Lock aria-hidden='true' className='size-4 shrink-0' />
            <AlertTitle className='text-sm font-medium'>并发互斥</AlertTitle>
            <AlertDescription>{DIGITAL_CALIBRATION_LOCK_TEXT}</AlertDescription>
          </Alert>

          <DialogFooter>
            <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
              取消
            </Button>
            <Button size='sm' onClick={handleSubmit} disabled={pending || validCount === 0}>
              {pending ? '校准中...' : '提交校准'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={generateConfirmOpen}
        onOpenChange={setGenerateConfirmOpen}
        title='按参考生成校准点'
        desc={`再点一次确认覆盖当前 ${points.filter((point) => point.targetSpl.trim() || point.gainLinear.trim()).length} 个校准点？`}
        confirmText='确认覆盖'
        handleConfirm={applyGenerated}
      />
    </>
  )
}
