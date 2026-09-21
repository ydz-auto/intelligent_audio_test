/**
 * AudioPlayerModal —— 进度条交互
 *
 * 负责进度拖拽（mousedown/mousemove/mouseup）、点击定位，以及拖拽结束后的外部设备 seek 联动。
 */
import type { Ref } from 'vue';

/** 进度交互模块依赖 */
export interface ProgressControlDeps {
  props: any;
  audio: Ref<HTMLAudioElement | null>;
  isDragging: Ref<boolean>;
  isPlaying: Ref<boolean>;
  currentTime: Ref<number>;
  duration: Ref<number>;
  progressPercentage: Ref<number>;
  progressBarRef: Ref<HTMLElement | null>;
  playOnExternalDevices: (offset?: number) => Promise<void>;
  stopOnExternalDevices: () => Promise<void>;
  startSimulatedProgress: (baseTime?: number) => void;
  stopSimulatedProgress: () => void;
}

/** 创建进度条拖拽与点击定位控制 */
export function createProgressControl(deps: ProgressControlDeps) {
  const {
    props,
    audio,
    isDragging,
    isPlaying,
    currentTime,
    duration,
    progressPercentage,
    progressBarRef,
    playOnExternalDevices,
    stopOnExternalDevices,
    startSimulatedProgress,
    stopSimulatedProgress,
  } = deps;

  const startDrag = (event: MouseEvent) => {
    try {
      console.log('Starting progress drag');
      isDragging.value = true;
      document.addEventListener('mousemove', handleDrag);
      document.addEventListener('mouseup', stopDrag);
      updateProgress(event);
    } catch (error: any) {
      console.error('Error in startDrag:', error);
      isDragging.value = false;
    }
  };

  const handleDrag = (event: MouseEvent) => {
    try {
      if (isDragging.value) {
        updateProgress(event);
      }
    } catch (error: any) {
      console.error('Error in handleDrag:', error);
    }
  };

  const stopDrag = async () => {
    try {
      console.log('Stopping progress drag');
      isDragging.value = false;
      document.removeEventListener('mousemove', handleDrag);
      document.removeEventListener('mouseup', stopDrag);

      if (audio.value) {
        audio.value.currentTime = currentTime.value;
        console.log('Set audio currentTime to:', currentTime.value);
      }

      // 后端/设备播放模式下，拖动 seek 需要停止当前模拟计时，避免网络请求期间时间继续漂移
      const isExternalPlayback = props.selectedDevices.length > 0 || props.isTestCasePreview || props.playbackMode === 'backend';
      if (isPlaying.value && isExternalPlayback) {
        // 使用拖动的目标位置（progressPercentage）而不是当前位置（currentTime）
        const targetTime = (progressPercentage.value / 100) * (duration.value || 0);
        console.log('Seeking on external devices, target time:', targetTime, 'percentage:', progressPercentage.value);
        stopSimulatedProgress();
        await stopOnExternalDevices();
        await playOnExternalDevices(targetTime);
        // 重新以目标时间作为模拟时钟基准，与设备端实际 seek 位置对齐
        currentTime.value = targetTime;
        startSimulatedProgress(targetTime);
      }
    } catch (error: any) {
      console.error('Error in stopDrag:', error);
    }
  };

  const updateProgress = (event: MouseEvent) => {
    try {
      // 使用 ref 获取进度条容器：handleDrag 绑定在 document 上时 event.currentTarget 指向 document，
      // getBoundingClientRect 会取到整页矩形导致 seek 位置计算错误
      const progressBarContainer = progressBarRef.value;
      if (!progressBarContainer) {
        console.error('Progress bar container not found');
        return;
      }

      const rect = progressBarContainer.getBoundingClientRect();
      const offsetX = event.clientX - rect.left;
      const percentage = Math.max(0, Math.min(100, (offsetX / rect.width) * 100));
      progressPercentage.value = percentage;
      currentTime.value = (percentage / 100) * duration.value;

      console.log('Progress updated:', {
        offsetX,
        containerWidth: rect.width,
        percentage,
        currentTime: currentTime.value,
        duration: duration.value
      });
    } catch (error: any) {
      console.error('Error in updateProgress:', error);
    }
  };

  const updateProgressOnClick = (event: MouseEvent) => {
    try {
      if (!isDragging.value) {
        updateProgress(event);
        if (audio.value) {
          audio.value.currentTime = currentTime.value;
          console.log('Set audio currentTime via click:', currentTime.value);
        }
      }
    } catch (error: any) {
      console.error('Error in updateProgressOnClick:', error);
    }
  };

  return {
    startDrag,
    handleDrag,
    stopDrag,
    updateProgress,
    updateProgressOnClick,
  };
}