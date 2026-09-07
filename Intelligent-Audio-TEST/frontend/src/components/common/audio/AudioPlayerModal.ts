/**
 * AudioPlayerModal —— 组合根（聚合口）
 *
 * 原超大 composable 已按职责拆分至同目录 audioPlayerModal.*.ts：
 * - state:     播放状态与展示格式化（组件级共享 refs）
 * - events:    音频元素事件处理（initAudio / 事件绑定解绑）
 * - devices:   外部设备播放/停止
 * - playlist:  多音频连续播放
 * - playback:  播放/暂停/停止/切换与预览编排
 * - progress:  进度条拖拽与点击定位
 * - lifecycle: 生命周期与键盘交互
 * 本文件仅负责模块组装，保持原模块路径与全部具名导出不变。
 */
import { createAudioPlayerState } from './audioPlayerModal.state';
import { createAudioEvents } from './audioPlayerModal.events';
import { createDevicePlayback } from './audioPlayerModal.devices';
import { createPlaylistPlayer } from './audioPlayerModal.playlist';
import { createPlaybackControl } from './audioPlayerModal.playback';
import { createProgressControl } from './audioPlayerModal.progress';
import { createAudioPlayerLifecycle } from './audioPlayerModal.lifecycle';

export function useAudioPlayerModal(props: any, emit: any) {
  // ===== 共享状态 =====
  const state = createAudioPlayerState(props);

  // ===== 外部设备播放/停止 =====
  const { playOnExternalDevices, stopOnExternalDevices } = createDevicePlayback({ props, duration: state.duration });

  // ===== 音频元素事件处理 =====
  const events = createAudioEvents({ ...state, props, emit, stopOnExternalDevices });

  // ===== 多音频连续播放 =====
  const { playAudioPlaylist } = createPlaylistPlayer({
    audio: state.audio,
    isPlaying: state.isPlaying,
    multiAudioPlaylist: state.multiAudioPlaylist,
    playError: state.playError,
  });

  // ===== 播放控制 =====
  const playback = createPlaybackControl({
    props,
    emit,
    state,
    playAudioPlaylist,
    playOnExternalDevices,
    stopOnExternalDevices,
  });

  // ===== 进度条交互 =====
  const progress = createProgressControl({
    props,
    audio: state.audio,
    isDragging: state.isDragging,
    isPlaying: state.isPlaying,
    currentTime: state.currentTime,
    duration: state.duration,
    progressPercentage: state.progressPercentage,
    playOnExternalDevices,
    stopOnExternalDevices,
  });

  // ===== 生命周期与键盘交互 =====
  const { handleClose } = createAudioPlayerLifecycle({
    props,
    emit,
    audio: state.audio,
    initAudio: events.initAudio,
    stop: playback.stop,
    togglePlay: playback.togglePlay,
    detachAudioEvents: events.detachAudioEvents,
  });

  return {
    isPlaying: state.isPlaying,
    currentTime: state.currentTime,
    duration: state.duration,
    progressPercentage: state.progressPercentage,
    audioLoaded: state.audioLoaded,
    isDragging: state.isDragging,
    playError: state.playError,
    audioTypeLabel: state.audioTypeLabel,
    formatTime: state.formatTime,
    togglePlay: playback.togglePlay,
    stop: playback.stop,
    handleClose,
    startDrag: progress.startDrag,
    updateProgressOnClick: progress.updateProgressOnClick
  };
}