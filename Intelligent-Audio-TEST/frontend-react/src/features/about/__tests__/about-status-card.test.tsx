/**
 * 版本与服务状态卡组件测试（INT-460 返修 P2-1，交付清单#8 口径⑤）：
 * /health 成功 → 正常态三徽章 + 版本 + 数据库；请求失败 → 版本「—」+ 三徽章
 * 「检测中」+ Alert「服务状态检测失败，请稍后重试或联系管理员。」
 * 且正文（AboutContent）不被阻断（06_关于.md §3.1.1/§4.4）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ABOUT_DOCUMENT } from '@/infrastructure/content/aboutAssets'

import { AboutContent } from '../about-content'
import { AboutStatusCard } from '../about-status-card'

const gatewayFetch = vi.hoisted(() => vi.fn())
const authFetch = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/healthApi', () => ({
  MOCK_GATEWAY_HEALTH: {
    status: 'ok',
    service: 'api_gateway',
    version: 'V9.7.31',
    database: 'intelligent_audio_test',
  },
  MOCK_AUTH_HEALTH: { status: 'ok', service: 'auth_service' },
  fetchGatewayHealth: gatewayFetch,
  fetchAuthHealth: authFetch,
}))

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
  it('/health 成功 → 版本 V9.7.31 + 三徽章「正常」+ 数据库名，无提示条', async () => {
    gatewayFetch.mockResolvedValue({
      status: 'ok',
      service: 'api_gateway',
      version: 'V9.7.31',
      database: 'intelligent_audio_test',
    })
    authFetch.mockResolvedValue({ status: 'ok', service: 'auth_service' })
    renderAboutWithStatus()

    const card = statusCardScope()
    await waitFor(() => expect(card.getAllByText('正常')).toHaveLength(3))
    expect(card.getByText('V9.7.31')).toBeVisible()
    expect(card.getByText('intelligent_audio_test')).toBeInTheDocument()
    expect(
      card.queryByText('服务状态检测失败，请稍后重试或联系管理员。')
    ).not.toBeInTheDocument()
  })

  it('/health 整卡失败 → 版本「—」+ 三徽章「检测中」+ 提示条，且正文不阻断', async () => {
    gatewayFetch.mockRejectedValue(new Error('gateway down'))
    authFetch.mockRejectedValue(new Error('auth down'))
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

  it('网关失败但认证 ok → 全卡随网关降级（认证行亦「检测中」）', async () => {
    gatewayFetch.mockRejectedValue(new Error('gateway down'))
    authFetch.mockResolvedValue({ status: 'ok', service: 'auth_service' })
    renderAboutWithStatus()

    const card = statusCardScope()
    await waitFor(() => expect(card.getAllByText('检测中')).toHaveLength(3))
    expect(card.getAllByText('—')).toHaveLength(3)
    expect(
      card.getByText('服务状态检测失败，请稍后重试或联系管理员。')
    ).toBeInTheDocument()
  })

  it('认证失败但网关 ok → 仅认证行「检测中」，网关/版本保持正常，无提示条', async () => {
    gatewayFetch.mockResolvedValue({
      status: 'ok',
      service: 'api_gateway',
      version: 'V9.7.31',
      database: 'intelligent_audio_test',
    })
    authFetch.mockRejectedValue(new Error('auth down'))
    renderAboutWithStatus()

    const card = statusCardScope()
    await waitFor(() => expect(card.getAllByText('正常')).toHaveLength(2))
    expect(card.getAllByText('检测中')).toHaveLength(1)
    expect(card.getByText('V9.7.31')).toBeVisible()
    expect(card.getByText('intelligent_audio_test')).toBeInTheDocument()
    expect(
      card.queryByText('服务状态检测失败，请稍后重试或联系管理员。')
    ).not.toBeInTheDocument()
  })
})
