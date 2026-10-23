/**
 * 报告分享领域模型（domain 层，零依赖，前端只见 camelCase）。
 * 分享方式/权限/有效期枚举；分享端点（生成/列表/撤销/公开读取）INT-971 已部署，
 * infrastructure/api/report-share-api.ts 负责 DTO 映射。
 */

/** 访问权限（仅登录/指定人/公开） */
export type ShareAccess = 'login' | 'specific' | 'public'

/** 分享方式（生成分享链接 / 邮件分享 / 导出后分享；邮件本版本不实现，前端隐藏入口） */
export type ShareMethod = 'link' | 'email' | 'export'

/** 有效期（不过期/7 天/30 天/自定义） */
export type ShareExpiry = 'none' | '7d' | '30d' | 'custom'
