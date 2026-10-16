/**
 * 关于页内容解析四分支测试（INT-460 返修 P2-1，交付清单#8 口径①/②）：
 * 默认 md 资产（默认内容渲染）/ 空态回退默认 / URL iframe 分支 / HTML 分支
 * （06_关于.md §1.3/§4.2，对照 newAPI about-content.test.tsx 断言口径）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

/** 受控 ABOUT_DOCUMENT：vi.mock 工厂取 live 引用，逐用例改写四分支输入 */
const mockAboutDocument = vi.hoisted(() => ({ value: '# 关于智能语音测试平台' }))

vi.mock('@/infrastructure/content/aboutAssets', () => ({
  get ABOUT_DOCUMENT() {
    return mockAboutDocument.value
  },
}))

import { useAboutContent } from '../useAboutContent'

describe('useAboutContent', () => {
  beforeEach(() => {
    mockAboutDocument.value = '# 关于智能语音测试平台'
  })

  it('默认 md 资产 → markdown 分支（默认内容渲染）', () => {
    const state = useAboutContent()
    expect(state).toEqual({
      status: 'markdown',
      content: '# 关于智能语音测试平台',
    })
  })

  it('空态（全空白）回退默认 md 分支，不误判为 url/html（空态回退默认）', () => {
    mockAboutDocument.value = '   \n\t  '
    const state = useAboutContent()
    expect(state.status).toBe('markdown')
  })

  it('URL 内容 → url iframe 沙箱分支', () => {
    mockAboutDocument.value = 'https://example.com/about'
    expect(useAboutContent()).toEqual({
      status: 'url',
      url: 'https://example.com/about',
    })
  })

  it('HTML 内容 → html 隔离分支', () => {
    mockAboutDocument.value = '<!doctype html><html><body>关于</body></html>'
    expect(useAboutContent()).toEqual({
      status: 'html',
      html: '<!doctype html><html><body>关于</body></html>',
    })
  })
})
