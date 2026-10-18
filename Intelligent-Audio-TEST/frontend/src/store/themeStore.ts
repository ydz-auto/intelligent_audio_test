/**
 * 主题切换 Store（UX设计-VUE 总表 §2.4 ④）
 *
 * 启用 tokens.css `.dark` 块：浅色/深色两卡 Radio，
 * 写入 document.documentElement.classList.toggle('dark')，
 * localStorage 持久化 `iatp:theme:v1`。不引入多预设。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

const THEME_STORAGE_KEY = 'iatp:theme:v1'
export type ThemeMode = 'light' | 'dark'

export const useThemeStore = defineStore('theme', () => {
  const theme = ref<ThemeMode>('light')

  function apply(mode: ThemeMode) {
    theme.value = mode
    document.documentElement.classList.toggle('dark', mode === 'dark')
    try {
      if (mode === 'dark') {
        localStorage.setItem(THEME_STORAGE_KEY, 'dark')
      } else {
        localStorage.removeItem(THEME_STORAGE_KEY)
      }
    } catch {
      // 忽略持久化失败
    }
  }

  /** 初始化：应用启动时读取 localStorage 并挂 .dark（须在 mount 前调用） */
  function init() {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY)
      apply(saved === 'dark' ? 'dark' : 'light')
    } catch {
      apply('light')
    }
  }

  function toggle() {
    apply(theme.value === 'dark' ? 'light' : 'dark')
  }

  return { theme, apply, toggle, init }
})
