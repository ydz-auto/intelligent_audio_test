/**
 * 上传选项（§6.16/§6.17 共用 UploadOptions；buildUploadOptionsConfig 平移；INT-714 接线）。
 * 音频类型 radio + 生成测试用例 boolean + 算法类型 select（真实 /algorithm/options）
 * + 评估维度单组（真实 /evaluation/dimensions，DimensionPicker 主/子分组云 + 分类分组；
 *   INT-714 口径修订：用例类型由后端默认落库，模态窗不再显示 E2E/API 类型选择）
 * + 播放设备 select（真实 /playback-devices）+ 默认声压级 + 用例分组 radio + 继承音频标签 boolean。
 */
import { Check, Info } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import {
  useEvaluationDimensions,
  useEvaluationCategories,
  useAlgorithmOptions,
} from '@/application/evaluation/use-dimensions'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { DimensionPicker } from '@/features/testcases/modals/round-config/dimension-picker'
import { fetchPlaybackDevices } from '@/infrastructure/api/audio-upload-api'
import { fetchReferenceParams } from '@/infrastructure/api/algorithmApi'
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
  dimensionIds: number[]
  onDimensionIdsChange: (value: number[]) => void
  playbackDevice: string
  onPlaybackDeviceChange: (value: string) => void
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
  /** 标注代码（V9.7.10 referenceParamOptions select 对位；解析标注文件时作为 code 落库） */
  annotationCode: string
  onAnnotationCodeChange: (value: string) => void
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

export function UploadOptions(props: UploadOptionsProps) {
  // 真实数据源（INT-714 接线）：算法选项 /algorithm/options、评估维度 /evaluation/dimensions、播放设备 /playback-devices
  const algorithmOptionsQuery = useAlgorithmOptions()
  const algorithmOptions = algorithmOptionsQuery.data ?? []
  const uploadDimsQuery = useEvaluationDimensions()
  const uploadDimensions = uploadDimsQuery.data ?? []
  const categoriesQuery = useEvaluationCategories()
  const categories = categoriesQuery.data ?? []
  const playbackDevicesQuery = useQuery({
    queryKey: ['playback-devices'],
    queryFn: fetchPlaybackDevices,
    staleTime: 5 * 60_000,
  })
  const playbackDevices = playbackDevicesQuery.data ?? []
  // 标注代码（V9.7.10 referenceParamOptions 对位：选项走 /algorithm/reference-params，随算法类型联动）
  const referenceParamsQuery = useQuery({
    queryKey: ['algorithm', 'reference-params', props.algorithmType || ''],
    queryFn: () => fetchReferenceParams(props.algorithmType || undefined),
    enabled: Boolean(props.algorithmType),
    staleTime: 5 * 60_000,
  })
  const referenceParams = referenceParamsQuery.data ?? []
  const selectedAnnotationCodeLabel = referenceParams.find(
    (option) => option.value === props.annotationCode
  )?.label
  const selectedPlaybackDevice = playbackDevices.find(
    (device) => String(device.id) === props.playbackDevice
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

      {/* 标注代码（V9.7.10 UploadFileModal/FolderImportModal 对位；选中后作为解析标注的 code 落库） */}
      {Boolean(props.algorithmType) && (
        <div className='space-y-2'>
          <Label htmlFor='upload-annotation-code'>标注代码</Label>
          <Select
            value={props.annotationCode}
            onValueChange={(value) => props.onAnnotationCodeChange(value ?? '')}
          >
            <SelectTrigger id='upload-annotation-code' size='sm' className='w-full'>
              <SelectValue placeholder='留空则使用 JSON 内 code/name 字段'>
                {selectedAnnotationCodeLabel ?? ''}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {referenceParams.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className='text-muted-foreground text-xs'>
            标注文件解析时作为标注代码，留空则按 JSON 内 code 或文件名推断
          </p>
        </div>
      )}

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

          {/* 评估维度单组（INT-714 口径修订：不再按 E2E/API 分型平铺两组；用例类型由后端默认落库） */}
          <div className='space-y-2'>
            <Label>评估维度</Label>
            <DimensionPicker
              dimensions={uploadDimensions}
              categories={categories}
              selected={props.dimensionIds}
              onToggle={(ids, checked) =>
                props.onDimensionIdsChange(
                  checked
                    ? [...new Set([...props.dimensionIds, ...ids])]
                    : props.dimensionIds.filter((id) => !ids.includes(id))
                )
              }
            />
          </div>

          <div className='space-y-2'>
            <Label htmlFor='upload-playback-device'>播放设备</Label>
            <Select
              value={props.playbackDevice}
              onValueChange={(value) => props.onPlaybackDeviceChange(value ?? '')}
            >
              <SelectTrigger id='upload-playback-device' size='sm' className='w-full'>
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
              播放设备、声压级、噪声等参数将在用例编辑页面的轮次配置中填写
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
