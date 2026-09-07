/**
 * AudioPlayerModal —— 播放状态与展示格式化
 *
 * 集中声明组件级共享 refs（跨 events/playlist/devices/playback/progress/lifecycle 复用同一份响应式引用），
 * 并提供音频类型标签与时间的展示格式化。
 */
import { ref, computed, type Ref } from 'vue';
import { formatDuration } from '@/utils/audioUtils';

/** 后端播放模式无真实时长时使用的模拟时长（秒） */
export const DEFAULT_SIMULATED_DURATION = 10;

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
  playError: Ref<string>;
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
    playError,
  };

  return { ...state, audioTypeLabel, formatTime };
}