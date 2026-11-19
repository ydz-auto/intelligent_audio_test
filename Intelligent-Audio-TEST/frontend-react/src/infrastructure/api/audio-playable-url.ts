/**
 * 播放地址归一（infrastructure 层）。
 *
 * 后端有两种播放地址（AUDIO_STREAM_VIA_GATEWAY 开关）：
 * - COS 预签名绝对 URL：浏览器直连桶，可直接交给 <audio>；
 * - 网关相对地址 `/api/v1/audios/download?path=…`：需带 JWT 取字节（<audio> 无法
 *   附加 Authorization），因此先经 client 取 blob，再转 objectURL 播放。
 *
 * blob URL 按原始地址做 LRU 缓存：同一音频重复播放不重复下载，淘汰时释放。
 */
import { request } from '@/infrastructure/api/client'

/** 缓存上限（条）：试听场景同时存活的音频数远小于此值 */
const PLAYBACK_URL_CACHE_LIMIT = 50

const playbackUrlCache = new Map<string, string>()

/** 绝对地址（COS 预签名 / blob / data URI）原样返回，相对地址取字节后转 blob */
export async function resolvePlayableUrl(url: string): Promise<string> {
  if (!url || /^(https?:|blob:|data:)/i.test(url)) return url

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
