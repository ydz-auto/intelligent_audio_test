/**
 * 播放地址归一（infrastructure 层）。
 *
 * 后端有两种播放地址（AUDIO_STREAM_VIA_GATEWAY 开关）：
 * - COS 预签名绝对 URL：浏览器直连桶，可直接交给 <audio>；
 * - 网关相对地址 `/api/v1/audios/download?path=…&token=…`：URL 内嵌短效签名
 *   token，<audio> 原生流式播放（边缓存边播，不等整包下载）；无 token 的旧
 *   相对地址才带 JWT 取 blob 回退。
 *
 * blob URL 按原始地址做 LRU 缓存：同一音频重复播放不重复下载，淘汰时释放。
 */
import { request } from '@/infrastructure/api/client'
import { ApiError } from '@/infrastructure/api/api-error'

/** 缓存上限（条）：试听场景同时存活的音频数远小于此值 */
const PLAYBACK_URL_CACHE_LIMIT = 50

const playbackUrlCache = new Map<string, string>()

/** 绝对地址（COS 预签名 / blob / data）原样返回；带签名 token 的网关地址原样
 *  返回交给 <audio> 流式播放；其余相对地址取字节后转 blob */
export async function resolvePlayableUrl(url: string): Promise<string> {
  if (!url || /^(https?:|blob:|data:)/i.test(url)) return url
  // 网关取流地址已内嵌签名 token：直接流式播放，不整包取 blob（否则要等全量下载）
  if (/[?&]token=/i.test(url)) return url

  // /api/v1/audios/{id}/stream 是 JSON 预签名端点（非裸字节流），须先取 data.url 再播放
  const streamIdMatch = url
    .replace(/^\/api\/v1\//i, '')
    .match(/^audios\/(\d+)\/stream$/i)
  if (streamIdMatch) {
    const result = await request<{ url?: string }>(
      'GET',
      `/audios/${streamIdMatch[1]}/stream`
    )
    const presigned = result?.url
    if (!presigned) throw new ApiError({ message: '获取音频播放地址失败' })
    return resolvePlayableUrl(presigned)
  }

  const cached = playbackUrlCache.get(url)
  if (cached) return cached

  const relative = url.replace(/^\/api\/v1\//i, '')
  const data = await request<Blob>('GET', relative, undefined, {
    responseType: 'blob',
  })
  const blob = data instanceof Blob ? data : new Blob([data as unknown as BlobPart])
  const objectUrl = URL.createObjectURL(blob)

  if (playbackUrlCache.size >= PLAYBACK_URL_CACHE_LIMIT) {
    const oldestKey = playbackUrlCache.keys().next().value
    if (oldestKey !== undefined) {
      const oldestUrl = playbackUrlCache.get(oldestKey)
      playbackUrlCache.delete(oldestKey)
      if (oldestUrl) URL.revokeObjectURL(oldestUrl)
    }
  }
  playbackUrlCache.set(url, objectUrl)
  return objectUrl
}
