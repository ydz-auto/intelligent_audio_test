/**
 * ApiDevice → ApiConfig 投影（features/devices/lib；INT-1938）。
 *
 * 用途：「设备管理 → 测试 API」页签行菜单「编辑」与详情弹窗「编辑」复用
 * `features/test-execution/modals/api-edit-dialog.tsx`（10_测试执行.md:323 §5.3、
 * 16_设备域.md:157「本卡零重复，行菜单『编辑』直接开同件」），该弹窗的入参是 ApiConfig。
 *
 * 两个模型同源（都来自 GET /apis 的 ApiItemDto），ApiDevice 是视角更全的一方
 * （多 environment / proxy / rmsSpl 等设备页列），ApiConfig 是弹窗消费子集，
 * 因此投影只做字段裁剪、不改变值：
 * - protocol / streaming 必须带过去——弹窗的协议 × 流式性两维（INT-1800）缺了会回落到默认值，
 *   保存时把实际协议 / 流式性改写成默认组合；口径与 apiConfigAdapter.apiConfigFromDto 一致
 *   （越界或缺失 → protocol 为 null，界面显示「—」，不猜协议）；
 * - audioConfig 必须带过去——弹窗缺这列时音频格式编辑区读不到现值，保存会清空 audio_config；
 * - meta 带原始整块：弹窗以此 + 打开时 GET /apis/{id} 的最新快照做键级合并基座。
 */
import type { ApiConfig } from '@/domain/models/apiConfig'
import type { ApiDevice } from '@/domain/models/apiDevice'
import { isApiProtocol } from '@/domain/models/apiProtocol'

export function apiConfigFromApiDevice(device: ApiDevice): ApiConfig {
  const maxProcessValues = device.endpoints
    .map((endpoint) => endpoint.maxProcess)
    .filter((value): value is number => typeof value === 'number')

  return {
    id: device.id,
    name: device.name,
    vendor: device.vendor,
    description: device.description,
    status: device.status,
    algorithmType: device.algorithmType,
    defaultMaxProcess: device.defaultMaxProcess,
    defaultMaxTimeout: device.defaultMaxTimeout,
    defaultMaxAudioDuration: device.defaultMaxAudioDuration,
    healthScore: device.healthScore,
    endpoints: device.endpoints,
    // 与 apiConfigAdapter.apiConfigFromDto 同口径：端点级最大并发与默认并发的较大者
    maxConcurrent: maxProcessValues.length
      ? Math.max(...maxProcessValues, device.defaultMaxProcess ?? 0)
      : (device.defaultMaxProcess ?? 0),
    protocol: isApiProtocol(device.protocol) ? device.protocol : null,
    streaming: device.streaming,
    meta: device.meta,
    audioConfig: device.audioConfig,
  }
}
