/**
 * /ws/logs 主通道 transport 回归（INT-1685）：多 uvicorn worker 下 engine.io 会话只存在于
 * 接住握手的那个进程，polling 的后续 HTTP 请求被内核分到别的 worker 即「会话未知」。
 * 客户端必须固定 websocket-only（单条长连接、不依赖会话粘滞），不得再加回 polling 回退。
 */
import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const ioMock = vi.fn()

vi.mock('socket.io-client', () => ({
  io: (...args: unknown[]) => ioMock(...args),
}))

import { useLogRealtimeWs } from '../useLogRealtimeWs'

function makeSocket() {
  return {
    connected: false,
    on: vi.fn(),
    emit: vi.fn(),
    disconnect: vi.fn(),
  }
}

describe('useLogRealtimeWs transport 配置（INT-1685）', () => {
  beforeEach(() => {
    ioMock.mockReset()
    ioMock.mockReturnValue(makeSocket())
  })

  it('只走 websocket transport，不配 polling 回退', () => {
    renderHook(() => useLogRealtimeWs({ enabled: true, filter: {}, onLog: () => {} }))

    expect(ioMock).toHaveBeenCalledTimes(1)
    const [url, options] = ioMock.mock.calls[0] as [string, { transports: string[]; path: string }]
    expect(url).toBe('/ws/logs')
    expect(options.path).toBe('/socket.io')
    expect(options.transports).toEqual(['websocket'])
  })
})
