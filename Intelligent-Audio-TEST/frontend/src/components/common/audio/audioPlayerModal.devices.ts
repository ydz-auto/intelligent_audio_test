/**
 * AudioPlayerModal —— 外部设备播放控制
 *
 * 负责后端扬声器播放（/audios/{id}/preview、/testcases/{id}/preview）与停止接口的调用编排，
 * 以及设备数据格式归一（ID 数组 / 对象数组 → deviceUniqueId 列表）。
 */
import type { Ref } from 'vue';
import { audiosPort } from '@/composables/audio/audiosPort';
import { testcasesPort } from '@/composables/testCase/testcasesPort';

/** 外部设备播放模块依赖 */
export interface DevicePlaybackDeps {
  props: any;
  duration: Ref<number>;
}

/** 创建外部设备播放/停止控制 */
export function createDevicePlayback(deps: DevicePlaybackDeps) {
  const { props, duration } = deps;

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
        const previewResult = await testcasesPort.preview(props.audioId, previewPayload);
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
        const previewResult = await audiosPort.preview(props.audioId, previewPayload);
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
        await testcasesPort.stopPreview(props.audioId);
        console.log('[SUCCESS] 测试用例预览已停止');
      } else if (props.playbackMode === 'backend') {
        console.log(`[API Request] POST /audios/${props.audioId}/stop-preview`);
        await audiosPort.stopPreview(props.audioId);
        console.log('[SUCCESS] 后端扬声器播放已停止');
      }
    } catch (error: any) {
      console.error('Error in stopOnExternalDevices:', error);
    }
  };

  return { playOnExternalDevices, stopOnExternalDevices };
}