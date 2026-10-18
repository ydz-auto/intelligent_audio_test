/**
 * §6.4 参考参数分节筛选行测试（INT-723 返修 P2-1）：
 * 筛选行（搜索/类型/合并方式）渲染 + 按关键词/类型/合并方式过滤 + 无匹配空态。
 * 照 V9.7.10 AlgorithmConfigModal.vue filteredReferenceParams 语义（关键词命中 code/annotationCode/name/fieldPath/helpText）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'

import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import { ReferenceParamsSection } from '../reference-params-section'

function buildValues(): AlgorithmFormValues {
  return {
    type: 'asr_v3',
    name: '语音识别',
    groupId: '1',
    displayOrder: 0,
    status: 'online',
    description: '',
    deviceParams: [],
    apiParams: [],
    caseParams: [],
    referenceParams: [
      {
        key: 'r-1',
        code: 'ref_text',
        name: '参考文本',
        type: 'text',
        annotationCode: 'text_ann',
        annotationFormat: 'text',
        fieldPath: '',
        mergeMode: 'join',
        helpText: '参考文本帮助',
      },
      {
        key: 'r-2',
        code: 'ref_audio',
        name: '参考音频',
        type: 'audio',
        annotationCode: '',
        annotationFormat: '',
        fieldPath: 'audio.path',
        mergeMode: 'collect',
        helpText: '',
      },
      {
        key: 'r-3',
        code: 'ref_rttm',
        name: '参考标注',
        type: 'rttm',
        annotationCode: '',
        annotationFormat: 'rttm',
        fieldPath: '',
        mergeMode: 'first',
        helpText: '',
      },
    ],
    mappings: { device: [], api: [], evaluation: [] },
    associatedDimensions: [],
  }
}

function Harness({ values = buildValues() }: { values?: AlgorithmFormValues }) {
  const form = useForm<AlgorithmFormValues>({ defaultValues: values })
  return <ReferenceParamsSection form={form} />
}

describe('ReferenceParamsSection 参考参数筛选行（§6.4）', () => {
  it('筛选行渲染：搜索框 + 类型 Select + 合并方式 Select + 添加按钮', () => {
    render(<Harness />)
    expect(screen.getByPlaceholderText('搜索参考参数...')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '按类型筛选' })).toHaveTextContent('全部类型')
    expect(screen.getByRole('combobox', { name: '按合并方式筛选' })).toHaveTextContent('全部合并')
    expect(screen.getByRole('button', { name: '添加参考字段' })).toBeInTheDocument()
  })

  it('搜索关键词按名称过滤行（非命中行隐藏）', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    // 三行初始都在
    expect(screen.getByDisplayValue('ref_text')).toBeInTheDocument()
    expect(screen.getByDisplayValue('ref_audio')).toBeInTheDocument()
    expect(screen.getByDisplayValue('ref_rttm')).toBeInTheDocument()

    await user.type(screen.getByPlaceholderText('搜索参考参数...'), '音频')
    expect(screen.getByDisplayValue('ref_audio')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('ref_text')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('ref_rttm')).not.toBeInTheDocument()
  })

  it('搜索关键词可命中字段路径（V9.7.10 语义）', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(screen.getByPlaceholderText('搜索参考参数...'), 'audio.path')
    expect(screen.getByDisplayValue('ref_audio')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('ref_text')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('ref_rttm')).not.toBeInTheDocument()
  })

  it('无匹配 → 显示「未找到匹配参考参数」空态', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(screen.getByPlaceholderText('搜索参考参数...'), '不存在的关键词xyz')
    expect(
      screen.getByText('未找到匹配参考参数，换个关键词或筛选条件试试')
    ).toBeInTheDocument()
  })

  it('类型筛选：选「音频」仅保留 audio 行', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('combobox', { name: '按类型筛选' }))
    await user.click(await screen.findByRole('option', { name: '音频' }))
    expect(screen.getByDisplayValue('ref_audio')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('ref_text')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('ref_rttm')).not.toBeInTheDocument()
  })

  it('合并方式筛选：选「拼接」仅保留 join 行', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('combobox', { name: '按合并方式筛选' }))
    await user.click(await screen.findByRole('option', { name: '拼接' }))
    expect(screen.getByDisplayValue('ref_text')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('ref_audio')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('ref_rttm')).not.toBeInTheDocument()
  })
})
