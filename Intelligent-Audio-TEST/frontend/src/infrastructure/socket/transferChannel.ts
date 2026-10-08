/**
 * Transfer Socket Channel —— import_progress 消息通道封装（INT-25）
 *
 * Infrastructure 消息通道层：内部组合 socketService 与 dataTransferAdapter，
 * 对业务层只暴露 camelCase Domain 契约（'/' 命名空间，后端经 Redis 转发）。
 */
import socketService from '../../utils/socket'
import { toImportProgress } from '../adapters/dataTransferAdapter'
import type { ImportProgress } from '../../domain/model/dataTransfer'

/** Socket 事件名（后端 api_gateway 在 '/' 命名空间 emit） */
const TRANSFER_SOCKET_EVENTS = {
  importProgress: 'import_progress',
} as const

/** 监听任务数据导入进度（payload 已转 camelCase Domain） */
export function onImportProgress(handler: (progress: ImportProgress) => void): () => void {
  const wrapped = (raw: any) => handler(toImportProgress(raw ?? {}))
  socketService.on(TRANSFER_SOCKET_EVENTS.importProgress, wrapped)
  return () => socketService.off(TRANSFER_SOCKET_EVENTS.importProgress, wrapped)
}
