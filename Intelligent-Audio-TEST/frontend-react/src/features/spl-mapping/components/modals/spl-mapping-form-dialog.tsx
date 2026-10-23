/**
 * 物理域 SPL 映射表单（§6.7；Dialog sm:max-w-2xl）。
 * 标题「添加增益映射/编辑增益映射」；字段=映射名称* / 描述/关联播放设备/设备类型/测量距离/
 * 目标声压级/数字增益/测试频率/校准点集（增益偏移/基础电平-30 只读/最终电平只读警告/实测 SPL
 * + 测试·停止钮，同 §6.5）。
 * 校准重置交互（§6.7）：编辑已校准映射时修改测量距离或测试频率 → ConfirmDialog
 * 「修改测量距离/测试频率将使校准重置为未校准，确定继续吗？」；确认后置 uncalibrated。
 */
import { Play, Square, Trash2 } from 'lucide-react'
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
import { Textarea } from '@/components/ui/textarea'
import type { PlaybackDeviceRef, SplMapping } from '@/domain/models/splMapping'
import { DEVICE_TYPE_OPTIONS } from '@/features/spl-mapping/constants'
import { useSplMutations } from '@/application/spl/useSplMappings'

export type SplMappingFormDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mapping: SplMapping | null
  playbackDevices: PlaybackDeviceRef[]
}

interface PointDraft {
  gainOffset: string
  spl: string
}

/** 设备类型 Select 的 value→label 映射（缺 items 时闭合态显示 raw value「dry/noise」） */
const DEVICE_TYPE_SELECT_ITEMS = DEVICE_TYPE_OPTIONS.map((option) => ({
  value: option.value,
  label: option.label,
}))

/** 默认点集（编辑新建态：按 §11-12 模拟校准口径 5 点占位） */
const DEFAULT_POINTS: PointDraft[] = [
  { gainOffset: '-10', spl: '55' },
  { gainOffset: '0', spl: '65' },
  { gainOffset: '10', spl: '75' },
  { gainOffset: '20', spl: '85' },
]

export function SplMappingFormDialog(props: SplMappingFormDialogProps) {
  const isEdit = props.mapping != null
  const { create, update } = useSplMutations()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [deviceId, setDeviceId] = useState('')
  const [deviceType, setDeviceType] = useState('dry')
  const [distance, setDistance] = useState('1.0')
  const [targetSpl, setTargetSpl] = useState('65')
  const [digitalGain, setDigitalGain] = useState('0')
  const [testFrequency, setTestFrequency] = useState('1000')
  const [points, setPoints] = useState<PointDraft[]>(DEFAULT_POINTS)
  const [playingIndex, setPlayingIndex] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  // 校准重置确认（§6.7：已校准映射改距离/频率 → 二次确认）
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false)
  const [pendingPatch, setPendingPatch] = useState<Partial<SplMapping> | null>(null)
  const [calibrationReset, setCalibrationReset] = useState(false)

  // 打开时初始化表单（mapping 变化 → 重置字段）
  useEffect(() => {
    if (!props.open) return
    const mapping = props.mapping
    setName(mapping?.name ?? '')
    setDescription(mapping?.description ?? '')
    setDeviceId(mapping?.deviceId != null ? String(mapping.deviceId) : '')
    setDeviceType(mapping?.deviceType ?? 'dry')
    setDistance(mapping?.distance != null ? String(mapping.distance) : '1.0')
    setTargetSpl(mapping?.targetSpl != null ? String(mapping.targetSpl) : '65')
    setDigitalGain(mapping?.digitalGain != null ? String(mapping.digitalGain) : '0')
    setTestFrequency(mapping?.testFrequency != null ? String(mapping.testFrequency) : '1000')
    setPoints(
      mapping?.calibrationData?.points.length
        ? mapping.calibrationData.points.map((point) => ({
            gainOffset: point.gainOffset != null ? String(point.gainOffset) : '',
            spl: point.spl != null ? String(point.spl) : '',
          }))
        : DEFAULT_POINTS
    )
    setPlayingIndex(null)
    setCalibrationReset(false)
  }, [props.open, props.mapping])

  if (!props.open) return null

  const deviceOptions = props.playbackDevices.map((device) => ({
    value: String(device.id),
    label: device.model ? `${device.name}（${device.model}）` : device.name,
  }))

  /** §6.7 校准重置守卫：已校准映射改距离/频率 → 先确认再改 */
  const guardedChange = (key: 'distance' | 'testFrequency', value: string) => {
    if (
      isEdit &&
      props.mapping?.calibrationStatus === 'calibrated' &&
      value !== (key === 'distance'
        ? props.mapping.distance != null ? String(props.mapping.distance) : '1.0'
        : props.mapping.testFrequency != null ? String(props.mapping.testFrequency) : '1000')
    ) {
      setPendingPatch({ [key]: key === 'distance' ? Number(value) : Number(value) })
      setResetConfirmOpen(true)
      return
    }
    if (key === 'distance') setDistance(value)
    else setTestFrequency(value)
  }

  const confirmReset = () => {
    if (pendingPatch) {
      if (pendingPatch.distance != null) setDistance(String(pendingPatch.distance))
      if (pendingPatch.testFrequency != null) setTestFrequency(String(pendingPatch.testFrequency))
    }
    setPoints([])
    setCalibrationReset(true)
    setResetConfirmOpen(false)
    setPendingPatch(null)
  }

  const addPoint = () => setPoints((prev) => [...prev, { gainOffset: '', spl: '' }])
  const removePoint = (index: number) =>
    setPoints((prev) => prev.filter((_, i) => i !== index))
  const patchPoint = (index: number, patch: Partial<PointDraft>) =>
    setPoints((prev) => prev.map((point, i) => (i === index ? { ...point, ...patch } : point)))

  /** §6.5 测试音播放（mock：播放中态 2s；接线后 POST /spl/test-tone） */
  const playTestTone = (index: number) => {
    setPlayingIndex(index)
    window.setTimeout(() => setPlayingIndex((prev) => (prev === index ? null : prev)), 2000)
  }

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error('请输入映射名称')
      return
    }
    setPending(true)
    try {
      const calibrationData = {
        points: points
          .filter((point) => point.gainOffset !== '' || point.spl !== '')
          .map((point) => ({
            spl: point.spl ? Number(point.spl) : null,
            gainOffset: point.gainOffset ? Number(point.gainOffset) : null,
            digitalGain: point.gainOffset ? Number(point.gainOffset) : null,
            baseLevel: -30,
            finalLevel: point.gainOffset ? -30 + Number(point.gainOffset) : null,
          })),
      }
      const base = {
        name: name.trim(),
        description: description.trim() || null,
        deviceId: deviceId ? Number(deviceId) : null,
        deviceType: deviceType as SplMapping['deviceType'],
        distance: Number(distance),
        targetSpl: targetSpl ? Number(targetSpl) : null,
        digitalGain: digitalGain ? Number(digitalGain) : null,
        testFrequency: Number(testFrequency),
        calibrationData,
      }
      if (isEdit && props.mapping) {
        const patch: Partial<SplMapping> = { ...base }
        if (calibrationReset) {
          patch.calibrationStatus = 'uncalibrated'
          patch.calibrationData = null
        }
        await update.mutateAsync({ id: props.mapping.id, patch })
        toast.success('增益映射已保存')
      } else {
        await create.mutateAsync({ ...base, calibrationStatus: null, isCurrent: false })
        toast.success('增益映射创建成功')
      }
      props.onOpenChange(false)
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setPending(false)
    }
  }

  const finalLevelOf = (gainOffset: string): string =>
    gainOffset === '' || Number.isNaN(Number(gainOffset)) ? '—' : `${(-30 + Number(gainOffset)).toFixed(1)} dBFS`

  return (
    <>
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        <DialogContent className='sm:max-w-2xl'>
          <DialogHeader>
            <DialogTitle>{isEdit ? '编辑增益映射' : '添加增益映射'}</DialogTitle>
            <DialogDescription>
              E2E 物理域增益映射：目标声压级 ↔ 增益偏移点集，映射到播放设备
            </DialogDescription>
          </DialogHeader>

          <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
            <div className='space-y-2'>
              <Label required>映射名称</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder='请输入映射名称' aria-label='映射名称' />
            </div>
            <div className='space-y-2'>
              <Label>关联播放设备</Label>
              <Select
                value={deviceId}
                onValueChange={(value) => setDeviceId(value ?? '')}
                items={deviceOptions}
              >
                <SelectTrigger size='sm' className='w-full' aria-label='关联播放设备'>
                  <SelectValue placeholder='不使用声压映射' />
                </SelectTrigger>
                <SelectContent>
                  {deviceOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-2'>
              <Label>设备类型</Label>
              <Select
                value={deviceType}
                onValueChange={(value) => setDeviceType(value ?? 'dry')}
                items={DEVICE_TYPE_SELECT_ITEMS}
              >
                <SelectTrigger size='sm' className='w-full' aria-label='设备类型'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DEVICE_TYPE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-2'>
              <Label>测量距离（米）</Label>
              <Input
                type='number'
                step='0.1'
                value={distance}
                onChange={(e) => guardedChange('distance', e.target.value)}
                aria-label='测量距离'
              />
            </div>
            <div className='space-y-2'>
              <Label>目标声压级（dB）</Label>
              <Input
                type='number'
                value={targetSpl}
                onChange={(e) => setTargetSpl(e.target.value)}
                aria-label='目标声压级'
              />
            </div>
            <div className='space-y-2'>
              <Label>数字增益（dB）</Label>
              <Input
                type='number'
                step='0.1'
                value={digitalGain}
                onChange={(e) => setDigitalGain(e.target.value)}
                aria-label='数字增益'
              />
            </div>
            <div className='space-y-2'>
              <Label>测试频率（Hz）</Label>
              <Input
                type='number'
                value={testFrequency}
                onChange={(e) => guardedChange('testFrequency', e.target.value)}
                aria-label='测试频率'
              />
            </div>
          </div>

          <div className='space-y-2'>
            <Label>描述</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder='请输入描述' className='min-h-20' aria-label='描述' />
          </div>

          <section aria-labelledby='calibration-points-title'>
            <div className='mb-2 flex items-center justify-between'>
              <h3 id='calibration-points-title' className='text-sm font-medium'>校准点集</h3>
              <Button variant='outline' size='sm' onClick={addPoint}>
                添加校准点
              </Button>
            </div>
            {points.length === 0 ? (
              <div className='bg-card ring-foreground/10 text-muted-foreground rounded-lg px-3 py-4 text-center text-xs ring-1'>
                尚无校准点（已校准映射修改距离/频率将重置校准）
              </div>
            ) : (
              <div className='space-y-2'>
                <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
                  <div className='overflow-x-auto'>
                    <table className='w-full min-w-0 text-xs'>
                      <thead>
                        <tr className='bg-[var(--table-header)]'>
                          <th className='px-3 py-2 text-left font-medium'>增益偏移（dB）</th>
                          <th className='px-3 py-2 text-left font-medium'>基础电平</th>
                          <th className='px-3 py-2 text-left font-medium'>最终电平</th>
                          <th className='px-3 py-2 text-left font-medium'>实测 SPL（dB）</th>
                          <th className='w-20 px-3 py-2' />
                        </tr>
                      </thead>
                      <tbody>
                        {points.map((point, index) => {
                          const finalLevel =
                            point.gainOffset === '' || Number.isNaN(Number(point.gainOffset))
                              ? null
                              : -30 + Number(point.gainOffset)
                          return (
                            <tr key={index} className='border-border/50 border-b last:border-b-0'>
                              <td className='px-3 py-1.5'>
                                <Input
                                  type='number'
                                  step='0.1'
                                  value={point.gainOffset}
                                  onChange={(e) => patchPoint(index, { gainOffset: e.target.value })}
                                  aria-label={`第 ${index + 1} 行增益偏移`}
                                  className='h-7 w-24'
                                />
                              </td>
                              <td className='px-3 py-1.5 font-mono text-xs tabular-nums text-muted-foreground'>
                                -30 dBFS
                              </td>
                              <td
                                className={`px-3 py-1.5 font-mono text-xs tabular-nums ${
                                  finalLevel != null && finalLevel > -5
                                    ? 'text-destructive'
                                    : 'text-muted-foreground'
                                }`}
                              >
                                {finalLevelOf(point.gainOffset)}
                              </td>
                              <td className='px-3 py-1.5'>
                                <Input
                                  type='number'
                                  step='0.1'
                                  value={point.spl}
                                  onChange={(e) => patchPoint(index, { spl: e.target.value })}
                                  aria-label={`第 ${index + 1} 行实测 SPL`}
                                  className='h-7 w-24'
                                />
                              </td>
                              <td className='px-3 py-1.5'>
                                <div className='flex items-center gap-1'>
                                  <Button
                                    variant='outline'
                                    size='icon-sm'
                                    aria-label={`第 ${index + 1} 行播放测试音`}
                                    onClick={() =>
                                      playingIndex === index ? setPlayingIndex(null) : playTestTone(index)
                                    }
                                  >
                                    {playingIndex === index ? (
                                      <Square aria-hidden='true' className='size-3' />
                                    ) : (
                                      <Play aria-hidden='true' className='size-3' />
                                    )}
                                  </Button>
                                  <Button
                                    variant='ghost'
                                    size='icon-sm'
                                    aria-label={`删除第 ${index + 1} 个校准点`}
                                    onClick={() => removePoint(index)}
                                  >
                                    <Trash2 aria-hidden='true' className='size-3.5' />
                                  </Button>
                                </div>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
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
        open={resetConfirmOpen}
        onOpenChange={setResetConfirmOpen}
        title='校准重置确认'
        desc='修改测量距离/测试频率将使校准重置为未校准，确定继续吗？'
        confirmText='继续'
        handleConfirm={confirmReset}
      />
    </>
  )
}
