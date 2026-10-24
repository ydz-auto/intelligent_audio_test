/**
 * 用例表单标签 Combobox 测试（11_用例域.md §5.1「标签」，INT-1591）：
 * - chips：回车 / 逗号落 chip、✕ 移除；
 * - 建议下拉：GET /tags/names（keyword 服务端搜索）候选 + 已添加项置灰禁选；
 * - 输入词无同名候选 → 「新建「{词}」」创建项落 chip。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CaseTagCombobox } from '@/features/testcases/modals/case-tag-combobox'
import { fetchTagNames } from '@/infrastructure/api/tags-api'

vi.mock('@/infrastructure/api/tags-api', () => ({
  fetchTagNames: vi.fn(),
}))

const mockedFetchTagNames = vi.mocked(fetchTagNames)

const setup = (value: string[] = []) => {
  const onChange = vi.fn()
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <CaseTagCombobox value={value} onChange={onChange} />
    </QueryClientProvider>
  )
  return { onChange }
}

describe('CaseTagCombobox（§5.1 标签 Combobox，INT-1591）', () => {
  beforeEach(() => {
    mockedFetchTagNames.mockReset()
    mockedFetchTagNames.mockResolvedValue(['标签1', '标签2', '标签3'])
  })

  it('聚焦输入框按 GET /tags/names 拉候选并展开下拉', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(screen.getByRole('combobox', { name: '标签' }))

    const listbox = await screen.findByRole('listbox')
    expect(listbox).toBeInTheDocument()
    expect(mockedFetchTagNames).toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.getByRole('option', { name: '标签1' })).toBeInTheDocument()
    )
  })

  it('输入词按 keyword 走服务端搜索（防抖后带 keyword 请求）', async () => {
    const user = userEvent.setup()
    setup()

    await user.type(screen.getByRole('combobox', { name: '标签' }), '标签2')

    await waitFor(() =>
      expect(mockedFetchTagNames).toHaveBeenLastCalledWith('标签2')
    )
  })

  it('已添加项置灰禁选（disabled）', async () => {
    const user = userEvent.setup()
    setup(['标签1'])

    await user.click(screen.getByRole('combobox', { name: '标签' }))
    await screen.findByRole('listbox')

    const added = await screen.findByRole('option', { name: /标签1/ })
    expect(added).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('option', { name: '标签2' })).not.toHaveAttribute(
      'aria-disabled',
      'true'
    )
  })

  it('输入词无同名候选时给「新建「{词}」」项，点选落 chip', async () => {
    const user = userEvent.setup()
    const { onChange } = setup()

    await user.type(screen.getByRole('combobox', { name: '标签' }), '接线测试新标签')
    const createItem = await screen.findByRole('option', {
      name: /新建「接线测试新标签」/,
    })
    await user.click(createItem)

    expect(onChange).toHaveBeenCalledWith(['接线测试新标签'])
  })

  it('回车把当前输入落 chip（原 TagInput 语义不回退）', async () => {
    const user = userEvent.setup()
    const { onChange } = setup()

    const input = screen.getByRole('combobox', { name: '标签' })
    await user.type(input, '自由标签{Enter}')

    expect(onChange).toHaveBeenCalledWith(['自由标签'])
  })

  it('逗号把当前输入落 chip', async () => {
    const user = userEvent.setup()
    const { onChange } = setup()

    await user.type(screen.getByRole('combobox', { name: '标签' }), '逗号标签,')
    expect(onChange).toHaveBeenCalledWith(['逗号标签'])
  })

  it('✕ 移除已选 chip', async () => {
    const user = userEvent.setup()
    const { onChange } = setup(['标签1', '标签2'])

    await user.click(screen.getByRole('button', { name: '移除标签 标签1' }))
    expect(onChange).toHaveBeenCalledWith(['标签2'])
  })
})
