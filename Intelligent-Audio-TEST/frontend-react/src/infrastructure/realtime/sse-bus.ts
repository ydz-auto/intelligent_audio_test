/**
 * SSE 共享单连接总线（infrastructure/realtime 层）。
 *
 * 背景（INT-xxxx 性能热修）：全站 SSE 订阅点原本各自调用 subscribeSse 建立独立
 * /api/v1/sse/events 长连接——通知中心（常驻）+ 设备状态流 / 报告帧 / 报告生成等待
 * （页面级）叠加后单页常驻 1~2 条 SSE。站点走 HTTP/1.1（每主机仅 6 并发连接），
 * SSE 占位 + 首屏 10+ 并发请求后连接池饥饿，导航文档 TTFB 偶发 6~34s。
 *
 * 本总线只维护 1 条共享连接（引用计数管理生命周期），事件按订阅者声明的
 * channel 子集分发；最后一个订阅者解绑时才断开。断线重连/心跳/同事件去重由
 * 底层 subscribeSse 承担（单连接 = 单去重作用域，先于分发去重，各订阅者各收一次）。
 */
import {
  subscribeSse,
  type SseChannel,
  type SseEvent,
  type SseStatus,
} from './sse'

interface SharedSseSubscribeOptions {
  /** 订阅通道子集；缺省接收全部通道（未知通道事件仍透传） */
  channels?: SseChannel[]
  onEvent: (event: SseEvent) => void
  onStatusChange?: (status: SseStatus) => void
  signal?: AbortSignal
}

interface BusSubscriber {
  channels: SseChannel[] | undefined
  onEvent: (event: SseEvent) => void
  onStatusChange: ((status: SseStatus) => void) | undefined
  signal: AbortSignal | undefined
  onAbort: (() => void) | null
}

/** 当前活跃订阅者（Set 引用；解绑即移除） */
const subscribers = new Set<BusSubscriber>()
/** 共享连接解绑函数；null = 当前无连接 */
let teardownShared: (() => void) | null = null
/** 最近一次连接状态（新订阅者加入时回放，避免卡在 connecting） */
let lastStatus: SseStatus = 'connecting'

function emitStatus(status: SseStatus): void {
  lastStatus = status
  for (const sub of subscribers) {
    sub.onStatusChange?.(status)
  }
}

function ensureConnection(): void {
  if (teardownShared) return
  teardownShared = subscribeSse({
    // 不传 channels：单连接接收全部事件，分发由本总线按订阅者声明过滤
    onEvent: (event) => {
      for (const sub of subscribers) {
        if (
          sub.channels &&
          event.channel !== undefined &&
          !sub.channels.includes(event.channel)
        ) {
          continue
        }
        sub.onEvent(event)
      }
    },
    onStatusChange: emitStatus,
  })
}

function teardownIfIdle(): void {
  if (subscribers.size === 0 && teardownShared) {
    teardownShared()
    teardownShared = null
    lastStatus = 'connecting'
  }
}

/**
 * 订阅共享 SSE 事件流。返回解绑函数（引用计数归零时自动断开共享连接）。
 * 与 subscribeSse 同款能力子集：channels 过滤 / onStatusChange / signal 终止。
 */
export function subscribeSharedSse(options: SharedSseSubscribeOptions): () => void {
  const sub: BusSubscriber = {
    channels: options.channels,
    onEvent: options.onEvent,
    onStatusChange: options.onStatusChange,
    signal: options.signal,
    onAbort: null,
  }

  const unsubscribe = (): void => {
    if (!subscribers.has(sub)) return
    if (sub.signal && sub.onAbort) {
      sub.signal.removeEventListener('abort', sub.onAbort)
      sub.onAbort = null
    }
    subscribers.delete(sub)
    teardownIfIdle()
  }

  subscribers.add(sub)
  ensureConnection()

  // 回放当前状态：共享连接可能早已 open，新订阅者无需再经历 connecting 等待
  options.onStatusChange?.(lastStatus)

  if (sub.signal) {
    sub.onAbort = (): void => unsubscribe()
    if (sub.signal.aborted) {
      unsubscribe()
    } else {
      sub.signal.addEventListener('abort', sub.onAbort, { once: true })
    }
  }

  return unsubscribe
}
