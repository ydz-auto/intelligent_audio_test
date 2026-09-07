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
  playOnExternalDevices: (offset?: number) => Promise<void>;
  stopOnExternalDevices: () => Promise<void>;
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
    playOnExternalDevices,
    stopOnExternalDevices,
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

      if (isPlaying.value && (props.selectedDevices.length > 0 || props.isTestCasePreview)) {
        // 使用拖动的目标位置（progressPercentage）而不是当前位置（currentTime）
        const targetTime = (progressPercentage.value / 100) * (duration.value || 0);
        console.log('Seeking on external devices, target time:', targetTime, 'percentage:', progressPercentage.value);
        await stopOnExternalDevices();
        await playOnExternalDevices(targetTime);
      }
    } catch (error: any) {
      console.error('Error in stopDrag:', error);
    }
  };

  const updateProgress = (event: MouseEvent) => {
    try {
      // 使用ref获取DOM元素，而不是document.querySelector，避免访问不存在的元素
      const progressBarContainer = event.currentTarget as HTMLElement;
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