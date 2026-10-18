/**
 * §6.4 参考参数分节（mutate sheet 第三 Tab）。
 * 说明文案 + 内联可编辑表（参数代码/标注代码/参数名称/参考类型/标注格式/字段路径/合并方式/帮助文本）。
 */
import { Plus, Trash2 } from 'lucide-react'
import type { UseFormReturn } from 'react-hook-form'
import { useFieldArray } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import {
  REFERENCE_PARAMS_DESCRIPTION,
  REFERENCE_PARAM_MERGE_OPTIONS,
  REFERENCE_PARAM_TYPE_OPTIONS,
} from '@/features/algorithm-config/constants'

const ANNOTATION_FORMAT_OPTIONS = [
  { value: '', label: '不指定' },
  { value: 'text', label: '文本' },
  { value: 'json', label: 'JSON' },
  { value: 'rttm', label: 'RTTM' },
  { value: 'stm', label: 'STM' },
  { value: 'boolean', label: '布尔' },
] as const

export function ReferenceParamsSection({
  form,
}: {
  form: UseFormReturn<AlgorithmFormValues>
}) {
  const referenceParams = useFieldArray({
    control: form.control,
    name: 'referenceParams',
  })

  const addEmpty = () =>
    referenceParams.append({
      key: `r-${Date.now()}-${referenceParams.fields.length}`,
      code: '',
      name: '',
      type: 'text',
      annotationCode: '',
      annotationFormat: '',
      fieldPath: '',
      mergeMode: 'join',
      helpText: '',
    })

  return (
    <div className='space-y-3'>
      <p className='text-muted-foreground text-xs'>
        {REFERENCE_PARAMS_DESCRIPTION}
      </p>

      <div className='flex items-center justify-end'>
        <Button variant='outline' size='sm' type='button' onClick={addEmpty}>
          <Plus aria-hidden='true' />
          添加参考字段
        </Button>
      </div>

      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className='w-full min-w-[1000px] text-[13px]'>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>参数代码</th>
                <th className='px-3 py-2 text-left font-medium'>标注代码</th>
                <th className='px-3 py-2 text-left font-medium'>参数名称</th>
                <th className='px-3 py-2 text-left font-medium'>参考类型</th>
                <th className='px-3 py-2 text-left font-medium'>标注格式</th>
                <th className='px-3 py-2 text-left font-medium'>字段路径</th>
                <th className='px-3 py-2 text-left font-medium'>合并方式</th>
                <th className='px-3 py-2 text-left font-medium'>帮助文本</th>
                <th className='w-10 px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {referenceParams.fields.length === 0 ? (
                <tr>
                  <td colSpan={9} className='text-muted-foreground px-3 py-6 text-center'>
                    暂无参考参数，点击「添加参考字段」新增
                  </td>
                </tr>
              ) : (
                referenceParams.fields.map((field, index) => (
                  <tr key={field.key} className='border-border/50 border-b last:border-b-0'>
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='参数代码'
                        placeholder='ref_code'
                        className='h-7 font-mono text-xs'
                        {...form.register(`referenceParams.${index}.code`)}
                      />
                    </td>
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='标注代码'
                        placeholder='标注匹配代码，默认同算法代码'
                        className='h-7 text-xs'
                        {...form.register(`referenceParams.${index}.annotationCode`)}
                      />
                    </td>
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='参数名称'
                        placeholder='如：参考文本'
                        className='h-7 text-xs'
                        {...form.register(`referenceParams.${index}.name`)}
                      />
                    </td>
                    <td className='px-2 py-1.5'>
                      <Select
                        value={form.watch(`referenceParams.${index}.type`)}
                        onValueChange={(value) =>
                          form.setValue(`referenceParams.${index}.type`, value ?? 'text')
                        }
                      >
                        <SelectTrigger size='sm' className='w-24'>
                          <SelectValue>
                            {REFERENCE_PARAM_TYPE_OPTIONS.find(
                              (o) => o.value === form.watch(`referenceParams.${index}.type`)
                            )?.label ?? '文本'}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {REFERENCE_PARAM_TYPE_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className='px-2 py-1.5'>
                      <Select
                        value={form.watch(`referenceParams.${index}.annotationFormat`)}
                        onValueChange={(value) =>
                          form.setValue(`referenceParams.${index}.annotationFormat`, value ?? '')
                        }
                      >
                        <SelectTrigger size='sm' className='w-28'>
                          <SelectValue>
                            {ANNOTATION_FORMAT_OPTIONS.find(
                              (o) =>
                                o.value === form.watch(`referenceParams.${index}.annotationFormat`)
                            )?.label ?? '不指定'}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {ANNOTATION_FORMAT_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='字段路径'
                        placeholder='如：model 或 segments[].emotion'
                        className='h-7 font-mono text-xs'
                        {...form.register(`referenceParams.${index}.fieldPath`)}
                      />
                    </td>
                    <td className='px-2 py-1.5'>
                      <Select
                        value={form.watch(`referenceParams.${index}.mergeMode`)}
                        onValueChange={(value) =>
                          form.setValue(`referenceParams.${index}.mergeMode`, value ?? '')
                        }
                      >
                        <SelectTrigger size='sm' className='w-24'>
                          <SelectValue>
                            {REFERENCE_PARAM_MERGE_OPTIONS.find(
                              (o) => o.value === form.watch(`referenceParams.${index}.mergeMode`)
                            )?.label ?? '未指定'}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {REFERENCE_PARAM_MERGE_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='帮助文本'
                        placeholder='可选提示'
                        className='h-7 text-xs'
                        {...form.register(`referenceParams.${index}.helpText`)}
                      />
                    </td>
                    <td className='px-2 py-1.5'>
                      <div className='flex items-center justify-end'>
                        <Button
                          variant='ghost'
                          size='icon-sm'
                          type='button'
                          aria-label='删除该参考字段'
                          className='text-destructive'
                          onClick={() => referenceParams.remove(index)}
                        >
                          <Trash2 aria-hidden='true' className='size-3.5' />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
