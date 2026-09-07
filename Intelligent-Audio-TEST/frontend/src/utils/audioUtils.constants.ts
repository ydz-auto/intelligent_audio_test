/**
 * audioUtils —— 顶部常量
 *
 * 集中存放共享音频工具的全部顶部常量（API 基础路径 / DB 范围 / 时间换算 / 时长阈值 / 默认置信度 / 文件大小基数 / 音频流路径）。
 * 原为 audioUtils.ts 内的私有常量，拆分后 export 供各卫星模块引用；
 * 对外仅由主 barrel 暴露 DB_MIN / DB_MAX，其余保持模块内部可见性。
 */
import { API_CONFIG } from './config';

export const _apiBaseUrl = API_CONFIG.baseUrl;
export const _apiBaseNoV1 = _apiBaseUrl.replace('/v1', '');

export const DB_MIN = -60;
export const DB_MAX = 0;

// 时间换算常量（秒）
export const SECONDS_PER_MINUTE = 60;
export const SECONDS_PER_HOUR = 3600;
export const SECONDS_PER_DAY = 86400;

// 音频时长筛选阈值（秒）
export const DURATION_SHORT_MAX = 30;     // 短音频上限
export const DURATION_MEDIUM_MAX = 300;   // 中等音频上限（长音频下限）

// 默认置信度
export const DEFAULT_CONFIDENCE = 1.0;

// 文件大小换算基数
export const FILE_SIZE_BASE = 1024;

// 音频流播放接口路径
export const AUDIO_STREAM_BY_PATH = '/audio/stream-by-path';
