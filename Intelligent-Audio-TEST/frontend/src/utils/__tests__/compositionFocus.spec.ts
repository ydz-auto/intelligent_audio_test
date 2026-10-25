// -*- coding: utf-8 -*-
/**
 * INT-1835 · 规范 18 §3.1/§8.4：下单落点工具单测。
 *
 * 锁定口径：
 * - merge 出口带 `?focus=composition`，reexecute / reevaluate 出口不带（hash 路由只认 query，G6）
 * - `focus=composition` 判定（含重复参数数组形态）
 * - 滚动容器解析 = 最近可滚动祖先（模态窗内容区 / 布局主内容区），不是 window
 * - reduced-motion 下不做平滑滚动
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  COMPOSITION_FOCUS_HIGHLIGHT_CLASS,
  COMPOSITION_FOCUS_HIGHLIGHT_MS,
  COMPOSITION_FOCUS_QUERY,
  COMPOSITION_FOCUS_VALUE,
  focusScrollBehavior,
  isCompositionFocusRequested,
  prefersReducedMotion,
  resolveScrollContainer,
  scrollElementToContainerTop,
  taskDetailLocation,
} from '../compositionFocus'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('落点地址（§3.1）', () => {
  it('merge 出口带 ?focus=composition', () => {
    expect(taskDetailLocation('merge', 580)).toEqual({
      path: '/tasks/580',
      query: { [COMPOSITION_FOCUS_QUERY]: COMPOSITION_FOCUS_VALUE },
    })
  })

  it('reexecute / reevaluate 出口不带参数（行为不变）', () => {
    expect(taskDetailLocation('reexecute', 12)).toEqual({ path: '/tasks/12' })
    expect(taskDetailLocation('reevaluate', 34)).toEqual({ path: '/tasks/34' })
  })
})

describe('focus 参数判定', () => {
  it('字符串 / 数组重复参数都认 composition', () => {
    expect(isCompositionFocusRequested('composition')).toBe(true)
    expect(isCompositionFocusRequested(['composition'])).toBe(true)
    expect(isCompositionFocusRequested([null, 'composition'])).toBe(true)
  })

  it('缺参 / 其它值 / null 一律不认', () => {
    expect(isCompositionFocusRequested(undefined)).toBe(false)
    expect(isCompositionFocusRequested(null)).toBe(false)
    expect(isCompositionFocusRequested('cases')).toBe(false)
    expect(isCompositionFocusRequested(['cases'])).toBe(false)
  })
})

describe('滚动容器与定位', () => {
  const buildTree = () => {
    const outer = document.createElement('div')
    const scroller = document.createElement('div')
    const inner = document.createElement('div')
    const target = document.createElement('section')
    outer.appendChild(scroller)
    scroller.appendChild(inner)
    inner.appendChild(target)
    Object.defineProperty(scroller, 'scrollHeight', { value: 2000, configurable: true })
    Object.defineProperty(scroller, 'clientHeight', { value: 600, configurable: true })
    return { outer, scroller, inner, target }
  }

  it('解析最近的可滚动祖先（overflow-y:auto + 内容溢出）', () => {
    const { outer, scroller, inner, target } = buildTree()
    vi.spyOn(window, 'getComputedStyle').mockImplementation((el: Element) => {
      const overflowY = el === scroller ? 'auto' : 'visible'
      return { overflowY } as CSSStyleDeclaration
    })

    expect(resolveScrollContainer(target)).toBe(scroller)
    expect(resolveScrollContainer(inner)).toBe(scroller)
    expect(resolveScrollContainer(outer)).toBeNull()
  })

  it('把组成区滚到容器顶部（block:start 口径换算 scrollTop）', () => {
    const { scroller, target } = buildTree()
    scroller.scrollTop = 50
    vi.spyOn(scroller, 'getBoundingClientRect').mockReturnValue({ top: 100 } as DOMRect)
    vi.spyOn(target, 'getBoundingClientRect').mockReturnValue({ top: 800 } as DOMRect)
    const scrollTo = vi.fn()
    ;(scroller as any).scrollTo = scrollTo

    expect(scrollElementToContainerTop(target, scroller)).toBe(true)
    expect(scrollTo).toHaveBeenCalledWith({ top: 750, behavior: 'smooth' })
  })
})

describe('动效偏好', () => {
  it('reduced-motion 下无平滑滚动，默认平滑', () => {
    // jsdom 无 matchMedia，直接安装替身再还原
    const original = window.matchMedia
    ;(window as any).matchMedia = (query: string) =>
      ({ matches: query.includes('reduce'), media: query }) as MediaQueryList
    try {
      expect(prefersReducedMotion()).toBe(true)
      expect(focusScrollBehavior()).toBe('auto')
    } finally {
      window.matchMedia = original
    }
  })

  it('无 matchMedia 环境按常规动效处理', () => {
    const original = window.matchMedia
    // @ts-expect-error 测试环境模拟缺失
    delete window.matchMedia
    try {
      expect(prefersReducedMotion()).toBe(false)
      expect(focusScrollBehavior()).toBe('smooth')
    } finally {
      window.matchMedia = original
    }
  })
})

describe('高亮口径常量', () => {
  it('1.2s 高亮（§8.4）', () => {
    expect(COMPOSITION_FOCUS_HIGHLIGHT_MS).toBe(1200)
    expect(COMPOSITION_FOCUS_HIGHLIGHT_CLASS).toBe('is-composition-focus')
  })
})
