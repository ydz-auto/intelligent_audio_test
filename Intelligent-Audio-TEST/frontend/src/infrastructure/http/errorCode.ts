/**
 * 全局错误码 —— Infrastructure HTTP 层
 *
 * 0: Success
 * 1xx: Parameter Errors
 * 2xx: Business Errors
 * 3xx: System Errors
 *
 * API 响应信封契约（APIResponse/PaginatedData/PaginatedResponse）已下沉至 @/domain/model/common
 */
export enum ErrorCode {
    SUCCESS = 0,

    // 1xx: Parameter Errors
    INVALID_PARAMS = 100,
    MISSING_PARAMS = 101,
    INVALID_TYPE = 102,
    UNAUTHORIZED = 103,
    FORBIDDEN = 104,

    // 2xx: Business Errors
    BUSINESS_ERROR = 200,
    NOT_FOUND = 201,
    ALREADY_EXISTS = 202,
    OPERATION_FAILED = 203,
    TASK_ALREADY_RUNNING = 205,
    TASK_NOT_FOUND = 206,
    CALIBRATION_FAILED = 210,
    TASK_EXECUTION_ERROR = 220,

    // 3xx: System Errors
    SYSTEM_ERROR = 300,
    DATABASE_ERROR = 301,
    FILE_IO_ERROR = 302,
    NETWORK_ERROR = 303,
    INTERNAL_SERVER_ERROR = 304,
    INTERNAL_ERROR = 305,
    EXTERNAL_SERVICE_ERROR = 306
}
