/**
 * 容器详情「再次挑选」入口组件测试（18_挑选合并功能交互重设计.md §5.5.5，INT-1717）。
 * 覆盖：整批源结果加购 + toast 文案口径 + 打开购物车抽屉、「开始挑选」跨页开向导、
 * 无来源时按钮禁用（不臆造空加购请求）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  addEntries: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mocks.navigate,
}))

vi.mock('@/application/tasks/cherry-pick/use-pick-cart-store', () => ({
  usePickCartStore: (selector: (state: { addEntries: typeof mocks.addEntries }) => unknown) =>
    selector({ addEntries: mocks.addEntries }),
}))

vi.mock('@/features/tasks/cherry-pick/components/cart-drawer', () => ({
  CartDrawer: ({ open }: { open: boolean }) => (
    <div data-testid='cart-drawer' data-open={String(open)} />
  ),
}))

vi.mock('sonner', () => ({
  toast: { success: mocks.toastSuccess, error: mocks.toastError },
}))

import {
  ContainerRePickActions,
  describeAddToCartToast,
} from '@/features/tasks/detail/container-repick-actions'

describe('describeAddToCartToast（§5.5.5 toast 口径）', () => {
  it('失效优先：有失效条目时带失效数', () => {
    expect(describeAddToCartToast(3, 1, 2)).toBe('已加入购物车 3 条（2 条源结果已失效未加入）')
  })

  it('重复跳过：无失效时带重复数', () => {
    expect(describeAddToCartToast(2, 1, 0)).toBe('已加入购物车 2 条（重复 1 条已跳过）')
  })

  it('全部新增：只报条数', () => {
    expect(describeAddToCartToast(4, 0, 0)).toBe('已加入购物车 4 条')
  })

  it('全部重复：说明已跳过', () => {
    expect(describeAddToCartToast(0, 3, 0)).toBe('已加入购物车（重复条目已跳过）')
  })
})

describe('ContainerRePickActions（§5.5.5）', () => {
  beforeEach(() => {
    mocks.navigate.mockReset()
    mocks.addEntries.mockReset()
    mocks.toastSuccess.mockReset()
    mocks.toastError.mockReset()
  })

  it('复用本次结果：整批 result_id 加购 → toast → 打开购物车抽屉', async () => {
    mocks.addEntries.mockResolvedValue({ addedCount: 3, skippedCount: 1, invalidCount: 0 })
    render(<ContainerRePickActions resultIds={[5714, 3832, 3792]} />)

    fireEvent.click(screen.getByTestId('container-repick-reuse'))

    expect(mocks.addEntries).toHaveBeenCalledWith([5714, 3832, 3792])
    expect(await screen.findByTestId('cart-drawer')).toHaveAttribute('data-open', 'true')
    expect(mocks.toastSuccess).toHaveBeenCalledWith('已加入购物车 3 条（重复 1 条已跳过）')
    // 不复制容器、不新建任务：只有加购一次，没有额外导航
    expect(mocks.navigate).not.toHaveBeenCalled()
  })

  it('开始挑选：跨页打开挑选向导阶段 1', () => {
    render(<ContainerRePickActions resultIds={[5714]} />)

    fireEvent.click(screen.getByTestId('container-repick-start'))

    expect(mocks.navigate).toHaveBeenCalledWith({
      to: '/tasks/$tab',
      params: { tab: 'cherry-picks' },
      search: { wizard: 'pick' },
    })
    expect(mocks.addEntries).not.toHaveBeenCalled()
  })

  it('无来源记录：复用按钮禁用且不发请求', () => {
    render(<ContainerRePickActions resultIds={[]} />)

    const button = screen.getByTestId('container-repick-reuse')
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(mocks.addEntries).not.toHaveBeenCalled()
  })
})
