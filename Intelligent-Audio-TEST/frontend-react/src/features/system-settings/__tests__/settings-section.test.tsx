/**
 * 分节标题渲染测试（INT-489 返修②回归）：
 * SettingsPageProvider 默认不抑制分节标题——母版 B/C 资源页「分节标题 + 一句说明」
 * 必须渲染（05_系统设置.md §4.2/§4.4.1/§4.4.2/§4.7）；显式 suppressSectionHeader=true 时隐藏。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SettingsPageProvider } from '../components/settings-page-context'
import { SettingsSection } from '../components/settings-section'

describe('SettingsSection', () => {
  it('默认（未传 suppressSectionHeader）渲染分节标题与说明', () => {
    render(
      <SettingsPageProvider actionsContainer={null}>
        <SettingsSection
          title='归档管理'
          description='管理日志归档状态、归档文件与归档操作'
        >
          <span>归档内容</span>
        </SettingsSection>
      </SettingsPageProvider>
    )
    expect(
      screen.getByRole('heading', { level: 3, name: '归档管理' })
    ).toBeInTheDocument()
    expect(
      screen.getByText('管理日志归档状态、归档文件与归档操作')
    ).toBeInTheDocument()
    expect(screen.getByText('归档内容')).toBeInTheDocument()
  })

  it('suppressSectionHeader=true 时隐藏分节标题与说明', () => {
    render(
      <SettingsPageProvider actionsContainer={null} suppressSectionHeader>
        <SettingsSection
          title='归档管理'
          description='管理日志归档状态、归档文件与归档操作'
        >
          <span>归档内容</span>
        </SettingsSection>
      </SettingsPageProvider>
    )
    expect(
      screen.queryByRole('heading', { level: 3, name: '归档管理' })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText('管理日志归档状态、归档文件与归档操作')
    ).not.toBeInTheDocument()
    expect(screen.getByText('归档内容')).toBeInTheDocument()
  })
})
