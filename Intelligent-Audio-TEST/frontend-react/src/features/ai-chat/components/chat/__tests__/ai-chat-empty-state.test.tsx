/**
 * AI 对话组件测试——AiChatEmptyState（INT-435/INT-598 返修）：空态标题/描述渲染、
 * 常用入门 starter 按权限过滤、全能力分组 11 域入口卡（§3.3 区二）按在册权限码
 * 显可执行/待接入、点击回填输入框（不自动发送，对位 08_AI对话页.md §3.3）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AiChatEmptyState } from '@/features/ai-chat/components/chat/ai-chat-empty-state'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

const initialAuth = useAuthStore.getState()

beforeEach(() => {
  useAuthStore.getState().setAuth(null)
})

afterEach(() => {
  useAuthStore.setState(initialAuth)
})

describe('AiChatEmptyState', () => {
  it('渲染标题与描述（含 Demo 说明尾注 §3.10 与全能力文案）', () => {
    render(<AiChatEmptyState onFillPrompt={vi.fn()} />)
    expect(screen.getByText('开始与灵犀Agent对话')).toBeInTheDocument()
    expect(screen.getByText(/灵犀Agent基于平台数据起草文档/)).toBeInTheDocument()
    expect(screen.getByText(/也能生成用例、管理任务、诊断日志、校准设备/)).toBeInTheDocument()
    expect(screen.getByText(/当前为 Demo 预览/)).toBeInTheDocument()
  })

  it('未登录权限全失：常用入门 starter 不渲染，全能力分组 11 卡显「待接入」', () => {
    render(<AiChatEmptyState onFillPrompt={vi.fn()} />)
    expect(
      screen.queryByRole('button', { name: /生成测试报告/ })
    ).not.toBeInTheDocument()
    // 全能力分组照 §5 注5：全部可见、无在册权限统一标「待接入」（可显不可执行）
    expect(screen.getByText('全能力分组')).toBeInTheDocument()
    expect(screen.getAllByText('待接入')).toHaveLength(11)
  })

  it('超级管理员可见常用入门四卡 + 全能力分组 11 卡（仅系统设置待接入）', () => {
    useAuthStore.getState().setAuth({
      id: 'u1',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    render(<AiChatEmptyState onFillPrompt={vi.fn()} />)
    expect(
      screen.getByRole('button', { name: /生成测试报告/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /对比多份报告/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /解读报告指标/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /追问报告数据/ })
    ).toBeInTheDocument()
    // 11 域入口卡全显；无码域（系统设置）唯一待接入
    expect(screen.getByText('工作台（系统概览）')).toBeInTheDocument()
    expect(screen.getByText('音频导入（音频导入+标注）')).toBeInTheDocument()
    expect(screen.getByText('系统设置（配置域（OAuth/系统配置））')).toBeInTheDocument()
    expect(screen.getAllByText('待接入')).toHaveLength(1)
  })

  it('仅 report:read 时常用入门显解读/追问，分组仅报告域可执行、其余待接入', () => {
    useAuthStore.getState().setAuth({
      id: 'u2',
      username: 'reader',
      displayName: '报告读者',
      roleName: '访客',
      permissions: ['report:read'],
    })
    render(<AiChatEmptyState onFillPrompt={vi.fn()} />)
    expect(
      screen.queryByRole('button', { name: /生成测试报告/ })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /对比多份报告/ })
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /解读报告指标/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /追问报告数据/ })
    ).toBeInTheDocument()
    // 报告域在册 report:read → 可执行；其余 10 域待接入（可显不可执行）
    expect(
      screen.getByRole('button', { name: '对比最近两次测试的报告，找出退步项' })
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '帮我从 URL 导入这批音频并带上标注' })
    ).not.toBeInTheDocument()
    expect(screen.getAllByText('待接入')).toHaveLength(10)
  })

  it('点击常用入门 starter 回填提示词', async () => {
    useAuthStore.getState().setAuth({
      id: 'u1',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    const user = userEvent.setup()
    const onFillPrompt = vi.fn()
    render(<AiChatEmptyState onFillPrompt={onFillPrompt} />)
    await user.click(
      screen.getByRole('button', { name: /生成测试报告/ })
    )
    expect(onFillPrompt).toHaveBeenCalledWith(
      '帮我把最近的测试任务生成一份测试报告'
    )
  })

  it('点击全能力分组可执行芯片回填提示词（不自动发送）', async () => {
    useAuthStore.getState().setAuth({
      id: 'u1',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    const user = userEvent.setup()
    const onFillPrompt = vi.fn()
    render(<AiChatEmptyState onFillPrompt={onFillPrompt} />)
    await user.click(
      screen.getByRole('button', { name: '扫描播放设备，为豆包 APP 生成 Android 驱动' })
    )
    expect(onFillPrompt).toHaveBeenCalledWith(
      '扫描播放设备，为豆包 APP 生成 Android 驱动'
    )
    // 待接入卡（系统设置）无可点击按钮
    expect(
      screen.queryByRole('button', { name: /系统设置/ })
    ).not.toBeInTheDocument()
  })
})
