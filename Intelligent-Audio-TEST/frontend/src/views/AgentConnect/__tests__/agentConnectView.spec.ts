/**
 * INT-1193：「连接你的 agent」入口页验收测试（文案统一；INT-1154 基线）。
 * 覆盖：使用说明 / skill 服务地址配置（默认取地址栏、可改、保存落 localStorage）/
 * Access Token 指引（跳 /profile）/ 炫彩下载按钮 → 下载 skill（基础设施层真实 GET /api/v1/agent/skill，INT-1897）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'

const ports = vi.hoisted(() => ({
  downloadSkillPackage: vi.fn(),
}))
const routerPush = vi.hoisted(() => vi.fn())
const notification = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))
const downloadBlob = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))
vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => notification,
}))
vi.mock('@/infrastructure/api/agentSkillApi', () => ({
  downloadSkillPackage: ports.downloadSkillPackage,
}))
vi.mock('@/utils/utils', () => ({
  downloadBlob,
}))

import AgentConnectView from '../AgentConnectView.vue'

function findButton(w: VueWrapper, text: string) {
  const btn = w.findAll('button').find((b) => b.text().includes(text))
  if (!btn) throw new Error(`button not found: ${text}`)
  return btn
}

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  // 默认服务地址 = 浏览器地址栏
  Object.defineProperty(window, 'location', {
    value: { origin: 'http://localhost:5600' },
    writable: true,
    configurable: true,
  })
  ports.downloadSkillPackage.mockResolvedValue(new Blob(['sample-zip'], { type: 'application/zip' }))
})

async function mountPage() {
  const w = mount(AgentConnectView)
  await flushPromises()
  return w
}

describe('AgentConnectView 「连接你的 agent」（INT-1193）', () => {
  it('渲染使用说明 / 服务地址配置（默认取地址栏）/ Access Token 指引 / 下载按钮', async () => {
    const w = await mountPage()
    const text = w.text()
    expect(text).toContain('连接你的 agent')
    expect(text).toContain('使用说明')
    expect(text).toContain('创建 Access Token')
    expect(text).toContain('安装 skill')
    expect(text).toContain('配置 MCP')
    expect(text).toContain('skill 服务地址')
    expect(text).toContain('Access Token')
    expect(text).toContain('下载 skill')
    // 服务地址默认取浏览器地址栏
    const input = w.find('input[aria-label="skill 服务地址"]')
    expect((input.element as HTMLInputElement).value).toBe('http://localhost:5600')
  })

  it('保存服务地址 → localStorage 持久化 + 成功 toast', async () => {
    const w = await mountPage()
    const input = w.find('input[aria-label="skill 服务地址"]')
    await input.setValue('https://agent.example.com')
    await findButton(w, '保存配置').trigger('click')
    await flushPromises()
    expect(localStorage.getItem('iatp:agent-connect:v1')).toBe('https://agent.example.com')
    expect(notification.success).toHaveBeenCalledWith('skill 服务地址已保存')
  })

  it('空地址保存 → 警告 toast，不落库', async () => {
    const w = await mountPage()
    const input = w.find('input[aria-label="skill 服务地址"]')
    await input.setValue('')
    await findButton(w, '保存配置').trigger('click')
    await flushPromises()
    expect(notification.warning).toHaveBeenCalledWith('请填写 skill 服务地址')
    expect(localStorage.getItem('iatp:agent-connect:v1')).toBeNull()
  })

  it('下载按钮 → 走基础设施层真实请求并触发浏览器下载', async () => {
    const w = await mountPage()
    await findButton(w, '下载 skill').trigger('click')
    await flushPromises()
    expect(ports.downloadSkillPackage).toHaveBeenCalledTimes(1)
    // 传入的服务地址为当前配置（默认地址栏）
    expect(ports.downloadSkillPackage).toHaveBeenCalledWith(expect.objectContaining({ serviceUrl: 'http://localhost:5600' }))
    expect(downloadBlob).toHaveBeenCalledTimes(1)
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'intelligent-audio-test-skill.zip')
    expect(notification.success).toHaveBeenCalledWith('skill 包已开始下载')
  })

  it('下载失败 → 友好错误 toast', async () => {
    ports.downloadSkillPackage.mockRejectedValue(new Error('Server returned 404'))
    const w = await mountPage()
    await findButton(w, '下载 skill').trigger('click')
    await flushPromises()
    expect(notification.error).toHaveBeenCalled()
    expect(downloadBlob).not.toHaveBeenCalled()
  })

  it('「前往个人配置页」→ 跳转 /profile', async () => {
    const w = await mountPage()
    await findButton(w, '前往个人配置页').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/profile')
  })

  it('localStorage 有存量 → 回显存量地址', async () => {
    localStorage.setItem('iatp:agent-connect:v1', 'https://saved.example.com')
    const w = await mountPage()
    const input = w.find('input[aria-label="skill 服务地址"]')
    expect((input.element as HTMLInputElement).value).toBe('https://saved.example.com')
  })
})
