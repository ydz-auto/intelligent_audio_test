<template>
  <teleport to="body" v-if="visible">
    <div class="modal-overlay">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">{{ title }}</h3>
          <button type="button" class="modal-close" @click="() => handleClose()">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <!-- 错误提示 -->
          <div v-if="playError" class="error-message">
            <i class="fas fa-exclamation-circle"></i>
            <span>{{ playError }}</span>
            <button class="error-dismiss" @click="playError = ''">
              <i class="fas fa-times"></i>
            </button>
          </div>
          
          <div class="audio-info">
            <div class="audio-title">{{ audioTitle  }}</div>
            <div class="audio-type">{{ audioTypeLabel }}</div>
          </div>
          
          <div class="audio-player">
          <div class="progress-bar-container" 
               @mousedown="startDrag"
               @click="updateProgressOnClick">
            <div class="progress-bar" :style="{ width: progressPercentage + '%' }"></div>
          </div>
          <div class="time-info">
            <div class="time-display time-current">{{ formatTime(currentTime) }}</div>
            <div class="time-display time-total">{{ formatTime(duration) }}</div>
          </div>
            
            <div class="controls">
              <button type="button" class="control-btn" @click="togglePlay" :disabled="!audioLoaded">
                <i class="fas" :class="isPlaying ? 'fa-pause' : 'fa-play'"></i>
                {{ isPlaying ? '暂停' : '播放' }}
              </button>
              <button type="button" class="control-btn" @click="stop" :disabled="!audioLoaded">
                <i class="fas fa-stop"></i> 停止
              </button>
              <button type="button" class="control-btn" @click="handleClose">
                <i class="fas fa-times"></i> 关闭
              </button>
            </div>
          </div>
          
          <div class="device-info" v-if="selectedDevices.length > 0">
            <h5>播放设备</h5>
            <ul class="device-list">
              <li v-for="(device, index) in selectedDevices" :key="index" class="device-item">
                <i class="fas fa-check-circle device-status online"></i>
                <span class="device-name">{{ device?.name || '未知设备' }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, onBeforeUnmount } from 'vue';
import { audiosApi, playbackApi, testcasesApi } from '../../utils/api';
import { API_CONFIG } from '../../utils/config';
import type { PlaybackDevice } from '../../shared/types';

const apiBaseUrl = API_CONFIG.baseUrl;

interface Props {
  visible: boolean;
  title?: string;
  audioId?: string | number | null;
  audioTitle?: string;
  audioType?: string;
  selectedDevices?: PlaybackDevice[];
  isTestCasePreview?: boolean;
  modalId?: string;
  playbackMode?: string;
}

const props = withDefaults(defineProps<Props>(), {
  title: '音频播放',
  audioId: null,
  audioTitle: '未知音频',
  audioType: 'dry',
  selectedDevices: () => [],
  isTestCasePreview: false,
  modalId: '',
  playbackMode: 'frontend'
});

const emit = defineEmits(['close', 'play', 'pause', 'stop', 'confirm', 'cancel', 'save']);

const audio = ref<HTMLAudioElement | null>(null);
const isPlaying = ref(false);
const currentTime = ref(0);
const duration = ref(0);
const progressPercentage = ref(0);
const audioLoaded = ref(false);
const isDragging = ref(false);
const progressUpdateTimer = ref<ReturnType<typeof setInterval> | null>(null);
const defaultSimulatedDuration = 10;
const playError = ref('');

const audioTypeLabel = computed(() => {
  const typeMap: Record<string, string> = { 'dry': '干声 (信号音频)', 'noise': '噪声', 'prompt': '提示词音频', 'api': 'API测试音频' };
  return typeMap[props.audioType] || '未知类型';
});

const formatTime = (seconds: number): string => {
  const time = Number(seconds);
  
  if (isNaN(time) || time === Infinity || time === null || time === undefined || time < 0) {
    return '0:00';
  }
  
  const mins = Math.floor(time / 60);
  const secs = Math.floor(time % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

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
    audio.value = new Audio();
    
    audio.value.preload = 'metadata';
    audio.value.crossOrigin = 'anonymous';
    
    audio.value.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.value.addEventListener('timeupdate', handleTimeUpdate);
    audio.value.addEventListener('ended', handleEnded);
    audio.value.addEventListener('error', handleError);
    audio.value.addEventListener('loadeddata', handleLoadedData);
    audio.value.addEventListener('canplay', handleCanPlay);
    audio.value.addEventListener('canplaythrough', handleCanPlay);
    
    audio.value.addEventListener('progress', handleProgress);
    
    audioLoaded.value = true;
    console.log('Audio instance created and audioLoaded set to true');
  } catch (error) {
    console.error('Error initializing audio:', error);
    audioLoaded.value = false;
  }
};

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
      duration.value = audio.value.duration;
      console.log('Audio metadata loaded:', {
        duration: duration.value,
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
      
      if (!isNaN(audioDuration) && audioDuration > 0 && audioDuration !== Infinity) {
        duration.value = audioDuration;
      }
      
      if (duration.value > 0) {
        progressPercentage.value = Math.max(0, Math.min(100, (currentTime.value / duration.value) * 100));
      }
      
      if (Math.floor(currentTime.value * 10) % 5 === 0) {
        console.log('Audio time update:', {
          currentTime: currentTime.value,
          duration: duration.value,
          progress: progressPercentage.value
        });
      }
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
        duration.value = defaultSimulatedDuration;
      }
      
      if (progressUpdateTimer.value) {
        clearInterval(progressUpdateTimer.value);
        progressUpdateTimer.value = null;
      }
      progressUpdateTimer.value = setInterval(updateProgressSimulated, 100);
      console.log('Started simulated progress update timer for backend playback');
    }
  } catch (error: any) {
    console.error('音频播放失败:', error);
    isPlaying.value = false;
    if (error.response && error.response.status === 400) {
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
    const previewResult = await testcasesApi.preview(props.audioId, previewPayload);
    console.log('[SUCCESS] 测试用例预览响应:', previewResult);
    
    if (previewResult && previewResult.duration) {
      duration.value = previewResult.duration;
      console.log('Set real duration from testcases preview API:', duration.value);
    }
    
    if (previewResult && previewResult.playbackMode === 'frontend' && previewResult.audioStreamUrl) {
      console.log('Frontend mode: Playing audio stream URL:', previewResult.audioStreamUrl);
      if (audio.value) {
        const fullStreamUrl = `${apiBaseUrl}${previewResult.audioStreamUrl}`;
        audio.value.src = fullStreamUrl;
        try {
          await audio.value.load();
          await audio.value.play();
          console.log('Local audio playback started');
        } catch (playError: any) {
          console.error('Audio play error:', playError);
          playError.value = '音频播放失败，请检查音频文件是否有效';
          isPlaying.value = false;
        }
      }
    } else {
      console.log('Backend mode: Audio playing on external devices');
      if (duration.value === 0) {
        duration.value = defaultSimulatedDuration;
      }
      
      if (progressUpdateTimer.value) {
        clearInterval(progressUpdateTimer.value);
        progressUpdateTimer.value = null;
      }
      progressUpdateTimer.value = setInterval(updateProgressSimulated, 100);
      console.log('Started simulated progress update timer for backend playback');
    }
  } catch (error: any) {
    console.error('Error in playTestCasePreview:', error);
    throw error;
  }
};

const playAudioStream = async () => {
  if (audio.value && props.audioId) {
    const audioStreamUrl = `${apiBaseUrl}/audios/${props.audioId}/stream`;
    audio.value.src = audioStreamUrl;
    
    audio.value.addEventListener('error', (e) => {
      console.error('Audio element error:', audio.value?.error);
      if (audio.value?.error?.code === 4) {
        playError.value = '音频格式不支持或服务器返回错误(400)。可能的原因：音频文件格式不正确或后端服务异常';
      }
    });
    
    try {
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

const playOnExternalDevices = async (offset = 0) => {
  try {
    console.log('Playing on external devices:', props.selectedDevices.map((d: any) => d?.name), 'offset:', offset);
    console.log('AudioPlayerModal props:', {
      isTestCasePreview: props.isTestCasePreview,
      audioType: props.audioType,
      audioId: props.audioId
    });
    
    if (!props.audioId) {
      console.warn('Cannot play preview: audioId is null or undefined');
      return;
    }
    
    // 优先使用 selectedPlaybackDevices，如果没有则使用 selectedDevices
    const availableDevices = props.selectedPlaybackDevices && props.selectedPlaybackDevices.length > 0 ? props.selectedPlaybackDevices : props.selectedDevices;
    
    console.log('[AudioPlayerModal] selectedPlaybackDevices:', props.selectedPlaybackDevices);
    console.log('[AudioPlayerModal] selectedDevices:', props.selectedDevices);
    console.log('[AudioPlayerModal] availableDevices:', availableDevices);
    
    // 处理不同格式的设备数据
    let validDevices: any[] = [];
    
    // 如果设备是字符串或数字格式的ID数组
    if (availableDevices.every((device: any) => typeof device === 'string' || typeof device === 'number')) {
      // 根据ID从 playbackDevices 中查找对应的 deviceUniqueId
      validDevices = (availableDevices as unknown as (string | number)[]).map((deviceId: string | number) => {
        const id = typeof deviceId === 'number' ? deviceId : parseInt(deviceId, 10);
        const device = props.playbackDevices.find((d: any) => d.id === id);
        return {
          deviceUniqueId: device?.deviceUniqueId || String(deviceId),
          id: device?.id || id,
          name: device?.name || `Device ${deviceId}`
        };
      });
    } else {
      // 如果设备是对象格式，过滤出有效的设备
      validDevices = availableDevices.filter((device: any) => device && (device.id || device.deviceUniqueId));
    }
    
    console.log('Available devices for playback:', validDevices);
    
    // Extract device IDs once for all branches
    const deviceUniqueIds = validDevices.map((device: any) => {
      return device.deviceUniqueId || '';
    }).filter((id: string) => id);
    
    const playbackDeviceIds = validDevices.map((device: any) => {
      return device.id || device.deviceUniqueId || '';
    }).filter((id: string) => id);
    
    // 接口调用优先级：
    // 1. isTestCasePreview=true 且 audioType !== 'api' → 调用 /testcases/{id}/preview（用于测试用例预览）
    // 2. playbackMode === 'backend' → 调用 /audios/{id}/preview（用于TestCaseModal中的后端播放）
    
    if (props.isTestCasePreview && props.audioType !== 'api') {
      // 场景7.2.2: 测试用例预览，调用 /testcases/{id}/preview
      console.log('[DEBUG] TestCase Preview: isTestCasePreview=true, calling /testcases/preview API');
      
      const previewPayload = {
        offset: offset,
        previewType: 'e2e'
      };
      
      console.log(`[API Request] POST /testcases/${props.audioId}/preview with payload:`, JSON.stringify(previewPayload));
      const previewResult = await testcasesApi.preview(props.audioId, previewPayload);
      console.log('[SUCCESS] 测试用例预览已开始，使用 /testcases/preview 接口');
      
      if (previewResult && previewResult.duration) {
        duration.value = previewResult.duration;
        console.log('Set real duration from testcases preview API:', duration.value);
      }
    } else if (props.playbackMode === 'backend') {
      // 场景7.1.2/7.1.3: TestCaseModal中的后端播放，调用 /audios/{id}/preview
      console.log('[DEBUG] Backend playback: playbackMode=backend, calling /audios/preview API');
      console.log('[DEBUG] deviceUniqueIds:', deviceUniqueIds);
      console.log('[DEBUG] playbackDeviceIds:', playbackDeviceIds);
      
      const previewPayload: any = {
        deviceUniqueIds: deviceUniqueIds,
        playbackDeviceIds: playbackDeviceIds,
        playbackDeviceId: playbackDeviceIds[0] || '',
        spl: props.spl ?? 65.0,
        offset: props.offset ?? 0
      };
      
      console.log(`[API Request] POST /audios/${props.audioId}/preview with payload:`, JSON.stringify(previewPayload));
      const previewResult = await audiosApi.preview(props.audioId, previewPayload);
      console.log('[SUCCESS] 后端扬声器播放已开始，使用 /audios/preview 接口');
      
      if (previewResult && previewResult.duration) {
        duration.value = previewResult.duration;
        console.log('Set real duration from API response:', duration.value);
      }
    }
  } catch (error: any) {
    console.error('Error in playOnExternalDevices:', error);
    if (error.stack) {
      console.error('Error stack:', error.stack);
    }
  }
};

const stopOnExternalDevices = async () => {
  try {
    console.log('Stopping on external devices:', props.selectedDevices.map((d: any) => d.name));
    console.log('AudioPlayerModal stop props:', {
      isTestCasePreview: props.isTestCasePreview,
      playbackMode: props.playbackMode,
      audioType: props.audioType,
      audioId: props.audioId
    });
    
    if (!props.audioId) {
      console.warn('Cannot stop preview: audioId is null or undefined');
      return;
    }
    
    if (props.isTestCasePreview) {
      console.log(`[API Request] POST /testcases/${props.audioId}/stop_preview`);
      await testcasesApi.stopPreview(props.audioId);
      console.log('[SUCCESS] 测试用例预览已停止');
    } else if (props.playbackMode === 'backend') {
      console.log(`[API Request] POST /audios/${props.audioId}/stop-preview`);
      await audiosApi.stopPreview(props.audioId);
      console.log('[SUCCESS] 后端扬声器播放已停止');
    }
  } catch (error: any) {
    console.error('Error in stopOnExternalDevices:', error);
  }
};

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
    }, 100);
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
    audio.value.removeEventListener('loadedmetadata', handleLoadedMetadata);
    audio.value.removeEventListener('timeupdate', handleTimeUpdate);
    audio.value.removeEventListener('ended', handleEnded);
    audio.value.removeEventListener('error', handleError);
    audio.value.removeEventListener('loadeddata', handleLoadedData);
    audio.value.removeEventListener('canplay', handleCanPlay);
    audio.value.removeEventListener('canplaythrough', handleCanPlay);
    audio.value.removeEventListener('progress', handleProgress);
    audio.value = null;
  }
});

watch(() => props.audioId, (newId, oldId) => {
  if (newId && newId !== oldId && props.visible) {
    console.log('Audio ID changed, reinitializing audio');
    if (audio.value) {
      audio.value.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.value.removeEventListener('timeupdate', handleTimeUpdate);
      audio.value.removeEventListener('ended', handleEnded);
      audio.value.removeEventListener('error', handleError);
      audio.value.removeEventListener('loadeddata', handleLoadedData);
      audio.value.removeEventListener('canplay', handleCanPlay);
      audio.value.removeEventListener('canplaythrough', handleCanPlay);
      audio.value.removeEventListener('progress', handleProgress);
      
      audio.value.pause();
      audio.value.src = '';
      audio.value.load();
      audio.value = null;
    }
    setTimeout(() => {
      initAudio();
    }, 50);
  }
});
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: var(--z-index-modal-top);
  animation: fadeIn 0.3s ease;
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from { transform: translateY(-20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #343a40;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6c757d;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
  transform: rotate(90deg);
}

.modal-body {
  padding: 24px;
}

.error-message {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  margin-bottom: 20px;
  background-color: #fff5f5;
  border: 1px solid #feb2b2;
  border-radius: 8px;
  color: #c53030;
  font-size: 14px;
}

.error-message i.fa-exclamation-circle {
  font-size: 20px;
  flex-shrink: 0;
}

.error-message span {
  flex: 1;
}

.error-dismiss {
  background: none;
  border: none;
  color: #c53030;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.error-dismiss:hover {
  opacity: 1;
}

.audio-info {
  text-align: center;
  margin-bottom: 24px;
}

.audio-title {
  font-size: 18px;
  font-weight: 600;
  color: #343a40;
  margin-bottom: 8px;
}

.audio-type {
  font-size: 14px;
  color: #6c757d;
  background-color: #f8f9fa;
  padding: 4px 12px;
  border-radius: 12px;
  display: inline-block;
}

.audio-player {
  background-color: #f8f9fa;
  padding: 24px;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}

.progress-bar-container {
  height: 8px;
  background-color: #e9ecef;
  border-radius: 4px;
  margin-bottom: 8px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: all 0.2s;
}

.progress-bar-container:hover {
  height: 10px;
  background-color: #dee2e6;
}

.progress-bar {
  height: 100%;
  background-color: #007bff;
  width: 0;
  transition: width 0.1s linear;
}

.progress-bar-container:hover .progress-bar {
  background-color: #0056b3;
}

.time-info {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  padding: 0 8px;
}

.time-display {
  font-size: 14px;
  color: #343a40;
  font-weight: 500;
  white-space: nowrap;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  background-color: #ffffff;
  padding: 4px 8px;
  border-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  display: inline-block;
  min-width: 60px;
}

.time-current {
  text-align: left;
}

.time-total {
  text-align: right;
  color: #6c757d;
}

.controls {
  display: flex;
  justify-content: center;
  gap: 16px;
}

.control-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  background-color: #007bff;
  color: white;
}

.control-btn:hover:not(:disabled) {
  background-color: #0056b3;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
}

.control-btn:disabled {
  background-color: #e9ecef;
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
  box-shadow: none;
}

.control-btn:nth-child(2) {
  background-color: #6c757d;
}

.control-btn:nth-child(2):hover:not(:disabled) {
  background-color: #495057;
}

.control-btn:nth-child(3) {
  background-color: #dc3545;
}

.control-btn:nth-child(3):hover:not(:disabled) {
  background-color: #c82333;
}

.device-info {
  margin-top: 24px;
  padding: 16px;
  background-color: #ffffff;
  border: 1px solid #e9ecef;
  border-radius: 8px;
}

.device-info h5 {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
  color: #495057;
}

.device-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.device-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  font-size: 14px;
  color: #343a40;
}

.device-status {
  font-size: 16px;
}

.device-status.online {
  color: #28a745;
}

.device-status.offline {
  color: #dc3545;
}

.device-name {
  font-weight: 500;
}
</style>
