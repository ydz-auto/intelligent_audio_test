/**
 * 键名深度转换工具 —— snake_case ⇄ camelCase
 *
 * 用于 infrastructure/adapters 层：后端 JSON 返回 snake_case，
 * adapter 转换为 domain camelCase；反向同理。
 * 只转 key（属性名），不碰 value（枚举值、路径字符串等原样保留）。
 * snakeToCamel 亦可被 Presentation 层引用于归一化后端返回的动态标识符
 * （如 param_code 值），保证上层不持有 snake_case 字面量。
 */

/** snake_case → camelCase（单个 key） */
export function snakeToCamel(key: string): string {
  return key.replace(/_([a-z])/g, (_, g) => g.toUpperCase())
}

/** camelCase → snake_case（单个 key） */
function camelToSnake(key: string): string {
  return key.replace(/([A-Z])/g, (_, g: string) => '_' + g.toLowerCase())
}

/**
 * 从后端原始对象读取 camelCase key（自动兜底其 snake_case 形态）。
 * 供 Presentation 层读取未经过 adapter 的原始数据时使用，保证上层不持有 snake_case 字面量。
 */
export function readCamel<T = unknown>(obj: unknown, camelKey: string): T | undefined {
  if (!obj || typeof obj !== 'object') return undefined
  const record = obj as Record<string, unknown>
  if (record[camelKey] !== undefined) return record[camelKey] as T
  return record[camelToSnake(camelKey)] as T | undefined
}

/** 递归将对象内所有 snake_case key 转为 camelCase */
export function camelizeKeys<T>(obj: T): T {
  if (Array.isArray(obj)) return obj.map(camelizeKeys) as unknown as T
  if (obj && typeof obj === 'object') {
    const result: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(obj)) {
      result[snakeToCamel(k)] = camelizeKeys(v)
    }
    return result as T
  }
  return obj
}

/** 递归将对象内所有 camelCase key 转为 snake_case */
export function snakifyKeys<T>(obj: T): T {
  if (Array.isArray(obj)) return obj.map(snakifyKeys) as unknown as T
  if (obj && typeof obj === 'object') {
    const result: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(obj)) {
      result[camelToSnake(k)] = snakifyKeys(v)
    }
    return result as T
  }
  return obj
}
