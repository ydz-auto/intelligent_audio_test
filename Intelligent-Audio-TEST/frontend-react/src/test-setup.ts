/**
 * vitest jsdom 全局桩（照 newAPI web/src/test-setup.ts 等价移植，删 i18next 相关）：
 * matchMedia / rAF / ResizeObserver / scrollIntoView / getAnimations / Storage。
 */
import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// 照 newAPI 实测 5000（冷渲染首测在受控 CI runner 上偏慢；低于 vitest testTimeout
// 保证异步查找失败仍报「元素缺失」而非泛化超时）。
configure({ asyncUtilTimeout: 5000 })

afterEach(() => {
  cleanup()
})

// 照 newAPI：prefers-reduced-motion 返回 true——入场动画首帧写 inline opacity:0，
// jsdom 的 rAF 走 setTimeout shim，visibility 断言会与动画赛跑；reduced-motion
// 分支渲染相同 DOM 但无瞬时隐藏态。
Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  value: (query: string): MediaQueryList => ({
    matches:
      query.includes('prefers-reduced-motion') &&
      !query.includes('no-preference'),
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

// jsdom 未实现 Range 几何测量（照 newAPI 平移）。
if (!Range.prototype.getClientRects) {
  Object.defineProperty(Range.prototype, 'getClientRects', {
    configurable: true,
    writable: true,
    value: () => [],
  })
}
if (!Range.prototype.getBoundingClientRect) {
  Object.defineProperty(Range.prototype, 'getBoundingClientRect', {
    configurable: true,
    writable: true,
    value: () => new DOMRect(),
  })
}

window.requestAnimationFrame = (callback: FrameRequestCallback) =>
  window.setTimeout(() => callback(performance.now()), 0)
window.cancelAnimationFrame = (handle: number) => window.clearTimeout(handle)

class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

Object.defineProperty(globalThis, 'ResizeObserver', {
  configurable: true,
  value: ResizeObserverMock,
})

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: () => undefined,
})

// ScrollArea 检查运行中的动画；jsdom 未实现该 API（照 newAPI 平移）。
if (!Element.prototype.getAnimations) {
  Object.defineProperty(Element.prototype, 'getAnimations', {
    configurable: true,
    value: () => [],
  })
}

// Node 25+ 在 global 上定义了 localStorage/sessionStorage 访问器（未设
// --localstorage-file 时解析为 undefined），vitest jsdom 环境不会替换已存在的
// globals；提供内存 Storage 使测试与浏览器同 API（照 newAPI 平移）。
for (const name of ['localStorage', 'sessionStorage'] as const) {
  if (typeof globalThis[name]?.setItem === 'function') continue
  const entries = new Map<string, string>()
  const storage: Storage = {
    get length() {
      return entries.size
    },
    clear: () => entries.clear(),
    getItem: (key) => entries.get(String(key)) ?? null,
    key: (index) => [...entries.keys()][index] ?? null,
    removeItem: (key) => {
      entries.delete(String(key))
    },
    setItem: (key, value) => {
      entries.set(String(key), String(value))
    },
  }
  Object.defineProperty(globalThis, name, {
    configurable: true,
    enumerable: true,
    writable: true,
    value: storage,
  })
}
