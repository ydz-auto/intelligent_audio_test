/**
 * resolvePlayableUrl 播放地址归一（AUDIO_STREAM_VIA_GATEWAY 边缓存边播）：
 * 带签名 token 的网关地址原样直出（<audio> 流式播放，不整包取 blob）；
 * 无 token 的旧相对地址才带 JWT 取 blob 回退。
 */
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/infrastructure/api/client', () => ({
  request: vi.fn(async () => new Blob(['x'])),
}))

import { resolvePlayableUrl } from '../audio-playable-url'

// jsdom 自带真实 createObjectURL，强制桩掉供 blob 回退路径断言
URL.createObjectURL = vi.fn(() => 'blob:mock')

describe('resolvePlayableUrl 网关取流（边缓存边播）', () => {
  it('带签名 token 的网关相对地址原样返回，不整包取 blob', async () => {
    const url =
      '/api/v1/audios/download?path=oss%3A%2F%2Fcase_result%2F1%2Fa.wav&token=1700000000.abc'
    expect(await resolvePlayableUrl(url)).toBe(url)
  })

  it('绝对 http(s) 地址原样返回', async () => {
    const url = 'https://cos.example/audios/a.wav?sign=x'
    expect(await resolvePlayableUrl(url)).toBe(url)
  })

  it('blob/data 地址原样返回', async () => {
    expect(await resolvePlayableUrl('blob:abc')).toBe('blob:abc')
    expect(await resolvePlayableUrl('data:audio/wav;base64,AAAA')).toBe(
      'data:audio/wav;base64,AAAA'
    )
  })

  it('无 token 的相对地址回退为 blob（带 JWT 取字节）', async () => {
    const url = '/api/v1/audios/download?path=oss%3A%2F%2Fcase_result%2F1%2Fb.wav'
    expect(await resolvePlayableUrl(url)).toBe('blob:mock')
  })
})
