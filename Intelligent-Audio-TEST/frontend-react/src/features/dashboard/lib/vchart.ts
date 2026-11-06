/*
Copyright (C) 2023-2026 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/
/**
 * VChart 封装（移植自 newAPI web/src/lib/vchart.ts + use-chart-theme.ts + theme-radius.ts）：
 * ThemeManager.setCurrentTheme(light/dark) 就绪门控 themeReady + 圆角 CSS 变量解析。
 */
import { useEffect, useRef, useState } from 'react'

import { useTheme } from '@/context/theme-provider'
import { useThemeCustomization } from '@/context/theme-customization-provider'

export const VCHART_OPTION = {
  // 与 newAPI 保持一致（浏览器环境渲染优化）
  mode: 'desktop-browser',
} as const

export type VChartTheme = 'light' | 'dark'

/**
 * Lazy-load VChart 的 ThemeManager 并跟随站点深浅色；返回门控标记与主题键
 * （消费方把 themeKey 拼进 VChart key —— 主题变化整图重建）。
 */
let themeManagerPromise: Promise<
  (typeof import('@visactor/vchart'))['ThemeManager']
> | null = null

export function useChartTheme() {
  const { resolvedTheme } = useTheme()
  const [themeReady, setThemeReady] = useState(false)
  const themeRef = useRef<
    (typeof import('@visactor/vchart'))['ThemeManager'] | null
  >(null)

  useEffect(() => {
    let cancelled = false
    const updateTheme = async () => {
      setThemeReady(false)
      if (!themeManagerPromise) {
        themeManagerPromise = import('@visactor/vchart').then(
          (m) => m.ThemeManager
        )
      }
      const ThemeManager = await themeManagerPromise
      if (cancelled) return
      themeRef.current = ThemeManager
      ThemeManager.setCurrentTheme(resolvedTheme === 'dark' ? 'dark' : 'light')
      setThemeReady(true)
    }
    updateTheme()
    return () => {
      cancelled = true
    }
  }, [resolvedTheme])

  return {
    resolvedTheme,
    themeReady,
    themeKey: resolvedTheme === 'dark' ? 'dark' : 'light',
  }
}

export function resolveThemeRadiusPx(
  cssVariable = '--radius-md'
): number | undefined {
  if (typeof document === 'undefined') return undefined

  const probe = document.createElement('div')
  probe.style.borderRadius = `var(${cssVariable})`
  probe.style.pointerEvents = 'none'
  probe.style.position = 'absolute'
  probe.style.visibility = 'hidden'

  document.documentElement.appendChild(probe)
  const resolvedRadius = getComputedStyle(probe).borderTopLeftRadius
  probe.remove()

  const parsedRadius = Number.parseFloat(resolvedRadius)
  return Number.isFinite(parsedRadius) ? parsedRadius : undefined
}

export function useThemeRadiusPx(
  cssVariable = '--radius-md',
  refreshKey?: string
): number | undefined {
  const [radius, setRadius] = useState<number | undefined>()

  useEffect(() => {
    setRadius(resolveThemeRadiusPx(cssVariable))
  }, [cssVariable, refreshKey])

  return radius
}

/** 主题预设键（图表 key 组成之一：预设/主题/数据变化整图重建） */
export function useThemePresetKey(): string {
  const { customization } = useThemeCustomization()
  return customization.preset
}
