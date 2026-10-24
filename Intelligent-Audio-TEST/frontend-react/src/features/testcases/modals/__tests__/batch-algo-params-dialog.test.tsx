/**
 * 批量设置用例专属参数弹窗测试（INT-1686）：
 * P2 —— 选完算法后触发器显示算法中文名，不显示原始算法类型码（base-ui Select 未传 items
 * 时闭合态回退 stringify 原始 value）；
 * P3 —— schema 同时给顶层 fields 与 groups[].fields 时同一字段只渲染一个控件。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BatchAlgoParamsDialog } from '@/features/testcases/modals/batch-algo-params-dialog'
import {
  fetchAlgorithmFormSchema,
  type AlgorithmFormField,
  type AlgorithmFormSchema,
} from '@/infrastructure/api/algorithm-form-api'

vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction: vi.fn(),
}))

vi.mock('@/application/hooks/use-algorithm-options', () => ({
  useAlgorithmOptions: () => ({
    options: [{ value: 'voice_llm', name: '小艺语音大模型' }],
    isLoading: false,
  }),
}))

vi.mock('@/infrastructure/api/algorithm-form-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/infrastructure/api/algorithm-form-api')>()
  return { ...actual, fetchAlgorithmFormSchema: vi.fn() }
})

const mockedSchema = vi.mocked(fetchAlgorithmFormSchema)

const THRESHOLD: AlgorithmFormField = {
  code: 'wire_test_threshold',
  label: '接线测试阈值',
  component: 'input-number',
  type: 'number',
  required: false,
  defaultValue: 10,
  helpText: null,
  hidden: false,
  scope: null,
}

/** 同一字段既在顶层 fields 又在 groups[].fields（后端真实形态） */
const DUPLICATED_SCHEMA: AlgorithmFormSchema = {
  algorithmType: 'voice_llm',
  algorithmName: '小艺语音大模型',
  description: null,
  fields: [THRESHOLD],
  groups: [{ name: 'basic', label: '基础参数', fields: [THRESHOLD] }],
}

const setup = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <BatchAlgoParamsDialog open onOpenChange={vi.fn()} count={2} ids={['tc-1', 'tc-2']} />
    </QueryClientProvider>
  )
}

const chooseAlgorithm = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByRole('combobox'))
  await user.click(await screen.findByRole('option', { name: '小艺语音大模型' }))
}

describe('BatchAlgoParamsDialog（INT-1686）', () => {
  beforeEach(() => {
    mockedSchema.mockReset()
    mockedSchema.mockResolvedValue(DUPLICATED_SCHEMA)
  })

  it('选完算法后触发器显示算法中文名，不显示原始类型码', async () => {
    const user = userEvent.setup()
    setup()
    await chooseAlgorithm(user)

    const trigger = screen.getByRole('combobox')
    expect(trigger).toHaveTextContent('小艺语音大模型')
    expect(trigger).not.toHaveTextContent('voice_llm')
  })

  it('顶层 fields 与 groups[].fields 同字段只渲染一个控件', async () => {
    const user = userEvent.setup()
    setup()
    await chooseAlgorithm(user)

    // 字段 label 只出现一次（重复时两个输入框 → 两个同名 label）
    expect(await screen.findByText('接线测试阈值')).toBeInTheDocument()
    expect(screen.getAllByText('接线测试阈值')).toHaveLength(1)
    expect(screen.getAllByRole('spinbutton')).toHaveLength(1)
  })
})
