/**
 * 评估维度表单「API配置」分节（11_用例域.md §5.5 API配置；仅主维度）。
 * Master入口URL · API设置（请求方法/超时/Headers JSON/bodyTemplate JSON）·
 * 所需输入配置（行编辑器）· 输出字段配置（行编辑器）· 统计方式 · 聚合分母口径 ·
 * 排除轮次（多选「第{n}轮」+「最后一轮」(-1)）· API端点配置（行编辑器）。
 * P3-2 审计收敛：所需输入/输出字段/API 端点子编辑器由组件本地 useState 收敛进
 * RHF useFieldArray（随表单载荷提交，编辑态可反填）。
 */
import { Plus, Trash2 } from 'lucide-react'
import { useFieldArray, type UseFormReturn } from 'react-hook-form'

import { Button } from '@/components/ui/button'
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
import { Textarea } from '@/components/ui/textarea'
import {
  AGG_DENOMINATOR_OPTIONS,
  STATISTIC_METHOD_OPTIONS,
} from '@/features/evaluation/constants'
import type {
  ApiEndpointRow,
  DimensionFormValues,
  OutputFieldRow,
  RequiredInputRow,
} from '@/features/evaluation/mutate/dimension-form-schema'

const API_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] as const

/** 输入参数字段类型（后端契约原值；照 V9.7.10 RequiredInputsEditor） */
const INPUT_FIELD_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'audio', label: '音频' },
  { value: 'boolean', label: '布尔' },
  { value: 'json', label: 'JSON' },
  { value: 'timestamp', label: '时间戳' },
]

/** 输出字段类型（照 V9.7.10 OutputFieldsEditor：无音频） */
const OUTPUT_FIELD_TYPE_OPTIONS = [
  { value: 'number', label: '数字' },
  { value: 'text', label: '文本' },
  { value: 'boolean', label: '布尔' },
  { value: 'json', label: 'JSON' },
  { value: 'timestamp', label: '时间戳' },
]

/** 输出字段角色（output_role；照 V9.7.10） */
const OUTPUT_ROLE_OPTIONS = [
  { value: 'main', label: '主结果' },
  { value: 'aux', label: '辅助字段' },
]

/** 输出聚合角色（agg_role；照 V9.7.10：无/直接值/分子/分母/达标线≤/达标线≥/精确匹配==） */
const AGG_ROLE_OPTIONS = [
  { value: '', label: '无' },
  { value: 'value', label: '直接值' },
  { value: 'numerator', label: '分子' },
  { value: 'denominator', label: '分母' },
  { value: 'pass_le', label: '达标线(≤)' },
  { value: 'pass_ge', label: '达标线(≥)' },
  { value: 'pass_eq', label: '精确匹配(==)' },
]

const NEW_INPUT_ROW: RequiredInputRow = {
  paramCode: '',
  paramName: '',
  label: '',
  fieldType: 'text',
  required: false,
  defaultValue: '',
  helpText: '',
  uiOrder: 1,
}
const NEW_OUTPUT_ROW: OutputFieldRow = {
  paramCode: '',
  paramName: '',
  label: '',
  fieldPath: '',
  fieldType: 'number',
  outputRole: 'main',
  aggRole: 'value',
  defaultValue: '',
  visibleInReport: true,
  helpText: '',
  uiOrder: 1,
}
const NEW_ENDPOINT_ROW: ApiEndpointRow = {
  url: '',
  name: '',
  priority: 1,
  maxProcess: 5,
  maxTimeout: 30,
  maxAudioDuration: 60,
}

export function ApiSection({
  form,
}: {
  form: UseFormReturn<DimensionFormValues>
}) {
  const { register, watch, setValue, control } = form
  const inputs = useFieldArray({ control, name: 'requiredInputs' })
  const outputs = useFieldArray({ control, name: 'outputFields' })
  const endpoints = useFieldArray({ control, name: 'apiEndpoints' })

  return (
    <div className='space-y-3'>
      <div className='space-y-1.5'>
        <Label htmlFor='dim-api-url'>Master入口URL</Label>
        <Input
          id='dim-api-url'
          placeholder='请输入Master调度节点URL (分布式架构必填)'
          {...register('apiUrl')}
        />
      </div>

      {/* API 设置 */}
      <div className='bg-muted/50 space-y-3 rounded-lg border p-3'>
        <p className='text-sm font-medium'>API 设置</p>
        <div className='grid gap-3 sm:grid-cols-3'>
          <div className='space-y-1.5'>
            <Label required>请求方法</Label>
            <Select
              value={watch('apiMethod')}
              onValueChange={(value) =>
                setValue('apiMethod', value as DimensionFormValues['apiMethod'], {
                  shouldDirty: true,
                })
              }
            >
              <SelectTrigger className='w-full justify-between'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {API_METHODS.map((method) => (
                  <SelectItem key={method} value={method}>
                    {method}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='dim-api-timeout' required>
              超时(ms)
            </Label>
            <Input
              id='dim-api-timeout'
              type='number'
              min={1}
              {...register('apiTimeout', { valueAsNumber: true })}
            />
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='dim-api-headers'>Headers (JSON)</Label>
            <Textarea
              id='dim-api-headers'
              rows={3}
              className='font-mono text-xs'
              {...register('apiHeaders')}
            />
          </div>
        </div>
        <div className='space-y-1.5'>
          <Label htmlFor='dim-api-body'>bodyTemplate (JSON)</Label>
          <Textarea
            id='dim-api-body'
            rows={4}
            className='font-mono text-xs'
            {...register('apiBodyTemplate')}
          />
          <p className='text-muted-foreground text-xs'>
            rounds 内的字段由左侧表单管理，rounds 外的字段（如 model/prompt）可直接在此编辑
          </p>
        </div>
      </div>

      {/* 所需输入配置 */}
      <div className='space-y-2'>
        <div className='flex items-center justify-between'>
          <p className='text-sm font-medium'>所需输入配置</p>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1.5'
            onClick={() =>
              inputs.append({
                ...NEW_INPUT_ROW,
                uiOrder: inputs.fields.length + 1,
              })
            }
          >
            <Plus aria-hidden='true' className='size-3.5' />
            添加输入
          </Button>
        </div>
        <div className='space-y-2'>
          {inputs.fields.map((row, index) => (
            <div
              key={row.id}
              className='border-border/60 flex flex-wrap items-center gap-2 rounded-lg border px-2 py-1.5'
            >
              <Input
                aria-label={`输入参数键名 ${index + 1}`}
                placeholder='参数键名 (如: asr_result)'
                {...register(`requiredInputs.${index}.paramCode`)}
                className='h-8 w-40'
              />
              <Input
                aria-label={`输入显示标签 ${index + 1}`}
                placeholder='显示标签'
                {...register(`requiredInputs.${index}.paramName`)}
                className='h-8 w-32'
              />
              <Select
                value={watch(`requiredInputs.${index}.fieldType`)}
                onValueChange={(value) =>
                  setValue(`requiredInputs.${index}.fieldType`, value ?? 'text', {
                    shouldDirty: true,
                  })
                }
              >
                <SelectTrigger size='sm' className='w-28'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INPUT_FIELD_TYPE_OPTIONS.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <label className='flex items-center gap-1.5 text-xs'>
                <Checkbox
                  aria-label={`输入必填 ${index + 1}`}
                  checked={watch(`requiredInputs.${index}.required`)}
                  onCheckedChange={(checked) =>
                    setValue(`requiredInputs.${index}.required`, !!checked, {
                      shouldDirty: true,
                    })
                  }
                />
                必填
              </label>
              <Input
                aria-label={`输入默认值 ${index + 1}`}
                placeholder='默认值'
                {...register(`requiredInputs.${index}.defaultValue`)}
                className='h-8 w-24'
              />
              <Input
                aria-label={`输入描述 ${index + 1}`}
                placeholder='描述'
                {...register(`requiredInputs.${index}.helpText`)}
                className='h-8 w-36'
              />
              <Input
                aria-label={`输入排序 ${index + 1}`}
                type='number'
                min={0}
                {...register(`requiredInputs.${index}.uiOrder`, {
                  valueAsNumber: true,
                })}
                className='h-8 w-14'
                title='展示顺序'
              />
              <Button
                type='button'
                variant='ghost'
                size='icon-sm'
                className='text-destructive ml-auto'
                aria-label={`删除输入 ${index + 1}`}
                onClick={() => inputs.remove(index)}
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
              </Button>
            </div>
          ))}
        </div>
      </div>

      {/* 输出字段配置 */}
      <div className='space-y-2'>
        <div className='flex items-center justify-between'>
          <p className='text-sm font-medium'>输出字段配置</p>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1.5'
            onClick={() =>
              outputs.append({
                ...NEW_OUTPUT_ROW,
                uiOrder: outputs.fields.length + 1,
              })
            }
          >
            <Plus aria-hidden='true' className='size-3.5' />
            添加字段
          </Button>
        </div>
        <p className='text-muted-foreground text-xs'>
          配置评估结果提取字段及聚合角色（用于报告统计）
        </p>
        <div className='space-y-2'>
          {outputs.fields.map((row, index) => (
            <div
              key={row.id}
              className='border-border/60 flex flex-wrap items-center gap-2 rounded-lg border px-2 py-1.5'
            >
              <Input
                aria-label={`输出字段代码 ${index + 1}`}
                placeholder='字段代码 (如: wer)'
                {...register(`outputFields.${index}.paramCode`)}
                className='h-8 w-32'
              />
              <Input
                aria-label={`输出显示名 ${index + 1}`}
                placeholder='显示名'
                {...register(`outputFields.${index}.paramName`)}
                className='h-8 w-28'
              />
              <Input
                aria-label={`输出提取路径 ${index + 1}`}
                placeholder='提取路径 (如: data.result.wer)'
                {...register(`outputFields.${index}.fieldPath`)}
                className='h-8 w-40'
              />
              <Select
                value={watch(`outputFields.${index}.fieldType`)}
                onValueChange={(value) =>
                  setValue(`outputFields.${index}.fieldType`, value ?? 'number', {
                    shouldDirty: true,
                  })
                }
              >
                <SelectTrigger size='sm' className='w-24'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OUTPUT_FIELD_TYPE_OPTIONS.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={watch(`outputFields.${index}.outputRole`)}
                onValueChange={(value) =>
                  setValue(`outputFields.${index}.outputRole`, value ?? 'main', {
                    shouldDirty: true,
                  })
                }
              >
                <SelectTrigger size='sm' className='w-24'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OUTPUT_ROLE_OPTIONS.map((role) => (
                    <SelectItem key={role.value} value={role.value}>
                      {role.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={watch(`outputFields.${index}.aggRole`)}
                onValueChange={(value) =>
                  setValue(`outputFields.${index}.aggRole`, value ?? '', {
                    shouldDirty: true,
                  })
                }
              >
                <SelectTrigger size='sm' className='w-32'>
                  <SelectValue>
                    {AGG_ROLE_OPTIONS.find(
                      (o) => o.value === watch(`outputFields.${index}.aggRole`)
                    )?.label ?? ''}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {AGG_ROLE_OPTIONS.map((role) => (
                    <SelectItem key={role.value} value={role.value}>
                      {role.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                aria-label={`输出默认值 ${index + 1}`}
                placeholder='默认值'
                {...register(`outputFields.${index}.defaultValue`)}
                className='h-8 w-20'
              />
              <label className='flex items-center gap-1.5 text-xs'>
                <Checkbox
                  aria-label={`输出报告可见 ${index + 1}`}
                  checked={watch(`outputFields.${index}.visibleInReport`)}
                  onCheckedChange={(checked) =>
                    setValue(
                      `outputFields.${index}.visibleInReport`,
                      !!checked,
                      { shouldDirty: true }
                    )
                  }
                />
                显示
              </label>
              <Input
                aria-label={`输出排序 ${index + 1}`}
                type='number'
                min={0}
                {...register(`outputFields.${index}.uiOrder`, {
                  valueAsNumber: true,
                })}
                className='h-8 w-14'
                title='展示顺序'
              />
              <Button
                type='button'
                variant='ghost'
                size='icon-sm'
                className='text-destructive ml-auto'
                aria-label={`删除输出字段 ${index + 1}`}
                onClick={() => outputs.remove(index)}
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
              </Button>
            </div>
          ))}
        </div>
      </div>

      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='space-y-1.5'>
          <Label required>统计方式</Label>
          <Select
            value={watch('statisticMethod')}
            onValueChange={(value) =>
              setValue('statisticMethod', value ?? 'average', { shouldDirty: true })
            }
          >
            <SelectTrigger className='w-full justify-between'>
              <SelectValue>
                {STATISTIC_METHOD_OPTIONS.find(
                  (o) => o.value === watch('statisticMethod')
                )?.label ?? '简单平均'}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {STATISTIC_METHOD_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className='space-y-1.5'>
          <Label required>聚合分母口径</Label>
          <Select
            value={watch('aggDenominator')}
            onValueChange={(value) =>
              setValue('aggDenominator', value ?? 'case', { shouldDirty: true })
            }
          >
            <SelectTrigger className='w-full justify-between'>
              <SelectValue>
                {AGG_DENOMINATOR_OPTIONS.find(
                  (o) => o.value === watch('aggDenominator')
                )?.label ?? '按用例 (分母=配置该维度的用例数)'}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {AGG_DENOMINATOR_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* 排除轮次（多选） */}
      <div className='space-y-1.5'>
        <Label>排除轮次</Label>
        <div className='flex flex-wrap items-center gap-3'>
          {['1', '2', '3', '4'].map((round) => {
            const checked = watch('excludeRounds').includes(round)
            return (
              <label key={round} className='flex items-center gap-1.5 text-xs'>
                <Checkbox
                  aria-label={`排除第 ${round} 轮`}
                  checked={checked}
                  onCheckedChange={(next) => {
                    const current = watch('excludeRounds')
                    setValue(
                      'excludeRounds',
                      next
                        ? [...current, round]
                        : current.filter((r) => r !== round),
                      { shouldDirty: true }
                    )
                  }}
                />
                第 {round} 轮
              </label>
            )
          })}
          <label className='flex items-center gap-1.5 text-xs'>
            <Checkbox
              aria-label='排除最后一轮'
              checked={watch('excludeRounds').includes('-1')}
              onCheckedChange={(next) => {
                const current = watch('excludeRounds')
                setValue(
                  'excludeRounds',
                  next
                    ? [...current, '-1']
                    : current.filter((r) => r !== '-1'),
                  { shouldDirty: true }
                )
              }}
            />
            最后一轮 (-1)
          </label>
        </div>
      </div>

      {/* API 端点配置 */}
      <div className='space-y-2'>
        <div className='flex items-center justify-between'>
          <p className='text-sm font-medium'>API 端点配置</p>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1.5'
            onClick={() =>
              endpoints.append({
                ...NEW_ENDPOINT_ROW,
                priority: endpoints.fields.length + 1,
              })
            }
          >
            <Plus aria-hidden='true' className='size-3.5' />
            添加端点
          </Button>
        </div>
        <div className='space-y-2'>
          {endpoints.fields.map((row, index) => (
            <div
              key={row.id}
              className='border-border/60 flex flex-wrap items-center gap-2 rounded-lg border px-2 py-1.5'
            >
              <Input
                aria-label={`端点 URL ${index + 1}`}
                placeholder='端点 URL*'
                {...register(`apiEndpoints.${index}.url`)}
                className='h-8 min-w-52 flex-1 font-mono text-xs'
              />
              <Input
                aria-label={`端点名称 ${index + 1}`}
                placeholder='端点名称(可选)'
                {...register(`apiEndpoints.${index}.name`)}
                className='h-8 w-32'
              />
              <Input
                aria-label={`端点优先级 ${index + 1}`}
                type='number'
                min={1}
                max={10}
                {...register(`apiEndpoints.${index}.priority`, {
                  valueAsNumber: true,
                })}
                className='h-8 w-20'
              />
              <Button
                type='button'
                variant='ghost'
                size='icon-sm'
                className='text-destructive ml-auto'
                aria-label={`删除端点 ${index + 1}`}
                onClick={() => endpoints.remove(index)}
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
              </Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
