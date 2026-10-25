/**
 * 设备管理页常量（interfaces/features/devices；16_设备域.md §9 中文文案源）。
 * 三页签白名单、facet 选项、状态映射、分页选项——全部中文文案硬编码（§9 源）。
 */

/** 页签 key（§3.1 测试设备/播放设备/测试 API；路由白名单 §3.2） */
export type DevicesTabKey = 'test' | 'playback' | 'api'

export const DEVICES_TABS: ReadonlyArray<{
  value: DevicesTabKey
  label: string
  requiredPermission: string
}> = [
  { value: 'test', label: '测试设备', requiredPermission: 'device:read' },
  { value: 'playback', label: '播放设备', requiredPermission: 'playback:read' },
  { value: 'api', label: '测试 API', requiredPermission: 'api_config:read' },
]

export const DEVICES_TAB_WHITELIST: ReadonlyArray<string> = ['test', 'playback', 'api']

/** 搜索防抖毫秒（§5.2 search debounce 500ms 口径） */
export const DEVICES_SEARCH_DEBOUNCE_MS = 500

export const DEFAULT_PAGE_SIZE = 20

export const PAGE_SIZE_OPTIONS = [10, 20, 30, 40, 50, 100]

/** 五态状态 facet（§9：在线/离线/连接中/断开中/错误；「测试中」占用态不参与筛选 §3.4） */
export const STATUS_FILTER_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'online', label: '在线' },
  { value: 'offline', label: '离线' },
  { value: 'connecting', label: '连接中' },
  { value: 'disconnecting', label: '断开中' },
  { value: 'error', label: '错误' },
]

/** 播放设备类型 facet（§9：干声/噪声） */
export const PLAYBACK_TYPE_FILTER_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'dry', label: '干声' },
  { value: 'noise', label: '噪声' },
]

/** 测试设备连接方式 facet（§9：USB连接/远程连接） */
export const CONNECTION_TYPE_FILTER_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'usb', label: 'USB连接' },
  { value: 'remote', label: '远程连接' },
]

/** API 协议 facet（§9：HTTP/HTTPS/WS/WSS） */
/** API 协议 facet（INT-1800 / B0 §3.2：值域收敛为 4 个规范值，不再有 https/ws/wss） */
export const API_PROTOCOL_FILTER_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'http', label: 'HTTP' },
  { value: 'websocket', label: 'WebSocket' },
  { value: 'sse', label: 'SSE' },
  { value: 'grpc', label: 'gRPC' },
]

/** API 流式性 facet（INT-1800：第二维，与协议独立） */
export const API_STREAMING_FILTER_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'true', label: '流式' },
  { value: 'false', label: '非流式' },
]

/** API 环境 facet（§9：开发/测试/生产） */
export const API_ENV_FILTER_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'development', label: '开发' },
  { value: 'testing', label: '测试' },
  { value: 'production', label: '生产' },
]

/** 搜索占位（§9 逐页签） */
export const DEVICES_SEARCH_PLACEHOLDER: Record<DevicesTabKey, string> = {
  test: '搜索设备名称或型号',
  playback: '搜索播放设备名称或型号',
  api: '搜索 API 名称或端点',
}

/** 主按钮文案（§9：随页签） */
export const DEVICES_ADD_BUTTON_LABEL: Record<DevicesTabKey, string> = {
  test: '添加测试设备',
  playback: '添加播放设备',
  api: '添加测试API',
}

/** 统计徽章（§9：测试/播放 四枚；API 页签四枚独立口径） */
export const DEVICES_STATS_LABELS: Record<DevicesTabKey, string[]> = {
  test: ['总设备数', '在线设备', '离线设备', '异常设备'],
  playback: ['总设备数', '在线设备', '离线设备', '异常设备'],
  api: ['总测试API数', '可用API', '不可用API', '测试中API'],
}

/* ───────── 导入 / 导出（§3.3/§4.5；INT-816 三资源端点，INT-1624 接线） ───────── */

/** 资源中文名（弹窗标题与提示用；页签值 → 与菜单同源） */
export const DEVICES_RESOURCE_LABEL: Record<DevicesTabKey, string> = {
  test: '测试设备',
  playback: '播放设备',
  api: '测试 API',
}

/** 导入文件接收类型（后端 device_import_export_service.py `_parse_import_file` 支持集） */
export const DEVICES_IMPORT_ACCEPT = '.json,.csv,.xlsx'

/** 导入格式提示文案（§4.5.1） */
export const DEVICES_IMPORT_FORMAT_HINT = '支持格式：JSON / CSV / Excel'

/** 导出格式选项（ResourceExportQuery.format；默认 JSON） */
export const DEVICES_EXPORT_FORMAT_OPTIONS: ReadonlyArray<{
  value: 'json' | 'excel'
  label: string
}> = [
  { value: 'json', label: 'JSON' },
  { value: 'excel', label: 'Excel' },
]

/** 导出范围选项（§4.5.2；映射见 domain/models/deviceImportExport.ts） */
export const DEVICES_EXPORT_RANGE_OPTIONS: ReadonlyArray<{
  value: 'all' | 'selected' | 'filtered'
  label: string
}> = [
  { value: 'all', label: '全部' },
  { value: 'selected', label: '当前页选中' },
  { value: 'filtered', label: '当前筛选结果' },
]
