/**
 * 主题切换（深浅色）—— INT-745 启用 tokens.css `.dark` 块
 *
 * 原 Vue 的 tokens.css 已定义 .dark 双主题块但未启用；本卡新增浅/深两态切换：
 *  - document.documentElement.classList.toggle('dark', ...) 驱动全局令牌层
 *  - localStorage `iatp:theme:v1` 持久化（对齐总表 §2.4 B06）
 *  - 不引入多主题预设（单主题双色，照原 Vue 结构）
 */
export const THEME_STORAGE_KEY = 'iatp:theme:v1'
export type ThemeMode = 'light' | 'dark'

/** 应用主题：true=深色 / false=浅色 */
export function applyTheme(theme: ThemeMode): void {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

/** 读取当前生效主题（以 html 上的 .dark class 为准） */
export function getCurrentTheme(): ThemeMode {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

/** 应用启动时恢复持久化主题；无记录默认浅色 */
export function initTheme(): ThemeMode {
  const saved = localStorage.getItem(THEME_STORAGE_KEY)
  const theme: ThemeMode = saved === 'dark' ? 'dark' : 'light'
  applyTheme(theme)
  return theme
}

/** 切换浅/深并持久化，返回新主题 */
export function toggleTheme(): ThemeMode {
  const next: ThemeMode = getCurrentTheme() === 'dark' ? 'light' : 'dark'
  applyTheme(next)
  localStorage.setItem(THEME_STORAGE_KEY, next)
  return next
}
