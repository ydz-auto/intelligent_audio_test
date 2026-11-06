/**
 * 设备管理页类型（interfaces/features/devices；§10 组件树落位）。
 * 筛选态 / 弹窗群状态 / 行操作类型——mock 阶段本地态（接线后 URL 态化见 §3.2）。
 */
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'
import type { DevicesTabKey } from '@/features/devices/constants'

/** 三页签通用筛选（§9 facet） */
export interface DevicesFilters {
  search: string
  status: string | null
  /** 实验室 facet（INT-487：DTO 未暴露前隐藏，mock 先行；选项动态 GET /laboratories） */
  labId: string | null
  groupId: string | null
}

/** 测试设备页签扩展筛选（连接方式/分组，§3.2/§3.4） */
export interface TestDeviceFilters extends DevicesFilters {
  connectionType: string | null
}

/** 播放设备页签扩展筛选（设备类型，§3.5） */
export interface PlaybackDeviceFilters extends DevicesFilters {
  deviceType: string | null
}

/** API 页签筛选（协议 / 流式性 / 环境，§3.6；INT-1800：协议与流式性两维独立可筛） */
export interface ApiDeviceFilters {
  search: string
  status: string | null
  protocol: string | null
  /** 流式性筛选：'true' / 'false' 字符串（URL/控件口径），null = 不限 */
  streaming: string | null
  environment: string | null
}

/**
 * 设备抽屉可承载的资源（INT-2153）：测试 API 的新增/编辑统一走 §5.3 API 编辑弹窗
 * （`test-execution/modals/api-edit-dialog`），抽屉只剩测试设备 / 播放设备两类；
 * 抽屉里原先的 API 分支（无请求模板 / 响应解析 / 参数配置）已移除，避免两套表单。
 */
export type DeviceMutateKind = 'test' | 'playback'

/** 新增/编辑抽屉分派（§6.2：随页签二分叉；device 编辑态必填，新建态可空） */
export interface DeviceMutateState {
  open: boolean
  mode: 'create' | 'edit'
  kind: DeviceMutateKind
  device?: TestDevice | PlaybackDevice | ApiDevice | null
}

/** 详情弹窗（§6.2 只读） */
export interface DeviceDetailState {
  open: boolean
  kind: DevicesTabKey
  device: TestDevice | PlaybackDevice | ApiDevice | null
}

/** 关联声压映射（§6.4，播放设备） */
export interface AssociateSplState {
  open: boolean
  device: PlaybackDevice | null
}

/** 删除确认目标（三页签共用） */
export interface DeviceDeleteTarget {
  kind: DevicesTabKey
  device: TestDevice | PlaybackDevice | ApiDevice
}

/** 页头三开关（§3.3） */
export interface DeviceHeaderToggles {
  batchMode: boolean
  alarmsOpen: boolean
  idSort: boolean
}

/** 行操作枚举（§3.4.1/§3.5/§3.6 菜单项，按状态与权限显隐） */
export type DeviceRowAction =
  | 'detail'
  | 'edit'
  | 'health'
  | 'test'
  | 'stop-test'
  | 'connect'
  | 'disconnect'
  | 'reboot'
  | 'shutdown'
  | 'install-app'
  | 'uninstall-app'
  | 'delete'
  | 'associate-spl'
  | 'play-test'
  | 'stop'
  | 'restart-playback'
  | 'reset-playback-config'
  | 'mute'
  | 'unmute'
  | 'result-analysis'
  | 'diagnose'
