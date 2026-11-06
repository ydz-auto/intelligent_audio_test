/**
 * 音频特征分析·质量评估弹窗（§6.23；Dialog sm:max-w-3xl）。
 * 三区（音频导入功能设计文档.md §3.3.2）：
 *   特征 —— 频谱特征 / 能量分布 / 时域特征（GET /audios/{id}/features）
 *   质量评估 —— 信噪比 / 动态范围 / 频率响应 / 质量评分（GET /audios/{id}/quality）
 *   处理操作 —— 降噪 / 增益调整 / 剪辑（POST /audios/{id}/process，audio:update）
 * 三态口径：加载中 Skeleton / 失败错误态 + 重试（不得退化成「暂无数据」）/ 正常值。
 * 处理 mode=overwrite 覆盖原文件属破坏性操作，提交前二次确认；
 * mode=new 生成新音频记录，接口回 new_audio_id。
 */
import { useState } from 'react'
import { toast } from 'sonner'
import {
  Activity,
  AlertTriangle,
  AudioLines,
  Gauge,
  RotateCw,
  Scissors,
  SlidersHorizontal,
  Waves,
} from 'lucide-react'

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
import { Skeleton } from '@/components/ui/skeleton'
import { usePermissions } from '@/application/hooks/use-permissions'
import {
  useAudioFeatures,
  useAudioProcess,
  useAudioQuality,
} from '@/application/audio/useAudioAnalysis'
import type {
  AudioAsset,
  AudioFeatures,
  AudioProcessOperation,
  AudioProcessRequest,
  AudioProcessResult,
  AudioQuality,
} from '@/domain/models/audio'
import { formatDuration } from '@/features/audio-import/lib/format'

export type AudioFeatureAnalysisDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio: AudioAsset | null
}

/** 处理提交入参（与 useAudioProcess mutation 变量同构） */
type ProcessVars = { id: number; payload: AudioProcessRequest }

/** 处理操作展示名（§6.23 处理操作三件） */
const OPERATION_LABELS: Record<AudioProcessOperation, string> = {
  denoise: '降噪',
  gain: '增益调整',
  trim: '剪辑',
}

/** 单项指标（标签 + 值；值走 mono tabular 便于与值核对） */
function Metric(props: { label: string; value: string }) {
  return (
    <div className='min-w-0'>
      <dt className='text-muted-foreground text-xs'>{props.label}</dt>
      <dd className='font-mono text-sm tabular-nums'>{props.value}</dd>
    </div>
  )
}

/** 分区容器（标题 + 内容） */
function Section(props: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className='space-y-2'>
      <h3 className='flex items-center gap-1.5 text-sm font-medium'>
        {props.icon}
        {props.title}
      </h3>
      {props.children}
    </section>
  )
}

/** 加载态（三列骨架，与正常态版式同高） */
function SectionLoading() {
  return (
    <div className='grid grid-cols-1 gap-2 sm:grid-cols-3' aria-busy='true'>
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className='h-16 w-full rounded-lg' />
      ))}
    </div>
  )
}

/** 失败态 + 重试（禁用空态：接口失败不等于无数据） */
function SectionError(props: {
  title: string
  message: string
  onRetry: () => void
}) {
  return (
    <div
      role='alert'
      className='border-destructive/30 bg-destructive/5 text-destructive flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs'
    >
      <AlertTriangle aria-hidden='true' className='size-3.5 shrink-0' />
      <span className='min-w-0 flex-1'>
        {props.title}：{props.message}
      </span>
      <Button variant='outline' size='sm' className='h-7 gap-1' onClick={props.onRetry}>
        <RotateCw aria-hidden='true' className='size-3' />
        重试
      </Button>
    </div>
  )
}

/** 特征分区内容（三组：频谱 / 能量 / 时域） */
function FeaturesGrid(props: { features: AudioFeatures }) {
  const { spectral, energy, timeDomain } = props.features
  return (
    <div className='grid grid-cols-1 gap-3 sm:grid-cols-3'>
      <div className='space-y-2 rounded-lg border p-3'>
        <h4 className='text-muted-foreground text-xs font-medium'>频谱特征</h4>
        <dl className='space-y-1.5'>
          <Metric
            label='基频范围'
            value={`${spectral.fundamentalRangeLow}–${spectral.fundamentalRangeHigh} Hz`}
          />
          <Metric label='主频' value={`${spectral.dominantFrequency} Hz`} />
          <Metric label='谐波失真' value={`${spectral.harmonicDistortion}%`} />
        </dl>
      </div>
      <div className='space-y-2 rounded-lg border p-3'>
        <h4 className='text-muted-foreground text-xs font-medium'>能量分布</h4>
        <dl className='space-y-1.5'>
          <Metric label='平均能量' value={`${energy.averageEnergyDb} dBFS`} />
          <Metric label='峰值能量' value={`${energy.peakEnergyDb} dBFS`} />
          <Metric label='能量集中度' value={String(energy.energyConcentration)} />
        </dl>
      </div>
      <div className='space-y-2 rounded-lg border p-3'>
        <h4 className='text-muted-foreground text-xs font-medium'>时域特征</h4>
        <dl className='space-y-1.5'>
          <Metric label='过零率' value={String(timeDomain.zeroCrossingRate)} />
          <Metric label='有效时长占比' value={String(timeDomain.activeDurationRatio)} />
          <Metric label='起始时间' value={`${timeDomain.onsetTime} s`} />
        </dl>
      </div>
    </div>
  )
}

/** 质量评估分区内容（信噪比 / 动态范围 / 频率响应 / 质量评分） */
function QualityGrid(props: { quality: AudioQuality }) {
  const { quality } = props
  return (
    <dl className='grid grid-cols-2 gap-3 rounded-lg border p-3 sm:grid-cols-4'>
      <Metric label='信噪比' value={`${quality.snrDb} dB`} />
      <Metric label='动态范围' value={`${quality.dynamicRangeDb} dB`} />
      <Metric label='频率响应' value={`${quality.frequencyResponseScore} 分`} />
      <Metric label='质量评分' value={`${quality.qualityScore} 分`} />
    </dl>
  )
}

/** 处理结果摘要（提交成功后回显，与 GET /audios/{id} 回读字段同源） */
function ProcessResultLine(props: { result: AudioProcessResult }) {
  const { result } = props
  const target =
    result.mode === 'new'
      ? `已生成新音频 #${result.newAudioId ?? '—'}`
      : '已覆盖原文件'
  return (
    <p className='text-muted-foreground text-xs'>
      最近一次处理：{OPERATION_LABELS[result.operation]}（{target}）· {result.format.toUpperCase()} ·{' '}
      {formatDuration(result.duration)} · {Math.round(result.size / 1024)} KB
    </p>
  )
}

export function AudioFeatureAnalysisDialog(props: AudioFeatureAnalysisDialogProps) {
  const audio = props.audio
  if (!audio) return null

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <FeatureAnalysisBody
          audio={audio}
          onClose={() => props.onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  )
}

function FeatureAnalysisBody(props: { audio: AudioAsset; onClose: () => void }) {
  const audio = props.audio
  const { hasPermission } = usePermissions()
  const canProcess = hasPermission('audio:update')

  const featuresQuery = useAudioFeatures(audio.id)
  const qualityQuery = useAudioQuality(audio.id)
  const processMutation = useAudioProcess()

  const [operation, setOperation] = useState<AudioProcessOperation>('denoise')
  const [gainDb, setGainDb] = useState('3')
  const [startMs, setStartMs] = useState('0')
  const [endMs, setEndMs] = useState('')
  const [mode, setMode] = useState<'new' | 'overwrite'>('new')
  const [formError, setFormError] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [lastResult, setLastResult] = useState<AudioProcessResult | null>(null)

  const durationMs = audio.duration != null ? Math.round(audio.duration * 1000) : null

  /** 校验并组请求体；不合法时回填 formError 并返回 null */
  const buildPayload = (): ProcessVars | null => {
    setFormError(null)
    if (operation === 'gain') {
      const value = Number(gainDb)
      if (gainDb.trim() === '' || !Number.isFinite(value)) {
        setFormError('请输入有效的增益值（dB）')
        return null
      }
      return { id: audio.id, payload: { operation, mode, gainDb: value } }
    }
    if (operation === 'trim') {
      const start = Number(startMs)
      if (startMs.trim() === '' || !Number.isFinite(start) || start < 0) {
        setFormError('请输入有效的剪辑起点（毫秒）')
        return null
      }
      const end = endMs.trim() === '' ? null : Number(endMs)
      if (end != null && (!Number.isFinite(end) || end <= start)) {
        setFormError('剪辑终点须大于起点（毫秒）')
        return null
      }
      if (end != null && durationMs != null && end > durationMs) {
        setFormError(`剪辑终点超出音频时长（${durationMs} 毫秒）`)
        return null
      }
      return {
        id: audio.id,
        payload: { operation, mode, startMs: start, endMs: end },
      }
    }
    return { id: audio.id, payload: { operation, mode } }
  }

  const runProcess = async (payload: ProcessVars) => {
    try {
      const result = await processMutation.mutateAsync(payload)
      setLastResult(result)
      toast.success(
        result.mode === 'new'
          ? `处理完成，已生成新音频 #${result.newAudioId ?? '—'}`
          : '处理完成，原音频文件已覆盖'
      )
    } catch (error) {
      const message =
        error instanceof Error && error.message ? error.message : '处理失败，请重试'
      setFormError(message)
      toast.error(message)
    }
  }

  const handleSubmit = () => {
    const payload = buildPayload()
    if (!payload) return
    if (mode === 'overwrite') {
      setConfirmOpen(true)
      return
    }
    void runProcess(payload)
  }

  const handleConfirmOverwrite = () => {
    const payload = buildPayload()
    setConfirmOpen(false)
    if (!payload) return
    void runProcess(payload)
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>音频特征分析</DialogTitle>
        <DialogDescription>
          「{audio.name}」（{formatDuration(audio.duration)}）
        </DialogDescription>
      </DialogHeader>

      <Section title='特征' icon={<Activity aria-hidden='true' className='size-4' />}>
        {featuresQuery.isPending ? (
          <SectionLoading />
        ) : featuresQuery.isError ? (
          <SectionError
            title='特征分析加载失败'
            message={
              featuresQuery.error instanceof Error
                ? featuresQuery.error.message
                : '请重试'
            }
            onRetry={() => void featuresQuery.refetch()}
          />
        ) : featuresQuery.data ? (
          <>
            <FeaturesGrid features={featuresQuery.data} />
            <p className='text-muted-foreground text-xs'>
              分析样本时长 {featuresQuery.data.duration} 秒
            </p>
          </>
        ) : null}
      </Section>

      <Section
        title='质量评估'
        icon={<Gauge aria-hidden='true' className='size-4' />}
      >
        {qualityQuery.isPending ? (
          <SectionLoading />
        ) : qualityQuery.isError ? (
          <SectionError
            title='质量评估加载失败'
            message={qualityQuery.error instanceof Error ? qualityQuery.error.message : '请重试'}
            onRetry={() => void qualityQuery.refetch()}
          />
        ) : qualityQuery.data ? (
          <QualityGrid quality={qualityQuery.data} />
        ) : null}
      </Section>

      <Section
        title='处理操作'
        icon={<Waves aria-hidden='true' className='size-4' />}
      >
        <div className='space-y-3 rounded-lg border p-3'>
          <div className='flex flex-wrap gap-2' role='group' aria-label='处理操作'>
            {(
              [
                { value: 'denoise', label: '降噪', icon: AudioLines },
                { value: 'gain', label: '增益调整', icon: SlidersHorizontal },
                { value: 'trim', label: '剪辑', icon: Scissors },
              ] as const
            ).map((item) => {
              const Icon = item.icon
              const selected = operation === item.value
              return (
                <Button
                  key={item.value}
                  variant={selected ? 'secondary' : 'outline'}
                  size='sm'
                  className='gap-1.5'
                  aria-pressed={selected}
                  disabled={!canProcess || processMutation.isPending}
                  onClick={() => {
                    setOperation(item.value)
                    setFormError(null)
                  }}
                >
                  <Icon aria-hidden='true' className='size-3.5' />
                  {item.label}
                </Button>
              )
            })}
          </div>

          {operation === 'gain' && (
            <div className='max-w-48 space-y-1.5'>
              <Label htmlFor='audio-process-gain'>增益值（dB）</Label>
              <Input
                id='audio-process-gain'
                type='number'
                step='0.5'
                value={gainDb}
                disabled={!canProcess || processMutation.isPending}
                onChange={(event) => setGainDb(event.target.value)}
              />
            </div>
          )}

          {operation === 'trim' && (
            <div className='grid grid-cols-2 gap-3'>
              <div className='space-y-1.5'>
                <Label htmlFor='audio-process-start'>起点（毫秒）</Label>
                <Input
                  id='audio-process-start'
                  type='number'
                  min={0}
                  value={startMs}
                  disabled={!canProcess || processMutation.isPending}
                  onChange={(event) => setStartMs(event.target.value)}
                />
              </div>
              <div className='space-y-1.5'>
                <Label htmlFor='audio-process-end'>终点（毫秒，留空到末尾）</Label>
                <Input
                  id='audio-process-end'
                  type='number'
                  min={0}
                  placeholder={durationMs != null ? String(durationMs) : '音频末尾'}
                  value={endMs}
                  disabled={!canProcess || processMutation.isPending}
                  onChange={(event) => setEndMs(event.target.value)}
                />
              </div>
            </div>
          )}

          <div className='space-y-1.5'>
            <Label>输出方式</Label>
            <div className='flex flex-wrap gap-2' role='group' aria-label='输出方式'>
              <Button
                variant={mode === 'new' ? 'secondary' : 'outline'}
                size='sm'
                aria-pressed={mode === 'new'}
                disabled={!canProcess || processMutation.isPending}
                onClick={() => setMode('new')}
              >
                生成新文件
              </Button>
              <Button
                variant={mode === 'overwrite' ? 'secondary' : 'outline'}
                size='sm'
                aria-pressed={mode === 'overwrite'}
                disabled={!canProcess || processMutation.isPending}
                onClick={() => setMode('overwrite')}
              >
                覆盖原文件
              </Button>
            </div>
            <p className='text-muted-foreground text-xs'>
              「生成新文件」保留原音频并新建一条处理后的音频记录；「覆盖原文件」直接改写当前音频，不可恢复。
            </p>
          </div>

          {formError && (
            <p role='alert' className='text-destructive text-xs'>
              {formError}
            </p>
          )}
          {!canProcess && (
            <p className='text-muted-foreground text-xs'>
              当前账号无音频编辑权限（audio:update），处理操作不可用。
            </p>
          )}

          <div className='flex items-center gap-2'>
            <Button
              size='sm'
              onClick={handleSubmit}
              disabled={!canProcess || processMutation.isPending}
            >
              {processMutation.isPending ? '处理中...' : '开始处理'}
            </Button>
          </div>

          {lastResult && <ProcessResultLine result={lastResult} />}
        </div>
      </Section>

      <DialogFooter>
        <Button variant='outline' size='sm' onClick={props.onClose}>
          关闭
        </Button>
      </DialogFooter>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title='覆盖原音频文件'
        desc={`将用「${OPERATION_LABELS[operation]}」的处理结果覆盖当前音频文件，原文件不可恢复。确定继续？`}
        confirmText='确定覆盖'
        destructive
        isLoading={processMutation.isPending}
        handleConfirm={handleConfirmOverwrite}
      />
    </>
  )
}
