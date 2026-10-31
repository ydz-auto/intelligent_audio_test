/**
 * 参数映射行视图（Presentation；算法编辑模态窗与设备「参数配置」弹窗共用）。
 *
 * - `DeviceMappingRowView`：6 列「源参数代码 / 源参数名称 / 目标参数代码 / 目标参数名称 / 转换 / 操作」；
 * - `EvaluationMappingRowView`：7 列「来源 / 源参数代码 / 源参数名称 / 目标评估维度 / 目标参数 / 转换 / 操作」。
 *
 * 行只接收值 + 回调（不依赖 react-hook-form），作用域徽章由消费方以 `sourceBadge` 注入，
 * 保证算法级编辑与设备级覆盖编辑共用同一套视图。
 *
 * INT-2213 返工：行组件全部 `memo`。窗口化滚动时每次窗口位移只重渲染新进入视口的行，
 * 留在窗口内的行跳过（消费方需保证 `value` / 选项数组 / 回调的引用稳定）。
 */
import { memo, type ReactNode } from 'react'

import type { DimensionParam } from '@/domain/models/algorithmConfig'
import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import { DimensionSelect } from '../dimension-select'
import { evalSourceOptions, evalSourceParamName, EVALUATION_SOURCE_OPTIONS } from './helpers'
import {
  DeleteButton,
  MappingSelect,
  ParamNameCell,
  TransformSelect,
  type ParamOption,
} from './primitives'

/* ───────────────────────── 设备参数映射行 ───────────────────────── */

export interface DeviceMappingRowValues {
  sourceParam: string
  targetParam: string
  transformType: string
}

export const DeviceMappingRowView = memo(function DeviceMappingRowView({
  value,
  sourceName,
  targetName,
  sourceOptions,
  targetOptions,
  transformOptions,
  onChange,
  onRemove,
  sourceBadge,
  disabled = false,
}: {
  value: DeviceMappingRowValues
  /** 源/目标参数名称（消费方按参数表解析；空则回退代码） */
  sourceName: string
  targetName: string
  sourceOptions: ReadonlyArray<ParamOption>
  targetOptions: ReadonlyArray<ParamOption>
  transformOptions: ReadonlyArray<{ value: string; label: string }>
  onChange: (patch: Partial<DeviceMappingRowValues>) => void
  /** 不传 = 不可删除（算法级行） */
  onRemove?: () => void
  /** 行作用域徽章（本设备 / 算法级） */
  sourceBadge?: ReactNode
  disabled?: boolean
}) {
  return (
    <tr data-vkind='row' className='border-border/50 border-b last:border-b-0'>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={value.sourceParam}
          onValueChange={(next) => onChange({ sourceParam: next })}
          options={sourceOptions}
          className='w-44'
          disabled={disabled}
          ariaLabel='源参数代码'
        />
      </td>
      <td className='px-2 py-1.5'>
        <ParamNameCell name={sourceName} code={value.sourceParam} badge={sourceBadge} />
      </td>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={value.targetParam}
          onValueChange={(next) => onChange({ targetParam: next })}
          options={targetOptions}
          className='w-44'
          disabled={disabled}
          ariaLabel='目标参数代码'
        />
      </td>
      <td className='px-2 py-1.5'>
        <ParamNameCell name={targetName} code={value.targetParam} />
      </td>
      <td className='px-2 py-1.5'>
        <TransformSelect
          value={value.transformType}
          onValueChange={(next) => onChange({ transformType: next })}
          options={transformOptions}
          disabled={disabled}
        />
      </td>
      <td className='px-2 py-1.5'>
        <div className='flex items-center justify-end'>
          {onRemove ? (
            <DeleteButton onClick={onRemove} disabled={disabled} />
          ) : (
            <span className='text-muted-foreground text-[11px]'>继承</span>
          )}
        </div>
      </td>
    </tr>
  )
})

/* ───────────────────────── 评估参数映射行 ───────────────────────── */

export interface EvaluationMappingRowValues {
  /** 来源类型（缺省按「用例参数」） */
  source?: string
  sourceParam: string
  /** 目标评估维度 id（字符串形态，空 = 未指定） */
  dimensionId?: string
  targetParam: string
  transformType: string
  /** 存量参数名（查表不到时兜底） */
  paramName?: string | null
  targetParamName?: string | null
}

export const EvaluationMappingRowView = memo(function EvaluationMappingRowView({
  value,
  caseParams,
  referenceParams,
  deviceParams,
  dimensions,
  categories = [],
  dimensionParams,
  transformOptions,
  onChange,
  onRemove,
  sourceBadge,
  disabled = false,
  sourceOptions: sourceOptionsOverride,
  sourceDisabled = false,
}: {
  value: EvaluationMappingRowValues
  caseParams: Array<{ paramCode: string; paramName?: string }>
  referenceParams: Array<{ code: string; name?: string }>
  deviceParams: Array<{ paramCode: string; paramName?: string }>
  dimensions: Dimension[]
  categories?: EvaluationCategory[]
  /** 当前维度内的目标参数（`/algorithm/dimension-params`） */
  dimensionParams: DimensionParam[]
  transformOptions: ReadonlyArray<{ value: string; label: string }>
  onChange: (patch: Partial<EvaluationMappingRowValues>) => void
  /** 不传 = 不可删除（算法级行） */
  onRemove?: () => void
  sourceBadge?: ReactNode
  disabled?: boolean
  /** 来源选项覆盖（设备作用域下固定「设备输出」） */
  sourceOptions?: ReadonlyArray<ParamOption>
  sourceDisabled?: boolean
}) {
  const source = value.source || 'case'
  const sourceOptions =
    sourceOptionsOverride ?? evalSourceOptions(source, caseParams, referenceParams, deviceParams)
  /** 源参数名称：实时按 source 取对应集合兜底（存量行 paramName 为空时显示真实名称） */
  const resolvedSourceName =
    evalSourceParamName(source, value.sourceParam, caseParams, referenceParams, deviceParams) ||
    value.paramName ||
    value.sourceParam
  /** 维度内目标参数选项；存量 target_param（如旧版维度名）不在列表时回退展示（数据保全） */
  const targetOptions: ParamOption[] = dimensionParams.map((p) => ({
    value: p.code,
    label: `${p.code} · ${p.name || '（未填名称）'}`,
  }))
  if (value.targetParam && !targetOptions.some((o) => o.value === value.targetParam)) {
    targetOptions.unshift({
      value: value.targetParam,
      label: `${value.targetParam} · ${value.targetParamName || value.targetParam}`,
    })
  }

  return (
    <tr data-vkind='row' className='border-border/50 border-b last:border-b-0'>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={source}
          onValueChange={(next) => onChange({ source: next })}
          options={sourceOptionsOverride ?? EVALUATION_SOURCE_OPTIONS}
          className='w-28'
          disabled={disabled || sourceDisabled}
          ariaLabel='来源'
        />
      </td>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={value.sourceParam}
          onValueChange={(next) => onChange({ sourceParam: next })}
          options={sourceOptions}
          placeholder='选择参数'
          className='w-40'
          disabled={disabled}
          ariaLabel='源参数代码'
        />
      </td>
      <td className='px-2 py-1.5'>
        <ParamNameCell
          name={resolvedSourceName}
          code={value.sourceParam}
          badge={sourceBadge}
        />
      </td>
      <td className='px-2 py-1.5'>
        <DimensionSelect
          dimensions={dimensions}
          categories={categories}
          value={value.dimensionId ?? ''}
          onValueChange={(next) => onChange({ dimensionId: next })}
          valueOf={(dimension) => String(dimension.id)}
          placeholder='选择维度'
          triggerClassName='w-48'
        />
      </td>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={value.targetParam}
          onValueChange={(next) => onChange({ targetParam: next })}
          options={targetOptions}
          placeholder={value.dimensionId ? '选择参数' : '先选维度'}
          disabled={disabled || !value.dimensionId}
          className='w-40'
          ariaLabel='目标参数'
        />
      </td>
      <td className='px-2 py-1.5'>
        <TransformSelect
          value={value.transformType}
          onValueChange={(next) => onChange({ transformType: next })}
          options={transformOptions}
          disabled={disabled}
        />
      </td>
      <td className='px-2 py-1.5'>
        <div className='flex items-center justify-end'>
          {onRemove ? (
            <DeleteButton onClick={onRemove} disabled={disabled} />
          ) : (
            <span className='text-muted-foreground text-[11px]'>继承</span>
          )}
        </div>
      </td>
    </tr>
  )
})
