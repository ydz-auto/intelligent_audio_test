/**
 * audioUtils —— 共享音频工具函数（组合根 / barrel）
 *
 * 原单文件工具库已按职责拆分至同目录 audioUtils.*.ts：
 * - constants:         顶部常量（API 基础路径 / DB 范围 / 时间换算 / 时长阈值 / 默认置信度 / 文件大小基数 / 音频流路径）
 * - convert:           音量 ↔ 分贝 ↔ 线性增益换算与增益曲线生成
 * - format:            文件大小与音频时长格式化 / 解析（formatFileSize / formatDuration / parseDuration / formatDurationLong / formatAudioData）
 * - folder:            文件夹树构建、标签提取、展开状态与音频筛选
 * - annotation:        标注文件解析（音频 txt / JSON / JSONL / RTTM / STM）
 * - annotation-params: 按用例参数配置从标注提取参数值（extractParamsFromAnnotations）
 * - normalize:         音频 URL 构建、类型标签与音频项归一化
 * 本文件仅负责 re-export，保持原模块路径与全部导出面不变，消费方零改动。
 */

export { DB_MIN, DB_MAX } from './audioUtils.constants';
export * from './audioUtils.convert';
export * from './audioUtils.format';
export * from './audioUtils.folder';
export * from './audioUtils.annotation';
export * from './audioUtils.annotation-params';
export * from './audioUtils.normalize';
