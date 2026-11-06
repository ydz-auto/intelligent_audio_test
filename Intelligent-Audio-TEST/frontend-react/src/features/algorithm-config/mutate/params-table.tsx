/**
 * §6.4 统一参数表（INT-591 降维核心：用例参数一行一列可编辑）。
 *
 * 设备参数已迁到「设备管理 → 行操作 → 参数配置」（按 device_id 做设备级覆盖）；
 * 本表只维护用例参数；`deviceParams` 仍随表单载入与整份保存，只是不再在这里展示 /
 * 编辑，避免整份保存时把算法级设备参数误删。
 */
import { Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  type Path,
  type UseFieldArrayReturn,
  type UseFormReturn,
  useFieldArray,
} from 'react-hook-form'

import { Badge } from '@/components/ui/badge'
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
import type {
  AlgorithmFormValues,
  CaseParamRow,
  DeviceApiParamRow,
  ParamScope,
} from '@/features/algorithm-config/types'
import {
  CASE_PARAM_CODE_PRESETS,
  CASE_PARAM_SCOPE_OPTIONS,
  CASE_PARAM_TYPE_OPTIONS,
  DEVICE_PARAM_TYPE_OPTIONS,
  FEATURE_BUNDLES,
  FEATURE_BUNDLES_HINT,
  PARAM_DIRECTION_OPTIONS,
} from '@/features/algorithm-config/constants'
import { ParamScopeChips, type FeatureBundleItem } from './param-scope-chips'
import { CONTAINED_TABLE_CLASS } from './table-containment'
import { AnnotationCodeSelect, type AlgorithmOption } from './annotation-code-select'
import { RANGE_MESSAGES, isRangeInvalid } from './algorithm-form-schema'

const PRESET_DATALIST_ID = 'case-param-code-presets'

type ParamRowKind = 'device' | 'case'

type MergedRow = {
  kind: ParamRowKind
  index: number
  key: string
}

const SCOPE_BADGE_LABEL: Record<ParamRowKind, string> = {
  device: '设备',
  case: '用例',
}

/** 数组名（RHF 字段数组） */
type ParamArrayName = 'deviceParams' | 'caseParams'

const ARRAY_NAME: Record<ParamRowKind, ParamArrayName> = {
  device: 'deviceParams',
  case: 'caseParams',
}

export function ParamsTable({
  form,
  algorithmOptions,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  /** 算法列表（标注代码下拉选项：标注代码=算法类型） */
  algorithmOptions: AlgorithmOption[]
}) {
  const device = useFieldArray({ control: form.control, name: 'deviceParams' })
  const cases = useFieldArray({ control: form.control, name: 'caseParams' })

  // 作用域 chip（默认「全部」）；本地筛选行状态
  const [scope, setScope] = useState<ParamScope>('all')
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [requiredFilter, setRequiredFilter] = useState('all')

  const watchParams = form.watch()

  const counts = {
    device: 0,
    case: cases.fields.length,
  }

  /* ───────── 功能特性快捷开关（scope=全部/用例 显示；勾选自动批量添加/删除用例参数） ───────── */

  const featureBundles: FeatureBundleItem[] = useMemo(() => {
    const watchCase = watchParams.caseParams
    return FEATURE_BUNDLES.map((bundle) => ({
      key: bundle.key,
      label: bundle.label,
      params: bundle.params,
      active: bundle.params.every((code) =>
        watchCase.some((param) => param.paramCode === code)
      ),
    }))
  }, [watchParams.caseParams])

  const toggleBundle = (key: string) => {
    const bundle = FEATURE_BUNDLES.find((b) => b.key === key)
    if (!bundle) return
    const active = bundle.params.every((code) =>
      watchParams.caseParams.some((param) => param.paramCode === code)
    )
    const current = watchParams.caseParams.map((param) => param.paramCode)
    if (active) {
      // 取消：移除 bundle 参数行（照「勾选自动批量添加/删除」语义）
      cases.remove(
        watchParams.caseParams
          .map((param, index) =>
            bundle.params.includes(param.paramCode) ? index : -1
          )
          .filter((index) => index >= 0)
      )
    } else {
      // 勾选：补齐缺失的 bundle 参数行
      bundle.params.forEach((code) => {
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

  /* ───────── 添加用例参数 ───────── */

  const appendCase = () =>
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

  /* ───────── 合并行 + 过滤（scope chips → 搜索/类型/必填） ───────── */

  const visibleRows = useMemo(() => {
    // 设备参数不在本表展示（设备管理 → 参数配置），只列用例参数
    const rows: MergedRow[] = cases.fields.map((field, index) => ({
      kind: 'case',
      index,
      key: field.key,
    }))

    const keyword = search.trim().toLowerCase()
    const filterType = typeFilter !== 'all' ? typeFilter : null
    const filterRequired =
      requiredFilter === 'required'
        ? true
        : requiredFilter === 'optional'
          ? false
          : null

    return rows.filter((row) => {
      const values = getRowValues(watchParams, row)
      if (keyword) {
        if (
          !values.paramCode.toLowerCase().includes(keyword) &&
          !values.paramName.toLowerCase().includes(keyword)
        ) {
          return false
        }
      }
      if (filterType && values.paramType !== filterType) return false
      if (filterRequired != null && values.required !== filterRequired) return false
      return true
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, search, typeFilter, requiredFilter, cases.fields, watchParams])

  const showDirection = false
  const showCaseOnly = true

  return (
    <div className='space-y-2'>
      <ParamScopeChips
        scope={scope}
        onScopeChange={setScope}
        counts={counts}
        featureBundles={featureBundles}
        onToggleBundle={toggleBundle}
      />

      <p className='text-muted-foreground text-xs'>
        本表只维护用例参数。设备参数在「设备管理 → 行操作 → 参数配置」按设备配置（设备级覆盖算法级）。
        被测 API 的字段在 API 编辑弹窗 →「参数配置」。
      </p>

      {showBundlesHint(scope) && (
        <p className='text-muted-foreground text-xs'>{FEATURE_BUNDLES_HINT}</p>
      )}

      <datalist id={PRESET_DATALIST_ID}>
        {CASE_PARAM_CODE_PRESETS.map((code) => (
          <option key={code} value={code} />
        ))}
      </datalist>

      {/* 筛选行（搜索/类型/必填 + 添加参数，随当前 chip 定作用域） */}
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          aria-label='搜索参数'
          placeholder='搜索参数代码/名称...'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className='h-7 w-44 text-xs'
        />
        <Select value={typeFilter} onValueChange={(value) => setTypeFilter(value ?? 'all')}>
          <SelectTrigger size='sm' className='w-28' aria-label='按类型筛选'>
            <SelectValue>
              {typeFilter === 'all'
                ? '全部类型'
                : (uniqueTypeOptions(scope).find((o) => o.value === typeFilter)
                    ?.label ?? '全部类型')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>全部类型</SelectItem>
            {uniqueTypeOptions(scope).map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={requiredFilter} onValueChange={(value) => setRequiredFilter(value ?? 'all')}>
          <SelectTrigger size='sm' className='w-24' aria-label='按必填筛选'>
            <SelectValue>
              {requiredFilter === 'all'
                ? '全部'
                : requiredFilter === 'required'
                  ? '必填'
                  : '非必填'}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>全部</SelectItem>
            <SelectItem value='required'>必填</SelectItem>
            <SelectItem value='optional'>非必填</SelectItem>
          </SelectContent>
        </Select>
        <div className='ml-auto'>
          <Button variant='outline' size='sm' type='button' onClick={appendCase}>
            <Plus aria-hidden='true' />
            添加用例参数
          </Button>
        </div>
      </div>

      {/* 统一参数表（桌面 min-w-[1100px] 横向滚动） */}
      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className={`w-full min-w-[1100px] text-[13px] ${CONTAINED_TABLE_CLASS}`}>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>作用域</th>
                <th className='px-3 py-2 text-left font-medium'>参数代码*</th>
                <th className='px-3 py-2 text-left font-medium'>参数名称</th>
                <th className='px-3 py-2 text-left font-medium'>参数类型</th>
                {showDirection && (
                  <th className='px-3 py-2 text-left font-medium'>方向</th>
                )}
                {showCaseOnly && (
                  <th className='px-3 py-2 text-left font-medium'>适用范围</th>
                )}
                <th className='px-3 py-2 text-center font-medium'>必填</th>
                <th className='px-3 py-2 text-left font-medium'>默认值</th>
                {showCaseOnly && (
                  <th className='px-3 py-2 text-left font-medium'>范围约束</th>
                )}
                {showCaseOnly && (
                  <th
                    title='标注代码=算法类型代码；默认同本算法，选其它算法表示复用该算法的标注'
                    className='px-3 py-2 text-left font-medium'
                  >
                    标注代码
                  </th>
                )}
                {showCaseOnly && (
                  <th className='px-3 py-2 text-left font-medium'>字段路径</th>
                )}
                <th className='px-3 py-2 text-left font-medium'>帮助文本</th>
                <th className='w-10 px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.length === 0 ? (
                <tr>
                  <td colSpan={13} className='text-muted-foreground px-3 py-6 text-center'>
                    {counts.device + counts.case === 0
                      ? '暂无参数，点击「添加参数」或勾选上方功能特性快捷添加'
                      : '未找到匹配参数，换个关键词或筛选条件试试'}
                  </td>
                </tr>
              ) : (
                visibleRows.map((row) => (
                  <ParamRow
                    key={row.key}
                    row={row}
                    form={form}
                    device={device}
                    cases={cases}
                    showDirection={showDirection}
                    showCaseOnly={showCaseOnly}
                    algorithmOptions={algorithmOptions}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function showBundlesHint(scope: ParamScope): boolean {
  return scope === 'all' || scope === 'case'
}

/** 按当前 chip 收敛类型筛选选项（设备与用例类型集不同） */
function uniqueTypeOptions(scope: ParamScope) {
  if (scope === 'case') return CASE_PARAM_TYPE_OPTIONS
  if (scope === 'device') return DEVICE_PARAM_TYPE_OPTIONS
  return [
    ...new Map(
      [...DEVICE_PARAM_TYPE_OPTIONS, ...CASE_PARAM_TYPE_OPTIONS].map((o) => [
        o.value,
        o,
      ])
    ).values(),
  ]
}

/** 统一行取值（供过滤用；非全量字段） */
function getRowValues(
  values: AlgorithmFormValues,
  row: MergedRow
): { paramCode: string; paramName: string; paramType: string; required: boolean } {
  if (row.kind === 'device') {
    const p = values.deviceParams[row.index]
    return p
      ? { paramCode: p.paramCode, paramName: p.paramName, paramType: p.paramType, required: p.required }
      : { paramCode: '', paramName: '', paramType: '', required: false }
  }
  const p = values.caseParams[row.index]
  return p
    ? { paramCode: p.paramCode, paramName: p.paramName, paramType: p.paramType, required: p.required }
    : { paramCode: '', paramName: '', paramType: '', required: false }
}

/* ───────────────────────── 单行渲染 ───────────────────────── */

function ParamRow({
  row,
  form,
  device,
  cases,
  showDirection,
  showCaseOnly,
  algorithmOptions,
}: {
  row: MergedRow
  form: UseFormReturn<AlgorithmFormValues>
  device: UseFieldArrayReturn<AlgorithmFormValues, 'deviceParams'>
  cases: UseFieldArrayReturn<AlgorithmFormValues, 'caseParams'>
  showDirection: boolean
  showCaseOnly: boolean
  algorithmOptions: AlgorithmOption[]
}) {
  const isCase = row.kind === 'case'
  const arrayName = ARRAY_NAME[row.kind]
  const index = row.index

  // 仅用例行路径（scope/范围/标注/字段路径字段不存在于设备行类型）
  const casePath = (suffix: string): Path<AlgorithmFormValues> =>
    `caseParams.${index}.${suffix}` as Path<AlgorithmFormValues>
  // 通用字段路径（两数组行类型均含；运行时前缀按行 kind 收窄，cast 为已知 Path 字面量）
  const commonPath = (suffix: string): Path<AlgorithmFormValues> =>
    `${arrayName}.${index}.${suffix}` as Path<AlgorithmFormValues>
  // 方向字段（仅设备行类型含）
  const directionPath = isCase
    ? null
    : (`deviceParams.${index}.direction` as Path<AlgorithmFormValues>)

  const rowErrors = isCase
    ? form.formState.errors.caseParams?.[index]
    : form.formState.errors.deviceParams?.[index]
  const paramCodeError = rowErrors?.paramCode?.message
  const paramTypeError = rowErrors?.paramType?.message

  const fieldArray = isCase ? cases : device

  const paramType = form.watch(commonPath('paramType')) as string
  const showRange = isCase && (paramType === 'number' || paramType === 'slider')
  // 范围约束字段级红字（§6.2/§6.6 失败字段红字 + aria-invalid；INT-1540）：
  // 按 watched 值实时判定——草稿自动保存成功后 form.reset 会清空 RHF errors，字段级提示
  // 不能只依赖 formState.errors；判定谓词与文案与发布 schema 的 checkRange 同源。
  const rangeInvalid =
    isCase && showRange
      ? isRangeInvalid(
          paramType,
          (form.watch(casePath('minValue')) as string) ?? '',
          (form.watch(casePath('maxValue')) as string) ?? ''
        )
      : false

  return (
    <tr className='border-border/50 border-b last:border-b-0'>
      {/* 作用域徽标（恒显，「全部」态区分行来源） */}
      <td className='px-2 py-1.5'>
        <Badge variant='secondary' className='text-[11px]'>
          {SCOPE_BADGE_LABEL[row.kind]}
        </Badge>
      </td>
      {/* 参数代码（用例行 datalist 预设） */}
      <td className='px-2 py-1.5'>
        <Input
          aria-label='参数代码'
          placeholder='param_code'
          list={isCase ? PRESET_DATALIST_ID : undefined}
          className='h-7 font-mono text-xs'
          aria-invalid={Boolean(paramCodeError)}
          {...form.register(commonPath('paramCode'))}
        />
        {paramCodeError && (
          <p className='text-destructive text-xs'>{paramCodeError}</p>
        )}
      </td>
      {/* 参数名称 */}
      <td className='px-2 py-1.5'>
        <Input
          aria-label='参数名称'
          placeholder='如：输入音频'
          className='h-7 text-xs'
          {...form.register(commonPath('paramName'))}
        />
      </td>
      {/* 参数类型（选项随行作用域切换） */}
      <td className='px-2 py-1.5'>
        <Select
          value={paramType}
          onValueChange={(value) =>
            form.setValue(commonPath('paramType'), value ?? 'text')
          }
        >
          <SelectTrigger
            size='sm'
            className='w-32'
            aria-invalid={Boolean(paramTypeError)}
          >
            <SelectValue>
              {(isCase ? CASE_PARAM_TYPE_OPTIONS : DEVICE_PARAM_TYPE_OPTIONS).find(
                (o) => o.value === paramType
              )?.label ?? '文本'}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {(isCase ? CASE_PARAM_TYPE_OPTIONS : DEVICE_PARAM_TYPE_OPTIONS).map(
              (option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              )
            )}
          </SelectContent>
        </Select>
        {paramTypeError && (
          <p className='text-destructive text-xs'>{paramTypeError}</p>
        )}
      </td>
      {/* 方向（仅设备行；用例 chip 隐藏列） */}
      {showDirection && (
        <td className='px-2 py-1.5'>
          {isCase || !directionPath ? (
            <span className='text-muted-foreground text-xs'>—</span>
          ) : (
            <Select
              value={form.watch(directionPath) as string}
              onValueChange={(value) =>
                form.setValue(
                  directionPath,
                  (value ?? 'input') as DeviceApiParamRow['direction']
                )
              }
            >
              <SelectTrigger size='sm' className='w-24'>
                <SelectValue>
                  {PARAM_DIRECTION_OPTIONS.find(
                    (o) =>
                      o.value ===
                      (form.watch(directionPath) as string)
                  )?.label ?? '输入'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {PARAM_DIRECTION_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </td>
      )}
      {/* 适用范围（仅用例行） */}
      {showCaseOnly && (
        <td className='px-2 py-1.5'>
          {isCase ? (
            <Select
              value={form.watch(casePath('scope')) as string}
              onValueChange={(value) =>
                form.setValue(
                  casePath('scope'),
                  (value ?? 'common') as CaseParamRow['scope']
                )
              }
            >
              <SelectTrigger size='sm' className='w-20'>
                <SelectValue>
                  {CASE_PARAM_SCOPE_OPTIONS.find(
                    (o) =>
                      o.value ===
                      (form.watch(casePath('scope')) as string)
                  )?.label ?? '通用'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {CASE_PARAM_SCOPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <span className='text-muted-foreground text-xs'>—</span>
          )}
        </td>
      )}
      {/* 必填 */}
      <td className='px-2 py-1.5 text-center'>
        <span className='inline-flex items-center justify-center'>
          <Checkbox
            aria-label={`必填 ${String(form.watch(commonPath('paramName')) ?? '')}`}
            checked={Boolean(form.watch(commonPath('required')))}
            onCheckedChange={(checked) =>
              form.setValue(commonPath('required'), Boolean(checked), {
                shouldDirty: true,
              })
            }
          />
        </span>
      </td>
      {/* 默认值（恒显，设备亦支持） */}
      <td className='px-2 py-1.5'>
        <Input
          aria-label='默认值'
          placeholder='如：zh'
          className='h-7 font-mono text-xs'
          {...form.register(commonPath('defaultValue'))}
        />
      </td>
      {/* 范围约束（仅用例行，number/slider 型显） */}
      {showCaseOnly && (
        <td className='px-2 py-1.5'>
          {isCase && showRange ? (
            <div className='space-y-1'>
              <div className='flex items-center gap-1'>
                <Input
                  aria-label='最小值'
                  placeholder='min'
                  className='h-7 w-14 font-mono text-xs'
                  aria-invalid={rangeInvalid}
                  {...form.register(casePath('minValue'))}
                />
                <span className='text-muted-foreground text-xs'>~</span>
                <Input
                  aria-label='最大值'
                  placeholder='max'
                  className='h-7 w-14 font-mono text-xs'
                  aria-invalid={rangeInvalid}
                  {...form.register(casePath('maxValue'))}
                />
                <Input
                  aria-label='步长'
                  placeholder='step'
                  className='h-7 w-14 font-mono text-xs'
                  {...form.register(casePath('step'))}
                />
                <Input
                  aria-label='单位'
                  placeholder='单位'
                  className='h-7 w-14 text-xs'
                  {...form.register(casePath('unit'))}
                />
              </div>
              {rangeInvalid && (
                <p className='text-destructive text-xs'>
                  {RANGE_MESSAGES.minGreaterThanMax}
                </p>
              )}
            </div>
          ) : (
            <span className='text-muted-foreground text-xs'>—</span>
          )}
        </td>
      )}
      {/* 标注代码（仅用例行；INT-1030 下拉=算法类型/标注代码映射，不再输原始代码） */}
      {showCaseOnly && (
        <td className='px-2 py-1.5'>
          {isCase ? (
            <AnnotationCodeSelect
              value={form.watch(casePath('annotationCode')) as string | undefined ?? ''}
              onValueChange={(value) => form.setValue(casePath('annotationCode'), value)}
              algorithmOptions={algorithmOptions}
            />
          ) : (
            <span className='text-muted-foreground text-xs'>—</span>
          )}
        </td>
      )}
      {/* 字段路径（仅用例行） */}
      {showCaseOnly && (
        <td className='px-2 py-1.5'>
          {isCase ? (
            <Input
              aria-label='字段路径'
              placeholder='默认同参数代码'
              className='h-7 font-mono text-xs'
              {...form.register(casePath('fieldPath'))}
            />
          ) : (
            <span className='text-muted-foreground text-xs'>—</span>
          )}
        </td>
      )}
      {/* 帮助文本 */}
      <td className='px-2 py-1.5'>
        <Input
          aria-label='帮助文本'
          placeholder='可选'
          className='h-7 text-xs'
          {...form.register(commonPath('helpText'))}
        />
      </td>
      {/* 操作 */}
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
  )
}
