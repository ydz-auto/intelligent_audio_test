/**
 * §6.4 统一参数表 + 作用域 chips 组件测试（INT-601）：
 * 两数组并集展示（作用域徽标区分行来源：设备/用例）+ 切 chip 过滤该作用域参数行 +
 * 用例 chip 显示功能特性快捷开关；添加参数随当前 chip 定作用域。
 * 算法级 API 入参已迁移到 API 实例作用域，表内不再出现 API 行/chip/入口。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { describe, expect, it } from 'vitest'

import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import { ParamsTable } from '../params-table'
import { algorithmFormSchema } from '../algorithm-form-schema'
import type { AlgorithmOption } from '../annotation-code-select'

const ALGORITHM_OPTIONS: AlgorithmOption[] = [
  { type: 'asr_v3', name: '语音识别' },
  { type: 'mt_2026', name: '机器翻译' },
]

function buildValues(): AlgorithmFormValues {
  return {
    type: 'asr_v3',
    name: '语音识别',
    groupId: '1',
    displayOrder: 0,
    status: 'online',
    description: '',
    deviceParams: [
      {
        key: 'd-1',
        paramCode: 'input_audio',
        paramName: '输入音频',
        direction: 'input',
        paramType: 'audio_file',
        required: true,
        defaultValue: '',
        helpText: '',
      },
    ],
    caseParams: [
      {
        key: 'c-1',
        paramCode: 'noise_level',
        paramName: '噪声等级',
        paramType: 'slider',
        scope: 'common',
        required: false,
        defaultValue: '0.5',
        minValue: '0',
        maxValue: '1',
        step: '0.1',
        unit: '档',
        annotationCode: '',
        fieldPath: '',
        helpText: '',
      },
    ],
    referenceParams: [],
    mappings: { device: [], evaluation: [] },
    associatedDimensions: [],
  }
}

function Harness({ values = buildValues() }: { values?: AlgorithmFormValues }) {
  const form = useForm<AlgorithmFormValues>({ defaultValues: values })
  return <ParamsTable form={form} algorithmOptions={ALGORITHM_OPTIONS} />
}

/** 挂发布严格 schema 的 Harness（范围约束字段级校验用） */
function ValidatingHarness({ values }: { values: AlgorithmFormValues }) {
  const form = useForm<AlgorithmFormValues>({
    mode: 'onChange',
    resolver: zodResolver(algorithmFormSchema),
    defaultValues: values,
  })
  useEffect(() => {
    void form.trigger()
  }, [form])
  return <ParamsTable form={form} algorithmOptions={ALGORITHM_OPTIONS} />
}

function withRange(minValue: string, maxValue: string): AlgorithmFormValues {
  const values = buildValues()
  values.caseParams = [
    { ...values.caseParams[0], paramType: 'number', minValue, maxValue },
  ]
  return values
}

describe('ParamsTable 统一参数表（§6.4）', () => {
  it('默认「全部」chip：只展示用例参数行（设备参数已迁到设备管理）', () => {
    render(<Harness />)

    // 设备参数不在算法弹窗展示（设备管理 → 行操作 → 参数配置）
    expect(screen.queryByDisplayValue('input_audio')).not.toBeInTheDocument()
    expect(screen.queryByText('设备')).not.toBeInTheDocument()
    // 用例参数行仍在
    expect(screen.getByText('用例')).toBeInTheDocument()
    expect(screen.getByDisplayValue('noise_level')).toBeInTheDocument()
    // 算法级 API 入参行已移除
    expect(screen.queryByText('API')).not.toBeInTheDocument()
  })

  it('不再提供「设备」chip（设备参数在设备管理页配置）', () => {
    render(<Harness />)
    expect(screen.queryByRole('button', { name: /设备 \(/ })).not.toBeInTheDocument()
  })

  it('切「用例」chip：仅用例行可见 + 功能特性快捷开关显示 + 方向列隐藏', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByRole('button', { name: /用例 \(1\)/ }))

    expect(screen.getByDisplayValue('noise_level')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('input_audio')).not.toBeInTheDocument()
    // 用例态：方向列隐藏、适用范围列显示
    expect(screen.queryByText('方向')).not.toBeInTheDocument()
    expect(screen.getByText('适用范围')).toBeInTheDocument()
    // 功能特性 hint + 开关
    expect(screen.getByText('勾选后自动批量添加/删除对应参数')).toBeInTheDocument()
  })

  it('「添加用例参数」为单按钮（设备参数入口已迁走）', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    const addButton = screen.getByRole('button', { name: '添加用例参数' })
    await user.click(addButton)

    expect(screen.queryByText('添加设备参数')).not.toBeInTheDocument()
    expect(screen.getAllByDisplayValue('').length).toBeGreaterThan(0)
  })

  it('用例行标注代码为下拉（算法类型/标注代码映射，INT-1030）', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByRole('button', { name: /用例 \(1\)/ }))

    const annotation = screen.getByRole('combobox', { name: '标注代码' })
    expect(annotation).toHaveTextContent('默认同算法类型')
    await user.click(annotation)
    expect(screen.getByRole('option', { name: '语音识别（asr_v3）' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '机器翻译（mt_2026）' })).toBeInTheDocument()
  })
})

describe('ParamsTable 范围约束字段级校验（INT-1540）', () => {
  it('min>max：范围单元格渲染红字，min/max 均置 aria-invalid', async () => {
    render(<ValidatingHarness values={withRange('10', '5')} />)

    expect(await screen.findByText('最小值不能大于最大值')).toBeInTheDocument()
    expect(screen.getByLabelText('最小值')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('最大值')).toHaveAttribute('aria-invalid', 'true')
  })

  it('min≤max：无红字，字段不置 aria-invalid', async () => {
    render(<ValidatingHarness values={withRange('0', '10')} />)

    await screen.findByLabelText('最小值')
    expect(screen.queryByText('最小值不能大于最大值')).not.toBeInTheDocument()
    expect(screen.queryByText('最大值不能小于最小值')).not.toBeInTheDocument()
    expect(screen.getByLabelText('最小值')).toHaveAttribute('aria-invalid', 'false')
    expect(screen.getByLabelText('最大值')).toHaveAttribute('aria-invalid', 'false')
  })
})

describe('ParamScopeChips 作用域 chips（§6.4）', () => {
  it('chips 只保留 全部/用例 两项且计数随行数（无设备/API chip）', () => {
    render(<Harness />)
    expect(screen.getByRole('button', { name: /全部 \(1\)/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /用例 \(1\)/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /设备 \(/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /API/ })).not.toBeInTheDocument()
  })
})
