/**
 * 上传选项（§6.16/§6.17 共用 UploadOptions；buildUploadOptionsConfig 平移）。
 * 音频类型 radio + 生成测试用例 boolean + 算法类型 select + 测试类型 checkbox
 * + 播放设备 select + 默认声压级 + 用例分组 radio + 继承音频标签 boolean。
 * E2E 时提示 info「播放设备、声压级、噪声等参数将在用例编辑页面的轮次配置中填写」
 * + 评估维度勾选用 DimensionPicker（照 V9.7.10 DimensionConfigPanel 平铺云，
 * 搜索+已选计数，默认勾选必填项——识别准确率/唤醒成功率）。
 */
import { Check, Info } from 'lucide-react'
import { useState } from 'react'

import { useEvaluationDimensions } from '@/application/evaluation/use-dimensions'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'
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
import {
  UPLOAD_AUDIO_TYPE_OPTIONS,
  UPLOAD_TEST_TYPE_OPTIONS,
} from '@/features/audio-import/constants'
import {
  MOCK_CASE_GROUP_OPTIONS,
  MOCK_PLAYBACK_DEVICES,
} from '@/infrastructure/mock/audio-mock'

export type UploadOptionsProps = {
  audioType: string
  onAudioTypeChange: (value: string) => void
  generateTestCase: boolean
  onGenerateTestCaseChange: (value: boolean) => void
  algorithmType: string
  onAlgorithmTypeChange: (value: string) => void
  testTypes: string[]
  onTestTypesChange: (value: string[]) => void
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
  const toggleTestType = (value: string) => {
    const next = props.testTypes.includes(value)
      ? props.testTypes.filter((v) => v !== value)
      : [...props.testTypes, value]
    props.onTestTypesChange(next)
  }

  // 评估维度勾选（照 V9.7.10 DimensionConfigPanel 平铺云；默认勾选必填项：识别准确率/唤醒成功率）
  const uploadDimsQuery = useEvaluationDimensions()
  const uploadDimensions = uploadDimsQuery.data ?? []
  const [selectedUploadDims, setSelectedUploadDims] = useState<number[]>([1, 3])
  const handleUploadDimToggle = (ids: number[], checked: boolean) => {
    setSelectedUploadDims((prev) =>
      checked
        ? [...new Set([...prev, ...ids])]
        : prev.filter((id) => !ids.includes(id))
    )
  }

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
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='asr-v3'>通用识别引擎</SelectItem>
              <SelectItem value='asr-stream'>流式识别引擎</SelectItem>
              <SelectItem value='eval-ensemble'>多维评估集成</SelectItem>
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
          <div className='space-y-2'>
            <Label>测试类型</Label>
            <div className='flex flex-wrap gap-4'>
              {UPLOAD_TEST_TYPE_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className='flex cursor-pointer items-center gap-2 text-sm'
                >
                  <Checkbox
                    checked={props.testTypes.includes(option.value)}
                    onCheckedChange={() => toggleTestType(option.value)}
                  />
                  {option.label}
                </label>
              ))}
            </div>
          </div>

          <div className='space-y-2'>
            <Label htmlFor='upload-playback-device'>播放设备</Label>
            <Select
              value={props.playbackDevice}
              onValueChange={(value) => props.onPlaybackDeviceChange(value ?? '')}
            >
              <SelectTrigger id='upload-playback-device' size='sm' className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MOCK_PLAYBACK_DEVICES.map((device) => (
                  <SelectItem key={device.id} value={String(device.id)}>
                    {device.name}（{device.model}）
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
              options={MOCK_CASE_GROUP_OPTIONS}
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

          <div className='space-y-2'>
            <Label>评估维度</Label>
            <DimensionPicker
              dimensions={uploadDimensions}
              algorithmType={props.algorithmType}
              selected={selectedUploadDims}
              onToggle={handleUploadDimToggle}
            />
          </div>
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
