/**
 * §6.5 参数映射三节测试（INT-1160 返工：列口径 + 搜索/筛选 + 分组视图照 V9.7.10）：
 * - 设备/API 6 列（源参数代码/名称、目标参数代码/名称、转换、操作）；
 * - 评估 7 列（来源/源参数代码/名称/目标评估维度/目标参数/转换/操作）；
 * - 默认「评估维度视图」按 dimensionId 分组（组头折叠 + 主/子徽章 + 计数 + 组尾添加预填维度）；
 * - 搜索映射 + 转换/来源/评估维度徽章筛选；平铺/分组视图切换。
 * 设备参数映射默认展开（defaultOpen），其余分节测试先折叠设备节，保证目标分节查询唯一。
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import { MappingsSection } from '../mappings-section'

vi.mock('sonner', () => ({
  toast: {
    warning: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
})

const DIMENSIONS: Dimension[] = [
  { id: 1, name: '识别准确率', dimensionType: 'main', parentDimensionId: null, categoryId: 1 },
  { id: 2, name: '响应延迟', dimensionType: 'main', parentDimensionId: null, categoryId: 1 },
  { id: 11, name: '字准率', dimensionType: 'sub', parentDimensionId: 1, categoryId: 1 },
]

const CATEGORIES: EvaluationCategory[] = [{ id: 1, name: '基础质量' }]

function buildValues(): AlgorithmFormValues {
  return {
    type: 'asr_v3',
    name: '语音识别',
    groupId: '1',
    displayOrder: 0,
    status: 'online',
    description: '',
    deviceParams: [{ key: 'd-1', paramCode: 'audio_in', paramName: '音频输入', direction: 'input', paramType: 'text', required: false, defaultValue: '', helpText: '' }],
    apiParams: [{ key: 'a-1', paramCode: 'api_key', paramName: 'API密钥', direction: 'input', paramType: 'text', required: false, defaultValue: '', helpText: '' }],
    caseParams: [
      { key: 'c-1', paramCode: 'asr_result', paramName: 'ASR结果', paramType: 'text', scope: 'common', required: false, defaultValue: '', minValue: '', maxValue: '', step: '', unit: '', annotationCode: '', fieldPath: '', helpText: '' },
      { key: 'c-2', paramCode: 'tts_text', paramName: 'TTS文本', paramType: 'text', scope: 'api', required: false, defaultValue: '', minValue: '', maxValue: '', step: '', unit: '', annotationCode: '', fieldPath: '', helpText: '' },
      { key: 'c-3', paramCode: 'char', paramName: '字符数', paramType: 'number', scope: 'e2e', required: false, defaultValue: '', minValue: '', maxValue: '', step: '', unit: '', annotationCode: '', fieldPath: '', helpText: '' },
    ],
    referenceParams: [{ key: 'r-1', code: 'ref_text', name: '参考文本', type: 'text', annotationCode: '', annotationFormat: '', fieldPath: '', mergeMode: '', helpText: '' }],
    mappings: {
      device: [
        { key: 'md-1', source: 'case', sourceDirection: 'output', sourceParam: 'asr_result', paramName: 'ASR结果', targetParam: 'audio_in', targetParamName: '音频输入', transformType: 'none' },
      ],
      api: [
        { key: 'ma-1', source: 'case', sourceDirection: 'output', sourceParam: 'tts_text', paramName: 'TTS文本', targetParam: 'api_key', targetParamName: 'API密钥', transformType: 'uppercase' },
      ],
      evaluation: [
        { key: 'me-1', source: 'case', sourceDirection: 'output', sourceParam: 'asr_result', paramName: 'ASR结果', dimensionId: '1', dimensionName: '识别准确率', targetParam: 'wer', targetParamName: '字错率', transformType: 'none' },
        { key: 'me-2', source: 'reference', sourceDirection: 'output', sourceParam: 'ref_text', paramName: '参考文本', dimensionId: '1', dimensionName: '识别准确率', targetParam: '', transformType: 'uppercase' },
        { key: 'me-3', source: 'case', sourceDirection: 'output', sourceParam: 'char', paramName: '字符数', dimensionId: '2', dimensionName: '响应延迟', targetParam: '', transformType: 'none' },
        { key: 'me-4', source: 'case', sourceDirection: 'output', sourceParam: 'other', paramName: '其他', dimensionId: '', dimensionName: '', targetParam: '', transformType: 'none' },
        { key: 'me-5', source: 'case', sourceDirection: 'output', sourceParam: 'char', paramName: '字符数', dimensionId: '11', dimensionName: '字准率', targetParam: '', transformType: 'none' },
      ],
    },
    associatedDimensions: [],
  }
}

function Harness() {
  const form = useForm<AlgorithmFormValues>({ defaultValues: buildValues() })
  return (
    <MappingsSection
      form={form}
      dimensions={DIMENSIONS}
      categories={CATEGORIES}
    />
  )
}

/** 两条存量完备设备映射行（判重 P2 复现：编辑第 2 行源参数制造重复） */
function TwoDeviceRowsHarness() {
  const form = useForm<AlgorithmFormValues>({
    defaultValues: {
      ...buildValues(),
      mappings: {
        ...buildValues().mappings,
        device: [
          { key: 'md-1', source: 'case', sourceDirection: 'output', sourceParam: 'asr_result', paramName: 'ASR结果', targetParam: 'audio_in', targetParamName: '音频输入', transformType: 'none' },
          { key: 'md-2', source: 'case', sourceDirection: 'output', sourceParam: 'tts_text', paramName: 'TTS文本', targetParam: 'audio_in', targetParamName: '音频输入', transformType: 'none' },
        ],
      },
    },
  })
  return (
    <MappingsSection
      form={form}
      dimensions={DIMENSIONS}
      categories={CATEGORIES}
    />
  )
}

/** 折叠默认展开的设备节，再展开目标分节，保证目标分节内查询唯一 */
async function isolateSection(user: ReturnType<typeof userEvent.setup>, sectionName: string) {
  await user.click(screen.getByRole('button', { name: /设备参数映射/ }))
  await user.click(screen.getByRole('button', { name: new RegExp(sectionName) }))
}

/** 维度分组组头按钮（名称以维度名开头 + 含计数「条」；避开子维度组头的父名提示与行内触发器） */
function groupHeader(name: string) {
  return screen.getByRole('button', { name: new RegExp(`^${name}.*条`) })
}

/** 点击指定维度组尾的「添加映射」 */
async function clickGroupAdd(user: ReturnType<typeof userEvent.setup>, name: string) {
  const header = groupHeader(name)
  const tr = header.closest('tr')
  expect(tr).not.toBeNull()
  let sibling = tr!.nextElementSibling
  while (sibling) {
    const btn = sibling.querySelector('button')
    if (btn && /添加映射/.test(btn.textContent ?? '')) {
      await user.click(btn as HTMLElement)
      return
    }
    sibling = sibling.nextElementSibling
  }
  throw new Error(`未找到「${name}」组的添加映射按钮`)
}

describe('评估参数映射 维度视图（INT-1160 返工）', () => {
  it('默认「评估维度视图」：按 dimensionId 分组，组头=维度名+计数，空行归「未指定维度」', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await isolateSection(user, '评估参数映射')
    expect(groupHeader('识别准确率')).toBeInTheDocument()
    expect(groupHeader('响应延迟')).toBeInTheDocument()
    expect(groupHeader('字准率')).toBeInTheDocument()
    expect(groupHeader('未指定维度')).toBeInTheDocument()
    // 识别准确率 2 条；其余各组 1 条
    expect(within(groupHeader('识别准确率')).getByText('2 条')).toBeInTheDocument()
    expect(screen.getAllByText('1 条').length).toBeGreaterThanOrEqual(3)
  })

  it('维度组头展示主/子徽章与子维度父名', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await isolateSection(user, '评估参数映射')
    expect(within(groupHeader('识别准确率')).getByText('主')).toBeInTheDocument()
    expect(within(groupHeader('响应延迟')).getByText('主')).toBeInTheDocument()
    const subGroup = groupHeader('字准率')
    expect(within(subGroup).getByText('子')).toBeInTheDocument()
    expect(within(subGroup).getByText(/识别准确率/)).toBeInTheDocument()
  })

  it('组尾「添加映射」预填该维度（识别准确率组）', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await isolateSection(user, '评估参数映射')
    await clickGroupAdd(user, '识别准确率')
    expect(within(groupHeader('识别准确率')).getByText('3 条')).toBeInTheDocument()
  })

  it('评估表 7 列；切换「平铺视图」无分组头', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await isolateSection(user, '评估参数映射')
    for (const header of ['来源', '源参数代码', '源参数名称', '目标评估维度', '目标参数', '转换', '操作']) {
      expect(screen.getByRole('columnheader', { name: header })).toBeInTheDocument()
    }
    await user.click(screen.getByRole('button', { name: '平铺视图' }))
    expect(screen.queryByRole('button', { name: /识别准确率.*条/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /未指定维度.*条/ })).not.toBeInTheDocument()
  })
})

describe('评估参数映射 搜索/筛选（INT-1160 返工）', () => {
  it('搜索映射按源参数代码过滤', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await isolateSection(user, '评估参数映射')
    await user.type(screen.getByPlaceholderText('搜索映射...'), 'ref_text')
    // 只有参考参数行仍在（识别准确率组）；其余组消失
    expect(groupHeader('识别准确率')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /响应延迟.*条/ })).not.toBeInTheDocument()
  })

  it('来源徽章筛选：只保留所选来源的行', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await isolateSection(user, '评估参数映射')
    await user.click(screen.getByRole('button', { name: '参考参数' }))
    // 识别准确率组只剩 1 条（reference 行）；其余组消失
    expect(within(groupHeader('识别准确率')).getByText('1 条')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /响应延迟.*条/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /字准率.*条/ })).not.toBeInTheDocument()
  })

  it('评估维度徽章筛选：只保留所选维度', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await isolateSection(user, '评估参数映射')
    await user.click(screen.getByRole('button', { name: '响应延迟' }))
    expect(groupHeader('响应延迟')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /识别准确率.*条/ })).not.toBeInTheDocument()
  })
})

describe('设备/API 参数映射（INT-1160 返工）', () => {
  it('设备映射 6 列 + 分组视图按源参数集合', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    // 设备节默认展开
    for (const header of ['源参数代码', '源参数名称', '目标参数代码', '目标参数名称', '转换', '操作']) {
      expect(screen.getByRole('columnheader', { name: header })).toBeInTheDocument()
    }
    // 分组视图：asr_result 属于用例参数·通用
    await user.click(screen.getByRole('button', { name: '分组视图' }))
    expect(screen.getByRole('button', { name: /用例参数 · 通用.*条/ })).toBeInTheDocument()
  })

  it('API 映射转换选项含 base64', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await isolateSection(user, 'API参数映射')
    // API 行 3 个下拉：源参数 / 目标参数 / 转换（最后一个）
    const combos = screen.getAllByRole('combobox')
    await user.click(combos[combos.length - 1])
    // 下拉 option 含 Base64（避开工具栏转换徽章筛选的「Base64」chip）
    expect(screen.getByRole('option', { name: 'Base64' })).toBeInTheDocument()
  })
})

describe('映射判重实时值（INT-1160 返工 P2：判重读 form.getValues() 实时快照，编辑存量完备行 sourceParam/维度制造重复必弹 toast）', () => {
  it('设备映射：新增行源参数与存量行重复 → 选源参数即时 toast（不再迟至选目标才报）', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '添加映射' }))
    const combos = await screen.findAllByRole('combobox')
    expect(combos.length).toBeGreaterThanOrEqual(6)
    // 新增行（第 2 行）源参数下拉 = combos[3]
    await user.click(combos[3])
    await user.click(screen.getByRole('option', { name: 'asr_result · ASR结果' }))
    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('映射已存在'))
  })

  it('设备映射：编辑存量完备行 sourceParam 与另一行重复 → 即时 toast（审计 P2 复现）', async () => {
    const user = userEvent.setup()
    render(<TwoDeviceRowsHarness />)
    const combos = screen.getAllByRole('combobox')
    // 第 2 行源参数下拉（row1 combos 0-2，row2 combos 3-5）
    await user.click(combos[3])
    await user.click(screen.getByRole('option', { name: 'asr_result · ASR结果' }))
    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('映射已存在'))
  })

  it('评估映射：编辑存量完备行维度与另一行相同 → 即时 toast（维度变更路径）', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await isolateSection(user, '评估参数映射')
    await user.click(screen.getByRole('button', { name: '平铺视图' }))
    const combos = screen.getAllByRole('combobox')
    // 5 行 × 5 下拉；me-5（case/char/维度11）的维度下拉 = 第 5 行第 3 个 = combos[22]
    // 改为「响应延迟」（维度2）→ (case, char, 2) 与 me-3 重复 → toast
    await user.click(combos[22])
    await user.click(screen.getByRole('option', { name: /响应延迟/ }))
    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('映射已存在'))
  })
})
