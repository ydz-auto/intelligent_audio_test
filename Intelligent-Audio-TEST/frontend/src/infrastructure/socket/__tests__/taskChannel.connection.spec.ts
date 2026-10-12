/**
 * INT-203：taskChannel 通道连接状态聚合
 *
 * 通道依赖 '/'（task_progress）与 '/ws/logs'（task_log）两个命名空间，
 * 任一断开即视为通道不可用；onConnectionChange 仅在聚合状态翻转时回调（边沿触发）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const socketMocks = vi.hoisted(() => ({
  isNamespaceConnected: vi.fn(),
  onConnectionChange: vi.fn(),
}))

vi.mock('@/utils/socket', () => ({
  default: {
    on: vi.fn(() => () => {}),
    off: vi.fn(),
    emit: vi.fn(),
    isNamespaceConnected: socketMocks.isNamespaceConnected,
    onConnectionChange: socketMocks.onConnectionChange,
  },
}))

import { isConnected, onConnectionChange } from '../taskChannel'

const setNamespaceState = (main: boolean, logs: boolean) => {
  socketMocks.isNamespaceConnected.mockImplementation(
    (namespace: string) => (namespace === '/ws/logs' ? logs : main),
  )
}

beforeEach(() => {
  socketMocks.isNamespaceConnected.mockReset().mockReturnValue(true)
  socketMocks.onConnectionChange.mockReset()
})

describe('taskChannel.isConnected', () => {
  it('两个命名空间均已连接 → true', () => {
    setNamespaceState(true, true)
    expect(isConnected()).toBe(true)
  })

  it('任一命名空间断开 → false', () => {
    setNamespaceState(false, true)
    expect(isConnected()).toBe(false)
    setNamespaceState(true, false)
    expect(isConnected()).toBe(false)
  })
})

describe('taskChannel.onConnectionChange', () => {
  it('聚合状态翻转时回调，未翻转不重复回调', () => {
    setNamespaceState(true, true)
    const handlers: Array<(namespace: string, connected: boolean) => void> = []
    socketMocks.onConnectionChange.mockImplementation((listener: (namespace: string, connected: boolean) => void) => {
      handlers.push(listener)
      return () => {}
    })

    const handler = vi.fn()
    onConnectionChange(handler)

    // 订阅时已连接，命名空间重连事件不触发回调
    handlers.forEach(h => h('/', true))
    expect(handler).not.toHaveBeenCalled()

    // 日志命名空间断开 → 聚合翻转 → false
    setNamespaceState(true, false)
    handlers.forEach(h => h('/ws/logs', false))
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenLastCalledWith(false)

    // 进度命名空间断开（已不可用，聚合未变）→ 不重复回调
    setNamespaceState(false, false)
    handlers.forEach(h => h('/', false))
    expect(handler).toHaveBeenCalledTimes(1)

    // 恢复 → true
    setNamespaceState(true, true)
    handlers.forEach(h => h('/ws/logs', true))
    expect(handler).toHaveBeenCalledTimes(2)
    expect(handler).toHaveBeenLastCalledWith(true)
  })

  it('退订后不再收到回调', () => {
    setNamespaceState(false, false)
    const registeredListeners: Array<(namespace: string, connected: boolean) => void> = []
    socketMocks.onConnectionChange.mockImplementation((listener: (namespace: string, connected: boolean) => void) => {
      registeredListeners.push(listener)
      return () => {
        const index = registeredListeners.indexOf(listener)
        if (index >= 0) registeredListeners.splice(index, 1)
      }
    })

    const handler = vi.fn()
    const off = onConnectionChange(handler)
    expect(registeredListeners).toHaveLength(1)

    off()
    expect(registeredListeners).toHaveLength(0)

    setNamespaceState(true, true)
    registeredListeners.forEach(h => h('/', true))
    expect(handler).not.toHaveBeenCalled()
  })
})
