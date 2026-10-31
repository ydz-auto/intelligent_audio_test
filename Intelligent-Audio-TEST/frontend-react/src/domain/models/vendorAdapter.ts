/**
 * 厂商适配器（meta.vendor_adapter）词表 —— 后端 `VendorAdapterType` 的同值域镜像。
 *
 * 单一来源：`shared/models/common_enums.py::VendorAdapterType` +
 * `api_test_service/infrastructure/adapters/registry.py::_FLAT_KEY_DIMENSIONS`。
 * 值只是「扁平适配器 key」，不是类名：执行期由注册表映射到
 * `(AdapterProtocol, AdapterVendor)` 再实例化；写错值会在执行期被拒绝，
 * 因此 UI 必须是受控下拉，不允许自由文本。
 */

export const VENDOR_ADAPTER_TYPES = [
  '',
  'api_driver',
  'mock',
  'openai',
  'openai_realtime',
] as const

export type VendorAdapterType = (typeof VENDOR_ADAPTER_TYPES)[number]

export interface VendorAdapterOption {
  value: VendorAdapterType
  label: string
  /** 下拉项说明（执行语义） */
  hint: string
}

/** 下拉候选（顺序即展示顺序；空串 = 不写 meta.vendor_adapter） */
export const VENDOR_ADAPTER_OPTIONS: readonly VendorAdapterOption[] = [
  {
    value: '',
    label: '默认（不指定）',
    hint: '按 API 的 protocol 列选协议实现，绝大多数场景选这个',
  },
  {
    value: 'api_driver',
    label: 'API 驱动（通用）',
    hint: 'HTTP / WS / SSE / gRPC 通用驱动，按 protocol 列分发',
  },
  {
    value: 'mock',
    label: 'Mock 回放（不出网）',
    hint: '回显输入 + 预设应答，用于联调与冒烟，不发起真实请求',
  },
  {
    value: 'openai',
    label: 'OpenAI Realtime 协议',
    hint: 'OpenAI Realtime 事件协议（response.audio.delta 等），仅用于实时语音',
  },
  {
    value: 'openai_realtime',
    label: 'OpenAI Realtime（历史别名）',
    hint: '与 openai 等价，存量配置兼容用；新建请选 openai',
  },
]
