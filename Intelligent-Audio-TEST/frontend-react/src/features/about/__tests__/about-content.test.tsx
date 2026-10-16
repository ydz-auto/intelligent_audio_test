/**
 * 关于页正文组件测试（INT-460 返修 P2-1，交付清单#8 口径①/③/④）：
 * 默认 md 资产渲染（默认内容渲染）/ 空态渲染不崩溃 / 站内链接补 router 路径 /
 * 外链统一 `_blank + noopener noreferrer`（06_关于.md §4.3，对照
 * newAPI about-content.test.tsx 断言口径）。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ABOUT_DOCUMENT } from '@/infrastructure/content/aboutAssets'

import { AboutContent } from '../about-content'

describe('AboutContent', () => {
  it('默认 md 资产渲染正文标题与平台能力段落（默认内容渲染）', () => {
    render(<AboutContent content={ABOUT_DOCUMENT} />)
    expect(
      screen.getByRole('heading', { name: '关于智能语音测试平台', level: 1 })
    ).toBeVisible()
    expect(screen.getByText(/一站式测试能力/)).toBeInTheDocument()
  })

  it('空态内容渲染不崩溃（空态由 useAboutContent 回退默认资产，正文层零错误）', () => {
    render(<AboutContent content='   ' />)
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
  })

  it('站内链接保留 router 路径，不开新窗口（不误标外链）', () => {
    render(
      <AboutContent content='[使用手册](/user-guide) 与 [API 手册](/user-guide-api)' />
    )
    const guide = screen.getByRole('link', { name: '使用手册' })
    expect(guide).toHaveAttribute('href', '/user-guide')
    expect(guide).not.toHaveAttribute('target')
    expect(guide).not.toHaveAttribute('rel')
    expect(screen.getByRole('link', { name: 'API 手册' })).toHaveAttribute(
      'href',
      '/user-guide-api'
    )
  })

  it('外链统一 _blank + noopener noreferrer', () => {
    render(<AboutContent content='[外部仓库](https://github.com/example/doc)' />)
    const external = screen.getByRole('link', { name: '外部仓库' })
    expect(external).toHaveAttribute('href', 'https://github.com/example/doc')
    expect(external).toHaveAttribute('target', '_blank')
    expect(external).toHaveAttribute('rel', 'noopener noreferrer')
  })
})
