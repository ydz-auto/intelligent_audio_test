/**
 * 评估维度表单「结果配置」分节（11_用例域.md §5.5 结果配置）。
 * 分数单位 · 结果类型*（数值/布尔/文本/LLM Judge）· LLM Judge 配置节（仅 LLM Judge）·
 * 结果最小值* · 结果最大值* · 小数位数*（0-4）· 权重*（1-10）· 预计执行时间(s)*（≥1）·
 * 评分规则（规则编辑器：行=「如果结果 {≥/>/=/</≤} {值} → {得分} 分」+ 添加/删除）。
 */
import { Plus, Trash2 } from 'lucide-react'
import { useFieldArray, type UseFormReturn } from 'react-hook-form'

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
import { Slider } from '@/components/ui/slider'
import { Textarea } from '@/components/ui/textarea'
import { WEIGHT_MAX, WEIGHT_MIN } from '@/features/evaluation/constants'
import type {
  DimensionFormValues,
  RuleRow,
} from '@/features/evaluation/mutate/dimension-form-schema'

const RESULT_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '1', label: '数值' },
  { value: '2', label: '布尔' },
  { value: '3', label: '文本' },
  { value: 'llm_judge', label: 'LLM Judge' },
]

const CONDITION_OPTIONS = ['>=', '>', '=', '<', '<=']

export function ResultSection({
  form,
}: {
  form: UseFormReturn<DimensionFormValues>
}) {
  const { register, watch, setValue, formState, control } = form
  const ruleField = useFieldArray({
    control,
    name: 'rule',
  })
  const resultType = watch('resultType')
  const isLlmJudge = resultType === 'llm_judge'
  const { fields, append, remove } = ruleField

  return (
    <div className='space-y-3'>
      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='space-y-1.5'>
          <Label htmlFor='dim-score-unit'>分数单位</Label>
          <Input
            id='dim-score-unit'
            placeholder='如: %, 分, 秒等'
            {...register('scoreUnit')}
          />
        </div>
        <div className='space-y-1.5'>
          <Label required>结果类型</Label>
          <Select
            value={resultType}
            onValueChange={(value) =>
              setValue('resultType', value as DimensionFormValues['resultType'], {
                shouldDirty: true,
              })
            }
          >
            <SelectTrigger className='w-full justify-between'>
              <SelectValue placeholder='请选择结果类型' />
            </SelectTrigger>
            <SelectContent>
              {RESULT_TYPE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {isLlmJudge && (
        <div className='bg-muted/50 space-y-3 rounded-lg border p-3'>
          <p className='text-sm font-medium'>LLM Judge 配置</p>
          <div className='space-y-1.5'>
            <Label htmlFor='llm-model' required>
              模型
            </Label>
            <Input
              id='llm-model'
              placeholder='如：gpt-4o-mini'
              {...register('llmModel')}
            />
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='llm-prompt' required>
              Prompt 模板
            </Label>
            <Textarea
              id='llm-prompt'
              rows={3}
              placeholder='可使用 {{asr_result}} {{asr_ref}} 等变量'
              {...register('llmPromptTemplate')}
            />
          </div>
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='space-y-1.5'>
              <Label htmlFor='llm-max-tokens' required>
                最大 Token 数
              </Label>
              <Input
                id='llm-max-tokens'
                type='number'
                min={1}
                max={8192}
                {...register('llmMaxTokens', { valueAsNumber: true })}
              />
            </div>
            <div className='space-y-1.5'>
              <Label htmlFor='llm-temperature' required>
                Temperature
              </Label>
              <Input
                id='llm-temperature'
                type='number'
                min={0}
                max={2}
                step={0.1}
                {...register('llmTemperature', { valueAsNumber: true })}
              />
            </div>
          </div>
        </div>
      )}

      <div className='grid gap-3 sm:grid-cols-4'>
        <div className='space-y-1.5'>
          <Label htmlFor='dim-result-min' required>
            结果最小值
          </Label>
          <Input
            id='dim-result-min'
            type='number'
            aria-invalid={Boolean(formState.errors.resultMin)}
            {...register('resultMin', { valueAsNumber: true })}
          />
          {formState.errors.resultMin && (
            <p className='text-destructive text-xs'>
              {formState.errors.resultMin.message}
            </p>
          )}
        </div>
        <div className='space-y-1.5'>
          <Label htmlFor='dim-result-max' required>
            结果最大值
          </Label>
          <Input
            id='dim-result-max'
            type='number'
            aria-invalid={Boolean(formState.errors.resultMax)}
            {...register('resultMax', { valueAsNumber: true })}
          />
          {formState.errors.resultMax && (
            <p className='text-destructive text-xs'>
              {formState.errors.resultMax.message}
            </p>
          )}
        </div>
        <div className='space-y-1.5'>
          <Label htmlFor='dim-decimal-places' required>
            小数位数
          </Label>
          <Input
            id='dim-decimal-places'
            type='number'
            min={0}
            max={4}
            aria-invalid={Boolean(formState.errors.decimalPlaces)}
            {...register('decimalPlaces', { valueAsNumber: true })}
          />
          {formState.errors.decimalPlaces && (
            <p className='text-destructive text-xs'>
              {formState.errors.decimalPlaces.message}
            </p>
          )}
        </div>
        <div className='space-y-1.5'>
          <Label htmlFor='dim-exec-time' required>
            预计执行时间(s)
          </Label>
          <Input
            id='dim-exec-time'
            type='number'
            min={1}
            aria-invalid={Boolean(formState.errors.estimatedExecTime)}
            {...register('estimatedExecTime', { valueAsNumber: true })}
          />
          {formState.errors.estimatedExecTime && (
            <p className='text-destructive text-xs'>
              {formState.errors.estimatedExecTime.message}
            </p>
          )}
        </div>
      </div>

      <div className='space-y-1.5'>
        <Label required>权重</Label>
        <div className='flex items-center gap-3'>
          <Slider
            min={WEIGHT_MIN}
            max={WEIGHT_MAX}
            step={1}
            value={[watch('weight')]}
            onValueChange={(next) =>
              setValue(
                'weight',
                Array.isArray(next) ? (next[0] ?? WEIGHT_MIN) : next,
                { shouldDirty: true }
              )
            }
            className='w-48'
          />
          <span className='tabular-nums'>{watch('weight')}</span>
        </div>
        {formState.errors.weight && (
          <p className='text-destructive text-xs'>
            {formState.errors.weight.message}
          </p>
        )}
      </div>

      {/* 评分规则编辑器 */}
      <div className='space-y-2'>
        <div className='flex items-center justify-between'>
          <Label required>评分规则</Label>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1.5'
            onClick={() =>
              append({ condition: '>=', value: 0, score: 0 } as RuleRow)
            }
          >
            <Plus aria-hidden='true' className='size-3.5' />
            添加规则
          </Button>
        </div>
        <p className='text-muted-foreground text-xs'>
          配置评分规则：根据结果值区间映射得分
        </p>
        <div className='space-y-2'>
          {fields.map((field, index) => (
            <div
              key={field.id}
              className='border-border/60 flex items-center gap-2 rounded-lg border px-2 py-1.5'
            >
              <span className='text-muted-foreground shrink-0 text-xs'>
                如果结果
              </span>
              <Select
                value={watch(`rule.${index}.condition`)}
                onValueChange={(value) =>
                  setValue(`rule.${index}.condition`, value ?? '>=', {
                    shouldDirty: true,
                  })
                }
              >
                <SelectTrigger size='sm' className='w-20'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONDITION_OPTIONS.map((condition) => (
                    <SelectItem key={condition} value={condition}>
                      {condition}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                aria-label={`规则 ${index + 1} 阈值`}
                type='number'
                className='h-8 w-24'
                {...register(`rule.${index}.value`, { valueAsNumber: true })}
              />
              <span className='text-muted-foreground shrink-0 text-xs'>
                →
              </span>
              <span className='text-muted-foreground shrink-0 text-xs'>
                {watch(`rule.${index}.score`)} 分
              </span>
              <Input
                aria-label={`规则 ${index + 1} 得分`}
                type='number'
                className='h-8 w-20'
                {...register(`rule.${index}.score`, { valueAsNumber: true })}
              />
              <Button
                type='button'
                variant='ghost'
                size='icon-sm'
                className='text-destructive ml-auto'
                aria-label={`删除规则 ${index + 1}`}
                disabled={fields.length <= 1}
                onClick={() => remove(index)}
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
              </Button>
            </div>
          ))}
        </div>
        {formState.errors.rule && (
          <p className='text-destructive text-xs'>
            {formState.errors.rule.message}
          </p>
        )}
      </div>
    </div>
  )
}
