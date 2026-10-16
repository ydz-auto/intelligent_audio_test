/**
 * 导航壳/侧栏组件测试——NavGroup（INT-377 基座）：组标题/链接项渲染、
 * 激活态 data-active、折叠子菜单展开。
 */
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClipboardList, Activity, ListChecks } from 'lucide-react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { NavGroup } from '@/components/layout/components/nav-group'
import { SidebarProvider } from '@/components/ui/sidebar'

const linkItems = [
  {
    title: '工作台',
    url: '/dashboard',
    icon: Activity,
    requiredPermission: 'home:read',
  },
  {
    title: '任务管理',
    url: '/tasks',
    icon: ClipboardList,
    requiredPermission: 'task:read',
  },
]

const collapsibleItems = [
  {
    title: '系统设置',
    items: [
      { title: '站点设置', url: '/system-settings/site' },
      { title: '用户管理', url: '/system-settings/users' },
    ],
  },
]

async function renderNavGroup(
  ui: ReactNode,
  initialEntry = '/dashboard'
) {
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => <SidebarProvider>{ui}</SidebarProvider>,
    }),
    history: createMemoryHistory({ initialEntries: [initialEntry] }),
  })
  await router.load()
  render(<RouterProvider router={router} />)
}

describe('NavGroup', () => {
  it('渲染组标题与全部链接项', async () => {
    await renderNavGroup(<NavGroup title='总览' items={linkItems} />)
    expect(screen.getByText('总览')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '工作台' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '任务管理' })).toBeInTheDocument()
  })

  it('当前路径命中项带 data-active 激活态', async () => {
    await renderNavGroup(
      <NavGroup title='总览' items={linkItems} />,
      '/tasks'
    )
    expect(
      screen.getByRole('link', { name: '任务管理' })
    ).toHaveAttribute('data-active')
    expect(
      screen.getByRole('link', { name: '工作台' })
    ).not.toHaveAttribute('data-active')
  })

  it('折叠子菜单项渲染并可展开子项', async () => {
    await renderNavGroup(
      <NavGroup title='管理' items={collapsibleItems} />,
      '/dashboard'
    )
    const trigger = screen.getByRole('button', { name: '系统设置' })
    await userEvent.click(trigger)
    expect(screen.getByRole('link', { name: '站点设置' })).toHaveAttribute(
      'href',
      '/system-settings/site'
    )
    expect(
      screen.getByRole('link', { name: '用户管理' })
    ).toBeInTheDocument()
  })

  it('INT-490 P1：activeUrls 前缀命中子路径——/testcases/by-group 高亮「用例管理」', async () => {
    const items = [
      {
        title: '用例管理',
        url: '/testcases',
        icon: ListChecks,
        requiredPermission: 'testcase:read',
        activeUrls: ['/testcases'],
      },
    ]
    await renderNavGroup(
      <NavGroup title='测试资产' items={items} />,
      '/testcases/by-group'
    )
    expect(
      screen.getByRole('link', { name: '用例管理' })
    ).toHaveAttribute('data-active')
  })
})
