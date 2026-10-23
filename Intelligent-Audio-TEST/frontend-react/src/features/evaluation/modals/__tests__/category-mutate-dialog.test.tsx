/**
 * 分类编辑弹窗回填回归（INT-1577）：取消关闭后重开同一分类，名称/描述/图标必须回填。
 * 旧实现用 useForm 的 values 同步，关闭时 form.reset 清空后重开同一分类（值深相等）
 * 会被 react-hook-form 的深比较判重跳过 → 三项全空；改为按 open/category 显式 reset。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'

import type { EvaluationCategory } from '@/domain/models/evaluationDimension'
import { CategoryMutateDialog } from '@/features/evaluation/modals/category-mutate-dialog'

const CATEGORY_A: EvaluationCategory = {
  id: 101,
  name: '接线测试_INT1577_分类A',
  description: '分类 A 描述',
  icon: 'fas fa-microphone',
}

/** 复刻评估维度页的受控用法：关闭时把 category 置空。 */
function Harness({ category }: { category: EvaluationCategory }) {
  const [state, setState] = useState<{
    open: boolean
    category: EvaluationCategory | null
  }>({ open: false, category: null })

  return (
    <>
      <button
        type='button'
        onClick={() => setState({ open: true, category })}
      >
        编辑分类
      </button>
      <button
        type='button'
        onClick={() => setState({ open: true, category: null })}
      >
        新建分类
      </button>
      <CategoryMutateDialog
        open={state.open}
        onOpenChange={(open) =>
          setState((prev) => ({
            ...prev,
            open,
            category: open ? prev.category : null,
          }))
        }
        category={state.category}
        onSave={async () => {}}
      />
    </>
  )
}

describe('CategoryMutateDialog 回填', () => {
  it('连续两次打开同一分类时名称/描述/图标都回填', async () => {
    const user = userEvent.setup()
    render(<Harness category={CATEGORY_A} />)

    // 第一次打开
    await user.click(screen.getByRole('button', { name: '编辑分类' }))
    await waitFor(() =>
      expect(screen.getByLabelText(/分类名称/)).toHaveValue(CATEGORY_A.name)
    )
    expect(screen.getByLabelText('描述')).toHaveValue(CATEGORY_A.description)
    expect(screen.getByLabelText('图标')).toHaveValue(CATEGORY_A.icon)

    // 取消关闭
    await user.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() =>
      expect(screen.queryByLabelText(/分类名称/)).not.toBeInTheDocument()
    )

    // 重开同一分类（同一对象引用）
    await user.click(screen.getByRole('button', { name: '编辑分类' }))
    await waitFor(() =>
      expect(screen.getByLabelText(/分类名称/)).toHaveValue(CATEGORY_A.name)
    )
    expect(screen.getByLabelText('描述')).toHaveValue(CATEGORY_A.description)
    expect(screen.getByLabelText('图标')).toHaveValue(CATEGORY_A.icon)
  })

  it('编辑弹窗取消后打开新建分类，表单是空值', async () => {
    const user = userEvent.setup()
    render(<Harness category={CATEGORY_A} />)

    await user.click(screen.getByRole('button', { name: '编辑分类' }))
    await waitFor(() =>
      expect(screen.getByLabelText(/分类名称/)).toHaveValue(CATEGORY_A.name)
    )
    await user.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() =>
      expect(screen.queryByLabelText(/分类名称/)).not.toBeInTheDocument()
    )

    await user.click(screen.getByRole('button', { name: '新建分类' }))
    await waitFor(() => expect(screen.getByLabelText(/分类名称/)).toHaveValue(''))
    expect(screen.getByLabelText('描述')).toHaveValue('')
    expect(screen.getByLabelText('图标')).not.toHaveValue(CATEGORY_A.icon)
  })
})
