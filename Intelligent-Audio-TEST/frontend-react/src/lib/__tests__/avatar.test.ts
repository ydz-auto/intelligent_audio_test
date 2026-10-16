/**
 * lib/avatar 纯函数测试（照 newAPI 纯函数粒度）。
 */
import { describe, expect, it } from 'vitest'

import { getUserAvatarFallback, getUserAvatarStyle } from '@/lib/avatar'

describe('getUserAvatarStyle', () => {
  it('同一名字稳定生成一致的 HSL 背景色', () => {
    const a = getUserAvatarStyle('演示管理员')
    const b = getUserAvatarStyle('演示管理员')
    expect(a.backgroundColor).toMatch(/^hsl\(\d+ \d+% \d+%\)$/)
    expect(a).toEqual(b)
  })

  it('不同名字通常生成不同色相', () => {
    const a = getUserAvatarStyle('demo_admin')
    const b = getUserAvatarStyle('other_user')
    expect(a.backgroundColor).not.toBe(b.backgroundColor)
  })

  it('前景恒为白色', () => {
    expect(getUserAvatarStyle('任何人').color).toBe('white')
  })
})

describe('getUserAvatarFallback', () => {
  it('取首字符大写作为占位', () => {
    expect(getUserAvatarFallback('演示管理员')).toBe('演')
    expect(getUserAvatarFallback('admin')).toBe('A')
  })

  it('空白名字回退为问号', () => {
    expect(getUserAvatarFallback('   ')).toBe('?')
  })
})
