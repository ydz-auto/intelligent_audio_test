/**
 * TaskChannel Port —— 任务进度 / 日志 Socket 通道的应用层出口
 *
 * 薄直通封装（与 xxxPort 一致）：Infrastructure 的 taskChannel 单点收敛于此，
 * Presentation/Application 只许 import 本 Port；
 * 后续缓存 / 编排只需改本文件，消费方零改动。
 */
import {
  onTaskProgress,
  onTaskLog,
  subscribeTask,
  unsubscribeTask,
} from '../../infrastructure/socket/taskChannel'

export const taskChannelPort = {
  onTaskProgress,
  onTaskLog,
  subscribeTask,
  unsubscribeTask,
}
