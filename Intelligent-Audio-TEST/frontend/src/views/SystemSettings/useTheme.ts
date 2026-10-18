/**
 * 主题切换 composable —— 浅色/深色双主题（照总表 §2.4 与 tokens.css .dark 块）
 * localStorage 键 `iatp:theme:v1`（与基座壳 ThemeSwitcher 共用，右上角快入口与此处同步生效）。
 */
import { ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'auto'

const THEME_KEY = 'iatp:theme:v1'

const hasDOM = typeof window !== 'undefined' && typeof document !== 'undefined'

function prefersDark(): boolean {
  return hasDOM
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches
}

function loadMode(): ThemeMode {
  if (!hasDOM) return 'auto'
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === 'light' || saved === 'dark' || saved === 'auto') return saved
  return 'auto'
}

function applyDark(dark: boolean) {
  if (!hasDOM) return
  document.documentElement.classList.toggle('dark', dark)
}

export function useTheme() {
  const mode = ref<ThemeMode>(loadMode())

  function apply(next: ThemeMode) {
    mode.value = next
    if (hasDOM) localStorage.setItem(THEME_KEY, next)
    applyDark(next === 'dark' || (next === 'auto' && prefersDark()))
  }

  function isDark(): boolean {
    return mode.value === 'dark' || (mode.value === 'auto' && prefersDark())
  }

  // 模块级初始化：把已存主题落到 .dark class（否则深色仅在切换后生效）
  apply(mode.value)

  return { mode, apply, isDark }
}
