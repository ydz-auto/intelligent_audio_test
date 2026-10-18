/**
 * 版本与服务状态卡组件测试（INT-732 返修：mock 健康数据 → 真实 /api/v1/system/health
 * 汇总端点；端点未落地 → 请求失败 → 规范降级态）。口径（06_关于.md §3.1.1/§4.4）：
 * 成功 → 正常态三徽章 + 版本 + 数据库；请求失败 → 版本「—」+ 三徽章「检测中」+
 * Alert「服务状态检测失败，请稍后重试或联系管理员。」；网关/认证 status 非 ok →
 * 对应行「异常」destructive；且正文（AboutContent）不被阻断。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { SystemHealthResponse } from '@/domain/models/about'

import { ABOUT_DOCUMENT } from '@/infrastructure/content/aboutAssets'

import { AboutContent } from '../about-content'
import { AboutStatusCard } from '../about-status-card'

const systemHealthFetch = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/healthApi', () => ({
  fetchSystemHealth: systemHealthFetch,
}))

/** 汇总端点成功响应（网关 ok + 认证 ok） */
const gatewayOk = {
  status: 'ok',
  service: 'api_gateway',
  version: 'V9.7.31',
  database: 'intelligent_audio_test',
}
const authOk = { status: 'ok', service: 'auth_service' }

/** 模拟关于页 md 分支：正文 + 状态卡同屏（断言「失败不阻断正文」） */
function renderAboutWithStatus() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AboutContent content={ABOUT_DOCUMENT} />
      <AboutStatusCard />
    </QueryClientProvider>
  )
}

/** 状态卡根节点（data-slot=card），断言限域在卡内、避免与正文文案同名冲突 */
function statusCardScope() {
  // 正文 about.md 含「## 版本与服务状态」标题，取卡内 CardTitle 的卡根
  const title = screen
    .getAllByText('版本与服务状态')
    .find((element) => element.closest('[data-slot="card"]'))
  const root = title?.closest('[data-slot="card"]') as HTMLElement
  return within(root)
}

describe('AboutStatusCard', () => {
  it('/api/v1/system/health 成功 → 版本 V9.7.31 + 三徽章「正常」+ 数据库名，无提示条', async () => {
    systemHealthFetch.mockResolvedValue({
      gateway: gatewayOk,
      auth: authOk,
    } satisfies SystemHealthResponse)
    renderAboutWithStatus()

    const card = statusCardScope()
    await waitFor(() => expect(card.getAllByText('正常')).toHaveLength(3))
    expect(card.getByText('V9.7.31')).toBeVisible()
    expect(card.getByText('intelligent_audio_test')).toBeInTheDocument()
    expect(
      card.queryByText('服务状态检测失败，请稍后重试或联系管理员。')
    ).not.toBeInTheDocument()
  })

  it('/api/v1/system/health 整卡失败 → 版本「—」+ 三徽章「检测中」+ 提示条，且正文不阻断', async () => {
    systemHealthFetch.mockRejectedValue(new Error('system health down'))
    renderAboutWithStatus()

    const card = statusCardScope()
    await waitFor(() => expect(card.getAllByText('检测中')).toHaveLength(3))
    expect(card.getAllByText('—')).toHaveLength(4)
    expect(
      card.getByText('服务状态检测失败，请稍后重试或联系管理员。')
    ).toBeInTheDocument()
    // 正文不受影响（「不阻断正文」）
    expect(
      screen.getByRole('heading', { name: '关于智能语音测试平台', level: 1 })
    ).toBeVisible()
  })

  it('网关 status 非 ok → 版本/网关行「异常」（destructive），认证独立判定仍正常，无提示条', async () => {
    systemHealthFetch.mockResolvedValue({
      gateway: { ...gatewayOk, status: 'error' },
      auth: authOk,
    } satisfies SystemHealthResponse)
    renderAboutWithStatus()

    const card = statusCardScope()
    await waitFor(() => expect(card.getAllByText('异常')).toHaveLength(2))
    expect(card.getAllByText('正常')).toHaveLength(1)
    expect(card.getByText('V9.7.31')).toBeVisible()
    expect(
      card.queryByText('服务状态检测失败，请稍后重试或联系管理员。')
    ).not.toBeInTheDocument()
  })

  it('认证 status 非 ok → 仅认证行「异常」，网关/版本保持正常，无提示条', async () => {
    systemHealthFetch.mockResolvedValue({
      gateway: gatewayOk,
      auth: { ...authOk, status: 'error' },
    } satisfies SystemHealthResponse)
    renderAboutWithStatus()

    const card = statusCardScope()
    await waitFor(() => expect(card.getAllByText('异常')).toHaveLength(1))
    expect(card.getAllByText('正常')).toHaveLength(2)
    expect(card.getByText('V9.7.31')).toBeVisible()
    expect(card.getByText('intelligent_audio_test')).toBeInTheDocument()
    expect(
      card.queryByText('服务状态检测失败，请稍后重试或联系管理员。')
    ).not.toBeInTheDocument()
  })
})
