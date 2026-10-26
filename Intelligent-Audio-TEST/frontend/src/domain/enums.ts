/** 领域枚举定义 —— 值 = 后端原值，禁止改动值；文件为 domain 层单一来源 */
/** 任务状态枚举 */
export const TaskStatus = {
  PENDING: 'pending',
  QUEUED: 'queued',
  RUNNING: 'running',
  STARTING: 'starting',
  COMPLETED: 'completed',
  FAILED: 'failed',
  PAUSED: 'paused',
  STOPPED: 'stopped',
  SKIPPED: 'skipped',
  MERGED: 'merged',
  // 后端扩展状态（评估相关）
  EVALUATING: 'evaluating',
  REEVALUATING: 'reevaluating',
  REEVALUATE_QUEUED: 'reevaluate_queued',
} as const

/** 任务状态类型（由 TaskStatus 派生的字符串联合，供响应式状态标注使用） */
export type TaskStatusType = typeof TaskStatus[keyof typeof TaskStatus]

/**
 * 任务级评估状态枚举（INT-301，值 = 后端任务级评估状态原值，禁止改动值）。
 * 任务级双状态：执行状态（TaskStatus 执行域值）与评估状态完全分离，
 * 重新评估推进只落评估侧（evaluating→completed），执行侧不变。
 */
export const TaskEvaluationStatus = {
  PENDING: 'pending',
  EVALUATING: 'evaluating',
  COMPLETED: 'completed',
  FAILED: 'failed',
  SKIPPED: 'skipped',
} as const

/** 任务级评估状态类型 */
export type TaskEvaluationStatusType = typeof TaskEvaluationStatus[keyof typeof TaskEvaluationStatus]

/** 已结束的任务状态集合 */
export const FINISHED_STATUSES = [
  TaskStatus.COMPLETED,
  TaskStatus.FAILED,
  TaskStatus.STOPPED,
  TaskStatus.PAUSED,
  TaskStatus.SKIPPED,
  TaskStatus.MERGED,
] as const

/**
 * 可重执行任务状态集合（INT-410，任务重新执行功能设计文档 §5 约束#1，负责人裁定 2026-10-15）。
 * 重执行准入 = completed/failed/stopped 三态；pending 不允许（需先停止），
 * queued/running/paused 亦不可见。区别于 FINISHED_STATUSES（含 paused/skipped/merged）。
 */
export const REEXECUTE_ELIGIBLE_STATUSES = [
  TaskStatus.COMPLETED,
  TaskStatus.FAILED,
  TaskStatus.STOPPED,
] as const

/**
 * 可挑选（加入购物车）任务状态集合（INT-553 P3-4，INT-339 §10 默认仅终态任务可挑选）。
 * 挑选入口可见性（TestExecutionComponent）与 openCherryPick 门控（TaskDetailModal）同源此集合，
 * 禁止散落字面量。后端历史遗留 'finished'/'success' 不在集合内——入口不可见即不可点，
 * 消除「按钮可见但点击仅 warning」的前后口径不一致。
 * 类型用 readonly string[]：门控以任意 task status 字符串入参，字面量联合会让 includes 报类型错。
 */
export const PICKABLE_STATUSES: readonly string[] = [
  TaskStatus.COMPLETED,
  TaskStatus.FAILED,
  TaskStatus.STOPPED,
]

/** 用例执行状态枚举 */
export const ExecutionStatus = {
  PENDING: 'pending',
  QUEUED: 'queued',
  IN_PROGRESS: 'in_progress',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  STOPPED: 'stopped',
} as const

/** 用例评估状态枚举（值 = 后端 shared EvaluationStatus 原值，含停止中断评估 stopped） */
export const EvaluationStatus = {
  PENDING: 'pending',
  QUEUED: 'queued',
  CALCULATING: 'calculating',
  RUNNING: 'running',
  COMPLETED: 'completed',
  STOPPED: 'stopped',
  FAILED: 'failed',
} as const

/**
 * 用例复合结果状态枚举（INT-405，值 = 后端 TaskCaseStatus 原值，禁止改动值）。
 * 由后端 derive_task_case_status(execution_status, evaluation_status) 派生，
 * 仅作筛选/行底色等数据口径，展示走执行/评估双徽章独立映射。
 */
export const TaskCaseStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  EVALUATING: 'evaluating',
  COMPLETED: 'completed',
  FAILED: 'failed',
  SKIPPED: 'skipped',
} as const

/** 测试类型枚举 */
export const TestType = {
  API: 'api',
  E2E: 'e2e',
} as const

/** 评估维度轮次模式枚举（值 = 后端 round_mode 原值，禁止改动值） */
export const RoundMode = {
  ALL: 'all',
  SPECIFIC: 'specific',
  PER_ROUND: 'per_round',
} as const

/** 评估维度轮次模式类型 */
export type RoundModeType = typeof RoundMode[keyof typeof RoundMode]

/** 视图模式枚举 */
export const ViewMode = {
  ALL: 'all',
  GROUP: 'group',
  TAG: 'tag',
} as const

/**
 * 音频导入「标签来源」枚举（值 = 后端 tag_source 原值，禁止改动值；INT-1983）
 * - both：请求 tags = 手填标签 + 各分组 JSON 顶层 tags，后端同时按目录路径解析
 * - path：请求 tags 只含手填标签（不并入 JSON tags），后端按目录路径解析
 * - json：请求 tags = 手填标签 + 各分组 JSON 顶层 tags，后端不做路径解析
 */
export const AudioTagSource = {
  BOTH: 'both',
  PATH: 'path',
  JSON: 'json',
} as const

/** 音频导入「标签来源」类型 */
export type AudioTagSourceType = typeof AudioTagSource[keyof typeof AudioTagSource]

/** 上传状态枚举 */
export const UploadStatus = {
  IDLE: 'idle',
  PREPARING: 'preparing',
  PENDING: 'pending',
  UPLOADING: 'uploading',
  COMPLETED: 'completed',
  FAILED: 'failed',
  PAUSED: 'paused',
  STOPPED: 'stopped',
} as const

/** 字段类型枚举（值 = 后端 shared.models.common_enums.FieldType 原值，禁止改动值） */
export const FieldType = {
  RTTM: 'rttm',
  STM: 'stm',
  TEXT: 'text',
  AUDIO_FILE: 'audio_file',
  AUDIO: 'audio',
  NUMBER: 'number',
  BOOLEAN: 'boolean',
  JSON: 'json',
  TIMESTAMP: 'timestamp',
} as const

/** 字段类型（由 FieldType 派生的字符串联合） */
export type FieldTypeType = typeof FieldType[keyof typeof FieldType]

/** 报告状态枚举 */
export const ReportStatus = {
  COMPLETED: 'completed',
  FAILED: 'failed',
  RUNNING: 'running',
  DRAFT: 'draft',
  FINAL: 'final',
  PUBLISHED: 'published',
  GENERATING: 'generating',
} as const

/** HTTP 状态码 */
export const HttpStatus = {
  OK: 200,
  CREATED: 201,
  NO_CONTENT: 204,
  PARTIAL_CONTENT: 206,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  TOO_MANY_REQUESTS: 429,
  SERVER_ERROR: 500,
  INTERNAL_SERVER_ERROR: 500,
  BAD_GATEWAY: 502,
  SERVICE_UNAVAILABLE: 503,
  GATEWAY_TIMEOUT: 504,
} as const

/** 认证域业务错误码（值 = 后端 api_gateway ErrorCode.AUTH_*，禁止改动值） */
export const AuthErrorCode = {
  /** 登录加密校验失败（加密开启时载荷无效/明文提交），应引导刷新重试而非提示密码错误 */
  ENCRYPTION_INVALID: 105,
  /** 用户名或密码错误 */
  CREDENTIALS_INVALID: 106,
} as const

/** 设备状态枚举（值 = 后端 status 字段原值，禁止改动值） */
export const DeviceStatus = {
  ONLINE: 'online',
  OFFLINE: 'offline',
  TESTING: 'testing',
} as const

/** 设备状态类型（含后端扩展值兜底，供 domain/model/device.ts 引用） */
export type DeviceStatusType = typeof DeviceStatus[keyof typeof DeviceStatus] | (string & {})

/** 日志级别枚举（值 = 后端 level 查询参数原值，大写） */
export const LogLevel = {
  DEBUG: 'DEBUG',
  INFO: 'INFO',
  WARNING: 'WARNING',
  ERROR: 'ERROR',
} as const

/** 日志级别类型 */
export type LogLevelType = typeof LogLevel[keyof typeof LogLevel]

/** API 端点/配置状态枚举（值 = 后端 status 字段原值，禁止改动值） */
export const ApiEndpointStatus = {
  ONLINE: 'online',
  OFFLINE: 'offline',
  BUSY: 'busy',
  ERROR: 'error',
} as const

/** API 端点/配置状态类型 */
export type ApiEndpointStatusType = typeof ApiEndpointStatus[keyof typeof ApiEndpointStatus]

/** 被测设备类型枚举（值 = 后端 shared.models.common_enums.DeviceType 原值，决定执行路由） */
export const DeviceType = {
  PHYSICAL: 'physical',
  HTTP_API: 'http_api',
  WEBSOCKET_API: 'websocket_api',
} as const

/** 被测设备类型（由 DeviceType 派生的字符串联合） */
export type DeviceTypeType = typeof DeviceType[keyof typeof DeviceType]

/**
 * 设备管理页页签类型枚举（Device 页 UI 页签语义，INT-74）
 * 区别于后端 DeviceType（被测设备类型，决定执行路由）：
 * TEST/PLAYBACK 为物理设备分组页签，API 为被测 API 页签
 */
export const DeviceTabType = {
  TEST: 'test',
  API: 'api',
  PLAYBACK: 'playback',
} as const

/** 设备管理页页签类型（由 DeviceTabType 派生的字符串联合） */
export type DeviceTabTypeType = typeof DeviceTabType[keyof typeof DeviceTabType]

/** API 传输协议枚举（值 = 后端 shared.models.common_enums.APIProtocol 原值，Adapter 分型依据） */
export const APIProtocol = {
  HTTP: 'http',
  WEBSOCKET: 'websocket',
} as const

/** API 传输协议类型 */
export type APIProtocolType = typeof APIProtocol[keyof typeof APIProtocol]

/** API 输出类型枚举（值 = 后端 shared.models.common_enums.OutputType 原值，多模态输出采集） */
export const OutputType = {
  AUDIO: 'audio',
  TEXT: 'text',
  VIDEO: 'video',
  IMAGE: 'image',
} as const

/** API 输出类型（由 OutputType 派生的字符串联合） */
export type OutputTypeType = typeof OutputType[keyof typeof OutputType]

/** 被测 API 网络代理类型枚举（INT-839，值 = 后端 api 表 proxy_type 原值；NULL 或空 = 不用代理） */
export const ProxyType = {
  HTTP: 'http',
  HTTPS: 'https',
  SOCKS5: 'socks5',
  SOCKS5H: 'socks5h',
} as const

/** 被测 API 网络代理类型（由 ProxyType 派生的字符串联合） */
export type ProxyTypeType = typeof ProxyType[keyof typeof ProxyType]

/** SPL 校准状态枚举（值 = 后端 shared.models.common_enums.CalibrationStatus 原值） */
export const CalibrationStatus = {
  CALIBRATED: 'calibrated',
  UNCALIBRATED: 'uncalibrated',
} as const

/** SPL 校准状态类型 */
export type CalibrationStatusType = typeof CalibrationStatus[keyof typeof CalibrationStatus]

/** Benchmark 被测类别枚举（值 = 网关 PublishedTaskCreateRequest.benchmark_category 契约值，快照 benchmarkCategory，排行分组用） */
export const BenchmarkCategory = {
  ASR: 'asr',
  VOICE_LLM: 'voice_llm',
  TTS: 'tts',
  TRANSLATION: 'translation',
} as const

/** Benchmark 被测类别类型（由 BenchmarkCategory 派生的字符串联合） */
export type BenchmarkCategoryType = typeof BenchmarkCategory[keyof typeof BenchmarkCategory]

/** Benchmark 被测类别标签（展示用，与枚举值一一对应） */
export const BenchmarkCategoryLabels: Record<BenchmarkCategoryType, string> = {
  [BenchmarkCategory.ASR]: '语音识别（ASR）',
  [BenchmarkCategory.VOICE_LLM]: '语音大模型（Voice LLM）',
  [BenchmarkCategory.TTS]: '语音合成（TTS）',
  [BenchmarkCategory.TRANSLATION]: '翻译（Translation）',
}

/**
 * Benchmark 被测类别页签标签（排行页 Hero 下划线页签，INT-359 文案口径：
 * 全部/语音识别/语音对话/语音合成/翻译；空串 = 全部）。
 * 与既有 BenchmarkCategoryLabels（完整名，用于发布任务等上下文）并存，互不影响。
 */
export const BenchmarkCategoryTabLabels: Record<'' | BenchmarkCategoryType, string> = {
  '': '全部',
  [BenchmarkCategory.ASR]: '语音识别',
  [BenchmarkCategory.VOICE_LLM]: '语音对话',
  [BenchmarkCategory.TTS]: '语音合成',
  [BenchmarkCategory.TRANSLATION]: '翻译',
}

/** Benchmark 排行数据来源枚举（值 = 后端 benchmark_rankings.source 原值，禁止改动值） */
export const BenchmarkSource = {
  PLATFORM_TEST: 'platform_test',
  EXTERNAL_IMPORT: 'external_import',
} as const

/** Benchmark 排行数据来源类型（由 BenchmarkSource 派生的字符串联合） */
export type BenchmarkSourceType = typeof BenchmarkSource[keyof typeof BenchmarkSource]

/** Benchmark 排行数据来源标签（展示用，与枚举值一一对应） */
export const BenchmarkSourceLabels: Record<BenchmarkSourceType, string> = {
  [BenchmarkSource.PLATFORM_TEST]: '平台实测',
  [BenchmarkSource.EXTERNAL_IMPORT]: '外部基线',
}

/** Benchmark 排行方向枚举（值 = 后端 RankingDirection 原值，禁止改动值） */
export const BenchmarkDirection = {
  LOWER_IS_BETTER: 'lower_is_better',
  HIGHER_IS_BETTER: 'higher_is_better',
} as const

/** Benchmark 排行方向类型（由 BenchmarkDirection 派生的字符串联合） */
export type BenchmarkDirectionType = typeof BenchmarkDirection[keyof typeof BenchmarkDirection]

/** Benchmark 排行方向标签（展示用，与枚举值一一对应） */
export const BenchmarkDirectionLabels: Record<BenchmarkDirectionType, string> = {
  [BenchmarkDirection.LOWER_IS_BETTER]: '越低越好',
  [BenchmarkDirection.HIGHER_IS_BETTER]: '越高越好',
}

/** Benchmark 被测主体类型枚举（值 = 后端 benchmark_rankings.subject_type 原值，禁止改动值） */
export const BenchmarkSubjectType = {
  OPEN_SOURCE: 'open_source',
  CLOSED_SOURCE: 'closed_source',
  APP: 'app',
} as const

/** Benchmark 被测主体类型（由 BenchmarkSubjectType 派生的字符串联合） */
export type BenchmarkSubjectTypeType = typeof BenchmarkSubjectType[keyof typeof BenchmarkSubjectType]

/** Benchmark 被测主体类型标签（展示用，与枚举值一一对应） */
export const BenchmarkSubjectTypeLabels: Record<BenchmarkSubjectTypeType, string> = {
  [BenchmarkSubjectType.OPEN_SOURCE]: '开源',
  [BenchmarkSubjectType.CLOSED_SOURCE]: '闭源',
  [BenchmarkSubjectType.APP]: 'App',
}

/** Benchmark 被测设备类型标签（值 = 既有 DeviceType 枚举，展示用） */
export const BenchmarkDeviceTypeLabels: Record<DeviceTypeType, string> = {
  [DeviceType.PHYSICAL]: '实体设备',
  [DeviceType.HTTP_API]: 'HTTP API',
  [DeviceType.WEBSOCKET_API]: 'WebSocket API',
}

/** 认证模式枚举（值 = 后端 Config.AUTH_MODE 原值，禁止改动值；前端构建期同名变量 VITE_AUTH_MODE） */
export const AuthMode = {
  /** 关闭认证（向后兼容）：后端注入 permissions=['*']，前端无 token 放行 */
  OFF: 'off',
  /** 本地 OAuth（开发态） */
  DEV: 'dev',
  /** 华为云 OAuth（生产态） */
  PROD: 'prod',
} as const

/** 认证模式类型（由 AuthMode 派生的字符串联合） */
export type AuthModeType = typeof AuthMode[keyof typeof AuthMode]

/** 认证模式全部合法取值（生产构建注入校验单一来源，vite.config 构建守卫引用） */
export const AUTH_MODE_VALUES: readonly AuthModeType[] = [
  AuthMode.OFF,
  AuthMode.DEV,
  AuthMode.PROD,
]

/**
 * 前端本地生效认证模式（INT-180 启动自检比对基准）。
 * 与 router/client 401 判定同源（未注入回退 off，向后兼容语义不变），
 * 启动自检用它和后端 /auth/mode 报告值比对，两侧读法必须一致。
 * readEnv 仅供测试注入；vitest 下各模块 import.meta.env 为独立快照，
 * 直接改写无法被本函数读到。
 */
type AuthModeEnvReader = () => unknown

const defaultAuthModeEnvReader: AuthModeEnvReader = () =>
  (import.meta as any).env?.VITE_AUTH_MODE

export function getEffectiveAuthMode(
  readEnv: AuthModeEnvReader = defaultAuthModeEnvReader,
): AuthModeType {
  return (readEnv() || AuthMode.OFF) as AuthModeType
}

/**
 * 资源可见性枚举（INT-423/467，值 = 后端 Visibility 原值，禁止改动值）。
 * 二值体系：private=仅 owner+admin 可见可操作；shared=回落 RBAC 权限点语义。
 */
export const Visibility = {
  SHARED: 'shared',
  PRIVATE: 'private',
} as const

/** 资源可见性类型（由 Visibility 派生；字符串兜底兼容后端扩展） */
export type VisibilityType = typeof Visibility[keyof typeof Visibility] | (string & {})

/** Realtime 输入节奏策略枚举（INT-475，值 = 后端 shared RealtimePacingStrategy 原值，禁止改动值）。
 *  FIXED 恒定节奏（默认=现状）/ WAIT_TURN_END 等输出 turn 结束再推下一帧 /
 *  ALLOW_BARGE_IN 允许输入推流中模型提前回话/打断 / TIMEOUT_FALLBACK 无输出按配置超时兜底。
 */
export const RealtimePacingStrategy = {
  FIXED: 'fixed',
  WAIT_TURN_END: 'wait_turn_end',
  ALLOW_BARGE_IN: 'allow_barge_in',
  TIMEOUT_FALLBACK: 'timeout_fallback',
} as const

/** Realtime 输入节奏策略类型（由 RealtimePacingStrategy 派生） */
export type RealtimePacingStrategyType =
  typeof RealtimePacingStrategy[keyof typeof RealtimePacingStrategy]

/** 权限点（INT-298，对齐 V9.7.10 / 后端 RBAC seed「资源:操作」命名；值 = 后端 PermissionPoints 原值，禁止改动值） */
export const PermissionPoint = {
  /** 发布已发布任务（POST /published-tasks） */
  TASK_PUBLISH: 'task:publish',
  /** 挑选合并（购物车/下单三出口，INT-339 seed_rbac task:cherry_pick） */
  TASK_CHERRY_PICK: 'task:cherry_pick',
  /** 人工复核测试结果（INT-340 seed_rbac task.result.review） */
  TASK_RESULT_REVIEW: 'task.result.review',
  /** 查看已发布任务 */
  PUBLISHED_TASK_READ: 'published_task:read',
  /** 执行已发布任务 */
  PUBLISHED_TASK_EXECUTE: 'published_task:execute',
  /** 创建已发布任务新版本 */
  PUBLISHED_TASK_VERSION: 'published_task:version',
  /** 归档已发布任务 */
  PUBLISHED_TASK_ARCHIVE: 'published_task:archive',
  /** 查看 Benchmark 报告（GET /benchmarks/reports，INT-483） */
  BENCHMARK_REPORT_READ: 'benchmark:report:read',
  /** 发布 Benchmark 报告（POST /benchmarks/reports，INT-483） */
  BENCHMARK_REPORT_PUBLISH: 'benchmark:report:publish',
  /** 查看日志/统计/归档状态/归档列表/归档文件（GET /logs 系列，RBAC 口径） */
  LOG_READ: 'log:read',
  /** 标记/刷新/清空/触发归档/删除归档（写操作，RBAC 口径） */
  LOG_MANAGE: 'log:manage',
} as const

/** 权限点类型（由 PermissionPoint 派生） */
export type PermissionPointValue = typeof PermissionPoint[keyof typeof PermissionPoint]

/**
 * 列表加载失败分类（INT-255：错误态与空态分离；前端 UI 状态枚举，值非后端契约，禁止魔法字符串）。
 * 供列表类 composable 在请求失败时以枚举表达错误类型，视图据此渲染错误提示与重试入口。
 */
export const ListLoadErrorType = {
  /** 网络不可达（后端离线 / fetch 无响应 / http=000） */
  NETWORK: 'network',
  /** 服务端错误（HTTP 5xx / 业务系统错误码 3xx） */
  SERVER: 'server',
  /** 其它 / 未分类错误 */
  UNKNOWN: 'unknown',
} as const

/** 列表加载失败分类类型（由 ListLoadErrorType 派生） */
export type ListLoadErrorTypeValue = typeof ListLoadErrorType[keyof typeof ListLoadErrorType]
