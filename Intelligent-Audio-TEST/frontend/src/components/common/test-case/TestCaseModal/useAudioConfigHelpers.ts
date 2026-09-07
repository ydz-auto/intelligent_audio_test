/**
 * 音频配置辅助函数 composable
 *
 * 统一封装 audioConfig 上的音频信息查询代理逻辑，消除 6 个子组件中的逐字符重复。
 * getNormalizedTags 为纯函数，不依赖 audioConfig，可直接独立导出使用。
 */

/** 纯函数：将标签字符串归一化为 string[]，不依赖 audioConfig */
export function getNormalizedTags(tagsStr: string): string[] {
  if (!tagsStr) return []
  try {
    const parsed = JSON.parse(tagsStr)
    if (Array.isArray(parsed)) return parsed.map(String)
    if (typeof parsed === 'string') return parsed.split(',').map((s: string) => s.trim()).filter(Boolean)
  } catch {
    return String(tagsStr).split(',').map((s: string) => s.trim()).filter(Boolean)
  }
  return []
}

/**
 * 创建绑定到指定 audioConfig 的音频信息查询辅助函数集合。
 *
 * @param audioConfig 通过 inject 获取的音频配置对象
 * @param getAudioNameFallback 当 audioConfig.getAudioName 未命中时的回退值；可为静态字符串，也可为以 audioId 入参为参数的函数
 */
export function useAudioConfigHelpers(
  audioConfig: any,
  getAudioNameFallback: string | ((audioId: string | number) => string) = '未知音频'
) {
  function getAudioName(audioId: string | number): string {
    const name = audioConfig?.getAudioName?.(audioId)
    if (name) return name
    return typeof getAudioNameFallback === 'function'
      ? getAudioNameFallback(audioId)
      : getAudioNameFallback
  }

  function getAudioTags(audioId: string | number): string {
    return audioConfig?.getAudioTags?.(audioId) || ''
  }

  function getAudioDuration(audioId: string | number): number {
    return audioConfig?.getAudioDuration?.(audioId) || 0
  }

  function formatDuration(seconds: number): string {
    return audioConfig?.formatDuration?.(seconds) || '0s'
  }

  return {
    getAudioName,
    getAudioTags,
    getAudioDuration,
    formatDuration,
    getNormalizedTags
  }
}
