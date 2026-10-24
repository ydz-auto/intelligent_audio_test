/**
 * 轮次步骤①：算法参数 DynamicForm（11_用例域.md §5.1，按算法 schema 渲染）。
 * INT-996 接线：改接真实 GET /algorithm/form-schema/{algo_type}（infrastructure/api/algorithm-form-api，
 * 与批量专属参数弹窗 batch-algo-params-dialog.tsx 同源），删除 mock ALGO_SCHEMAS；
 * 受控组件（value/onChange），保存侧由抽屉序列化到 algorithm_params 独立列（[{round_number, params}]）。
 * 字段分组行（Collapsible 组头）+ 字段类型 text/number/select/switch/code-editor；
 * 排除 voiceprint/interferers/audio_select 类型参数（归噪声与干扰/音频列表步骤）。
 */
import { ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import type { RoundAlgorithmParamItem } from '@/features/testcases/modals/round-config/round-nav'
import {
  dedupeFormFields,
  fetchAlgorithmFormSchema,
  type AlgorithmFormField,
} from '@/infrastructure/api/algorithm-form-api'

/** 这些字段类型不在算法参数步骤显示（归噪声与干扰/音频列表步骤；照 V9.7.10 AlgoParamsStep.vue 口径） */
const EXCLUDED_TYPES = new Set([
  'voiceprint_editor',
  'noise_config',
  'audio_select',
  'audio_file',
])

/** 这些 param_code 由专门步骤处理（照 V9.7.10 口径，含旧格式拆分字段） */
const EXCLUDED_CODES = new Set([
  'interferers',
  'voiceprint',
  'voiceprintEnabled',
  'voiceprintAudioId',
  'voiceprintPlaybackDeviceId',
  'voiceprintSpl',
  'voiceprintWaitTime',
])

function isEligible(field: AlgorithmFormField): boolean {
  return !EXCLUDED_TYPES.has(field.component) && !EXCLUDED_TYPES.has(field.type) && !EXCLUDED_CODES.has(field.code)
}

function jsonDefault(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

/** 参数输入控件（受控；照 batch-algo-params-dialog.tsx AlgoParamInput 同源渲染） */
function ParamInput({
  field,
  value,
  onChange,
}: {
  field: AlgorithmFormField
  value: unknown
  onChange: (v: string | boolean) => void
}) {
  const component = field.component ?? 'input'
  if (component === 'switch' || field.type === 'switch') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Switch
          checked={Boolean(value ?? field.defaultValue)}
          onCheckedChange={(v) => onChange(v)}
          aria-label={field.label}
        />
        {field.helpText && <p className='text-muted-foreground/70 text-xs'>{field.helpText}</p>}
      </div>
    )
  }
  if (component === 'select') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Select
          value={String(value ?? field.defaultValue ?? '')}
          onValueChange={(v) => v != null && onChange(v)}
        >
          <SelectTrigger size='sm' className='h-8 w-full'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(field.options ?? []).map((o) => (
              <SelectItem key={o} value={o}>
                {o}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {field.helpText && <p className='text-muted-foreground/70 text-xs'>{field.helpText}</p>}
      </div>
    )
  }
  if (component === 'code-editor' || field.type === 'json') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <textarea
          value={value === undefined ? jsonDefault(field.defaultValue) : String(value)}
          rows={4}
          aria-label={field.label}
          placeholder={field.helpText ?? undefined}
          className='border-border/60 bg-background focus:border-primary focus:ring-primary/20 min-h-0 w-full rounded-md border px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2'
          onChange={(e) => onChange(e.target.value)}
        />
        {field.helpText && <p className='text-muted-foreground/70 text-xs'>{field.helpText}</p>}
      </div>
    )
  }
  if (component === 'input-number' || field.type === 'number') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Input
          type='number'
          value={String(value ?? field.defaultValue ?? '')}
          placeholder={field.helpText ?? undefined}
          className='h-8'
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    )
  }
  return (
    <div className='space-y-1.5'>
      <Label className='text-sm'>{field.label}</Label>
      <Input
        type='text'
        value={String(value ?? field.defaultValue ?? '')}
        placeholder={field.helpText ?? undefined}
        className='h-8'
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

export function AlgorithmParamsStep({
  algorithmType,
  value,
  onChange,
}: {
  algorithmType?: string | null
  /** 当前轮算法参数（独立列 params [{field_code, field_value}]；仅含本步骤可编辑字段的增量） */
  value: RoundAlgorithmParamItem[]
  onChange: (next: RoundAlgorithmParamItem[]) => void
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const schemaQuery = useQuery({
    queryKey: ['algorithm-form-schema', algorithmType ?? ''],
    queryFn: () => fetchAlgorithmFormSchema(algorithmType ?? ''),
    enabled: Boolean(algorithmType),
  })

  /** 展平（顶层 fields + 分组内 fields 按 fieldCode 去重；§5.3.1 参数表单逐字段） + 排除专项字段 */
  const allFields = useMemo(
    () =>
      schemaQuery.data
        ? dedupeFormFields([
            ...schemaQuery.data.fields,
            ...schemaQuery.data.groups.flatMap((g) => g.fields),
          ])
            .filter((f) => !f.hidden)
            .filter(isEligible)
        : [],
    [schemaQuery.data]
  )

  /** 当前值 → 字段值 dict（仅回填已存在的可编辑字段） */
  const valueDict = useMemo(() => {
    const dict: Record<string, unknown> = {}
    const eligibleCodes = new Set(allFields.map((f) => f.code))
    for (const p of value) {
      if (eligibleCodes.has(p.field_code)) dict[p.field_code] = p.field_value
    }
    return dict
  }, [value, allFields])

  const handleFieldChange = (fieldCode: string, fieldValue: string | boolean) => {
    // 保持存量参数（声纹/干扰人等非本步骤字段不丢），仅更新/追加被编辑字段
    const next = [...value]
    const idx = next.findIndex((p) => p.field_code === fieldCode)
    if (idx >= 0) next[idx] = { field_code: fieldCode, field_value: fieldValue }
    else next.push({ field_code: fieldCode, field_value: fieldValue })
    onChange(next)
  }

  if (!algorithmType) {
    return (
      <div className='border-border/60 rounded-lg border border-dashed px-3 py-6 text-center'>
        <p className='text-muted-foreground text-sm'>
          请先在「关联算法」选择算法类型，参数表单将按算法 schema 加载
        </p>
      </div>
    )
  }

  if (schemaQuery.isLoading) {
    return (
      <div className='flex h-24 items-center justify-center gap-2 rounded-lg border text-sm text-muted-foreground'>
        <Spinner className='size-4' />
        正在加载算法参数表单...
      </div>
    )
  }

  if (schemaQuery.isError) {
    return (
      <div className='rounded-lg border px-3 py-6 text-center'>
        <p className='text-destructive text-sm'>加载算法参数表单失败</p>
        <Button
          type='button'
          variant='outline'
          size='sm'
          className='mt-2 h-7'
          onClick={() => void schemaQuery.refetch()}
        >
          重试
        </Button>
      </div>
    )
  }

  if (allFields.length === 0) {
    return (
      <div className='border-border/60 rounded-lg border border-dashed px-3 py-6 text-center'>
        <p className='text-muted-foreground text-sm'>该算法暂无参数配置</p>
      </div>
    )
  }

  /** schema 分组（非空组按渲染；无分组时顶层 fields 直接平铺）。
   *  同一字段既在顶层 fields 又在 groups[].fields 时只渲一次：进组的字段只在组内出现，
   *  顶层只平铺未进组的字段（INT-1686）。 */
  const groups = schemaQuery.data?.groups ?? []
  const groupedCodes = new Set<string>()
  const renderGroups = groups
    .map((group) => {
      const fields = dedupeFormFields(group.fields)
        .filter((f) => !f.hidden)
        .filter(isEligible)
        .filter((f) => {
          if (!f.code) return true
          if (groupedCodes.has(f.code)) return false
          groupedCodes.add(f.code)
          return true
        })
      return { group, fields }
    })
    .filter((item) => item.fields.length > 0)
  const topFields = dedupeFormFields(schemaQuery.data?.fields ?? [])
    .filter((f) => !f.hidden)
    .filter(isEligible)
    .filter((f) => !f.code || !groupedCodes.has(f.code))

  return (
    <div className='space-y-3'>
      <p className='text-muted-foreground text-xs'>
        按算法「{schemaQuery.data?.algorithmName || algorithmType}」schema 渲染参数表单；声纹注册/干扰人/音频选择类参数归后续步骤。
      </p>
      {topFields.length > 0 && (
        <div className='grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3'>
          {topFields.map((f) => (
            <ParamInput
              key={f.code}
              field={f}
              value={valueDict[f.code]}
              onChange={(v) => handleFieldChange(f.code, v)}
            />
          ))}
        </div>
      )}
      {renderGroups.map(({ group, fields }) => {
        const isCollapsed = collapsed.has(group.name || group.label)
        return (
          <div key={group.name || group.label} className='overflow-hidden rounded-lg border'>
            <button
              type='button'
              className='hover:bg-muted/40 flex w-full items-center gap-1.5 px-3 py-2 text-start text-sm font-medium transition-colors'
              onClick={() =>
                setCollapsed((prev) => {
                  const next = new Set(prev)
                  const key = group.name || group.label
                  if (next.has(key)) next.delete(key)
                  else next.add(key)
                  return next
                })
              }
              aria-expanded={!isCollapsed}
            >
              <ChevronDown
                aria-hidden='true'
                className={cn('size-4 text-muted-foreground transition-transform', isCollapsed && '-rotate-90')}
              />
              {group.label || group.name}
            </button>
            {!isCollapsed && (
              <div className='grid gap-x-6 gap-y-3 border-t p-3 sm:grid-cols-2 lg:grid-cols-3'>
                {fields.map((f) => (
                  <ParamInput
                    key={f.code}
                    field={f}
                    value={valueDict[f.code]}
                    onChange={(v) => handleFieldChange(f.code, v)}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
