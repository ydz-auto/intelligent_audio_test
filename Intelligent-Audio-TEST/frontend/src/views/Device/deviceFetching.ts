import { devicesPort, BATCH_LIST_PARAMS } from '../../composables/device/devicesPort';
import { playbackPort } from '../../composables/device/playbackPort';
import { laboratoriesPort } from '../../composables/device/laboratoriesPort';
import { apisPort } from '../../composables/apiTest/apisPort';
import { audiosPort } from '../../composables/audio/audiosPort';
import type { PlaybackDevice } from '../../domain';
import type { TestDeviceView, ApiDeviceView, DeviceUnion, ListResponse } from '@/domain';
import { HttpStatus, DeviceStatus, DeviceType, DeviceTabType } from '../../domain/enums';
import { resolveApiDeviceType } from '../../domain/model/device';
import {
  activeTab,
  loading,
  error,
  isHealthChecking,
  testDevices,
  apiDevices,
  playbackDevices,
  promptAudios,
  laboratories,
  getDeviceManagement
} from './deviceState';

/** 加载实验室列表（INT-655：「实验室」facet 选项数据源，失败静默降级为无实验室选项） */
export async function loadLaboratories() {
  try {
    const labs = await laboratoriesPort.getAllFlat({ page: 1, per_page: 500 });
    laboratories.value = labs;
  } catch (err) {
    console.error('Failed to fetch laboratories:', err);
  }
}

export async function fetchAllDevices() {
  loading.value = true;
  error.value = null;
  // INT-289：并行拉取失败项累计——失败不清空既有列表、保留旧数据并给出可见错误
  const failedParts: string[] = [];
  try {
    const basicResults = await Promise.allSettled([
      devicesPort.getAll() as Promise<ListResponse<TestDeviceView> | TestDeviceView[]>,
      apisPort.getAll() as Promise<ListResponse<ApiDeviceView> | ApiDeviceView[]>,
      audiosPort.getAll({ audioType: 'prompt' }) as Promise<ListResponse<PlaybackDevice>>
    ]);

    if (basicResults[0].status === 'fulfilled') {
      const testRes = basicResults[0].value;
      const testDevicesData = (Array.isArray(testRes) ? testRes : (testRes.items || [])).filter(d => d);
      const currentTestDevices = [...testDevices.value];
      testDevices.value = testDevicesData.map((d) => {
        const deviceId = d.id;
        const existingDevice = currentTestDevices.find(existing => existing.id === deviceId);
        const currentStatus = existingDevice && existingDevice.status === DeviceStatus.TESTING ? DeviceStatus.TESTING : d.status;
        // 物理被测设备执行路由恒为 physical（DeviceType 枚举消费，INT-74）
        return { ...d, category: d.category || '测试设备', status: currentStatus, deviceType: DeviceType.PHYSICAL } as TestDeviceView;
      });
    } else {
      console.error('Failed to fetch test devices:', basicResults[0].reason);
      failedParts.push('测试设备');
    }

    if (basicResults[1].status === 'fulfilled') {
      const apiRes = basicResults[1].value;
      const apiDevicesData = (Array.isArray(apiRes) ? apiRes : (apiRes.items || [])).filter(d => d);
      const currentAPIDevices = [...apiDevices.value];
      apiDevices.value = apiDevicesData.map((d) => {
        const deviceId = d.id;
        const existingDevice = currentAPIDevices.find(existing => existing.id === deviceId);
        const currentStatus = existingDevice && existingDevice.status === DeviceStatus.TESTING ? DeviceStatus.TESTING : d.status;

        let processedEndpoints: { endpoint: string; url?: string }[] = [];
        if (d.endpoints && Array.isArray(d.endpoints)) {
          processedEndpoints = d.endpoints.map(endpoint => ({
            ...endpoint,
            endpoint: endpoint.endpoint || endpoint.url || ''
          }));
        }

        // 被测设备类型按端点协议推导（DeviceType 枚举消费，执行路由依据，INT-74）
        const routingType = resolveApiDeviceType(processedEndpoints[0]?.endpoint);

        return { ...d, category: d.category || 'API设备', status: currentStatus, endpoints: processedEndpoints, deviceType: routingType } as ApiDeviceView;
      });
    } else {
      console.error('Failed to fetch API devices:', basicResults[1].reason);
      failedParts.push('API设备');
    }

    if (basicResults[2].status === 'fulfilled') {
      // audiosPort.getAll 已通过 audioAdapter 转换为 camelCase 分页
      const audioRes = basicResults[2].value as any;
      promptAudios.value = ((audioRes as any).items || (audioRes as any).data || []).filter((d: any) => d);
    } else {
      console.error('Failed to fetch prompt audios:', basicResults[2].reason);
      failedParts.push('提示词音频');
    }

    // playbackPort.getAll 已展平为 Domain 数组（大批量分页一次性拉取全部）
    let allPlaybackDevices: PlaybackDevice[] | null = null;
    try {
      allPlaybackDevices = await playbackPort.getAll(BATCH_LIST_PARAMS);
    } catch (err) {
      console.error('Failed to fetch playback devices:', err);
      failedParts.push('播放设备');
    }

    if (allPlaybackDevices) {
      const currentPlaybackDevices = [...playbackDevices.value];
      playbackDevices.value = allPlaybackDevices.map(d => {
        const device = d || {} as PlaybackDevice;
        const deviceId = device.id;
        const existingDevice = currentPlaybackDevices.find(existing => existing.id === deviceId);
        const currentStatus = existingDevice && existingDevice.status === DeviceStatus.TESTING ? DeviceStatus.TESTING :
                           (device.status || DeviceStatus.OFFLINE);
        return { ...device, status: currentStatus, name: device.name || '未命名设备', model: device.model || '未知型号', id: deviceId } as PlaybackDevice;
      });
    }

    autoHealthCheck();

    const deviceManagement = getDeviceManagement()!;
    deviceManagement.devices.value = [
      ...testDevices.value,
      ...playbackDevices.value,
      ...apiDevices.value
    ];
    console.log('设备数据已同步到deviceManagement.devices', deviceManagement.devices.value.length, '个设备');

    // INT-289：任一分区拉取失败时给出可见错误条，旧数据已被保留
    if (failedParts.length > 0) {
      error.value = `获取设备列表失败（${failedParts.join('/')}），已保留现有数据`;
    }
  } catch (err) {
    console.error('Failed to fetch devices:', err);
    error.value = '获取设备列表失败';
  } finally {
    loading.value = false;
  }
}

export async function autoHealthCheck() {
  if (isHealthChecking.value) return;
  isHealthChecking.value = true;

  try {
    let deviceIds: (string | number)[] = [];
    if (activeTab.value === DeviceTabType.PLAYBACK) {
      deviceIds = playbackDevices.value.map(d => d.id);
    } else if (activeTab.value === DeviceTabType.TEST) {
      deviceIds = testDevices.value.map(d => d.id);
    } else if (activeTab.value === DeviceTabType.API) {
      deviceIds = apiDevices.value.map(d => d.id);
    }

    if (deviceIds.length > 0) {
      console.log(`自动运行健康检查，设备ID: ${deviceIds}`);

      if (activeTab.value === DeviceTabType.TEST) {
        const results = await devicesPort.healthCheck(deviceIds) as any[];
        results.forEach((item: any) => {
          const device = testDevices.value.find(d => String(d.id) === String(item.id));
          if (device) {
            device.status = item.status;
            if (item.lastOnlineAt) {
              (device as any).lastOnlineAt = item.lastOnlineAt;
            }
          }
        });
      } else if (activeTab.value === DeviceTabType.PLAYBACK) {
        const results = await playbackPort.checkStatus() as any[];
        results.forEach((item: any) => {
          const device = playbackDevices.value.find(d => String(d.id) === String(item.id));
          if (device) {
            device.status = item.status || DeviceStatus.OFFLINE;
          }
        });
      } else if (activeTab.value === DeviceTabType.API) {
        for (const deviceId of deviceIds) {
          try {
            const result = await apisPort.testConnection(deviceId as string | number);
            const device = apiDevices.value.find(d => String(d.id) === String(deviceId));
            if (device && result) {
              device.status = DeviceStatus.ONLINE;
            }
          } catch (err: any) {
            console.error(`API设备 ${deviceId} 健康检查失败:`, err);
            const device = apiDevices.value.find(d => String(d.id) === String(deviceId));
            if (device) {
              // 检查是否是404错误（设备不存在）
              if (err.response?.status === HttpStatus.NOT_FOUND) {
                // 从设备列表中移除不存在的设备
                apiDevices.value = apiDevices.value.filter(d => String(d.id) !== String(deviceId));
                // 同时更新deviceManagement.devices
                const dm = getDeviceManagement()!;
                dm.devices.value = (dm.devices.value || []).filter(d => String(d.id) !== String(deviceId));
                console.log(`API设备 ${deviceId} 不存在，已从列表中移除`);
              } else {
                // 其他错误（如网络超时等），标记为离线
                device.status = DeviceStatus.OFFLINE;
              }
            }
          }
        }
      }
    }
  } catch (error) {
    console.error('自动健康检查失败:', error);
  } finally {
    isHealthChecking.value = false;
  }
}

export type { DeviceUnion };
