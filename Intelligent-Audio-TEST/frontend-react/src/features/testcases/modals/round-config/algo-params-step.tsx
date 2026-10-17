/**
 * 轮次步骤①：算法参数 DynamicForm（11_用例域.md §5.1，按算法 schema 渲染）。
 * 字段分组行（Collapsible 组头）+ 字段类型 text/number/select/switch；
 * 排除 voiceprint/interferers/audio_select 类型参数（归噪声与干扰/音频列表步骤）。
 * mock 阶段按 MOCK_ALGORITHMS 预置三套 schema 演示按算法重载；接线后走 GET /algorithm/form-schema/{algo_type}。
 */
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

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

export interface AlgorithmParamField {
  code: string
  label: string
  type: 'text' | 'number' | 'select' | 'switch'
  options?: string[]
  placeholder?: string
  default?: string | number | boolean
}

export interface ParamGroup {
  title: string
  fields: AlgorithmParamField[]
}

/** 算法参数 schema 登记表（§5.3.1 批量专属参数弹窗复用同一数据源） */
export const ALGO_SCHEMAS: Record<string, ParamGroup[]> = {
  'asr-v3': [
    {
      title: '基础识别',
      fields: [
        { code: 'sample_rate', label: '采样率（Hz）', type: 'select', options: ['16000', '8000'], default: '16000' },
        { code: 'channels', label: '声道数', type: 'number', default: 1 },
        { code: 'encode_format', label: '编码格式', type: 'select', options: ['wav', 'flac', 'mp3'], default: 'wav' },
        { code: 'language', label: '识别语言', type: 'select', options: ['中文', '英文', '中英混'], default: '中文' },
      ],
    },
    {
      title: '解码优化',
      fields: [
        { code: 'vad_threshold', label: 'VAD 阈值', type: 'number', default: 0.3 },
        { code: 'max_audio_sec', label: '最大音频时长（秒）', type: 'number', default: 300 },
        { code: 'speaker_diarization', label: '说话人分离', type: 'switch', default: false },
      ],
    },
  ],
  'asr-stream': [
    {
      title: '流式配置',
      fields: [
        { code: 'stream_mode', label: '流式模式', type: 'select', options: ['全量', '半程', '关键帧'], default: '全量' },
        { code: 'chunk_ms', label: '分片时长（ms）', type: 'number', default: 500 },
        { code: 'stream_denoise', label: '流式去噪', type: 'switch', default: true },
      ],
    },
  ],
  'eval-ensemble': [
    {
      title: '评估策略',
      fields: [
        { code: 'eval_mode', label: '评估模式', type: 'select', options: ['自动评估', '人工评估'], default: '自动评估' },
        { code: 'agg_method', label: '聚合方法', type: 'select', options: ['简单平均', '加权平均', '比率'], default: '简单平均' },
        { code: 'confidence_threshold', label: '置信度阈值', type: 'number', default: 0.8 },
      ],
    },
  ],
}

/** DynamicForm 字段渲染（mock 态受控演示；排除 voiceprint/interferers/audio_select 类型参数） */
function ParamField({ field }: { field: AlgorithmParamField }) {
  const [value, setValue] = useState(field.default)
  if (field.type === 'switch') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Switch checked={Boolean(value)} onCheckedChange={(v) => setValue(v)} aria-label={field.label} />
      </div>
    )
  }
  if (field.type === 'select') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Select value={String(value)} onValueChange={(v) => v != null && setValue(v)}>
          <SelectTrigger size='sm' className='h-8 w-full'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {field.options?.map((o) => (
              <SelectItem key={o} value={o}>
                {o}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    )
  }
  return (
    <div className='space-y-1.5'>
      <Label className='text-sm'>{field.label}</Label>
      <Input
        type={field.type === 'number' ? 'number' : 'text'}
        value={String(value)}
        placeholder={field.placeholder}
        className='h-8'
        onChange={(e) => setValue(e.target.value)}
      />
    </div>
  )
}

export function AlgorithmParamsStep({ algorithmType }: { algorithmType?: string | null }) {
  const normalizedType =
    algorithmType && ALGO_SCHEMAS[algorithmType] ? algorithmType : 'asr-v3'
  const effectiveSchema = ALGO_SCHEMAS[normalizedType] ?? []
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  return (
    <div className='space-y-3'>
      <p className='text-muted-foreground text-xs'>
        按算法「{algorithmType ?? '—'}」schema 渲染参数表单；声纹注册/干扰人/音频选择类参数归后续步骤。
      </p>
      {effectiveSchema.map((group) => {
        const isCollapsed = collapsed.has(group.title)
        return (
          <div key={group.title} className='overflow-hidden rounded-lg border'>
            <button
              type='button'
              className='hover:bg-muted/40 flex w-full items-center gap-1.5 px-3 py-2 text-start text-sm font-medium transition-colors'
              onClick={() =>
                setCollapsed((prev) => {
                  const next = new Set(prev)
                  if (next.has(group.title)) next.delete(group.title)
                  else next.add(group.title)
                  return next
                })
              }
              aria-expanded={!isCollapsed}
            >
              <ChevronDown
                aria-hidden='true'
                className={cn('size-4 text-muted-foreground transition-transform', isCollapsed && '-rotate-90')}
              />
              {group.title}
            </button>
            {!isCollapsed && (
              <div className='grid gap-x-6 gap-y-3 border-t p-3 sm:grid-cols-2 lg:grid-cols-3'>
                {group.fields.map((f) => (
                  <ParamField key={f.code} field={f} />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
