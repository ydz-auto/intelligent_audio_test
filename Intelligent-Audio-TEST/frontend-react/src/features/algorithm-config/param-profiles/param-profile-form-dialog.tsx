/**
 * 参数策略新建 / 编辑对话框（features/algorithm-config/param-profiles；T4.3）。
 *
 * 表单结构对齐 evaluation/mutate/api-section.tsx：
 * 基础信息（作用域 / 算法类型 / 名称 / 状态 / 描述）+ 输入参数字段 + 输出参数字段 + 映射，
 * 三组行编辑器统一走 RHF `useFieldArray`，整份随表单提交。
 *
 * 提交口径（POST /algorithm/param-profiles 或 PUT /{id}）：
 * params = 输入行（direction=input）+ 输出行（direction=output）；mappings 保留每行的来源与方向。
 *
 * 整份保存纪律（INT-2267）：后端 `_sync_params` / `_sync_mappings` 按自然键整份同步，
 * 请求里没带的列会被写成默认值。因此凡表单不展示的字段（label / validation_rules /
 * config 快照）一律按详情读到的原值透传，不用常量兜底。
 * 作用域由入口给定：本入口只编辑 scope=api 的策略，设备策略走设备侧。
 */
import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useFieldArray, useForm, type UseFormRegisterReturn } from 'react-hook-form'
import { toast } from 'sonner'

import { useParamProfileDetail, useParamProfileMutations } from '@/application/algorithm-config/useParamProfiles'
import { useTestAlgorithmOptions } from '@/application/test-execution/useTestAlgorithmOptions'
import {
  PARAM_PROFILE_SCOPE_LABEL,
  type ApiConfigSnapshot,
  type ParamDirection,
  type ParamProfile,
  type ParamProfileInput,
  type ParamProfileMappingDraft,
  type ParamProfileMappingSource,
  type ParamProfileParamDraft,
  type ParamProfileScope,
  type ParamProfileStatus,
  type ParamTransformType,
  type ParamType,
} from '@/domain/models/paramProfile'
import { ApiError } from '@/infrastructure/api/api-error'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import { Textarea } from '@/components/ui/textarea'
import {
  PARAM_DIRECTION_OPTIONS,
  PARAM_MAPPING_SOURCE_OPTIONS,
  PARAM_PROFILE_STATUS_OPTIONS,
  PARAM_TYPE_OPTIONS,
  TRANSFORM_TYPE_OPTIONS,
} from '@/features/algorithm-config/param-profiles/constants'

interface ParamRowValues {
  paramCode: string
  paramName: string
  paramType: ParamType
  uiOrder: number
  fieldPath: string
  required: boolean
  defaultValue: string
  helpText: string
  hidden: boolean
  /** 不在表单展示，编辑既有策略时按原值透传（否则后端整份同步会清空） */
  label: string | null
  validationRules: string | null
}

interface MappingRowValues {
  source: ParamProfileMappingSource
  sourceDirection: ParamDirection
  sourceParam: string
  targetParam: string
  dimensionId: string
  transformType: ParamTransformType
}

interface ParamProfileFormValues {
  scope: ParamProfileScope
  algorithmType: string
  name: string
  description: string
  status: ParamProfileStatus
  /** API 配置快照：不在表单展示，编辑时按详情原值透传 */
  config: ApiConfigSnapshot | null
  inputParams: ParamRowValues[]
  outputParams: ParamRowValues[]
  mappings: MappingRowValues[]
}

function emptyParamRow(uiOrder: number): ParamRowValues {
  return {
    paramCode: '',
    paramName: '',
    paramType: 'text',
    uiOrder,
    fieldPath: '',
    required: false,
    defaultValue: '',
    helpText: '',
    hidden: false,
    label: null,
    validationRules: null,
  }
}

function emptyValues(algorithmType: string, scope: ParamProfileScope): ParamProfileFormValues {
  return {
    scope,
    algorithmType,
    name: '',
    description: '',
    status: 'online',
    config: null,
    inputParams: [emptyParamRow(1)],
    outputParams: [],
    mappings: [],
  }
}

function valuesOf(profile: ParamProfile): ParamProfileFormValues {
  const toRow = (param: ParamProfile['params'][number], index: number): ParamRowValues => ({
    paramCode: param.paramCode,
    paramName: param.paramName ?? '',
    paramType: param.paramType,
    uiOrder: param.uiOrder ?? index + 1,
    fieldPath: param.fieldPath ?? '',
    required: param.required,
    defaultValue: param.defaultValue ?? '',
    helpText: param.helpText ?? '',
    hidden: param.hidden,
    label: param.label,
    validationRules: param.validationRules,
  })
  return {
    scope: profile.scope,
    algorithmType: profile.algorithmType,
    name: profile.name,
    description: profile.description ?? '',
    status: profile.status,
    config: profile.config,
    inputParams: profile.params
      .filter((param) => param.direction === 'input')
      .map(toRow),
    outputParams: profile.params
      .filter((param) => param.direction === 'output')
      .map(toRow),
    mappings: profile.mappings.map((mapping) => ({
      source: mapping.source,
      sourceDirection: mapping.sourceDirection,
      sourceParam: mapping.sourceParam,
      targetParam: mapping.targetParam,
      dimensionId: mapping.dimensionId == null ? '' : String(mapping.dimensionId),
      transformType: mapping.transformType,
    })),
  }
}

function paramDraftsOf(rows: ParamRowValues[], direction: ParamDirection): ParamProfileParamDraft[] {
  return rows
    .filter((row) => row.paramCode.trim())
    .map((row) => ({
      paramCode: row.paramCode.trim(),
      paramName: row.paramName.trim() || null,
      paramType: row.paramType,
      direction,
      required: row.required,
      defaultValue: row.defaultValue.trim() === '' ? null : row.defaultValue,
      helpText: row.helpText.trim() === '' ? null : row.helpText,
      uiOrder: Number(row.uiOrder) || 0,
      hidden: row.hidden,
      fieldPath: row.fieldPath.trim() || null,
      label: row.label,
      validationRules: row.validationRules,
    }))
}

function mappingDraftsOf(rows: MappingRowValues[]): ParamProfileMappingDraft[] {
  return rows
    .filter((row) => row.sourceParam.trim() && row.targetParam.trim())
    .map((row) => ({
      source: row.source,
      sourceDirection: row.sourceDirection,
      sourceParam: row.sourceParam.trim(),
      targetParam: row.targetParam.trim(),
      dimensionId: row.dimensionId.trim() === '' ? null : Number(row.dimensionId),
      transformType: row.transformType,
    }))
}

function toInput(values: ParamProfileFormValues): ParamProfileInput {
  return {
    scope: values.scope,
    algorithmType: values.algorithmType,
    name: values.name.trim(),
    description: values.description.trim() || null,
    status: values.status,
    config: values.config,
    params: [
      ...paramDraftsOf(values.inputParams, 'input'),
      ...paramDraftsOf(values.outputParams, 'output'),
    ],
    mappings: mappingDraftsOf(values.mappings),
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.userMessage
  return error instanceof Error && error.message ? error.message : '保存失败，请重试'
}

export interface ParamProfileFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'create' | 'edit'
  profileId: number | null
  defaultAlgorithmType: string
  /** 本入口的作用域：新建时写死为该值；编辑时以详情为准（后端不接受改作用域） */
  scope?: ParamProfileScope
}

export function ParamProfileFormDialog({
  open,
  onOpenChange,
  mode,
  profileId,
  defaultAlgorithmType,
  scope = 'api',
}: ParamProfileFormDialogProps) {
  const detail = useParamProfileDetail(profileId, open && mode === 'edit')
  const { save } = useParamProfileMutations()
  const algorithmsQuery = useTestAlgorithmOptions()
  const appliedRef = useRef<number | null>(null)

  const form = useForm<ParamProfileFormValues>({
    defaultValues: emptyValues(defaultAlgorithmType, scope),
  })
  const { register, watch, setValue, reset, formState, setError } = form
  const inputs = useFieldArray({ control: form.control, name: 'inputParams' })
  const outputs = useFieldArray({ control: form.control, name: 'outputParams' })
  const mappings = useFieldArray({ control: form.control, name: 'mappings' })

  useEffect(() => {
    if (!open) {
      appliedRef.current = null
      return
    }
    if (mode === 'create') {
      if (appliedRef.current === 0) return
      appliedRef.current = 0
      reset(emptyValues(defaultAlgorithmType, scope))
      return
    }
    if (!detail.profile) return
    if (appliedRef.current === detail.profile.id) return
    appliedRef.current = detail.profile.id
    reset(valuesOf(detail.profile))
  }, [open, mode, defaultAlgorithmType, scope, detail.profile, reset])

  const algorithmOptions = [
    ...(algorithmsQuery.data ?? []).map((item) => ({
      value: item.id,
      label: item.name,
    })),
  ]

  const onSubmit = form.handleSubmit(async (values) => {
    if (!values.algorithmType) {
      setError('algorithmType', { message: '请选择算法类型' })
      return
    }
    try {
      await save.mutateAsync({
        profileId: mode === 'edit' ? profileId : null,
        input: toInput(values),
      })
      toast.success(mode === 'edit' ? '参数策略已更新' : '参数策略已创建')
      onOpenChange(false)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='max-h-[85vh] overflow-y-auto sm:max-w-4xl'>
        <DialogHeader>
          <DialogTitle>{mode === 'edit' ? '编辑参数策略' : '新建参数策略'}</DialogTitle>
          <DialogDescription>
            策略可被多个 API 实例绑定；解析优先级为 实例覆盖 &gt; 策略 &gt; 空。
          </DialogDescription>
        </DialogHeader>

        {mode === 'edit' && detail.isLoading ? (
          <div className='text-muted-foreground flex items-center justify-center gap-2 py-10 text-xs'>
            <Spinner className='size-4' />
            正在读取策略详情…
          </div>
        ) : (
          <form onSubmit={onSubmit} className='space-y-4'>
            <div className='grid gap-3 sm:grid-cols-2'>
              <div className='space-y-1.5'>
                <Label htmlFor='profile-name' required>
                  策略名称
                </Label>
                <Input
                  id='profile-name'
                  maxLength={100}
                  placeholder='请输入策略名称'
                  {...register('name', { required: '请输入策略名称' })}
                />
                {formState.errors.name && (
                  <p className='text-destructive text-xs'>{formState.errors.name.message}</p>
                )}
              </div>
              <div className='space-y-1.5'>
                <Label required>算法类型</Label>
                <Select
                  value={watch('algorithmType')}
                  items={algorithmOptions}
                  onValueChange={(value) =>
                    setValue('algorithmType', value ?? '', { shouldDirty: true })
                  }
                  disabled={mode === 'edit'}
                >
                  <SelectTrigger className='w-full justify-between'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {algorithmOptions.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {formState.errors.algorithmType && (
                  <p className='text-destructive text-xs'>请选择算法类型</p>
                )}
              </div>
              <div className='space-y-1.5'>
                <Label>作用域</Label>
                <div className='border-border/60 bg-muted/30 flex h-8 items-center gap-2 rounded-lg border px-2.5'>
                  <Badge variant='secondary'>{PARAM_PROFILE_SCOPE_LABEL[watch('scope')]}</Badge>
                  <span className='text-muted-foreground text-xs'>
                    由入口决定，设备策略在设备侧编辑
                  </span>
                </div>
              </div>
              <div className='space-y-1.5'>
                <Label required>状态</Label>
                <Select
                  value={watch('status')}
                  items={PARAM_PROFILE_STATUS_OPTIONS}
                  onValueChange={(value) =>
                    setValue('status', value as ParamProfileStatus, { shouldDirty: true })
                  }
                >
                  <SelectTrigger className='w-full justify-between'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PARAM_PROFILE_STATUS_OPTIONS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='space-y-1.5 sm:col-span-2'>
                <Label htmlFor='profile-description'>描述</Label>
                <Textarea
                  id='profile-description'
                  rows={2}
                  placeholder='可选：说明字段来源 / 适用场景'
                  {...register('description')}
                />
              </div>
            </div>

            <ParamRowsEditor
              title='输入参数字段'
              rows={watch('inputParams')}
              showFieldPath={false}
              onAdd={() =>
                inputs.append(emptyParamRow(watch('inputParams').length + 1))
              }
              onRemove={inputs.remove}
              onParamTypeChange={(index, value) =>
                setValue(`inputParams.${index}.paramType`, value, { shouldDirty: true })
              }
              onCheckChange={(index, key, checked) =>
                setValue(`inputParams.${index}.${key}`, checked, { shouldDirty: true })
              }
              registerPath={(index, key) =>
                register(`inputParams.${index}.${key}` as const)
              }
            />

            <ParamRowsEditor
              title='输出参数字段'
              rows={watch('outputParams')}
              showFieldPath
              onAdd={() =>
                outputs.append(emptyParamRow(watch('outputParams').length + 1))
              }
              onRemove={outputs.remove}
              onParamTypeChange={(index, value) =>
                setValue(`outputParams.${index}.paramType`, value, { shouldDirty: true })
              }
              onCheckChange={(index, key, checked) =>
                setValue(`outputParams.${index}.${key}`, checked, { shouldDirty: true })
              }
              registerPath={(index, key) =>
                register(`outputParams.${index}.${key}` as const)
              }
            />

            {/* 映射行编辑器 */}
            <div className='space-y-1.5'>
              <div className='flex items-center justify-between'>
                <Label>映射</Label>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='h-7 gap-1 text-xs'
                  onClick={() =>
                    mappings.append({
                      source: 'api',
                      sourceDirection: 'output',
                      sourceParam: '',
                      targetParam: '',
                      dimensionId: '',
                      transformType: 'none',
                    })
                  }
                >
                  <Plus aria-hidden='true' className='size-3.5' />
                  新增映射
                </Button>
              </div>
              {watch('mappings').length === 0 ? (
                <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
                  无映射行；新增时来源默认 API 输出，可改为用例参数 / 设备输出。
                </p>
              ) : (
                <div className='space-y-2'>
                  {watch('mappings').map((row, index) => (
                    <div key={index} className='flex flex-wrap items-end gap-2'>
                      <div className='space-y-1'>
                        <Label className='text-xs'>来源</Label>
                        <Select
                          value={row.source}
                          items={PARAM_MAPPING_SOURCE_OPTIONS}
                          onValueChange={(value) =>
                            setValue(
                              `mappings.${index}.source`,
                              value as ParamProfileMappingSource,
                              { shouldDirty: true }
                            )
                          }
                        >
                          <SelectTrigger size='sm' className='w-28'>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {PARAM_MAPPING_SOURCE_OPTIONS.map((item) => (
                              <SelectItem key={item.value} value={item.value}>
                                {item.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className='space-y-1'>
                        <Label className='text-xs'>来源方向</Label>
                        <Select
                          value={row.sourceDirection}
                          items={PARAM_DIRECTION_OPTIONS}
                          onValueChange={(value) =>
                            setValue(
                              `mappings.${index}.sourceDirection`,
                              value as ParamDirection,
                              { shouldDirty: true }
                            )
                          }
                        >
                          <SelectTrigger size='sm' className='w-20'>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {PARAM_DIRECTION_OPTIONS.map((item) => (
                              <SelectItem key={item.value} value={item.value}>
                                {item.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className='space-y-1'>
                        <Label className='text-xs'>源参数</Label>
                        <Input
                          className='h-7 w-32 font-mono text-xs'
                          placeholder='api 字段'
                          {...register(`mappings.${index}.sourceParam`)}
                        />
                      </div>
                      <div className='space-y-1'>
                        <Label className='text-xs'>目标维度</Label>
                        <Input
                          className='h-7 w-20 text-xs'
                          type='number'
                          placeholder='id'
                          {...register(`mappings.${index}.dimensionId`)}
                        />
                      </div>
                      <div className='space-y-1'>
                        <Label className='text-xs'>目标参数</Label>
                        <Input
                          className='h-7 w-32 font-mono text-xs'
                          placeholder='维度字段'
                          {...register(`mappings.${index}.targetParam`)}
                        />
                      </div>
                      <div className='space-y-1'>
                        <Label className='text-xs'>转换</Label>
                        <Select
                          value={row.transformType}
                          items={TRANSFORM_TYPE_OPTIONS}
                          onValueChange={(value) =>
                            setValue(
                              `mappings.${index}.transformType`,
                              value as ParamTransformType,
                              { shouldDirty: true }
                            )
                          }
                        >
                          <SelectTrigger size='sm' className='w-32'>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {TRANSFORM_TYPE_OPTIONS.map((item) => (
                              <SelectItem key={item.value} value={item.value}>
                                {item.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <Button
                        type='button'
                        variant='ghost'
                        size='icon-sm'
                        className='size-7 text-destructive'
                        aria-label='删除映射'
                        onClick={() => mappings.remove(index)}
                      >
                        <Trash2 aria-hidden='true' className='size-3.5' />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <DialogFooter>
              <Button type='button' variant='outline' onClick={() => onOpenChange(false)}>
                取消
              </Button>
              <Button type='submit' disabled={save.isPending}>
                {save.isPending ? '保存中…' : '保存'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** 参数行表格（输入 / 输出共用；direction 由父级数组决定） */
function ParamRowsEditor({
  title,
  rows,
  showFieldPath,
  onAdd,
  onRemove,
  onParamTypeChange,
  registerPath,
  onCheckChange,
}: {
  title: string
  rows: ParamRowValues[]
  showFieldPath: boolean
  onAdd: () => void
  onRemove: (index: number) => void
  onParamTypeChange: (index: number, value: ParamType) => void
  registerPath: (
    index: number,
    key: 'paramCode' | 'paramName' | 'uiOrder' | 'fieldPath' | 'defaultValue' | 'helpText'
  ) => UseFormRegisterReturn
  onCheckChange: (index: number, key: 'required' | 'hidden', checked: boolean) => void
}) {
  return (
    <div className='space-y-1.5'>
      <div className='flex items-center justify-between'>
        <Label>{title}</Label>
        <Button
          type='button'
          variant='outline'
          size='sm'
          className='h-7 gap-1 text-xs'
          onClick={onAdd}
        >
          <Plus aria-hidden='true' className='size-3.5' />
          新增字段
        </Button>
      </div>
      {rows.length === 0 ? (
        <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
          无字段行
        </p>
      ) : (
        <div className='space-y-2'>
          {rows.map((row, index) => (
            <div
              key={index}
              className='border-border/60 bg-muted/20 flex flex-wrap items-end gap-2 rounded-lg border p-2'
            >
              <div className='space-y-1'>
                <Label className='text-xs'>参数代码</Label>
                <Input
                  className='h-7 w-32 font-mono text-xs'
                  placeholder='param_code'
                  {...registerPath(index, 'paramCode')}
                />
              </div>
              <div className='space-y-1'>
                <Label className='text-xs'>参数名称</Label>
                <Input
                  className='h-7 w-32 text-xs'
                  placeholder='param_name'
                  {...registerPath(index, 'paramName')}
                />
              </div>
              <div className='space-y-1'>
                <Label className='text-xs'>类型</Label>
                <Select
                  value={row.paramType}
                  items={PARAM_TYPE_OPTIONS}
                  onValueChange={(value) =>
                    onParamTypeChange(index, value as ParamType)
                  }
                >
                  <SelectTrigger size='sm' className='w-28'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PARAM_TYPE_OPTIONS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='space-y-1'>
                <Label className='text-xs'>排序</Label>
                <Input
                  className='h-7 w-16 text-xs'
                  type='number'
                  {...registerPath(index, 'uiOrder')}
                />
              </div>
              {showFieldPath && (
                <div className='space-y-1'>
                  <Label className='text-xs'>响应路径</Label>
                  <Input
                    className='h-7 w-40 font-mono text-xs'
                    placeholder='data.items[0].text'
                    {...registerPath(index, 'fieldPath')}
                  />
                </div>
              )}
              <div className='space-y-1'>
                <Label className='text-xs'>默认值</Label>
                <Input
                  className='h-7 w-32 font-mono text-xs'
                  placeholder='default_value'
                  {...registerPath(index, 'defaultValue')}
                />
              </div>
              <div className='space-y-1'>
                <Label className='text-xs'>帮助提示</Label>
                <Input
                  className='h-7 w-44 text-xs'
                  placeholder='填写说明'
                  {...registerPath(index, 'helpText')}
                />
              </div>
              <label className='flex h-7 items-center gap-1.5 text-xs'>
                <Checkbox
                  aria-label={`必填 ${row.paramCode || index + 1}`}
                  checked={row.required}
                  onCheckedChange={(checked) =>
                    onCheckChange(index, 'required', Boolean(checked))
                  }
                />
                必填
              </label>
              <label className='flex h-7 items-center gap-1.5 text-xs'>
                <Checkbox
                  aria-label={`隐藏 ${row.paramCode || index + 1}`}
                  checked={row.hidden}
                  onCheckedChange={(checked) =>
                    onCheckChange(index, 'hidden', Boolean(checked))
                  }
                />
                隐藏
              </label>
              <Button
                type='button'
                variant='ghost'
                size='icon-sm'
                className='size-7 text-destructive'
                aria-label='删除字段'
                onClick={() => onRemove(index)}
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
