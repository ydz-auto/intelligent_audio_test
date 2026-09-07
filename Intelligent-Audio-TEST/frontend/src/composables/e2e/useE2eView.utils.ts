/**
 * useE2eView —— 工具（utils）
 *
 * 通用纯函数：测试用例 ID 归一化（过滤空值并按字符串去重）。
 */

/** 归一化选中的用例 ID：过滤空值/非法值并去重 */
export function normalizeSelectedCaseIds(ids: (string | number)[]) {
  const normalizedIds = ids.filter((id): id is string | number => {
    if (id === null || id === undefined) return false
    if (typeof id === 'number') return Number.isFinite(id)
    return String(id).trim().length > 0
  })

  const seen = new Set<string>()
  const uniqueIds: (string | number)[] = []
  for (const id of normalizedIds) {
    const key = String(id)
    if (seen.has(key)) continue
    seen.add(key)
    uniqueIds.push(id)
  }

  return uniqueIds
}