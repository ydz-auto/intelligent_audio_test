/**
 * §6.4 统一参数表 + 作用域 chips 组件测试（INT-601）：
 * 三数组并集展示（作用域徽标区分行来源）+ 切 chip 过滤该作用域参数行 +
 * 用例 chip 显示功能特性快捷开关；添加参数随当前 chip 定作用域。
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
    apiParams: [
      {
        key: 'a-1',
        paramCode: 'language',
        paramName: '语言',
        direction: 'input',
        paramType: 'text',
        required: false,
        defaultValue: 'zh',
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
    mappings: { device: [], api: [], evaluation: [] },
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
  it('默认「全部」chip：三作用域参数行并集展示，徽标区分来源', () => {
    render(<Harness />)

    // 三个作用域徽标各出现一次（3 行）
    expect(screen.getByText('设备')).toBeInTheDocument()
    expect(screen.getByText('API')).toBeInTheDocument()
    expect(screen.getByText('用例')).toBeInTheDocument()
    // 参数代码行内容
    expect(screen.getByDisplayValue('input_audio')).toBeInTheDocument()
    expect(screen.getByDisplayValue('language')).toBeInTheDocument()
    expect(screen.getByDisplayValue('noise_level')).toBeInTheDocument()
  })

  it('切「设备」chip：仅设备行可见，方向列保留、用例专属列隐藏', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByRole('button', { name: /设备 \(1\)/ }))

    // 设备行保留，API/用例行隐藏
    expect(screen.getByDisplayValue('input_audio')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('language')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('noise_level')).not.toBeInTheDocument()
    // 列随 chip 动态显隐：设备态保留「方向」列，隐藏用例专属「适用范围」列
    expect(screen.getByText('方向')).toBeInTheDocument()
    expect(screen.queryByText('适用范围')).not.toBeInTheDocument()
  })

  it('切「用例」chip：仅用例行可见 + 功能特性快捷开关显示 + 方向列隐藏', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByRole('button', { name: /用例 \(1\)/ }))

    expect(screen.getByDisplayValue('noise_level')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('input_audio')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('language')).not.toBeInTheDocument()
    // 用例态：方向列隐藏、适用范围列显示
    expect(screen.queryByText('方向')).not.toBeInTheDocument()
    expect(screen.getByText('适用范围')).toBeInTheDocument()
    // 功能特性 hint + 开关
    expect(screen.getByText('勾选后自动批量添加/删除对应参数')).toBeInTheDocument()
  })

  it('「全部」chip 下「添加参数」为小菜单（三作用域可选）', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByRole('button', { name: '添加参数' }))

    expect(screen.getByText('添加设备参数')).toBeInTheDocument()
    expect(screen.getByText('添加API参数')).toBeInTheDocument()
    expect(screen.getByText('添加用例参数')).toBeInTheDocument()
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
  it('chips 计数实时随行数（全部=3）', () => {
    render(<Harness />)
    expect(screen.getByRole('button', { name: /全部 \(3\)/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /设备 \(1\)/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /API \(1\)/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /用例 \(1\)/ })).toBeInTheDocument()
  })
})
