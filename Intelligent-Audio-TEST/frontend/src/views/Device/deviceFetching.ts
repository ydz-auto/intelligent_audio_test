import { devicesApi, playbackApi, apisApi, audiosApi } from '../../utils/api';
import type { PlaybackDevice } from '../../shared/types';
import type { TestDevice, APIDevice, DeviceUnion, ListResponse } from './deviceTypes';
import {
  activeTab,
  loading,
  error,
  isHealthChecking,
  testDevices,
  apiDevices,
  playbackDevices,
  promptAudios,
  getDeviceManagement
} from './deviceState';

export async function fetchAllDevices() {
  loading.value = true;
  error.value = null;
  try {
    const basicResults = await Promise.allSettled([
      devicesApi.getAll() as Promise<ListResponse<TestDevice> | TestDevice[]>,
      apisApi.getAll() as Promise<ListResponse<APIDevice> | APIDevice[]>,
      audiosApi.getAll({ audioType: 'prompt' }) as Promise<ListResponse<PlaybackDevice>>
    ]);

    if (basicResults[0].status === 'fulfilled') {
      const testRes = basicResults[0].value;
      const testDevicesData = (Array.isArray(testRes) ? testRes : (testRes.items || [])).filter(d => d);
      const currentTestDevices = [...testDevices.value];
      testDevices.value = testDevicesData.map((d) => {
        const deviceId = d.id;
        const existingDevice = currentTestDevices.find(existing => existing.id === deviceId);
        const currentStatus = existingDevice && existingDevice.status === 'testing' ? 'testing' : d.status;
        return { ...d, category: d.category || '测试设备', status: currentStatus } as TestDevice;
      });
    } else {
      console.error('Failed to fetch test devices:', basicResults[0].reason);
      testDevices.value = [];
    }

    if (basicResults[1].status === 'fulfilled') {
      const apiRes = basicResults[1].value;
      const apiDevicesData = (Array.isArray(apiRes) ? apiRes : (apiRes.items || [])).filter(d => d);
      const currentAPIDevices = [...apiDevices.value];
      apiDevices.value = apiDevicesData.map((d) => {
        const deviceId = d.id;
        const existingDevice = currentAPIDevices.find(existing => existing.id === deviceId);
        const currentStatus = existingDevice && existingDevice.status === 'testing' ? 'testing' : d.status;

        let processedEndpoints: { endpoint: string; url?: string }[] = [];
        if (d.endpoints && Array.isArray(d.endpoints)) {
          processedEndpoints = d.endpoints.map(endpoint => ({
            ...endpoint,
            endpoint: endpoint.endpoint || endpoint.url || ''
          }));
        }

        return { ...d, category: d.category || 'API设备', status: currentStatus, endpoints: processedEndpoints } as APIDevice;
      });
    } else {
      console.error('Failed to fetch API devices:', basicResults[1].reason);
      apiDevices.value = [];
    }

    if (basicResults[2].status === 'fulfilled') {
      const audioRes = basicResults[2].value as any;
      promptAudios.value = (audioRes.items || []).filter((d: any) => d);
    } else {
      console.error('Failed to fetch prompt audios:', basicResults[2].reason);
      promptAudios.value = [];
    }

    let allPlaybackDevices: PlaybackDevice[] = [];
    let currentPage = 1;
    let totalPages = 1;

    while (currentPage <= totalPages) {
      try {
        const playbackRes = await playbackApi.getAll({ page: currentPage, perPage: 100 }) as ListResponse<PlaybackDevice> | PlaybackDevice[];
        const devicesData = (Array.isArray(playbackRes) ? playbackRes : (playbackRes.items || []));
        allPlaybackDevices = [...allPlaybackDevices, ...devicesData];
        totalPages = (!Array.isArray(playbackRes) && playbackRes.pages) || 1;
        currentPage++;
      } catch (err) {
        console.error(`Failed to fetch playback devices page ${currentPage}:`, err);
        break;
      }
    }

    const currentPlaybackDevices = [...playbackDevices.value];
    playbackDevices.value = allPlaybackDevices.map(d => {
      const device = d || {} as PlaybackDevice;
      const deviceId = device.id;
      const existingDevice = currentPlaybackDevices.find(existing => existing.id === deviceId);
      const currentStatus = existingDevice && existingDevice.status === 'testing' ? 'testing' :
                         (device.status || 'offline');
      return { ...device, status: currentStatus, name: device.name || '未命名设备', model: device.model || '未知型号', id: deviceId } as PlaybackDevice;
    });

    autoHealthCheck();

    const deviceManagement = getDeviceManagement()!;
    deviceManagement.devices.value = [
      ...testDevices.value,
      ...playbackDevices.value,
      ...apiDevices.value
    ];
    console.log('设备数据已同步到deviceManagement.devices', deviceManagement.devices.value.length, '个设备');
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
    if (activeTab.value === 'playback') {
      deviceIds = playbackDevices.value.map(d => d.id);
    } else if (activeTab.value === 'test') {
      deviceIds = testDevices.value.map(d => d.id);
    } else if (activeTab.value === 'api') {
      deviceIds = apiDevices.value.map(d => d.id);
    }

    if (deviceIds.length > 0) {
      console.log(`自动运行健康检查，设备ID: ${deviceIds}`);

      if (activeTab.value === 'test') {
        const results = await devicesApi.healthCheck(deviceIds) as any[];
        results.forEach((item: any) => {
          const device = testDevices.value.find(d => String(d.id) === String(item.id));
          if (device) {
            device.status = item.status;
            if (item.lastOnlineAt) {
              (device as any).lastOnlineAt = item.lastOnlineAt;
            }
          }
        });
      } else if (activeTab.value === 'playback') {
        const results = await playbackApi.checkStatus() as any[];
        results.forEach((item: any) => {
          const device = playbackDevices.value.find(d => String(d.id) === String(item.id));
          if (device) {
            device.status = item.status || 'offline';
          }
        });
      } else if (activeTab.value === 'api') {
        for (const deviceId of deviceIds) {
          try {
            const result = await apisApi.testConnection(deviceId as string | number);
            const device = apiDevices.value.find(d => String(d.id) === String(deviceId));
            if (device && result) {
              device.status = 'online';
            }
          } catch (err: any) {
            console.error(`API设备 ${deviceId} 健康检查失败:`, err);
            const device = apiDevices.value.find(d => String(d.id) === String(deviceId));
            if (device) {
              // 检查是否是404错误（设备不存在）
              if (err.response?.status === 404) {
                // 从设备列表中移除不存在的设备
                apiDevices.value = apiDevices.value.filter(d => String(d.id) !== String(deviceId));
                // 同时更新deviceManagement.devices
                const dm = getDeviceManagement()!;
                dm.devices.value = (dm.devices.value || []).filter(d => String(d.id) !== String(deviceId));
                console.log(`API设备 ${deviceId} 不存在，已从列表中移除`);
              } else {
                // 其他错误（如网络超时等），标记为离线
                device.status = 'offline';
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
