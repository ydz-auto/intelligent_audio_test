/**
 * 数字域 RMS-SPL 映射表单（§6.12 简化口径 INT-1031 返工 + INT-2081 补校准点集；Dialog sm:max-w-2xl）。
 * 标题「添加/编辑 RMS-SPL 映射」；字段=关联被测 API*（create-only，编辑态隐藏）/映射名称*
 * （必填）/参考声压级（30-120 默认 65，hint「未校准时的参考基准」）/参考线性增益（正数
 * 默认 1.0）/增益下限（默认 0.001「防静音限幅」）/增益上限（默认 10.0「防爆音限幅」）。
 * 校准点集（INT-2081 同物理域表单内嵌模式）：目标SPL + 实测 RMS(dBFS 必填主输入) 可编辑、
 * 线性增益只读推导（10^((dBFS+30)/20)）、行级校验、重复目标 SPL 拦截、可选「按参考生成」；
 * 创建/编辑提交真实 calibrationPoints（不再恒空），编辑态回填既有点集。
 * 供应商/协议不再出现在表单，提交映射 vendor=null、protocol=websocket；主钮「保存」。
 */
import { Plus, RefreshCw, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

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
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ApiConfigRef, ApiRmsSplMapping } from '@/domain/models/digitalSpl'
import {
  CALIBRATION_RMS_MAX,
  CALIBRATION_RMS_MIN,
  CALIBRATION_TARGET_SPL_MAX,
  CALIBRATION_TARGET_SPL_MIN,
  DEFAULT_MAX_GAIN_LINEAR,
  DEFAULT_MIN_GAIN_LINEAR,
  DEFAULT_REFERENCE_GAIN_LINEAR,
  DEFAULT_REFERENCE_SPL,
} from '@/features/spl-mapping/constants'
import {
  buildCalibrationPayload,
  detectDuplicateIndexes,
  deriveGainLinear,
  generateCalibrationPointsByReference,
  validatePoint,
  type CalibrationPointDraft,
} from '@/features/spl-mapping/lib/calibration'
import { gainToDb, formatLinearGain } from '@/features/spl-mapping/lib/format'
import { useDigitalSplMutations } from '@/application/spl/useDigitalSplMappings'

export type ApiRmsSplFormDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mapping: ApiRmsSplMapping | null
  apis: ApiConfigRef[]
}

type PointDraft = CalibrationPointDraft

/** 正数数值解析：空/非正数回退默认（增益三字段不做必填校验，可带默认值） */
function parsePositiveNumeric(value: string, fallback: number): number {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

/** 参考声压级解析：限定 30-120，越界/空回退默认 65 */
function parseReferenceSpl(value: string, fallback: number): number {
  const n = Number(value)
  return Number.isFinite(n) && n >= 30 && n <= 120 ? n : fallback
}

export function ApiRmsSplFormDialog(props: ApiRmsSplFormDialogProps) {
  const isEdit = props.mapping != null
  const { create, update } = useDigitalSplMutations()

  const [apiId, setApiId] = useState('')
  const [name, setName] = useState('')
  const [referenceSpl, setReferenceSpl] = useState(String(DEFAULT_REFERENCE_SPL))
  const [referenceGainLinear, setReferenceGainLinear] = useState(String(DEFAULT_REFERENCE_GAIN_LINEAR))
  const [minGainLinear, setMinGainLinear] = useState(String(DEFAULT_MIN_GAIN_LINEAR))
  const [maxGainLinear, setMaxGainLinear] = useState(String(DEFAULT_MAX_GAIN_LINEAR))
  const [points, setPoints] = useState<PointDraft[]>([])
  const [pending, setPending] = useState(false)
  // 「按参考生成」两步确认（已有非空点集时再点一次确认覆盖）
  const [generateConfirmOpen, setGenerateConfirmOpen] = useState(false)

  useEffect(() => {
    if (!props.open) return
    const mapping = props.mapping
    setApiId(mapping?.apiId != null ? String(mapping.apiId) : '')
    setName(mapping?.name ?? '')
    setReferenceSpl(mapping?.referenceSpl != null ? String(mapping.referenceSpl) : String(DEFAULT_REFERENCE_SPL))
    setReferenceGainLinear(
      mapping?.referenceGainLinear != null ? String(mapping.referenceGainLinear) : String(DEFAULT_REFERENCE_GAIN_LINEAR)
    )
    setMinGainLinear(mapping?.minGainLinear != null ? String(mapping.minGainLinear) : String(DEFAULT_MIN_GAIN_LINEAR))
    setMaxGainLinear(mapping?.maxGainLinear != null ? String(mapping.maxGainLinear) : String(DEFAULT_MAX_GAIN_LINEAR))
    setPoints(
      mapping?.calibrationPoints?.length
        ? mapping.calibrationPoints.map((point) => ({
            targetSpl: String(point.targetSpl),
            rmsDbfs: point.rmsDbfs != null ? String(point.rmsDbfs) : '',
          }))
        : []
    )
    setGenerateConfirmOpen(false)
  }, [props.open, props.mapping])

  if (!props.open) return null

  const apiOptions = props.apis.map((api) => ({
    value: String(api.id),
    label: api.vendor ? `${api.name}（${api.vendor}）` : api.name,
  }))

  /** 校准点集行级校验（INT-2081：目标 SPL 范围 / dBFS 必填与范围 / 重复 x 拦截） */
  const duplicateIndexes = detectDuplicateIndexes(points)
  const errors = points.map((point) => validatePoint(point))

  const addPoint = () => setPoints((prev) => [...prev, { targetSpl: '', rmsDbfs: '' }])
  const removePoint = (index: number) =>
    setPoints((prev) => prev.filter((_, i) => i !== index))
  const patchPoint = (index: number, patch: Partial<PointDraft>) =>
    setPoints((prev) => prev.map((point, i) => (i === index ? { ...point, ...patch } : point)))

  /** 「按参考生成」两步确认（INT-2081：按参考声压级/参考线性增益按 dBFS 口径生成 5 点） */
  const handleGenerate = () => {
    const nonEmpty = points.filter((point) => point.targetSpl.trim() || point.rmsDbfs.trim()).length
    if (nonEmpty > 0) {
      setGenerateConfirmOpen(true)
      return
    }
    applyGenerated()
  }

  const applyGenerated = () => {
    const refSpl = parseReferenceSpl(referenceSpl, DEFAULT_REFERENCE_SPL)
    const refGain = parsePositiveNumeric(referenceGainLinear, DEFAULT_REFERENCE_GAIN_LINEAR)
    setPoints(generateCalibrationPointsByReference(refSpl, refGain))
    setGenerateConfirmOpen(false)
  }

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error('请输入映射名称')
      return
    }
    if (!isEdit && !apiId) {
      toast.error('请选择关联被测 API')
      return
    }
    setPending(true)
    try {
      // INT-2081：提交真实校准点集（有效行过滤，增益由 dBFS 推导）
      const calibrationPoints = buildCalibrationPayload(points, errors, duplicateIndexes)
      if (calibrationPoints.length === 0) {
        toast.error('必须至少添加 1 个有效校准点（目标 SPL + 实测 dBFS）')
        return
      }
      const base = {
        name: name.trim(),
        description: null,
        vendor: null,
        protocol: 'websocket' as ApiRmsSplMapping['protocol'],
        referenceSpl: parseReferenceSpl(referenceSpl, DEFAULT_REFERENCE_SPL),
        referenceGainLinear: parsePositiveNumeric(referenceGainLinear, DEFAULT_REFERENCE_GAIN_LINEAR),
        minGainLinear: parsePositiveNumeric(minGainLinear, DEFAULT_MIN_GAIN_LINEAR),
        maxGainLinear: parsePositiveNumeric(maxGainLinear, DEFAULT_MAX_GAIN_LINEAR),
        calibrationStatus: null,
        calibrationPoints,
        createdAt: null,
        updatedAt: null,
      }
      if (isEdit && props.mapping) {
        await update.mutateAsync({ id: props.mapping.id, patch: base })
        toast.success('RMS-SPL 映射更新成功')
      } else {
        await create.mutateAsync({ ...base, apiId: Number(apiId) })
        toast.success('RMS-SPL 映射创建成功')
      }
      props.onOpenChange(false)
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <>
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑 RMS-SPL 映射' : '添加 RMS-SPL 映射'}</DialogTitle>
          <DialogDescription>
            数字域 RMS→SPL 灵敏度映射：配置目标SPL↔实测dBFS 校准点与增益限幅（增益由 dBFS 推导；无校准点时原音频电平不动）
          </DialogDescription>
        </DialogHeader>

        <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
          {!isEdit && (
            <div className='space-y-2'>
              <Label required>关联被测 API</Label>
              <Select
                value={apiId}
                onValueChange={(value) => setApiId(value ?? '')}
                items={apiOptions}
              >
                <SelectTrigger size='sm' className='w-full' aria-label='关联被测 API'>
                  <SelectValue placeholder='请选择被测 API（API 1:N 映射）' />
                </SelectTrigger>
                <SelectContent>
                  {apiOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className='space-y-2'>
            <Label required>映射名称</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder='请输入映射名称' aria-label='映射名称' />
          </div>
          <div className='space-y-2'>
            <Label>增益下限</Label>
            <Input
              type='number'
              min={0.001}
              step='0.001'
              value={minGainLinear}
              onChange={(e) => setMinGainLinear(e.target.value)}
              aria-label='增益下限'
            />
            <p className='text-muted-foreground text-xs'>防静音限幅</p>
          </div>
          <div className='space-y-2'>
            <Label>增益上限</Label>
            <Input
              type='number'
              min={0.001}
              step='0.1'
              value={maxGainLinear}
              onChange={(e) => setMaxGainLinear(e.target.value)}
              aria-label='增益上限'
            />
            <p className='text-muted-foreground text-xs'>防爆音限幅</p>
          </div>
        </div>

        {/* 校准点集（INT-2081：目标SPL + 实测 dBFS 主输入，增益只读推导） */}
        <section aria-labelledby='digital-form-calibration-points-title'>
          <div className='mb-2 flex flex-wrap items-center justify-between gap-2'>
            <h3 id='digital-form-calibration-points-title' className='text-sm font-medium'>
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
                      <th className='px-3 py-2 text-left font-medium'>实测 RMS（dBFS）</th>
                      <th className='px-3 py-2 text-left font-medium'>线性增益</th>
                      <th className='px-3 py-2 text-left font-medium'>增益（dB）</th>
                      <th className='w-10 px-3 py-2' />
                    </tr>
                  </thead>
                  <tbody>
                    {points.map((point, index) => {
                      const error = errors[index]
                      const isDuplicate = duplicateIndexes.has(index)
                      const gain = deriveGainLinear(point.rmsDbfs)
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
                              step='0.5'
                              min={CALIBRATION_RMS_MIN}
                              max={CALIBRATION_RMS_MAX}
                              value={point.rmsDbfs}
                              onChange={(e) => patchPoint(index, { rmsDbfs: e.target.value })}
                              aria-label={`第 ${index + 1} 行实测 RMS`}
                              className='h-7 w-24 aria-[invalid=true]:border-destructive'
                            />
                            {error?.rmsDbfs && (
                              <p className='text-destructive mt-0.5 text-[10px]'>
                                {error.rmsDbfs}
                              </p>
                            )}
                          </td>
                          <td className='px-3 py-1.5 font-mono text-xs tabular-nums'>
                            {gain != null ? formatLinearGain(gain) : '-'}
                          </td>
                          <td className='px-3 py-1.5 font-mono text-xs tabular-nums text-muted-foreground'>
                            {gain != null && gain > 0 ? gainToDb(gain) : '-'}
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

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' onClick={handleSave} disabled={pending}>
            {pending ? '保存中...' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <ConfirmDialog
      open={generateConfirmOpen}
      onOpenChange={setGenerateConfirmOpen}
      title='按参考生成校准点'
      desc={`再点一次确认覆盖当前 ${points.filter((point) => point.targetSpl.trim() || point.rmsDbfs.trim()).length} 个校准点？`}
      confirmText='确认覆盖'
      handleConfirm={applyGenerated}
    />
    </>
  )
}
