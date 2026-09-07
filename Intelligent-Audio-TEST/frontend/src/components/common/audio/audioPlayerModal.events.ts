/**
 * AudioPlayerModal —— 音频元素事件处理
 *
 * 负责 HTMLAudioElement 的创建、播放事件绑定/解绑，以及元数据、时间更新、结束、错误等事件回调。
 */
import type { Ref } from 'vue';

/** 事件处理模块依赖（共享状态 refs + 外部设备停止回调） */
export interface AudioEventsDeps {
  props: any;
  emit: any;
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
  stopOnExternalDevices: () => Promise<void>;
}

/** 创建音频元素事件处理（含 initAudio 初始化与事件绑定/解绑） */
export function createAudioEvents(deps: AudioEventsDeps) {
  const {
    props,
    emit,
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
    stopOnExternalDevices,
  } = deps;

  const handleProgress = () => {
    try {
      console.log('Audio progress event fired');
      if (audio.value && audio.value.buffered.length > 0) {
        const bufferedEnd = audio.value.buffered.end(audio.value.buffered.length - 1);
        const loadingProgress = (bufferedEnd / audio.value.duration) * 100;
        console.log('Audio loading progress:', loadingProgress + '%');
      }
    } catch (error: any) {
      console.error('Error in handleProgress:', error);
    }
  };

  const handleLoadedData = () => {
    console.log('Audio data loaded');
    audioLoaded.value = true;
  };

  const handleCanPlay = () => {
    console.log('Audio can play now');
    audioLoaded.value = true;
  };

  const handleLoadedMetadata = () => {
    try {
      if (audio.value) {
        // 多音频连续播放时，不覆盖从 API 拿到的总时长
        if (!multiAudioPlaylist.value || multiAudioPlaylist.value.length <= 1) {
          duration.value = audio.value.duration;
        }
        console.log('Audio metadata loaded:', {
          duration: audio.value.duration,
          totalDuration: duration.value,
          currentTime: audio.value.currentTime,
          paused: audio.value.paused
        });
        if (isNaN(duration.value) || duration.value === Infinity) {
          duration.value = 0;
          console.warn('Invalid duration value:', audio.value.duration);
        }
      }
      audioLoaded.value = true;
    } catch (error) {
      console.error('Error in handleLoadedMetadata:', error);
      duration.value = 0;
      audioLoaded.value = true;
    }
  };

  const handleTimeUpdate = () => {
    try {
      if (!isDragging.value && audio.value) {
        const currentAudioTime = audio.value.currentTime;
        const audioDuration = audio.value.duration;

        currentTime.value = currentAudioTime;

        // 多音频连续播放时，不覆盖总时长
        if (!multiAudioPlaylist.value || multiAudioPlaylist.value.length <= 1) {
          if (!isNaN(audioDuration) && audioDuration > 0 && audioDuration !== Infinity) {
            duration.value = audioDuration;
          }
        }

        if (duration.value > 0) {
          progressPercentage.value = Math.max(0, Math.min(100, (currentTime.value / duration.value) * 100));
        }

        console.log('Audio time update:', {
          audioCurrentTime: currentAudioTime,
          audioDuration: audioDuration,
          displayCurrentTime: currentTime.value,
          displayDuration: duration.value,
          progress: progressPercentage.value
        });
      }
    } catch (error) {
      console.error('Error in handleTimeUpdate:', error);
    }
  };

  const handleEnded = () => {
    try {
      console.log('Audio playback ended');

      if (progressUpdateTimer.value) {
        clearInterval(progressUpdateTimer.value);
        progressUpdateTimer.value = null;
        console.log('Stopped simulated progress update timer on ended');
      }

      isPlaying.value = false;
      currentTime.value = 0;
      progressPercentage.value = 0;
      emit('stop');

      // 测试用例预览或后端播放模式都需要调用外部设备停止接口
      if (props.isTestCasePreview || props.playbackMode === 'backend') {
        stopOnExternalDevices();
      }
    } catch (error: any) {
      console.error('Error in handleEnded:', error);
    }
  };

  const handleError = (event: Event) => {
    try {
      const target = event.target as HTMLAudioElement;
      const error = target.error;
      if (error) {
        console.error('音频播放错误:', error);
        console.error('Error code:', error.code, 'Error message:', error.message);

        // 根据错误代码设置用户友好的错误消息
        let errorMessage = '';
        switch (error.code) {
          case 1:
            errorMessage = '音频文件未找到，请检查文件是否存在';
            break;
          case 2:
            errorMessage = '音频格式不支持，请联系管理员';
            break;
          case 3:
            errorMessage = '音频解码错误，可能是文件损坏';
            break;
          case 4:
            errorMessage = '音频格式不支持或服务器返回错误(400)';
            break;
          default:
            errorMessage = '音频播放失败，请重试';
        }
        playError.value = errorMessage;
      }
      emit('stop');

      // 测试用例预览或后端播放模式都需要调用外部设备停止接口
      if (props.isTestCasePreview || props.playbackMode === 'backend') {
        stopOnExternalDevices();
      }
    } catch (err: any) {
      console.error('Error in handleError:', err);
    }
  };

  /** 为指定音频元素绑定全部播放事件 */
  const attachAudioEvents = (el: HTMLAudioElement) => {
    el.addEventListener('loadedmetadata', handleLoadedMetadata);
    el.addEventListener('timeupdate', handleTimeUpdate);
    el.addEventListener('ended', handleEnded);
    el.addEventListener('error', handleError);
    el.addEventListener('loadeddata', handleLoadedData);
    el.addEventListener('canplay', handleCanPlay);
    el.addEventListener('canplaythrough', handleCanPlay);
    el.addEventListener('progress', handleProgress);
  };

  /** 为指定音频元素解绑全部播放事件 */
  const detachAudioEvents = (el: HTMLAudioElement) => {
    el.removeEventListener('loadedmetadata', handleLoadedMetadata);
    el.removeEventListener('timeupdate', handleTimeUpdate);
    el.removeEventListener('ended', handleEnded);
    el.removeEventListener('error', handleError);
    el.removeEventListener('loadeddata', handleLoadedData);
    el.removeEventListener('canplay', handleCanPlay);
    el.removeEventListener('canplaythrough', handleCanPlay);
    el.removeEventListener('progress', handleProgress);
  };

  /** 创建音频实例并绑定事件，同时重置播放状态（各类播放模式共用） */
  const initAudio = () => {
    console.log('Initializing audio player...');

    if (audio.value) {
      audio.value.pause();
      audio.value.src = '';
      audio.value = null;
    }

    if (progressUpdateTimer.value) {
      clearInterval(progressUpdateTimer.value);
      progressUpdateTimer.value = null;
      console.log('Stopped simulated progress update timer on init');
    }

    isPlaying.value = false;
    currentTime.value = 0;
    duration.value = 0;
    progressPercentage.value = 0;
    audioLoaded.value = false;

    try {
      console.log('Creating audio instance for all modes, audioType:', props.audioType, 'isTestCasePreview:', props.isTestCasePreview);
      const el = new Audio();
      el.preload = 'metadata';
      el.crossOrigin = 'anonymous';
      audio.value = el;
      attachAudioEvents(el);
      audioLoaded.value = true;
      console.log('Audio instance created and audioLoaded set to true');
    } catch (error) {
      console.error('Error initializing audio:', error);
      audioLoaded.value = false;
    }
  };

  return {
    handleProgress,
    handleLoadedData,
    handleCanPlay,
    handleLoadedMetadata,
    handleTimeUpdate,
    handleEnded,
    handleError,
    attachAudioEvents,
    detachAudioEvents,
    initAudio,
  };
}