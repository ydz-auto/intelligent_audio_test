/**
 * 评估维度表单「层级配置」分节（11_用例域.md §5.5 层级配置）。
 * 维度类型*（Select 主/子，默认主）· 所属主维度（Select，仅子维度显示；选项=全部主维度）·
 * 继承提示（Alert info「子维度将自动使用父维度的API配置，无需手动配置」，仅子维度）·
 * 搜索关键词 keywords（Input，仅主维度；帮助「逗号分隔的搜索关键词串」）。
 */
import type { UseFormReturn } from 'react-hook-form'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Info } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Dimension } from '@/domain/models/evaluationDimension'
import { DIMENSION_TYPE_OPTIONS } from '@/features/evaluation/constants'
import type { DimensionFormValues } from '@/features/evaluation/mutate/dimension-form-schema'

export function HierarchySection({
  form,
  mainDimensions,
}: {
  form: UseFormReturn<DimensionFormValues>
  mainDimensions: Dimension[]
}) {
  const { register, watch, setValue, formState } = form
  const dimensionType = watch('dimensionType')
  const parentDimensionId = watch('parentDimensionId')
  const isSub = dimensionType === 'sub'

  return (
    <div className='space-y-3'>
      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='space-y-1.5'>
          <Label required>维度类型</Label>
          <Select
            value={dimensionType}
            onValueChange={(value) => {
              setValue('dimensionType', value as 'main' | 'sub', {
                shouldDirty: true,
              })
              if (value === 'main') {
                setValue('parentDimensionId', '', { shouldDirty: true })
              }
            }}
          >
            <SelectTrigger className='w-full justify-between'>
              <SelectValue placeholder='请选择维度类型' />
            </SelectTrigger>
            <SelectContent>
              {DIMENSION_TYPE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {isSub && (
          <div className='space-y-1.5'>
            <Label required>所属主维度</Label>
            <Select
              value={parentDimensionId}
              onValueChange={(value) =>
                setValue('parentDimensionId', value ?? '', { shouldDirty: true })
              }
            >
              <SelectTrigger
                className='w-full justify-between'
                aria-invalid={Boolean(formState.errors.parentDimensionId)}
              >
                <SelectValue placeholder='请选择所属主维度' />
              </SelectTrigger>
              <SelectContent>
                {mainDimensions.map((dim) => (
                  <SelectItem key={dim.id} value={String(dim.id)}>
                    {dim.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {formState.errors.parentDimensionId && (
              <p className='text-destructive text-xs'>
                {formState.errors.parentDimensionId.message}
              </p>
            )}
          </div>
        )}
      </div>

      {isSub ? (
        <Alert className='items-start gap-2'>
          <Info aria-hidden='true' className='mt-0.5 size-4 shrink-0' />
          <AlertTitle>继承提示</AlertTitle>
          <AlertDescription>
            子维度将自动使用父维度的API配置，无需手动配置
          </AlertDescription>
        </Alert>
      ) : (
        <div className='space-y-1.5'>
          <Label htmlFor='dim-keywords'>搜索关键词</Label>
          <Input
            id='dim-keywords'
            placeholder='如：准确,精度'
            {...register('keywords')}
          />
          <p className='text-muted-foreground text-xs'>
            逗号分隔的搜索关键词串，用于维度列表按关键词搜索
          </p>
        </div>
      )}
    </div>
  )
}
