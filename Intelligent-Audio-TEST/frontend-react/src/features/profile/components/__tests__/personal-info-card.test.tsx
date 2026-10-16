/**
 * 个人信息卡组件测试（13_个人中心.md §3.4/§3.4.1）：
 * 只读行渲染 / 权限概览 Popover——通配态单行 vs 普通权限按模块分组展示。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import type { AuthUser } from '@/domain/models/user'
import { PersonalInfoCard } from '@/features/profile/components/personal-info-card'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

function setStoreUser(user: AuthUser | null) {
  useAuthStore.setState({ user })
}

afterEach(() => {
  setStoreUser(null)
})

describe('PersonalInfoCard', () => {
  it('渲染只读信息行（用户名/角色/用户 ID/邮箱/权限概览）', () => {
    setStoreUser({
      id: 'user-001',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    render(<PersonalInfoCard />)

    expect(screen.getByText('个人信息')).toBeInTheDocument()
    expect(screen.getByText('账号基础信息与权限概览')).toBeInTheDocument()
    expect(screen.getByText('@demo_admin')).toBeInTheDocument()
    expect(screen.getByText('超级管理员')).toBeInTheDocument()
    expect(screen.getByText('user-001')).toBeInTheDocument()
    expect(screen.getByText('邮箱')).toBeInTheDocument()
    expect(
      screen.getByText('当前页面为只读展示。如需修改用户名、邮箱或重置密码，请联系平台管理员。')
    ).toBeInTheDocument()
  })

  it('通配权限（*）→ 权限概览 Popover 显示单行通配文案', async () => {
    const user = userEvent.setup()
    setStoreUser({
      id: 'user-001',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    render(<PersonalInfoCard />)

    // 徽章显示权限数量（['*'] → 1 项）
    expect(screen.getByText('1 项权限')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '查看权限清单' }))
    expect(
      await screen.findByText('超级管理员持有全部权限（通配 *）')
    ).toBeInTheDocument()
  })

  it('普通权限 → 权限清单按模块分组展示权限码', async () => {
    const user = userEvent.setup()
    setStoreUser({
      id: 'user-002',
      username: 'tester',
      displayName: '测试工程师',
      roleName: '测试工程师',
      permissions: ['task:read', 'task:create', 'report:read'],
    })
    render(<PersonalInfoCard />)

    expect(screen.getByText('3 项权限')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '查看权限清单' }))

    expect(
      await screen.findByText('当前账号在角色权限基础上生效的权限码')
    ).toBeInTheDocument()
    // 模块组头（去重排序）：report（1）/ task（2）
    expect(screen.getByText('report（1）')).toBeInTheDocument()
    expect(screen.getByText('task（2）')).toBeInTheDocument()
    expect(screen.getByText('task:read')).toBeInTheDocument()
    expect(screen.getByText('task:create')).toBeInTheDocument()
    expect(screen.getByText('report:read')).toBeInTheDocument()
  })
})
