/**
 * 日志时间格式化公共 helper
 *
 * 统一处理 LogView 列表（time：仅时间）与任务日志（datetime：日期时间）的时间展示，
 * 消除各处重复的 new Date + toLocale* 逻辑。
 *
 * - 空值（undefined/null）返回 ''（与原调用方 `|| ''` 行为一致）；
 * - 非法日期返回原字符串（原样展示原始值）；
 * - 合法日期按 mode 格式化为 toLocaleTimeString / toLocaleString。
 */
export function formatLogTime(
  raw: string | undefined | null,
  mode: 'time' | 'datetime'
): string {
  const rawTime = raw ?? ''
  try {
    const date = new Date(rawTime)
    if (!isNaN(date.getTime())) {
      return mode === 'time' ? date.toLocaleTimeString() : date.toLocaleString()
    }
  } catch (e) {
    // 兜底：日期解析异常时按原始值返回，不影响日志列表展示
    console.error('Failed to format log time:', e)
  }
  return rawTime
}