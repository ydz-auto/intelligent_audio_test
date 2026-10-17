/**
 * 平台统一接口错误码（domain 层；对照 api_gateway/utils/error_codes.py 全量枚举）。
 * 枚举值 = 后端 ErrorCode 原值，禁止改动；auth 域 105/106 与 domain/models/auth.ts
 * AuthErrorCode 同源（本枚举为全量视图）。
 */

export enum ApiErrorCode {
  SUCCESS = 0,
  // 1xx: 参数错误
  INVALID_PARAMS = 100,
  MISSING_PARAMS = 101,
  INVALID_TYPE = 102,
  UNAUTHORIZED = 103,
  FORBIDDEN = 104,
  // 登录 401 语义区分（INT-188）：加密载荷无效 vs 凭证错误
  AUTH_ENCRYPTION_INVALID = 105,
  AUTH_CREDENTIALS_INVALID = 106,
  // 2xx: 业务错误
  BUSINESS_ERROR = 200,
  NOT_FOUND = 201,
  ALREADY_EXISTS = 202,
  OPERATION_FAILED = 203,
  CONFLICT = 204,
  TASK_ALREADY_RUNNING = 205,
  TASK_NOT_FOUND = 206,
  CALIBRATION_FAILED = 210,
  TASK_EXECUTION_ERROR = 220,
  // 3xx: 系统错误
  SYSTEM_ERROR = 300,
  DATABASE_ERROR = 301,
  FILE_IO_ERROR = 302,
  NETWORK_ERROR = 303,
  INTERNAL_SERVER_ERROR = 304,
  INTERNAL_ERROR = 305,
  EXTERNAL_SERVICE_ERROR = 306,
}

/**
 * HTTP 状态码枚举（对照旧 Vue frontend/src/domain/enums.ts HttpStatus；
 * 信封成功码判定 / HTTP 兜底文案键引用，拒绝魔法数字）。
 */
export enum HttpStatus {
  OK = 200,
  CREATED = 201,
  NO_CONTENT = 204,
  PARTIAL_CONTENT = 206,
  BAD_REQUEST = 400,
  UNAUTHORIZED = 401,
  FORBIDDEN = 403,
  NOT_FOUND = 404,
  TOO_MANY_REQUESTS = 429,
  INTERNAL_SERVER_ERROR = 500,
  BAD_GATEWAY = 502,
  SERVICE_UNAVAILABLE = 503,
  GATEWAY_TIMEOUT = 504,
}

/**
 * 已知业务错误码 → 中文文案兜底（error_response 的 message/detail 已是中文时
 * 优先用服务端文案；本映射用于服务端文案缺失/过于笼统时的统一收敛）。
 * 引用 ApiErrorCode 枚举成员，拒绝魔法数字。
 */
export const API_ERROR_COPY: Partial<Record<ApiErrorCode, string>> = {
  [ApiErrorCode.UNAUTHORIZED]: '登录已过期，请重新登录',
  [ApiErrorCode.FORBIDDEN]: '无权限执行此操作',
  [ApiErrorCode.AUTH_ENCRYPTION_INVALID]: '登录加密校验失败，请刷新页面重试',
  [ApiErrorCode.AUTH_CREDENTIALS_INVALID]: '登录失败：用户名或密码错误',
  [ApiErrorCode.NOT_FOUND]: '请求的资源不存在',
  [ApiErrorCode.ALREADY_EXISTS]: '资源已存在，请勿重复创建',
  [ApiErrorCode.OPERATION_FAILED]: '操作失败，请稍后重试',
  [ApiErrorCode.CONFLICT]: '操作冲突，请刷新后重试',
  [ApiErrorCode.TASK_ALREADY_RUNNING]: '任务已在运行中，请先停止',
  [ApiErrorCode.TASK_NOT_FOUND]: '任务不存在或已被删除',
  [ApiErrorCode.SYSTEM_ERROR]: '系统内部错误，请稍后重试',
  [ApiErrorCode.DATABASE_ERROR]: '数据服务异常，请稍后重试',
  [ApiErrorCode.FILE_IO_ERROR]: '文件读写异常，请稍后重试',
  [ApiErrorCode.INTERNAL_SERVER_ERROR]: '系统内部错误，请稍后重试',
  [ApiErrorCode.INTERNAL_ERROR]: '系统内部错误，请稍后重试',
  [ApiErrorCode.EXTERNAL_SERVICE_ERROR]: '外部服务异常，请稍后重试',
}

/** HTTP 状态码兜底文案（响应无业务错误码时使用；键引用 HttpStatus 枚举） */
export const HTTP_STATUS_COPY: Record<number, string> = {
  [HttpStatus.BAD_REQUEST]: '请求参数有误，请检查后重试',
  [HttpStatus.UNAUTHORIZED]: '登录已过期，请重新登录',
  [HttpStatus.FORBIDDEN]: '无权限执行此操作',
  [HttpStatus.NOT_FOUND]: '请求的资源不存在',
  [HttpStatus.TOO_MANY_REQUESTS]: '请求过于频繁，请稍后重试',
  [HttpStatus.INTERNAL_SERVER_ERROR]: '服务器内部错误，请稍后重试',
  [HttpStatus.BAD_GATEWAY]: '网关错误，请稍后重试',
  [HttpStatus.SERVICE_UNAVAILABLE]: '服务暂不可用，请稍后重试',
  [HttpStatus.GATEWAY_TIMEOUT]: '网关超时，请稍后重试',
}
