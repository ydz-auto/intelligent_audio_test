/**
 * 首页门户组件测试——StatsBar（INT-379 门户 / INT-1543 平台规模条）：
 * 未登录/无权限降级登录引导、登录态渲染平台规模六项并整项可点击跳转、
 * 无对应权限项不渲染链接、任务/音频副行细分、API 在线率告警（03_首页.md §3.2）。
 * useHomeStats 为真实接口 query（INT-728 接线后），组件测试 mock hook 供稳态数据。
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

const { MOCK_HOME_STATS, homeStatsState } = vi.hoisted(() => {
  const stats = {
    testCases: { total: 579, groups: 6 },
    tasks: { total: 124, completed: 74, running: 1, failed: 38 },
    devices: { online: 3, offline: 0, total: 3 },
    audioFiles: { total: 1953, dry: 1953, noise: 0, prompt: 0 },
    playbackDevices: 12,
    apis: { online: 1, offline: 0, total: 1 },
    reports: 55,
    dimensions: { total: 37, withEndpoints: 0, endpoints: 0 },
    updatedAt: '2026-10-18T11:05:08',
  }
  return {
    MOCK_HOME_STATS: stats,
    homeStatsState: { stats: stats as HomeStatsDetails },
  }
})

vi.mock('@/application/hooks/use-home-stats', () => ({
  useHomeStats: () => ({
    data: homeStatsState.stats,
    isLoading: false,
  }),
}))

const initialAuth = useAuthStore.getState()

beforeEach(() => {
  homeStatsState.stats = MOCK_HOME_STATS
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

  it('权限齐全时六项整项 Link 跳对应管理页', async () => {
    useAuthStore.getState().setAuth({
      id: 'u1',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    await renderStatsBar()
    const expectations: [string, string][] = [
      ['测试用例', '/testcases'],
      ['测试任务', '/tasks'],
      ['评估维度', '/Evaluation'],
      ['音频文件', '/audio-import'],
      ['在线设备', '/devices'],
      ['API 服务', '/APITest'],
    ]
    for (const [name, href] of expectations) {
      expect(screen.getByRole('link', { name })).toHaveAttribute('href', href)
    }
  })

  it('无对应子权限时整项仍展示但不渲染链接', async () => {
    useAuthStore.getState().setAuth({
      id: 'u3',
      username: 'guest',
      displayName: '访客',
      roleName: '访客',
      permissions: ['home:read', 'task:read'],
    })
    await renderStatsBar()
    expect(screen.getByText(/测试用例/)).toBeInTheDocument()
    expect(screen.getByText(/API 服务/)).toBeInTheDocument()
    // 仅任务项有 task:read，其余五项不渲染链接
    expect(screen.getAllByRole('link')).toHaveLength(1)
    expect(screen.getByRole('link', { name: '测试任务' })).toHaveAttribute(
      'href',
      '/tasks'
    )
  })

  it('任务/音频副行按接口细分字段渲染', async () => {
    useAuthStore.getState().setAuth({
      id: 'u1',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    await renderStatsBar()
    expect(
      screen.getByText('测试任务 · 74 已完成 / 1 进行中 / 38 失败')
    ).toBeInTheDocument()
    expect(
      screen.getByText('音频文件 · 1953 干音 / 0 噪声 / 0 提示音')
    ).toBeInTheDocument()
  })

  it('API 在线率低于阈值标 Alert 色并附故障告警角标', async () => {
    homeStatsState.stats = {
      ...MOCK_HOME_STATS,
      apis: { online: 1, offline: 2, total: 3 },
    }
    useAuthStore.getState().setAuth({
      id: 'u1',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    await renderStatsBar()
    expect(screen.getByText('故障告警')).toBeInTheDocument()
    expect(screen.getByText(/API 服务/)).toHaveClass('text-destructive')
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
