/**
 * AudioPreviewConfigModal —— 试听配置契约（INT-2044）
 *
 * 音频管理页「预览」入口先打开试听配置（播放模式 / 播放设备 / 声压级 / 偏移量），
 * 确认后交给既有 AudioPlayerModal 起播。字段口径对齐 React 版试听弹窗
 * （features/audio-import/components/modals/audio-preview-dialog.tsx）。
 */
import type { PlaybackDevice } from '../../domain';

/** 试听播放模式：frontend = 浏览器播放，backend = 实验室设备播放（与 AudioPlayerModal 同值域） */
export type PreviewPlaybackMode = 'frontend' | 'backend';

/** 默认声压级（对齐 React 版 DEFAULT_SPL = 65 dB） */
export const DEFAULT_PREVIEW_SPL = 65;

/** 试听配置确认结果 */
export interface AudioPreviewConfig {
  playbackMode: PreviewPlaybackMode;
  /** 实验室播放时选中的播放设备（浏览器播放为 null） */
  device: PlaybackDevice | null;
  spl: number;
  offset: number;
}
