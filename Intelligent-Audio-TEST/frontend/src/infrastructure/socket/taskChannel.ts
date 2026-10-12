/**
 * Task Socket Channel —— task_progress / task_log 消息通道封装
 *
 * Infrastructure 消息通道层：内部组合 socketService 与 taskProgressAdapter，
 * 对业务层只暴露 camelCase Domain 契约（snake_case 转换不出本层）。
 */
import socketService from '../../utils/socket'
import { toTaskProgress, toTaskLogPayload } from '../adapters/taskProgressAdapter'
import type { TaskProgress } from '../../domain/model/taskProgress'
import type { Log } from '../../domain'

/** Socket 原始事件名与命名空间（通道契约，业务层不感知） */
const TASK_SOCKET_EVENTS = {
  progress: 'task_progress',
  log: 'task_log',
  subscribe: 'subscribe_task',
  unsubscribe: 'unsubscribe_task',
} as const

/** 日志命名空间（task_log / 订阅事件走此通道） */
const LOG_NAMESPACE = '/ws/logs'

/** 通道依赖的两个命名空间：进度走默认 '/'，日志走 '/ws/logs' */
const CHANNEL_NAMESPACES = ['/', LOG_NAMESPACE] as const

/**
 * 通道整体是否可用：两个命名空间均已连接。
 * 任一命名空间断开即视为通道不可用（进度或日志至少一路失联）。
 */
export function isConnected(): boolean {
  return CHANNEL_NAMESPACES.every(namespace => socketService.isNamespaceConnected(namespace))
}

/** 订阅通道整体连接变化（边沿触发：仅在 / 与 /ws/logs 的聚合状态翻转时回调） */
export function onConnectionChange(handler: (connected: boolean) => void): () => void {
  let lastConnected = isConnected()
  return socketService.onConnectionChange(() => {
    const connected = isConnected()
    if (connected === lastConnected) return
    lastConnected = connected
    handler(connected)
  })
}

/** 监听任务进度推送（payload 已转 camelCase Domain） */
export function onTaskProgress(handler: (progress: TaskProgress) => void): () => void {
  const wrapped = (raw: any) => handler(toTaskProgress(raw))
  socketService.on(TASK_SOCKET_EVENTS.progress, wrapped)
  return () => socketService.off(TASK_SOCKET_EVENTS.progress, wrapped)
}

/** 监听任务日志推送（已拆分为 taskId + Log） */
export function onTaskLog(handler: (taskId: string, log: any) => void): () => void {
  const wrapped = (raw: any) => {
    const payload = toTaskLogPayload(raw)
    handler(payload.taskId, payload.log)
  }
  socketService.on(TASK_SOCKET_EVENTS.log, wrapped, LOG_NAMESPACE)
  return () => socketService.off(TASK_SOCKET_EVENTS.log, wrapped, LOG_NAMESPACE)
}

/** 订阅任务频道（emit 体在通道内转 snake_case） */
export function subscribeTask(taskId: string | number): void {
  socketService.emit(TASK_SOCKET_EVENTS.subscribe, { task_id: String(taskId) }, LOG_NAMESPACE)
}

/** 退订任务频道 */
export function unsubscribeTask(taskId: string | number): void {
  socketService.emit(TASK_SOCKET_EVENTS.unsubscribe, { task_id: String(taskId) }, LOG_NAMESPACE)
}
