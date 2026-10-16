/**
 * §6.3 参数配置分节（mutate sheet 第二 Tab）。
 * 内层 Tabs 设备参数/API参数/用例参数 + useFieldArray 受控行内联编辑；
 * 用例参数页签含「功能特性快捷开关」（chips 勾选自动批量添加/删除对应参数）。
 */
import { Plus, Trash2 } from 'lucide-react'
import {
  type UseFieldArrayReturn,
  type UseFormReturn,
  useFieldArray,
} from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import {
  CASE_PARAM_SCOPE_OPTIONS,
  CASE_PARAM_TYPE_OPTIONS,
  DEVICE_PARAM_TYPE_OPTIONS,
  FEATURE_BUNDLES_HINT,
  PARAM_DIRECTION_OPTIONS,
} from '@/features/algorithm-config/constants'
import { MOCK_CASE_PARAM_CODE_PRESETS, MOCK_FEATURE_BUNDLES } from '@/infrastructure/mock/algorithm-config-mock'

const PRESET_DATALIST_ID = 'case-param-code-presets'

export function ParamsSection({
  form,
}: {
  form: UseFormReturn<AlgorithmFormValues>
}) {
  const device = useFieldArray({ control: form.control, name: 'deviceParams' })
  const api = useFieldArray({ control: form.control, name: 'apiParams' })
  const cases = useFieldArray({ control: form.control, name: 'caseParams' })

  return (
    <div className='space-y-3'>
      <Tabs defaultValue='device'>
        <TabsList variant='line' className='w-full justify-start'>
          <TabsTrigger value='device'>设备参数（{device.fields.length}）</TabsTrigger>
          <TabsTrigger value='api'>API参数（{api.fields.length}）</TabsTrigger>
          <TabsTrigger value='case'>用例参数（{cases.fields.length}）</TabsTrigger>
        </TabsList>

        <TabsContent value='device' className='pt-3'>
          <DeviceApiParamTable
            form={form}
            fieldArray={device}
            arrayName='deviceParams'
            addEmpty={() =>
              device.append({
                key: `d-${Date.now()}-${device.fields.length}`,
                paramCode: '',
                paramName: '',
                direction: 'input',
                paramType: 'text',
                required: false,
                helpText: '',
              })
            }
          />
        </TabsContent>

        <TabsContent value='api' className='pt-3'>
          <DeviceApiParamTable
            form={form}
            fieldArray={api}
            arrayName='apiParams'
            addEmpty={() =>
              api.append({
                key: `a-${Date.now()}-${api.fields.length}`,
                paramCode: '',
                paramName: '',
                direction: 'input',
                paramType: 'text',
                required: false,
                helpText: '',
              })
            }
          />
        </TabsContent>

        <TabsContent value='case' className='pt-3'>
          <FeatureBundles form={form} cases={cases} />
          <CaseParamTable form={form} cases={cases} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

/* ───────────────────────── 功能特性快捷开关（§6.3 用例参数页签） ───────────────────────── */

function FeatureBundles({
  form,
  cases,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  cases: UseFieldArrayReturn<AlgorithmFormValues, 'caseParams'>
}) {
  const watchParams = form.watch('caseParams')

  const isActive = (bundleParams: string[]) =>
    bundleParams.every((code) =>
      watchParams.some((param) => param.paramCode === code)
    )

  const toggleBundle = (bundleParams: string[]) => {
    const active = isActive(bundleParams)
    const current = watchParams.map((param) => param.paramCode)
    if (active) {
      // 取消：移除 bundle 参数行（照「勾选自动批量添加/删除」语义）
      cases.remove(
        watchParams
          .map((param, index) => (bundleParams.includes(param.paramCode) ? index : -1))
          .filter((index) => index >= 0)
      )
    } else {
      // 勾选：补齐缺失的 bundle 参数行
      bundleParams.forEach((code) => {
        if (current.includes(code)) return
        cases.append({
          key: `c-${Date.now()}-${Math.random()}`,
          paramCode: code,
          paramName: '',
          paramType: 'text',
          scope: 'common',
          required: false,
          defaultValue: '',
          minValue: '',
          maxValue: '',
          step: '',
          unit: '',
          annotationCode: '',
          fieldPath: '',
          helpText: '',
        })
      })
    }
  }

  return (
    <div className='mb-3'>
      <p className='mb-1.5 text-xs'>{FEATURE_BUNDLES_HINT}</p>
      <div className='flex flex-wrap gap-1.5'>
        {MOCK_FEATURE_BUNDLES.map((bundle) => {
          const active = isActive(bundle.params)
          return (
            <label
              key={bundle.key}
              className='hover:bg-accent inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-background px-3 text-xs transition-colors has-data-[slot=checkbox]:bg-primary/10 has-[[data-checked=true]]:border-primary/40'
            >
              <Checkbox
                checked={active}
                onCheckedChange={() => toggleBundle(bundle.params)}
                aria-label={`功能特性 ${bundle.label}`}
              />
              {bundle.label} {bundle.params.length} 个参数
            </label>
          )
        })}
      </div>
    </div>
  )
}

/* ───────────────────────── 设备/API 参数表（§6.3） ───────────────────────── */

function DeviceApiParamTable({
  form,
  fieldArray,
  arrayName,
  addEmpty,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  fieldArray: UseFieldArrayReturn<AlgorithmFormValues, 'deviceParams' | 'apiParams'>
  arrayName: 'deviceParams' | 'apiParams'
  addEmpty: () => void
}) {
  const errors = form.formState.errors

  return (
    <div className='space-y-2'>
      <div className='flex items-center justify-end'>
        <Button variant='outline' size='sm' type='button' onClick={addEmpty}>
          <Plus aria-hidden='true' />
          添加参数
        </Button>
      </div>
      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className='w-full min-w-[760px] text-[13px]'>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>参数代码*</th>
                <th className='px-3 py-2 text-left font-medium'>参数名称</th>
                <th className='px-3 py-2 text-left font-medium'>方向</th>
                <th className='px-3 py-2 text-left font-medium'>类型</th>
                <th className='px-3 py-2 text-center font-medium'>必填</th>
                <th className='px-3 py-2 text-left font-medium'>帮助文本</th>
                <th className='w-10 px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {fieldArray.fields.length === 0 ? (
                <tr>
                  <td colSpan={7} className='text-muted-foreground px-3 py-6 text-center'>
                    暂无参数，点击「添加参数」新增
                  </td>
                </tr>
              ) : (
                fieldArray.fields.map((field, index) => (
                  <tr key={field.key} className='border-border/50 border-b last:border-b-0'>
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='参数代码'
                        placeholder='param_code'
                        className='h-7 font-mono text-xs'
                        aria-invalid={Boolean(errors[arrayName]?.[index]?.paramCode)}
                        {...form.register(`${arrayName}.${index}.paramCode`)}
                      />
                      {errors[arrayName]?.[index]?.paramCode && (
                        <p className='text-destructive text-xs'>
                          {errors[arrayName]?.[index]?.paramCode?.message}
                        </p>
                      )}
                    </td>
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='参数名称'
                        placeholder='如：输入音频'
                        className='h-7 text-xs'
                        {...form.register(`${arrayName}.${index}.paramName`)}
                      />
                    </td>
                    <td className='px-2 py-1.5'>
                      <Select
                        value={form.watch(`${arrayName}.${index}.direction`)}
                        onValueChange={(value) =>
                          form.setValue(
                            `${arrayName}.${index}.direction`,
                            (value ?? 'input') as 'input' | 'output'
                          )
                        }
                      >
                        <SelectTrigger size='sm' className='w-24'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {PARAM_DIRECTION_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className='px-2 py-1.5'>
                      <Select
                        value={form.watch(`${arrayName}.${index}.paramType`)}
                        onValueChange={(value) =>
                          form.setValue(`${arrayName}.${index}.paramType`, value ?? 'text')
                        }
                      >
                        <SelectTrigger size='sm' className='w-32'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {DEVICE_PARAM_TYPE_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className='px-2 py-1.5 text-center'>
                      <span className='inline-flex items-center justify-center'>
                        <Checkbox
                          aria-label={`必填 ${String(form.watch(`${arrayName}.${index}.paramName`) ?? '')}`}
                          checked={form.watch(`${arrayName}.${index}.required`)}
                          onCheckedChange={(checked) =>
                            form.setValue(`${arrayName}.${index}.required`, Boolean(checked))
                          }
                        />
                      </span>
                    </td>
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='帮助文本'
                        placeholder='可选'
                        className='h-7 text-xs'
                        {...form.register(`${arrayName}.${index}.helpText`)}
                      />
                    </td>
                    <td className='px-2 py-1.5'>
                      <div className='flex items-center justify-end'>
                        <Button
                          variant='ghost'
                          size='icon-sm'
                          type='button'
                          aria-label='删除该参数'
                          className='text-destructive'
                          onClick={() => fieldArray.remove(index)}
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

/* ───────────────────────── 用例参数表（§6.3） ───────────────────────── */

function CaseParamTable({
  form,
  cases,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  cases: UseFieldArrayReturn<AlgorithmFormValues, 'caseParams'>
}) {
  const errors = form.formState.errors

  return (
    <div className='space-y-2'>
      <datalist id={PRESET_DATALIST_ID}>
        {MOCK_CASE_PARAM_CODE_PRESETS.map((code) => (
          <option key={code} value={code} />
        ))}
      </datalist>

      <div className='flex items-center justify-end'>
        <Button
          variant='outline'
          size='sm'
          type='button'
          onClick={() =>
            cases.append({
              key: `c-${Date.now()}-${cases.fields.length}`,
              paramCode: '',
              paramName: '',
              paramType: 'text',
              scope: 'common',
              required: false,
              defaultValue: '',
              minValue: '',
              maxValue: '',
              step: '',
              unit: '',
              annotationCode: '',
              fieldPath: '',
              helpText: '',
            })
          }
        >
          <Plus aria-hidden='true' />
          添加参数
        </Button>
      </div>

      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className='w-full min-w-[1080px] text-[13px]'>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>参数代码*</th>
                <th className='px-3 py-2 text-left font-medium'>参数名称</th>
                <th className='px-3 py-2 text-left font-medium'>类型</th>
                <th className='px-3 py-2 text-left font-medium'>适用范围</th>
                <th className='px-3 py-2 text-center font-medium'>必填</th>
                <th className='px-3 py-2 text-left font-medium'>默认值</th>
                <th className='px-3 py-2 text-left font-medium'>范围约束</th>
                <th className='px-3 py-2 text-left font-medium'>标注代码</th>
                <th className='px-3 py-2 text-left font-medium'>字段路径</th>
                <th className='w-10 px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {cases.fields.length === 0 ? (
                <tr>
                  <td colSpan={10} className='text-muted-foreground px-3 py-6 text-center'>
                    暂无参数，点击「添加参数」或勾选上方功能特性快捷添加
                  </td>
                </tr>
              ) : (
                cases.fields.map((field, index) => {
                  const paramType = form.watch(`caseParams.${index}.paramType`)
                  const showRange = paramType === 'number' || paramType === 'slider'
                  return (
                    <tr key={field.key} className='border-border/50 border-b last:border-b-0'>
                      <td className='px-2 py-1.5'>
                        <Input
                          aria-label='参数代码'
                          placeholder='param_code'
                          list={PRESET_DATALIST_ID}
                          className='h-7 font-mono text-xs'
                          aria-invalid={Boolean(errors.caseParams?.[index]?.paramCode)}
                          {...form.register(`caseParams.${index}.paramCode`)}
                        />
                        {errors.caseParams?.[index]?.paramCode && (
                          <p className='text-destructive text-xs'>
                            {errors.caseParams?.[index]?.paramCode?.message}
                          </p>
                        )}
                      </td>
                      <td className='px-2 py-1.5'>
                        <Input
                          aria-label='参数名称'
                          placeholder='如：源语言'
                          className='h-7 text-xs'
                          {...form.register(`caseParams.${index}.paramName`)}
                        />
                      </td>
                      <td className='px-2 py-1.5'>
                        <Select
                          value={paramType}
                          onValueChange={(value) =>
                            form.setValue(`caseParams.${index}.paramType`, value ?? 'text')
                          }
                        >
                          <SelectTrigger size='sm' className='w-28'>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {CASE_PARAM_TYPE_OPTIONS.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </td>
                      <td className='px-2 py-1.5'>
                        <Select
                          value={form.watch(`caseParams.${index}.scope`)}
                          onValueChange={(value) =>
                            form.setValue(
                              `caseParams.${index}.scope`,
                              (value ?? 'common') as 'common' | 'api' | 'e2e'
                            )
                          }
                        >
                          <SelectTrigger size='sm' className='w-20'>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {CASE_PARAM_SCOPE_OPTIONS.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </td>
                      <td className='px-2 py-1.5 text-center'>
                        <span className='inline-flex items-center justify-center'>
                          <Checkbox
                            aria-label={`必填 ${form.watch(`caseParams.${index}.paramName`) ?? ''}`}
                            checked={form.watch(`caseParams.${index}.required`)}
                            onCheckedChange={(checked) =>
                              form.setValue(`caseParams.${index}.required`, Boolean(checked))
                            }
                          />
                        </span>
                      </td>
                      <td className='px-2 py-1.5'>
                        <Input
                          aria-label='默认值'
                          placeholder='如：zh'
                          className='h-7 font-mono text-xs'
                          {...form.register(`caseParams.${index}.defaultValue`)}
                        />
                      </td>
                      <td className='px-2 py-1.5'>
                        {showRange ? (
                          <div className='flex items-center gap-1'>
                            <Input
                              aria-label='最小值'
                              placeholder='min'
                              className='h-7 w-14 font-mono text-xs'
                              {...form.register(`caseParams.${index}.minValue`)}
                            />
                            <span className='text-muted-foreground text-xs'>~</span>
                            <Input
                              aria-label='最大值'
                              placeholder='max'
                              className='h-7 w-14 font-mono text-xs'
                              {...form.register(`caseParams.${index}.maxValue`)}
                            />
                            <Input
                              aria-label='步长'
                              placeholder='step'
                              className='h-7 w-14 font-mono text-xs'
                              {...form.register(`caseParams.${index}.step`)}
                            />
                            <Input
                              aria-label='单位'
                              placeholder='单位'
                              className='h-7 w-14 text-xs'
                              {...form.register(`caseParams.${index}.unit`)}
                            />
                          </div>
                        ) : (
                          <span className='text-muted-foreground text-xs'>—</span>
                        )}
                      </td>
                      <td className='px-2 py-1.5'>
                        <Input
                          aria-label='标注代码'
                          placeholder='默认同算法类型'
                          className='h-7 text-xs'
                          {...form.register(`caseParams.${index}.annotationCode`)}
                        />
                      </td>
                      <td className='px-2 py-1.5'>
                        <Input
                          aria-label='字段路径'
                          placeholder='默认同参数代码'
                          className='h-7 font-mono text-xs'
                          {...form.register(`caseParams.${index}.fieldPath`)}
                        />
                      </td>
                      <td className='px-2 py-1.5'>
                        <div className='flex items-center justify-end'>
                          <Button
                            variant='ghost'
                            size='icon-sm'
                            type='button'
                            aria-label='删除该参数'
                            className='text-destructive'
                            onClick={() => cases.remove(index)}
                          >
                            <Trash2 aria-hidden='true' className='size-3.5' />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
