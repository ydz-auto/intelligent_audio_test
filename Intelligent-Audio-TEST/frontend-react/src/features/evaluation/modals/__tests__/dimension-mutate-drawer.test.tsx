/**
 * 维度编辑抽屉回填回归（INT-1660 / 同型 INT-1577）：
 * 旧实现用 useForm 的 values 同步——react-hook-form 按深相等判重，关闭时 form.reset(空值)
 * 不更新其内部比对值，重开同一行（值深相等）同步被跳过 → 表单清空、分类回落「未分类」、
 * 页脚报「维度名称不能为空」；换成另一行对象不同才生效。改为按 open/行/详情显式 reset。
 *
 * 第二条链路（本抽屉独有）：列表行不含 required_inputs / output_fields，编辑态靠详情
 * useEvaluationDimensionDetail 补全全量配置——详情对象到达后必须再 reset 一次，
 * 否则第二次打开只有基础字段（故下面单独覆盖「详情到达重同步」）。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { Dimension } from '@/domain/models/evaluationDimension'
import { DimensionMutateDrawer } from '@/features/evaluation/modals/dimension-mutate-drawer'

const { detailStore, saveMock, saveCategoryMock } = vi.hoisted(() => ({
  // 详情缓存：按 id 取；空表示 react-query 缓存已过期 / 首次打开未命中（列表行数据兜底）
  detailStore: { current: {} as Record<string, unknown> },
  saveMock: vi.fn().mockResolvedValue(undefined),
  saveCategoryMock: vi.fn().mockResolvedValue({ id: 999 }),
}))

vi.mock('@/application/evaluation/use-dimensions', () => ({
  useEvaluationDimensionDetail: (id: number | string | null) => ({
    data: id == null ? undefined : detailStore.current[String(id)],
  }),
  useEvaluationMutations: () => ({
    save: { mutateAsync: saveMock, isPending: false },
  }),
  useEvaluationCategoryMutations: () => ({
    save: { mutateAsync: saveCategoryMock, isPending: false },
  }),
}))

const CATEGORIES = [
  { id: 7, name: '拒识' },
  { id: 8, name: '环境' },
]

/** 列表行数据（不含 required_inputs / output_fields，与后端列表 DTO 同口径） */
const LIST_ROW: Dimension = {
  id: 101,
  name: '拒识成功数量',
  description: '统计拒识成功的音频数量',
  categoryId: 7,
  weight: 3,
  type: 'auto',
  dimensionType: 'main',
  resultType: 1,
  status: true,
  resultMin: 0,
  resultMax: 100,
  estimatedExecTime: 5,
  rule: { rules: [{ condition: '>=', value: 90, score: 10 }] },
}

/** 详情数据（含输入参数 / 输出字段配置） */
const DETAIL: Dimension = {
  ...LIST_ROW,
  requiredInputs: [
    {
      paramCode: 'custom_param',
      paramName: '自定义输入',
      label: '自定义输入',
      fieldType: 'text',
      required: true,
      helpText: '详情才有',
      uiOrder: 1,
    },
  ],
  outputFields: [
    {
      paramCode: 'custom_result',
      paramName: '自定义输出',
      label: '自定义输出',
      fieldPath: 'data.custom_result',
      fieldType: 'number',
      outputRole: 'main',
      aggRole: 'value',
      visibleInReport: true,
      uiOrder: 1,
    },
  ],
}

/** 空规则 + result_type=0 的真实维度形态（INT-1732：真实库 55/63 维度 rules=[] 带 defaultScore） */
const EMPTY_RULE_ROW: Dimension = {
  ...LIST_ROW,
  id: 121,
  name: '拒识成功数量',
  resultType: 0,
  rule: { rules: [], defaultScore: 7 },
}

/** 复刻评估维度页的受控用法：关闭时把 dimension 置空（evaluation-page.tsx 同款）。 */
function Harness({ dimension }: { dimension: Dimension }) {
  const [state, setState] = useState<{
    open: boolean
    mode: 'create' | 'edit'
    dimension: Dimension | null
  }>({ open: false, mode: 'edit', dimension: null })

  return (
    <>
      <button type='button' onClick={() => setState({ open: true, mode: 'edit', dimension })}>
        编辑维度
      </button>
      <button type='button' onClick={() => setState({ open: true, mode: 'create', dimension: null })}>
        新增维度
      </button>
      <DimensionMutateDrawer
        open={state.open}
        onOpenChange={(open) =>
          setState((prev) => ({
            ...prev,
            open,
            dimension: open ? prev.dimension : null,
          }))
        }
        mode={state.mode}
        dimension={state.dimension}
        categories={CATEGORIES}
        mainDimensions={[]}
        algorithmOptions={[]}
        canManage
      />
    </>
  )
}

/** 「权重」行右侧的数值回显（result-section.tsx） */
function weightText(): string | null | undefined {
  const label = screen.getByText('权重').closest('[data-slot="label"]')
  return label?.parentElement?.querySelector('span.tabular-nums')?.textContent
}

async function expectBackfilled(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() =>
    expect(screen.getByLabelText(/维度名称/)).toHaveValue(LIST_ROW.name)
  )
  expect(screen.getByLabelText('描述')).toHaveValue(LIST_ROW.description)
  // 分类闭合态必须回显分类名（回落「未分类」即本卡缺陷表现）
  expect(screen.getByText('拒识')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: '结果配置' }))
  await waitFor(() => expect(weightText()).toBe(String(LIST_ROW.weight)))
  await user.click(screen.getByRole('tab', { name: '基本信息' }))
}

describe('DimensionMutateDrawer 回填（INT-1660）', () => {
  it('连续三次打开同一维度，名称/描述/分类/权重都回填', async () => {
    const user = userEvent.setup()
    detailStore.current = {}
    render(<Harness dimension={LIST_ROW} />)

    for (let round = 1; round <= 3; round += 1) {
      await user.click(screen.getByRole('button', { name: '编辑维度' }))
      await expectBackfilled(user)
      // 取消关闭：抽屉内容卸载
      await user.click(screen.getByRole('button', { name: '取消' }))
      await waitFor(() =>
        expect(screen.queryByLabelText(/维度名称/)).not.toBeInTheDocument()
      )
    }
  })

  it('编辑取消后打开新建维度，表单是空值', async () => {
    const user = userEvent.setup()
    detailStore.current = {}
    render(<Harness dimension={LIST_ROW} />)

    await user.click(screen.getByRole('button', { name: '编辑维度' }))
    await waitFor(() =>
      expect(screen.getByLabelText(/维度名称/)).toHaveValue(LIST_ROW.name)
    )
    await user.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() =>
      expect(screen.queryByLabelText(/维度名称/)).not.toBeInTheDocument()
    )

    await user.click(screen.getByRole('button', { name: '新增维度' }))
    await waitFor(() => expect(screen.getByLabelText(/维度名称/)).toHaveValue(''))
    expect(screen.getByLabelText('描述')).toHaveValue('')
    expect(screen.getByText('未分类')).toBeInTheDocument()
  })

  it('详情到达后重同步输入参数/输出字段（第二次打开同样回填）', async () => {
    const user = userEvent.setup()
    detailStore.current = {}
    const { rerender } = render(<Harness dimension={LIST_ROW} />)

    // 首次打开：详情未命中 → 列表行数据 + 空表单默认行
    await user.click(screen.getByRole('button', { name: '编辑维度' }))
    await waitFor(() =>
      expect(screen.getByLabelText(/维度名称/)).toHaveValue(LIST_ROW.name)
    )
    await user.click(screen.getByRole('tab', { name: 'API配置' }))
    await waitFor(() =>
      expect(screen.getByLabelText('输入参数键名 1')).toHaveValue('asr_result')
    )

    // 详情接口返回 → 抽屉 re-render（hook 返回详情对象）再同步一次全量配置
    detailStore.current = { '101': DETAIL }
    rerender(<Harness dimension={LIST_ROW} />)
    await waitFor(() =>
      expect(screen.getByLabelText('输入参数键名 1')).toHaveValue('custom_param')
    )
    expect(screen.getByLabelText('输出字段代码 1')).toHaveValue('custom_result')

    // 关闭 → 重开同一行：详情走缓存（不发请求，staleTime 30s），字段仍须全量回填
    await user.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() =>
      expect(screen.queryByLabelText(/维度名称/)).not.toBeInTheDocument()
    )
    await user.click(screen.getByRole('button', { name: '编辑维度' }))
    await waitFor(() =>
      expect(screen.getByLabelText(/维度名称/)).toHaveValue(LIST_ROW.name)
    )
    await user.click(screen.getByRole('tab', { name: 'API配置' }))
    await waitFor(() =>
      expect(screen.getByLabelText('输入参数键名 1')).toHaveValue('custom_param')
    )
    expect(screen.getByLabelText('输出字段代码 1')).toHaveValue('custom_result')
  })

  it('空规则维度：不注入默认规则、结果类型 0 显示中文标签、原样保存保留 defaultScore（INT-1732）', async () => {
    const user = userEvent.setup()
    // INT-2247：编辑态以详情为提交基座，详情先就绪再保存
    detailStore.current = { '121': EMPTY_RULE_ROW }
    saveMock.mockClear()
    render(<Harness dimension={EMPTY_RULE_ROW} />)

    await user.click(screen.getByRole('button', { name: '编辑维度' }))
    await waitFor(() =>
      expect(screen.getByLabelText(/维度名称/)).toHaveValue(EMPTY_RULE_ROW.name)
    )
    await user.click(screen.getByRole('tab', { name: '结果配置' }))

    // 空规则：明确提示，且不得凭空出现默认 5 条
    expect(screen.getByTestId('dimension-rule-empty')).toHaveTextContent(
      '该维度未配置评分规则'
    )
    expect(screen.queryByLabelText('规则 1 阈值')).not.toBeInTheDocument()
    // result_type=0 → 中文标签（不再是「请选择结果类型」）
    expect(screen.getByText('未设置')).toBeInTheDocument()
    expect(screen.queryByText('请选择结果类型')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    const payload = saveMock.mock.calls[0][0] as Partial<Dimension>
    expect(payload.rule).toEqual({ rules: [], defaultScore: 7 })
    expect(payload.resultType).toBe(0)
  })

  it('详情未就绪时禁用保存并提示（避免以列表占位配置覆盖真实配置，INT-2247）', async () => {
    const user = userEvent.setup()
    detailStore.current = {}
    saveMock.mockClear()
    render(<Harness dimension={LIST_ROW} />)

    await user.click(screen.getByRole('button', { name: '编辑维度' }))
    await waitFor(() =>
      expect(screen.getByLabelText(/维度名称/)).toHaveValue(LIST_ROW.name)
    )
    expect(screen.getByTestId('dimension-detail-pending')).toHaveTextContent(
      '正在加载维度详情…'
    )
    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
  })
})
