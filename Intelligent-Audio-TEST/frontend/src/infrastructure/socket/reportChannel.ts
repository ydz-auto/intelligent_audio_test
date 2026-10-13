/**
 * Report Socket Channel —— report_generated / secondary_compare_generated 消息通道封装
 *
 * Infrastructure 消息通道层：内部组合 socketService，对业务层只暴露事件名常量与
 * 订阅/退订封装（原始 payload 透传；报告事件结构由后端协议决定，前端 camelCase 读取）。
 */
import socketService from '../../utils/socket'

/** Socket 原始事件名（通道契约，业务层不感知） */
const REPORT_SOCKET_EVENTS = {
  /** 任务报告异步生成完成 */
  generated: 'report_generated',
  /** 二次对比报告异步生成完成 */
  secondaryCompareGenerated: 'secondary_compare_generated',
} as const

/** 建立默认命名空间连接（报告事件走 '/'） */
export function connect(): void {
  socketService.connect()
}

/** 订阅报告事件，返回退订函数 */
export function onReportGenerated(handler: (data: any) => void): () => void {
  return socketService.on(REPORT_SOCKET_EVENTS.generated, handler)
}

export function offReportGenerated(handler: (data: any) => void): void {
  socketService.off(REPORT_SOCKET_EVENTS.generated, handler)
}

export function onSecondaryCompareGenerated(handler: (data: any) => void): () => void {
  return socketService.on(REPORT_SOCKET_EVENTS.secondaryCompareGenerated, handler)
}

export function offSecondaryCompareGenerated(handler: (data: any) => void): void {
  socketService.off(REPORT_SOCKET_EVENTS.secondaryCompareGenerated, handler)
}
