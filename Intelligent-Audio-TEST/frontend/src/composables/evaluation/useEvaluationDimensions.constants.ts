/**
 * useEvaluationDimensions —— 常量定义
 *
 * 维度管理模块的全部模块级常量：新建分类标识、维度类型、各类默认值与保存操作类型。
 */

// === 常量定义 ===
/** 新建分类的特殊标识 */
export const NEW_CATEGORY_FLAG = '__new__';
/** 维度类型：主维度 */
export const DIMENSION_TYPE_MAIN = 'main';
/** 维度类型：子维度 */
export const DIMENSION_TYPE_SUB = 'sub';
/** 默认分类图标 */
export const DEFAULT_CATEGORY_ICON = 'fas fa-tachometer-alt';
/** 默认 LLM 最大 Token 数 */
export const DEFAULT_LLM_MAX_TOKENS = 1024;
/** 默认 LLM 温度 */
export const DEFAULT_LLM_TEMPERATURE = 0.7;
/** 默认 API 端点最大并发数 */
export const DEFAULT_MAX_PROCESS = 5;
/** 默认 API 端点超时（秒） */
export const DEFAULT_MAX_TIMEOUT = 30;
/** 默认 API 端点最大音频时长（秒） */
export const DEFAULT_MAX_AUDIO_DURATION = 60;
/** 默认 API 超时（毫秒） */
export const DEFAULT_API_TIMEOUT = 30000;
/** 编辑模态框默认 API 超时（毫秒） */
export const DEFAULT_EDITOR_API_TIMEOUT = 5000;
/** 默认分页大小 */
export const DEFAULT_PAGE_SIZE = 10;
/** 保存操作类型：新增 */
export const SAVE_TYPE_ADD = 'add';
/** 保存操作类型：编辑 */
export const SAVE_TYPE_EDIT = 'edit';
