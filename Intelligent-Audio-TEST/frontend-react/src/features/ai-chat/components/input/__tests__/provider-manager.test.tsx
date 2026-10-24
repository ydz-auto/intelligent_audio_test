/**
 * LLM 供应商管理弹窗组件测试（INT-1596 回归）。
 * 覆盖两条审计缺陷：
 * 1. 模型行 key 曾含输入值，每敲一个字符整行 input 重建 → 只保留首字符、焦点丢失；
 * 2. 校验红字只在保存时重算 → 字段已填合法值仍挂在输入框下方。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ProviderManager } from '../provider-manager'

function renderManager() {
  const onAdd = vi.fn()
  render(
    <ProviderManager
      onAdd={onAdd}
      onFetchModels={vi.fn().mockResolvedValue([])}
      onOpenChange={vi.fn()}
      onRemove={vi.fn()}
      onSetDefault={vi.fn()}
      onTestConnection={vi.fn().mockResolvedValue({ ok: true, models: [] })}
      onUpdate={vi.fn()}
      open
      providers={[]}
    />
  )
  return { onAdd }
}

async function openAddForm() {
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /添加供应商/ }))
  await screen.findByLabelText('名称')
  return user
}

describe('ProviderManager 模型列表手动输入（INT-1596 缺陷 1）', () => {
  it('逐字符输入多字符模型 id 时保留完整值且焦点不丢失', async () => {
    renderManager()
    const user = await openAddForm()

    await user.click(screen.getByRole('button', { name: /添加模型/ }))
    const modelInput = screen.getByPlaceholderText('如 gpt-4o') as HTMLInputElement

    await user.type(modelInput, 'gd-4o')

    expect(modelInput.value).toBe('gd-4o')
    expect(document.activeElement).toBe(modelInput)
  })

  it('两行模型各自输入后都保留完整值并随保存提交', async () => {
    const { onAdd } = renderManager()
    const user = await openAddForm()

    await user.type(screen.getByLabelText('名称'), '接线测试_供应商')
    await user.type(screen.getByLabelText('API Base URL'), 'https://api.example.com/v1')
    await user.type(screen.getByLabelText('API Key'), 'sk-test')

    await user.click(screen.getByRole('button', { name: /添加模型/ }))
    await user.click(screen.getByRole('button', { name: /添加模型/ }))
    const [first, second] = screen.getAllByPlaceholderText('如 gpt-4o') as HTMLInputElement[]

    await user.type(first, 'audit-model-a')
    await user.type(second, 'audit-model-b')

    expect(first.value).toBe('audit-model-a')
    expect(second.value).toBe('audit-model-b')

    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1))
    expect(onAdd.mock.calls[0][0].models).toEqual(['audit-model-a', 'audit-model-b'])
  })
})

describe('ProviderManager 校验红字（INT-1596 缺陷 2）', () => {
  it('空表单保存出现三条红字，逐项填好后即时消失', async () => {
    renderManager()
    const user = await openAddForm()

    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(await screen.findByText('请输入供应商名称')).toBeInTheDocument()
    expect(screen.getByText('请输入 API Base URL')).toBeInTheDocument()
    expect(screen.getByText('请输入 API Key')).toBeInTheDocument()

    await user.type(screen.getByLabelText('名称'), '接线测试_供应商')
    await waitFor(() => expect(screen.queryByText('请输入供应商名称')).not.toBeInTheDocument())

    await user.type(screen.getByLabelText('API Base URL'), 'https://api.example.com/v1')
    await waitFor(() => expect(screen.queryByText('请输入 API Base URL')).not.toBeInTheDocument())

    await user.type(screen.getByLabelText('API Key'), 'sk-test')
    await waitFor(() => expect(screen.queryByText('请输入 API Key')).not.toBeInTheDocument())
  })

  it('只填空格不清红字（未满足非空校验）', async () => {
    renderManager()
    const user = await openAddForm()

    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByText('请输入供应商名称')).toBeInTheDocument()

    await user.type(screen.getByLabelText('名称'), '   ')
    expect(screen.getByText('请输入供应商名称')).toBeInTheDocument()
  })
})
