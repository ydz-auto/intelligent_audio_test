/**
 * AudioPlayerModal —— 播放控制
 *
 * 负责播放/暂停/停止/切换，测试用例预览与流式播放的编排，以及后端播放的模拟进度推进。
 */
import { HttpStatus } from '../../../domain/enums';
import { audiosPort } from '@/composables/audio/audiosPort';
import { testcasesPort } from '@/composables/testCase/testcasesPort';
import { DEFAULT_SIMULATED_DURATION, SIMULATED_PROGRESS_INTERVAL_MS, type AudioPlayerState } from './audioPlayerModal.state';

/** 播放控制模块依赖 */
export interface PlaybackControlDeps {
  props: any;
  emit: any;
  state: AudioPlayerState;
  playAudioPlaylist: (urls: string[] | undefined, singleUrl: string | undefined) => Promise<void>;
  playOnExternalDevices: (offset?: number) => Promise<void>;
  stopOnExternalDevices: () => Promise<void>;
}

/** 创建播放控制（togglePlay/play/pause/stop 与预览、流式播放编排） */
export function createPlaybackControl(deps: PlaybackControlDeps) {
  const { props, emit, state, playAudioPlaylist, playOnExternalDevices, stopOnExternalDevices } = deps;
  const { audio, isPlaying, currentTime, duration, progressPercentage, progressUpdateTimer, playError } = state;

  /** 后端播放无真实时长时按固定增量推进进度 */
  const updateProgressSimulated = () => {
    if (isPlaying.value && duration.value > 0) {
      const increment = 0.1;
      currentTime.value += increment;

      if (currentTime.value >= duration.value) {
        currentTime.value = duration.value;
        progressPercentage.value = 100;
        console.log('Simulated playback reached end');
        stop();
        return;
      }

      progressPercentage.value = Math.max(0, Math.min(100, (currentTime.value / duration.value) * 100));

      if (Math.floor(currentTime.value * 10) % 10 === 0) {
        console.log('Simulated progress:', {
          currentTime: currentTime.value.toFixed(1),
          duration: duration.value.toFixed(1),
          progress: progressPercentage.value.toFixed(1) + '%'
        });
      }
    }
  };

  const play = async () => {
    try {
      console.log('play() method called', { audioType: props.audioType, isTestCasePreview: props.isTestCasePreview, playbackMode: props.playbackMode });

      playError.value = '';

      isPlaying.value = true;
      emit('play');

      if (props.isTestCasePreview) {
        console.log('TestCase Preview: calling /testcases/preview API with playbackMode:', props.playbackMode);
        await playTestCasePreview();
      } else if (props.audioPath) {
        console.log('Audio path provided: Playing directly from path');
        await playAudioStream();
      } else if (props.audioType === 'api') {
        console.log('API audio: Playing directly on frontend speakers');
        await playAudioStream();
      } else if (props.playbackMode === 'frontend') {
        console.log('Frontend playback mode: Playing directly on frontend speakers');
        await playAudioStream();
      } else {
        console.log('Backend playback mode: Calling backend API to play on selected devices');
        await playOnExternalDevices();

        if (duration.value === 0) {
          duration.value = DEFAULT_SIMULATED_DURATION;
        }

        if (progressUpdateTimer.value) {
          clearInterval(progressUpdateTimer.value);
          progressUpdateTimer.value = null;
        }
        progressUpdateTimer.value = setInterval(updateProgressSimulated, SIMULATED_PROGRESS_INTERVAL_MS);
        console.log('Started simulated progress update timer for backend playback');
      }
    } catch (error: any) {
      console.error('音频播放失败:', error);
      isPlaying.value = false;
      if (error.response && error.response.status === HttpStatus.BAD_REQUEST) {
        playError.value = '服务器返回400错误。音频文件可能不存在或格式不正确';
      } else if (error.message) {
        playError.value = `音频播放失败: ${error.message}`;
      } else {
        playError.value = '音频播放失败，请重试';
      }
      if (progressUpdateTimer.value) {
        clearInterval(progressUpdateTimer.value);
        progressUpdateTimer.value = null;
      }
    }
  };

  const playTestCasePreview = async () => {
    try {
      if (!props.audioId) {
        console.warn('Cannot play preview: audioId is null or undefined');
        return;
      }

      const previewPayload: any = {
        offset: 0,
        playbackMode: props.playbackMode || 'frontend'
      };

      if (props.audioType === 'e2e') {
        previewPayload.previewType = 'e2e';
      } else if (props.audioType === 'api') {
        previewPayload.previewType = 'api';
      }

      console.log(`[API Request] POST /testcases/${props.audioId}/preview with payload:`, JSON.stringify(previewPayload));
      const previewResult = await testcasesPort.preview(props.audioId, previewPayload);
      console.log('[SUCCESS] 测试用例预览响应:', previewResult);

      if (previewResult && previewResult.duration) {
        duration.value = previewResult.duration;
        console.log('Set real duration from testcases preview API:', duration.value);
      }

      if (previewResult && previewResult.playbackMode === 'frontend' && (previewResult.audioStreamUrls || previewResult.audioStreamUrl)) {
        const urls = previewResult.audioStreamUrls;
        const singleUrl = previewResult.audioStreamUrl;
        console.log('Frontend mode: Playing audio stream URL(s):', urls || singleUrl);
        await playAudioPlaylist(urls, singleUrl);
      } else {
        console.log('Backend mode: Audio playing on external devices');
        if (duration.value === 0) {
          duration.value = DEFAULT_SIMULATED_DURATION;
        }

        if (progressUpdateTimer.value) {
          clearInterval(progressUpdateTimer.value);
          progressUpdateTimer.value = null;
        }
        progressUpdateTimer.value = setInterval(updateProgressSimulated, SIMULATED_PROGRESS_INTERVAL_MS);
        console.log('Started simulated progress update timer for backend playback');
      }
    } catch (error: any) {
      console.error('Error in playTestCasePreview:', error);
      throw error;
    }
  };

  const playAudioStream = async () => {
    if (!audio.value) return;

    try {
      // 后端返回 OSS 预签名 URL，前端直接从 OSS 拉取音频
      // 走 audiosPort（JWT 由 client.ts 拦截器注入）
      let result: any;
      if (props.audioId) {
        result = await audiosPort.stream(props.audioId);
      } else if (props.audioPath) {
        result = await audiosPort.streamByPath(props.audioPath);
      } else {
        console.warn('Cannot play audio: both audioId and audioPath are empty');
        playError.value = '缺少音频ID或路径，无法播放';
        isPlaying.value = false;
        return;
      }

      const presignedUrl = result?.url || result?.data?.url;
      if (!presignedUrl) {
        playError.value = '获取音频 URL 失败';
        isPlaying.value = false;
        return;
      }
      audio.value.src = presignedUrl;
      await audio.value.load();
      await audio.value.play();
      console.log('Local audio playback started');
    } catch (playError: any) {
      console.error('Audio play error:', playError);
      if (playError.name === 'NotSupportedError') {
        playError.value = '浏览器不支持该音频格式，请尝试使用其他格式的音频文件';
      } else if (playError.message && playError.message.includes('400')) {
        playError.value = '服务器返回400错误，可能是音频文件不存在或格式不正确';
      } else {
        playError.value = '音频播放失败，请检查音频文件是否有效';
      }
      isPlaying.value = false;
    }
  };

  const pause = async () => {
    try {
      console.log('pause() method called');

      if (progressUpdateTimer.value) {
        clearInterval(progressUpdateTimer.value);
        progressUpdateTimer.value = null;
        console.log('Stopped simulated progress update timer');
      }

      if (audio.value) {
        audio.value.pause();
        console.log('Local audio paused');
      }

      isPlaying.value = false;
      emit('pause');

      // 测试用例预览或后端播放模式都需要调用外部设备停止接口
      if (props.isTestCasePreview || props.playbackMode === 'backend') {
        await stopOnExternalDevices();
      }
    } catch (error: any) {
      console.error('音频暂停失败:', error);
      if (error.stack) {
        console.error('Error stack:', error.stack);
      }
    }
  };

  const stop = async () => {
    try {
      console.log('stop() method called');

      if (progressUpdateTimer.value) {
        clearInterval(progressUpdateTimer.value);
        progressUpdateTimer.value = null;
      }

      if (audio.value) {
        audio.value.pause();
        audio.value.currentTime = 0;
        audio.value.removeAttribute('src');
        audio.value.load();
      }

      isPlaying.value = false;
      currentTime.value = 0;
      progressPercentage.value = 0;

      emit('stop');

      // 测试用例预览或后端播放模式都需要调用外部设备停止接口
      if (props.isTestCasePreview || props.playbackMode === 'backend') {
        await stopOnExternalDevices();
      }
    } catch (error: any) {
      console.error('音频停止失败:', error);
    }
  };

  const togglePlay = async () => {
    try {
      console.log('togglePlay() method called');
      console.log('togglePlay() current isPlaying:', isPlaying.value);

      if (isPlaying.value) {
        console.log('togglePlay(): isPlaying is true, calling pause()');
        await pause();
        console.log('togglePlay(): pause() returned');
      } else {
        console.log('togglePlay(): isPlaying is false, calling play()');
        await play();
        console.log('togglePlay(): play() returned');
      }
    } catch (error: any) {
      console.error('Error in togglePlay:', error);
      if (error.stack) {
        console.error('Error stack:', error.stack);
      }
    }
  };

  return {
    updateProgressSimulated,
    play,
    playTestCasePreview,
    playAudioStream,
    pause,
    stop,
    togglePlay,
  };
}