/**
 * 角色权限管理弹窗校验/关闭时机测试（INT-1586）：
 * 新建/编辑名称留空（含全空格）前端拦截、零请求、字段级红字 + aria-invalid；
 * 提交失败弹窗保持打开且输入保留，成功才关闭。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RolesPage } from '@/features/system-settings/iam/roles-page'
import type { PlatformRole } from '@/domain/models/role'

const { createMutateAsync, updateMutateAsync, permissionsMutateAsync, state } = vi.hoisted(
  () => ({
    createMutateAsync: vi.fn(),
    updateMutateAsync: vi.fn(),
    permissionsMutateAsync: vi.fn(),
    state: { roles: [] as PlatformRole[] },
  })
)

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ user: null, hasPermission: () => true, hasAnyPermission: () => true }),
}))

vi.mock('@/application/iam/use-users-query', () => ({
  useUsersQuery: () => ({ data: [], isLoading: false, isError: false }),
}))

vi.mock('@/application/iam/use-roles-query', () => ({
  useRolesQuery: () => ({
    data: state.roles,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  usePermissionCatalogQuery: () => ({ data: [] }),
  useRoleMutations: () => ({
    createRole: { mutateAsync: createMutateAsync, isPending: false },
    updateRole: { mutateAsync: updateMutateAsync, isPending: false },
    setPermissions: { mutateAsync: permissionsMutateAsync, isPending: false },
    deleteRole: { mutate: vi.fn(), isPending: false },
  }),
}))

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  render(
    <QueryClientProvider client={client}>
      <RolesPage />
    </QueryClientProvider>
  )
}

async function openCreateDialog() {
  const user = userEvent.setup()
  renderPage()
  await user.click(screen.getByRole('button', { name: /新建角色/ }))
  await screen.findByText('新建角色')
  return user
}

const TEST_ROLE: PlatformRole = {
  id: '42',
  code: 'custom_role',
  name: '接线测试_编辑角色',
  description: '初始描述',
  isSystem: false,
  permissions: ['log:read'],
  userCount: 0,
}

async function openEditDialog() {
  state.roles = [TEST_ROLE]
  const user = userEvent.setup()
  renderPage()
  await user.click(screen.getByRole('button', { name: /角色操作：接线测试_编辑角色/ }))
  await user.click(await screen.findByRole('menuitem', { name: '编辑' }))
  await screen.findByText('编辑角色')
  return user
}

describe('角色弹窗必填校验与关闭时机', () => {
  beforeEach(() => {
    createMutateAsync.mockReset()
    updateMutateAsync.mockReset()
    permissionsMutateAsync.mockReset()
    updateMutateAsync.mockResolvedValue(undefined)
    permissionsMutateAsync.mockResolvedValue(undefined)
    state.roles = []
  })

  it('新建态名称留空提交：零请求 + 字段红字 + aria-invalid，弹窗保持', async () => {
    const user = await openCreateDialog()

    await user.click(screen.getByRole('button', { name: '创建' }))

    expect(screen.getByText('请输入角色名称')).toBeInTheDocument()
    expect(document.getElementById('role-name')).toHaveAttribute('aria-invalid', 'true')
    expect(createMutateAsync).not.toHaveBeenCalled()
    expect(screen.getByText('新建角色')).toBeInTheDocument()
  })

  it('新建态名称全空格同样拦截（trim 后判空）', async () => {
    const user = await openCreateDialog()

    await user.type(screen.getByLabelText(/角色名称/), '   ')
    await user.click(screen.getByRole('button', { name: '创建' }))

    expect(screen.getByText('请输入角色名称')).toBeInTheDocument()
    expect(createMutateAsync).not.toHaveBeenCalled()
  })

  it('输入后清空字段错误；成功提交 trim 名称并在成功后关闭弹窗', async () => {
    createMutateAsync.mockResolvedValue(TEST_ROLE)
    const user = await openCreateDialog()

    await user.click(screen.getByRole('button', { name: '创建' }))
    expect(screen.getByText('请输入角色名称')).toBeInTheDocument()

    await user.type(screen.getByLabelText(/角色名称/), '  接线测试_空名校验  ')
    expect(screen.queryByText('请输入角色名称')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    expect(createMutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ name: '接线测试_空名校验' })
    )
    await waitFor(() => expect(screen.queryByText('新建角色')).not.toBeInTheDocument())
  })

  it('提交失败：弹窗保持打开、名称/描述仍保留', async () => {
    createMutateAsync.mockRejectedValue(new Error('name 为必填项'))
    const user = await openCreateDialog()

    await user.type(screen.getByLabelText(/角色名称/), '接线测试_失败保留')
    await user.type(screen.getByLabelText('描述'), '保留描述')
    await user.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    expect(screen.getByText('新建角色')).toBeInTheDocument()
    expect(screen.getByLabelText(/角色名称/)).toHaveValue('接线测试_失败保留')
    expect(screen.getByLabelText('描述')).toHaveValue('保留描述')
  })

  it('编辑态清空名称保存：前端拦截零请求（不弹二次确认）', async () => {
    const user = await openEditDialog()

    const nameInput = screen.getByLabelText(/角色名称/)
    await user.clear(nameInput)
    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(screen.getByText('请输入角色名称')).toBeInTheDocument()
    expect(screen.queryByText('确认保存角色权限')).not.toBeInTheDocument()
    expect(updateMutateAsync).not.toHaveBeenCalled()
    expect(permissionsMutateAsync).not.toHaveBeenCalled()
  })

  it('编辑态提交失败：弹窗保持打开，输入与名称保留', async () => {
    updateMutateAsync.mockRejectedValue(new Error('角色名称已存在'))
    const user = await openEditDialog()

    const nameInput = screen.getByLabelText(/角色名称/)
    await user.clear(nameInput)
    await user.type(nameInput, '接线测试_改名失败')
    await user.click(screen.getByRole('button', { name: '保存' }))
    await user.click(await screen.findByRole('button', { name: '确认保存' }))

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1))
    expect(screen.getByText('编辑角色')).toBeInTheDocument()
    expect(screen.getByLabelText(/角色名称/)).toHaveValue('接线测试_改名失败')
  })

  it('编辑态保存成功才关闭弹窗', async () => {
    const user = await openEditDialog()

    const nameInput = screen.getByLabelText(/角色名称/)
    await user.clear(nameInput)
    await user.type(nameInput, '接线测试_改名成功')
    await user.click(screen.getByRole('button', { name: '保存' }))
    await user.click(await screen.findByRole('button', { name: '确认保存' }))

    await waitFor(() => expect(permissionsMutateAsync).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.queryByText('编辑角色')).not.toBeInTheDocument())
  })
})
