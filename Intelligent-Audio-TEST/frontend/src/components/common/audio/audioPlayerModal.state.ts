/**
 * AudioPlayerModal —— 播放状态与展示格式化
 *
 * 集中声明组件级共享 refs（跨 events/playlist/devices/playback/progress/lifecycle 复用同一份响应式引用），
 * 并提供音频类型标签与时间的展示格式化。
 */
import { ref, computed, type Ref } from 'vue';
import { formatDuration } from '@/utils/audioUtils';

/** 模拟进度刷新间隔（毫秒） */
export const SIMULATED_PROGRESS_INTERVAL_MS = 100;

/** 播放器共享状态（组件级 refs 集合） */
export interface AudioPlayerState {
  audio: Ref<HTMLAudioElement | null>;
  isPlaying: Ref<boolean>;
  multiAudioPlaylist: Ref<string[]>;
  currentTime: Ref<number>;
  duration: Ref<number>;
  progressPercentage: Ref<number>;
  audioLoaded: Ref<boolean>;
  isDragging: Ref<boolean>;
  progressUpdateTimer: Ref<ReturnType<typeof setInterval> | null>;
  /** 进度条容器 DOM 引用（拖动 seek 计算用，避免 event.currentTarget 指向 document） */
  progressBarRef: Ref<HTMLElement | null>;
  /** 模拟进度墙钟起点（performance.now() 毫秒），0 表示未启动 */
  progressClockStart: Ref<number>;
  /** 模拟进度墙钟基准时间（秒），即启动模拟时音频已处于的位置 */
  progressClockBase: Ref<number>;
  playError: Ref<string>;
}

/** 停止模拟进度定时器并重置墙钟基准（各模块共用，避免散落 clearInterval） */
export function clearSimulatedProgress(
  state: Pick<AudioPlayerState, 'progressUpdateTimer' | 'progressClockStart' | 'progressClockBase'>
) {
  if (state.progressUpdateTimer.value) {
    clearInterval(state.progressUpdateTimer.value);
    state.progressUpdateTimer.value = null;
  }
  state.progressClockStart.value = 0;
  state.progressClockBase.value = 0;
}

/** 创建播放器共享状态与展示格式化（audioTypeLabel / formatTime） */
export function createAudioPlayerState(props: any) {
  const audio = ref<HTMLAudioElement | null>(null);
  const isPlaying = ref(false);

  // 多音频连续播放的播放列表
  const multiAudioPlaylist = ref<string[]>([]);
  const currentTime = ref(0);
  const duration = ref(0);
  const progressPercentage = ref(0);
  const audioLoaded = ref(false);
  const isDragging = ref(false);
  const progressUpdateTimer = ref<ReturnType<typeof setInterval> | null>(null);
  const progressBarRef = ref<HTMLElement | null>(null);
  const progressClockStart = ref(0);
  const progressClockBase = ref(0);
  const playError = ref('');

  const audioTypeLabel = computed(() => {
    const typeMap: Record<string, string> = { 'dry': '干声 (信号音频)', 'noise': '噪声', 'prompt': '提示词音频', 'api': 'API测试音频' };
    return typeMap[props.audioType] || '未知类型';
  });

  const formatTime = (seconds: number): string => {
    if (!Number.isFinite(seconds)) return '0:00';
    return formatDuration(seconds);
  };

  const state: AudioPlayerState = {
    audio,
    isPlaying,
    multiAudioPlaylist,
    currentTime,
    duration,
    progressPercentage,
    audioLoaded,
    isDragging,
    progressUpdateTimer,
    progressBarRef,
    progressClockStart,
    progressClockBase,
    playError,
  };

  return { ...state, audioTypeLabel, formatTime };
}