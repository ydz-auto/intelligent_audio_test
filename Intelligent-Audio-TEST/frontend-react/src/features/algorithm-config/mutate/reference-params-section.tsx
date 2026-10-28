/**
 * §6.4 参考参数分节（mutate sheet 第三 Tab）。
 * 说明文案 + 筛选行（搜索/类型/合并方式）+ 内联可编辑表（参数代码/标注代码/参数名称/参考类型/标注格式/字段路径/合并方式/帮助文本）。
 */
import { Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
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
import { AnnotationCodeSelect, type AlgorithmOption } from './annotation-code-select'
import { CONTAINED_TABLE_CLASS } from './table-containment'
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
  algorithmOptions,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  /** 算法列表（标注代码下拉选项：标注代码=算法类型） */
  algorithmOptions: AlgorithmOption[]
}) {
  const referenceParams = useFieldArray({
    control: form.control,
    name: 'referenceParams',
  })

  // 筛选行状态（§6.4：搜索/类型/合并方式，照 V9.7.10 filteredReferenceParams）
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [mergeFilter, setMergeFilter] = useState('all')

  const watchReferenceParams = form.watch('referenceParams')

  // 仅显示过滤命中行的「原始数组下标」（RHF 注册/取值必须用原下标，与 params-table 同模式）
  const filteredIndices = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return referenceParams.fields
      .map((_, index) => index)
      .filter((index) => {
        const row = watchReferenceParams[index]
        if (!row) return false
        if (kw) {
          const haystack = [row.code, row.annotationCode, row.name, row.fieldPath, row.helpText]
            .join(' ')
            .toLowerCase()
          if (!haystack.includes(kw)) return false
        }
        if (typeFilter !== 'all' && row.type !== typeFilter) return false
        if (mergeFilter !== 'all' && row.mergeMode !== mergeFilter) return false
        return true
      })
  }, [search, typeFilter, mergeFilter, referenceParams.fields, watchReferenceParams])

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

      {/* 筛选行（搜索/类型/合并方式 + 添加参考字段，§6.4；样式照 params-table） */}
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          aria-label='搜索参考参数'
          placeholder='搜索参考参数...'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className='h-7 w-44 text-xs'
        />
        <Select value={typeFilter} onValueChange={(value) => setTypeFilter(value ?? 'all')}>
          <SelectTrigger size='sm' className='w-28' aria-label='按类型筛选'>
            <SelectValue>
              {typeFilter === 'all'
                ? '全部类型'
                : (REFERENCE_PARAM_TYPE_OPTIONS.find((o) => o.value === typeFilter)?.label ??
                    '全部类型')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>全部类型</SelectItem>
            {REFERENCE_PARAM_TYPE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={mergeFilter} onValueChange={(value) => setMergeFilter(value ?? 'all')}>
          <SelectTrigger size='sm' className='w-28' aria-label='按合并方式筛选'>
            <SelectValue>
              {mergeFilter === 'all'
                ? '全部合并'
                : (REFERENCE_PARAM_MERGE_OPTIONS.find((o) => o.value === mergeFilter)?.label ??
                    '全部合并')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>全部合并</SelectItem>
            {REFERENCE_PARAM_MERGE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className='ml-auto'>
          <Button variant='outline' size='sm' type='button' onClick={addEmpty}>
            <Plus aria-hidden='true' />
            添加参考字段
          </Button>
        </div>
      </div>

      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className={`w-full min-w-[1000px] text-[13px] ${CONTAINED_TABLE_CLASS}`}>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>参数代码</th>
                <th
                  title='标注代码=算法类型代码；默认同本算法，选其它算法表示复用该算法的标注'
                  className='px-3 py-2 text-left font-medium'
                >
                  标注代码
                </th>
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
              ) : filteredIndices.length === 0 ? (
                <tr>
                  <td colSpan={9} className='text-muted-foreground px-3 py-6 text-center'>
                    未找到匹配参考参数，换个关键词或筛选条件试试
                  </td>
                </tr>
              ) : (
                filteredIndices.map((index) => (
                  <tr
                    key={referenceParams.fields[index].key}
                    className='border-border/50 border-b last:border-b-0'
                  >
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='参数代码'
                        placeholder='ref_code'
                        className='h-7 font-mono text-xs'
                        {...form.register(`referenceParams.${index}.code`)}
                      />
                    </td>
                    <td className='px-2 py-1.5'>
                      <AnnotationCodeSelect
                        value={form.watch(`referenceParams.${index}.annotationCode`) ?? ''}
                        onValueChange={(value) =>
                          form.setValue(`referenceParams.${index}.annotationCode`, value)
                        }
                        algorithmOptions={algorithmOptions}
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
