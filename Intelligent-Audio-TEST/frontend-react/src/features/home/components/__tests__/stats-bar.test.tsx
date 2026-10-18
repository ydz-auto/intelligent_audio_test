/**
 * 首页门户组件测试——StatsBar（INT-379 门户）：未登录/无权限降级登录引导、
 * 登录态渲染平台规模六项（03_首页.md §3.2 尾部）。
 */
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { StatsBar } from '@/features/home/components/stats-bar'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import type { HomeStatsDetails } from '@/domain/models/home'

vi.mock('@/infrastructure/api/home', () => ({
  fetchHomeStatsDetails: vi.fn().mockResolvedValue({
    test_cases: { total: 128, groups: 32 },
    tasks: { total: 342, completed: 200, running: 10, failed: 5 },
    devices: { online: 50, offline: 10, total: 60 },
    audio_files: { total: 1560, dry: 1200, noise: 200, prompt: 160 },
    playback_devices: 10,
    apis: { online: 8, offline: 2, total: 10 },
    reports: 45,
    dimensions: { total: 38, with_endpoints: 30, endpoints: 26 },
    updated_at: '2026-10-18T00:00:00',
  } satisfies HomeStatsDetails),
}))

const initialAuth = useAuthStore.getState()

beforeEach(() => {
  useAuthStore.getState().setAuth(null)
})

afterEach(() => {
  useAuthStore.setState(initialAuth)
})

/** StatsBar 未登录态渲染 <Link to='/login'>，需 router 上下文（对位 newAPI render 模式） */
async function renderStatsBar() {
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => <StatsBar />,
    }),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  await router.load()
  render(<RouterProvider router={router} />)
}

describe('StatsBar', () => {
  it('未登录渲染登录引导而非数据', async () => {
    await renderStatsBar()
    expect(
      screen.getByText('登录后可查看平台实时规模')
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: '登录' })
    ).toBeInTheDocument()
    expect(screen.queryByText('平台规模')).not.toBeInTheDocument()
  })

  it('登录且具备 home:read 渲染六项规模指标', async () => {
    useAuthStore.getState().setAuth({
      id: 'u1',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    await renderStatsBar()
    expect(await screen.findByText(/测试用例/)).toBeInTheDocument()
    expect(screen.getByText(/测试任务/)).toBeInTheDocument()
    expect(screen.getByText(/评估维度/)).toBeInTheDocument()
    expect(screen.getByText(/音频文件/)).toBeInTheDocument()
    expect(screen.getByText(/在线设备/)).toBeInTheDocument()
    expect(screen.getByText(/API 服务/)).toBeInTheDocument()
    expect(
      screen.queryByText('登录后可查看平台实时规模')
    ).not.toBeInTheDocument()
  })

  it('登录但缺 home:read 权限仍降级为登录引导', async () => {
    useAuthStore.getState().setAuth({
      id: 'u2',
      username: 'guest',
      displayName: '访客',
      roleName: '访客',
      permissions: ['task:read'],
    })
    await renderStatsBar()
    expect(
      screen.getByText('登录后可查看平台实时规模')
    ).toBeInTheDocument()
  })
})
