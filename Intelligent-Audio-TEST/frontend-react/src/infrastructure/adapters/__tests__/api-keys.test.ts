/**
 * INT-1437 密钥池拆分/提取单测：textarea 草稿拆行（每行一个 key、可整段粘贴
 * 自动拆行）+ 写侧提取（草稿优先 / 显式数组兜底 / 留空不传）。
 */
import { describe, expect, it } from 'vitest'

import { extractEndpointApiKeys, splitApiKeysText } from '@/infrastructure/adapters/api-keys'

describe('splitApiKeysText（textarea 草稿拆行）', () => {
  it('按 \\r?\\n 拆分 → trim → 过滤空行（整段粘贴自动拆行）', () => {
    expect(splitApiKeysText('sk-a1\nsk-b2  \n\n  sk-c3')).toEqual(['sk-a1', 'sk-b2', 'sk-c3'])
  })

  it('Windows CRLF 换行归一（\\r\\n）', () => {
    expect(splitApiKeysText('sk-a1\r\nsk-b2\r\n')).toEqual(['sk-a1', 'sk-b2'])
  })

  it('全部空白/空文本 → 空数组（留空保留既有池）', () => {
    expect(splitApiKeysText('')).toEqual([])
    expect(splitApiKeysText('   \n  ')).toEqual([])
  })
})

describe('extractEndpointApiKeys（写侧密钥池提取）', () => {
  it('textarea 草稿 apiKeysText → 拆行密钥数组', () => {
    expect(extractEndpointApiKeys({ apiKeysText: 'sk-a1\n  sk-b2\n\nsk-c3' })).toEqual([
      'sk-a1',
      'sk-b2',
      'sk-c3',
    ])
  })

  it('apiKeysText 留空不返回密钥（不显式传 api_keys，后端保留既有池）', () => {
    expect(extractEndpointApiKeys({ apiKeysText: '   \n' })).toEqual([])
    expect(extractEndpointApiKeys({})).toEqual([])
  })

  it('显式 apiKeys 数组兜底（trim + 过滤空元素）', () => {
    expect(extractEndpointApiKeys({ apiKeys: ['sk-a1', ' sk-b2 ', ''] })).toEqual([
      'sk-a1',
      'sk-b2',
    ])
  })

  it('apiKeysText 草稿优先于显式数组', () => {
    expect(extractEndpointApiKeys({ apiKeysText: 'sk-text', apiKeys: ['sk-array'] })).toEqual(['sk-text'])
  })
})
