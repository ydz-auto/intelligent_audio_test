/**
 * 上传选项（§6.16/§6.17 共用 UploadOptions；buildUploadOptionsConfig 平移；INT-714 接线）。
 * 音频类型 radio + 生成测试用例 boolean + 算法类型 select（真实 /algorithm/options）
 * + 评估维度（§5.7 轮次范围三档 + DimensionPicker 云 + 多轮整体评估维度节；INT-1614）
 * + 播放设备（§5.7 轮次范围三档 + Select + 重新扫描；真实 /playback-devices）
 * + 默认声压级 + 用例分组 radio + 继承音频标签 boolean。
 * 轮次基数 N 由调用方按 §5.7.2 传入：上传窗 N=1（指定轮次 / 逐轮设置禁用 + Tooltip），
 * 文件夹导入 N = JSON rounds 最大轮数（三档全可用）。
 */
import {
  Check,
  CheckCheck,
  Copy,
  Info,
  Trash2,
} from 'lucide-react'
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  useEvaluationDimensions,
  useEvaluationCategories,
  useAlgorithmOptions,
} from '@/application/evaluation/use-dimensions'
import type { UploadRoundScopeController } from '@/application/audio/useUploadRoundScope'
import type { UploadRoundScopeMode } from '@/domain/models/uploadRoundScope'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { usePlaybackDevices } from '@/application/audio/usePlaybackDevices'
import type { PlaybackDeviceOption } from '@/infrastructure/api/audio-upload-api'
import { scanRealPlaybackDevices } from '@/infrastructure/api/playback-api'
import { cn } from '@/lib/utils'
import { DimensionPicker } from '@/features/testcases/modals/round-config/dimension-picker'
import {
  RoundScopeThreeField,
  type RoundScopeThreeValue,
} from '@/features/testcases/modals/batch-shared'
import {
  CASE_GROUP_OPTIONS,
  UPLOAD_AUDIO_TYPE_OPTIONS,
} from '@/features/audio-import/constants'

export type UploadOptionsProps = {
  audioType: string
  onAudioTypeChange: (value: string) => void
  generateTestCase: boolean
  onGenerateTestCaseChange: (value: boolean) => void
  algorithmType: string
  onAlgorithmTypeChange: (value: string) => void
  defaultSpl: number
  onDefaultSplChange: (value: number) => void
  caseGroup: string
  onCaseGroupChange: (value: string) => void
  customGroupName: string
  onCustomGroupNameChange: (value: string) => void
  inheritTags: boolean
  onInheritTagsChange: (value: boolean) => void
  /** 音频标签（V9.7.10 UploadOptions tags 输入对位；生成测试用例时显示） */
  tags: string
  onTagsChange: (value: string) => void
  /** 轮次基数 N（§5.7.2：上传窗 1、文件夹导入 = JSON rounds 最大轮数） */
  roundCount: number
  /** 轮次范围编排（useUploadRoundScope 返回值） */
  roundScope: UploadRoundScopeController
  /** N=1 时禁用档的 Tooltip 文案（§9：上传窗逐字；文件夹导入未附 JSON 时另有文案） */
  singleRoundHint: string
}

function OptionRadio({
  value,
  options,
  onChange,
}: {
  value: string
  options: ReadonlyArray<{ value: string; label: string }>
  onChange: (value: string) => void
}) {
  return (
    <div className='flex flex-wrap gap-2'>
      {options.map((option) => (
        <button
          key={option.value}
          type='button'
          role='radio'
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'hover:bg-accent flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-sm transition-colors',
            value === option.value && 'border-primary/50 bg-primary/[0.06] text-foreground dark:bg-primary/10'
          )}
        >
          {value === option.value && (
            <Check aria-hidden='true' className='text-primary size-3.5' />
          )}
          {option.label}
        </button>
      ))}
    </div>
  )
}

/** domain 的轮次范围值 → 共用件 RoundScopeThreeValue（补 rounds 数组；onChange 时剥离） */
function toThreeValue(
  scope: { mode: UploadRoundScopeMode; specificRounds: number[]; activeRound: number },
  roundCount: number
): RoundScopeThreeValue {
  return {
    mode: scope.mode,
    specificRounds: scope.specificRounds,
    activeRound: scope.activeRound,
    rounds: Array.from({ length: Math.max(1, roundCount) }, (_, i) => i + 1),
  }
}

/** 逐轮快捷操作三件（§5.7.1；文案逐字照 11_用例域 §5.3.5 ③） */
function PerRoundQuickActions({
  subject,
  applyAllSubject,
  activeRound,
  roundCount,
  valueEmpty,
  onCopyFromRound,
  onClear,
  onApplyAll,
}: {
  /** 清空确认框主体：「评估维度」/「播放设备」（§9 逐字） */
  subject: string
  /**
   * 应用到所有轮次确认框主体：维度段 §9 逐字为「维度」（「将第 {n} 轮的维度配置…」），
   * 设备段为「播放设备」；缺省同 subject。
   */
  applyAllSubject?: string
  activeRound: number
  roundCount: number
  /** 当前轮是否无取值（清空钮禁用条件） */
  valueEmpty: boolean
  onCopyFromRound: (sourceRound: number) => void
  onClear: () => void
  onApplyAll: () => void
}) {
  const [copyOpen, setCopyOpen] = useState(false)
  const [copySource, setCopySource] = useState(1)
  const [confirmAction, setConfirmAction] = useState<'clear' | 'applyAll' | null>(null)
  const otherRounds = Array.from({ length: Math.max(1, roundCount) }, (_, i) => i + 1).filter(
    (round) => round !== activeRound
  )
  const roundLabel = (round: number) => `第${round}轮`

  return (
    <div className='flex flex-wrap items-center gap-2'>
      <Popover
        open={copyOpen}
        onOpenChange={(open) => {
          if (open) setCopySource(otherRounds[0] ?? 1)
          setCopyOpen(open)
        }}
      >
        <PopoverTrigger
          render={
            <Button type='button' variant='outline' size='sm' disabled={roundCount <= 1}>
              <Copy aria-hidden='true' className='size-3.5' />
              从其他轮次复制
            </Button>
          }
        />
        <PopoverContent className='w-64' align='start'>
          <div className='space-y-2'>
            <div className='flex items-center gap-2'>
              <Label className='shrink-0 text-sm'>从</Label>
              <Select
                value={String(copySource)}
                onValueChange={(value) => setCopySource(Number(value))}
                items={otherRounds.map((round) => ({
                  value: String(round),
                  label: roundLabel(round),
                }))}
              >
                <SelectTrigger size='sm' className='h-8'>
                  {/* 直接渲染标签：列表未展开时 base-ui Value 只解析已挂载项，避免显示裸值 */}
                  <SelectValue>{roundLabel(copySource)}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {otherRounds.map((round) => (
                    <SelectItem key={round} value={String(round)}>
                      {roundLabel(round)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Label className='shrink-0 text-sm'>复制到{roundLabel(activeRound)}</Label>
            </div>
            <div className='flex justify-end gap-2'>
              <Button type='button' variant='outline' size='sm' onClick={() => setCopyOpen(false)}>
                取消
              </Button>
              <Button
                type='button'
                size='sm'
                onClick={() => {
                  onCopyFromRound(copySource)
                  setCopyOpen(false)
                }}
              >
                确定
              </Button>
            </div>
          </div>
        </PopoverContent>
      </Popover>

      <Button
        type='button'
        variant='outline'
        size='sm'
        disabled={valueEmpty}
        onClick={() => setConfirmAction('clear')}
      >
        <Trash2 aria-hidden='true' className='size-3.5' />
        清空当前轮次
      </Button>
      <Button
        type='button'
        variant='outline'
        size='sm'
        disabled={roundCount <= 1}
        onClick={() => setConfirmAction('applyAll')}
      >
        <CheckCheck aria-hidden='true' className='size-3.5' />
        应用到所有轮次
      </Button>

      <ConfirmDialog
        open={confirmAction === 'clear'}
        onOpenChange={(open) => !open && setConfirmAction(null)}
        title={`确定清空第 ${activeRound} 轮的${subject}？`}
        desc={`清空后该轮次的${subject}配置将被移除，无法撤销。`}
        confirmText='确定清空'
        destructive
        handleConfirm={() => {
          onClear()
          setConfirmAction(null)
        }}
      />
      <ConfirmDialog
        open={confirmAction === 'applyAll'}
        onOpenChange={(open) => !open && setConfirmAction(null)}
        title={`将第 ${activeRound} 轮的${applyAllSubject ?? subject}配置应用到所有其他轮次？`}
        desc={`其他轮次的${subject}配置将被覆盖为当前轮次的内容。`}
        confirmText='确定应用'
        handleConfirm={() => {
          onApplyAll()
          setConfirmAction(null)
        }}
      />
    </div>
  )
}

export function UploadOptions(props: UploadOptionsProps) {
  // 真实数据源（INT-714 接线）：算法选项 /algorithm/options、评估维度 /evaluation/dimensions、播放设备 /playback-devices
  const algorithmOptionsQuery = useAlgorithmOptions()
  const algorithmOptions = algorithmOptionsQuery.data ?? []
  const uploadDimsQuery = useEvaluationDimensions()
  const uploadDimensions = uploadDimsQuery.data ?? []
  const categoriesQuery = useEvaluationCategories()
  const categories = categoriesQuery.data ?? []
  const playbackDevicesQuery = usePlaybackDevices()
  const playbackDevices = playbackDevicesQuery.data ?? []
  const queryClient = useQueryClient()

  const roundScope = props.roundScope
  const roundCount = Math.max(1, props.roundCount)
  /** N=1 收敛：指定轮次 / 逐轮设置两档禁用 + Tooltip（§5.7.2） */
  const disabledModes: UploadRoundScopeMode[] =
    roundCount <= 1 ? ['specific', 'per_round'] : []

  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState('')
  const scanMutation = useMutation({
    mutationFn: scanRealPlaybackDevices,
    onMutate: () => {
      setScanning(true)
      setScanError('')
    },
    onSuccess: (scanned) => {
      setScanning(false)
      // 扫描到的设备并入列表（照 §5.7.4：按 name|channelIndex 去重追加——
      // 同名同型号不同通道是不同设备，按 model 去重会把它们吞掉）
      queryClient.setQueryData<typeof playbackDevices>(
        ['playback-devices'],
        (prev) => {
          const existing = prev ?? []
          const keyOf = (device: { name: string; channelIndex?: number | null }) =>
            `${device.name}|${device.channelIndex ?? ''}`
          const keys = new Set(existing.map(keyOf))
          const appended: PlaybackDeviceOption[] = []
          for (const device of scanned) {
            const key = keyOf(device)
            if (keys.has(key)) continue
            keys.add(key)
            appended.push({
              id: device.id,
              name: device.name,
              model: device.model ?? '',
              deviceType: device.deviceType ?? '',
              channelIndex: device.channelIndex ?? null,
            })
          }
          return [...existing, ...appended]
        }
      )
      toast.success('扫描完成')
    },
    onError: () => {
      setScanning(false)
      setScanError('扫描失败：无法连接设备管理器，请确认实验室设备在线后重试')
    },
  })

  const selectedPlaybackDevice = playbackDevices.find(
    (device) => String(device.id) === roundScope.deviceId
  )

  return (
    <div className='space-y-4'>
      <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
        <div className='space-y-2'>
          <Label>音频类型</Label>
          <OptionRadio
            value={props.audioType}
            options={UPLOAD_AUDIO_TYPE_OPTIONS}
            onChange={props.onAudioTypeChange}
          />
        </div>
        <div className='space-y-2'>
          <Label>算法类型</Label>
          <Select
            value={props.algorithmType}
            onValueChange={(value) => props.onAlgorithmTypeChange(value ?? '')}
            items={algorithmOptions.map((option) => ({
              value: option.value,
              label: option.label,
            }))}
          >
            <SelectTrigger size='sm' className='w-full' aria-label='算法类型'>
              <SelectValue placeholder={algorithmOptionsQuery.isLoading ? '加载中…' : '选择算法'}>
                {algorithmOptions.find((o) => o.value === props.algorithmType)?.label ?? ''}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {algorithmOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className='space-y-2'>
        <div className='flex items-center justify-between gap-2'>
          <Label htmlFor='upload-gen-case'>生成测试用例</Label>
          <Switch
            id='upload-gen-case'
            checked={props.generateTestCase}
            onCheckedChange={props.onGenerateTestCaseChange}
          />
        </div>
        {props.generateTestCase && (
          <p className='text-muted-foreground text-xs'>
            上传完成后按分组末文件自动生成测试用例
          </p>
        )}
      </div>

      {props.generateTestCase && (
        <>
          {/* 音频标签（V9.7.10 UploadOptions tags 输入对位；逗号分隔，随 merge 载荷 tags 落库） */}
          <div className='space-y-2'>
            <Label htmlFor='upload-tags'>标签</Label>
            <Input
              id='upload-tags'
              value={props.tags}
              onChange={(e) => props.onTagsChange(e.target.value)}
              placeholder='逗号分隔，如 客厅, 中文'
            />
            <p className='text-muted-foreground text-xs'>
              上传完成后作为音频标签，留空自动生成
            </p>
          </div>

          {/* 评估维度（§5.7.3：三档轮次范围 + 维度云 + 多轮整体评估维度节） */}
          <div className='space-y-2'>
            <Label>评估维度</Label>
            <RoundScopeThreeField
              name='upload-dimension-round'
              value={toThreeValue(roundScope.dimensionScope, roundCount)}
              onChange={(next) =>
                roundScope.setDimensionScope({
                  mode: next.mode,
                  specificRounds: next.specificRounds,
                  activeRound: next.activeRound,
                })
              }
              roundCount={roundCount}
              disabledModes={disabledModes}
              disabledHint={props.singleRoundHint}
              renderTabIndicator={(round) => {
                const count = roundScope.dimensionCountOf(round)
                return count > 0 ? (
                  <Badge className='rounded-sm px-1 font-mono text-[10px] tabular-nums'>
                    {count}
                  </Badge>
                ) : null
              }}
            />

            {roundScope.dimensionScope.mode === 'per_round' && (
              <PerRoundQuickActions
                subject='评估维度'
                applyAllSubject='维度'
                activeRound={roundScope.dimensionScope.activeRound}
                roundCount={roundCount}
                valueEmpty={roundScope.dimensionIds.length === 0}
                onCopyFromRound={roundScope.copyDimensionFromRound}
                onClear={roundScope.clearDimensionRound}
                onApplyAll={roundScope.applyDimensionRoundToAll}
              />
            )}

            <p className='text-muted-foreground text-xs'>
              已按当前算法过滤可用维度；不选任何维度时生成的用例不带评估维度
              <span className='ml-2 font-mono tabular-nums'>
                已选 {roundScope.dimensionIds.length} 个维度
              </span>
            </p>

            <div className='max-h-72 overflow-y-auto rounded-lg border p-2'>
              {uploadDimsQuery.isError ? (
                <Alert variant='destructive' className='py-2'>
                  <AlertTitle className='text-sm font-medium'>评估维度加载失败，请稍后重试</AlertTitle>
                  <AlertDescription>
                    <Button
                      type='button'
                      variant='outline'
                      size='sm'
                      className='mt-1 h-7'
                      onClick={() => void uploadDimsQuery.refetch()}
                    >
                      重试
                    </Button>
                  </AlertDescription>
                </Alert>
              ) : uploadDimsQuery.isLoading ? (
                <div className='space-y-1.5'>
                  {[0, 1, 2].map((row) => (
                    <div key={row} className='bg-muted/40 h-7 animate-pulse rounded-md' />
                  ))}
                </div>
              ) : (
                <DimensionPicker
                  dimensions={uploadDimensions}
                  categories={categories}
                  selected={roundScope.dimensionIds}
                  onToggle={(ids, checked) =>
                    roundScope.setDimensionIds(
                      checked
                        ? [...new Set([...roundScope.dimensionIds, ...ids])]
                        : roundScope.dimensionIds.filter((id) => !ids.includes(id))
                    )
                  }
                />
              )}
            </div>

            {/* 多轮整体评估维度（跨轮次聚合；§5.7.3） */}
            <div className='border-border/60 space-y-2 rounded-lg border p-3'>
              <div className='flex flex-wrap items-center gap-2'>
                <span className='text-sm font-medium'>多轮整体评估维度（跨轮次聚合）</span>
                <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                  可选
                </Badge>
              </div>
              <p className='text-muted-foreground text-xs leading-relaxed'>
                这些维度在所有轮次执行完成后触发，基于全量多轮数据计算跨轮次综合指标（如多轮平均
                WER、对话连贯性），与单轮维度独立配置；不选即不配置跨轮次整体评估维度。
              </p>
              <DimensionPicker
                dimensions={uploadDimensions}
                categories={categories}
                selected={roundScope.multiDimensionIds}
                onToggle={(ids, checked) =>
                  roundScope.setMultiDimensionIds(
                    checked
                      ? [...new Set([...roundScope.multiDimensionIds, ...ids])]
                      : roundScope.multiDimensionIds.filter((id) => !ids.includes(id))
                  )
                }
                showSearch={false}
              />
            </div>
          </div>

          {/* 播放设备（§5.7.4：三档轮次范围 + Select + 重新扫描） */}
          <div className='space-y-2'>
            <Label htmlFor='upload-playback-device'>播放设备</Label>
            <RoundScopeThreeField
              name='upload-device-round'
              value={toThreeValue(roundScope.deviceScope, roundCount)}
              onChange={(next) =>
                roundScope.setDeviceScope({
                  mode: next.mode,
                  specificRounds: next.specificRounds,
                  activeRound: next.activeRound,
                })
              }
              roundCount={roundCount}
              disabledModes={disabledModes}
              disabledHint={props.singleRoundHint}
              renderTabIndicator={(round) =>
                roundScope.deviceSelectedOf(round) ? (
                  <Check aria-hidden='true' className='text-primary size-3.5' />
                ) : null
              }
            />

            {roundScope.deviceScope.mode === 'per_round' && (
              <PerRoundQuickActions
                subject='播放设备'
                activeRound={roundScope.deviceScope.activeRound}
                roundCount={roundCount}
                valueEmpty={roundScope.deviceId === ''}
                onCopyFromRound={roundScope.copyDeviceFromRound}
                onClear={roundScope.clearDeviceRound}
                onApplyAll={roundScope.applyDeviceRoundToAll}
              />
            )}

            <div className='flex flex-wrap items-center gap-2'>
              <Select
                value={roundScope.deviceId}
                onValueChange={(value) => roundScope.setDeviceId(value ?? '')}
                items={playbackDevices.map((device) => ({
                  value: String(device.id),
                  label: `${device.name}${device.model ? `（${device.model}）` : ''}`,
                }))}
              >
                <SelectTrigger
                  id='upload-playback-device'
                  size='sm'
                  className='w-full sm:w-72'
                  disabled={playbackDevices.length === 0}
                >
                  <SelectValue placeholder={playbackDevicesQuery.isLoading ? '加载中…' : '选择播放设备'}>
                    {selectedPlaybackDevice
                      ? `${selectedPlaybackDevice.name}${selectedPlaybackDevice.model ? `（${selectedPlaybackDevice.model}）` : ''}`
                      : ''}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {playbackDevices.map((device) => (
                    <SelectItem key={device.id} value={String(device.id)}>
                      {device.name}
                      {device.model ? `（${device.model}）` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                type='button'
                variant='ghost'
                size='sm'
                className='h-7'
                disabled={scanMutation.isPending}
                onClick={() => scanMutation.mutate()}
              >
                重新扫描
              </Button>
              {scanning && (
                <span className='text-muted-foreground inline-flex items-center gap-1.5 text-xs'>
                  <Spinner className='size-3.5' />
                  正在扫描可用设备...
                </span>
              )}
              {scanError && <span className='text-destructive text-xs'>{scanError}</span>}
            </div>
            {playbackDevicesQuery.isLoading && (
              <p className='text-muted-foreground/70 inline-flex items-center gap-1.5 text-xs'>
                <Spinner className='size-3.5' />
                正在加载播放设备...
              </p>
            )}
            {!playbackDevicesQuery.isLoading && playbackDevices.length === 0 && (
              <p className='text-muted-foreground/70 text-xs'>暂无可用的播放设备</p>
            )}
          </div>

          <div className='space-y-2'>
            <Label htmlFor='upload-spl'>默认声压级（dB）</Label>
            <Input
              id='upload-spl'
              type='number'
              min={30}
              max={120}
              value={props.defaultSpl}
              onChange={(e) => props.onDefaultSplChange(Number(e.target.value))}
              className='w-32'
            />
          </div>

          <div className='space-y-2'>
            <Label>用例分组</Label>
            <OptionRadio
              value={props.caseGroup}
              options={CASE_GROUP_OPTIONS}
              onChange={props.onCaseGroupChange}
            />
            {props.caseGroup === 'custom' && (
              <Input
                aria-label='自定义分组名'
                value={props.customGroupName}
                onChange={(e) => props.onCustomGroupNameChange(e.target.value)}
                placeholder='输入自定义分组名'
                className='mt-1.5'
              />
            )}
          </div>

          <Alert className='py-2'>
            <Info aria-hidden='true' className='size-4' />
            <AlertTitle className='text-sm font-medium'>提示</AlertTitle>
            <AlertDescription>
              播放设备与评估维度按上面的轮次范围写入本次生成的用例；噪声与更细的轮次参数仍可在用例编辑页补充
            </AlertDescription>
          </Alert>
        </>
      )}

      <div className='flex items-center justify-between gap-2'>
        <Label htmlFor='upload-inherit-tags'>继承音频标签</Label>
        <Switch
          id='upload-inherit-tags'
          checked={props.inheritTags}
          onCheckedChange={props.onInheritTagsChange}
        />
      </div>
    </div>
  )
}
