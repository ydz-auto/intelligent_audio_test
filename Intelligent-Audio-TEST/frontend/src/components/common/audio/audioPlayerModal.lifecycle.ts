/**
 * AudioPlayerModal —— 生命周期与全局交互
 *
 * 负责 visible/audioId 变化的 watch、Escape 键关闭、卸载时的资源清理。
 */
import { watch, onUnmounted, onBeforeUnmount, type Ref } from 'vue';

/** 模态框显示后自动播放的延迟（毫秒） */
const AUTO_PLAY_DELAY_MS = 100;

/** audioId 变化后重建音频实例的延迟（毫秒） */
const REINIT_AUDIO_DELAY_MS = 50;

/** 生命周期模块依赖 */
export interface AudioPlayerLifecycleDeps {
  props: any;
  emit: any;
  audio: Ref<HTMLAudioElement | null>;
  initAudio: () => void;
  stop: () => Promise<void>;
  togglePlay: () => Promise<void>;
  detachAudioEvents: (el: HTMLAudioElement) => void;
}

/** 创建生命周期钩子与关闭/键盘交互（返回 handleClose 供组件模板使用） */
export function createAudioPlayerLifecycle(deps: AudioPlayerLifecycleDeps) {
  const { props, emit, audio, initAudio, stop, togglePlay, detachAudioEvents } = deps;

  const handleClose = async () => {
    await stop();
    emit('close');
  };

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && props.visible) {
      handleClose();
    }
  };

  watch(() => props.visible, (newVal) => {
    if (newVal) {
      window.addEventListener('keydown', handleKeyDown);
      initAudio();
      // 模态框显示时自动播放音频
      setTimeout(async () => {
        await togglePlay();
      }, AUTO_PLAY_DELAY_MS);
    } else {
      window.removeEventListener('keydown', handleKeyDown);
      stop();
    }
  }, { immediate: true });

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown);
  });

  onBeforeUnmount(() => {
    console.log('Component unmounting, cleaning up');
    stop();
    if (audio.value) {
      detachAudioEvents(audio.value);
      audio.value = null;
    }
  });

  watch(() => props.audioId, (newId, oldId) => {
    if (newId && newId !== oldId && props.visible) {
      console.log('Audio ID changed, reinitializing audio');
      if (audio.value) {
        detachAudioEvents(audio.value);

        audio.value.pause();
        audio.value.src = '';
        audio.value.load();
        audio.value = null;
      }
      setTimeout(() => {
        initAudio();
      }, REINIT_AUDIO_DELAY_MS);
    }
  });

  return { handleClose };
}