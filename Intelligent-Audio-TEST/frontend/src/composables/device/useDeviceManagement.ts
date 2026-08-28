import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { devicesApi, playbackApi, apisApi } from '../../utils/api';
import { useModalControl } from '../modal/useModal';
import { useNotification } from '../modal/useNotification';
import {
  MODAL_TYPES,
  type PlaybackDevice
} from '../../shared/types';

// Define local types since they're not exported from shared/types
type DeviceBase = {
  id: string | number;
  name: string;
  status: string;
  selected?: boolean;
  [key: string]: any;
};

type TestDevice = DeviceBase & {
  model?: string;
  serialNumber?: string;
  ip?: string;
  system?: string;
  systemVersion?: string;
  appName?: string;
  appVersion?: string;
  lastOnlineAt?: string;
};

type ApiDevice = DeviceBase & {
  apiUrl?: string;
  protocol?: string;
};

type DeviceUnion = TestDevice | PlaybackDevice | ApiDevice;
import { generateDeviceFields } from '../../utils/utils';
import type { APIResponse } from '../../shared/types';

// 设备管理组合式函数
export function useDeviceManagement(deviceType: 'test' | 'playback' | 'api' = 'test', onDevicesChanged?: () => Promise<void>) {
  // 状态定义
  const devices = ref<DeviceUnion[]>([]);
  const deviceSearchQuery = ref('');
  const selectedDeviceStatus = ref('all');
  const availableSerials = ref<string[]>([]);
  const isLoading = ref(false);
  const activeDeviceType = ref(deviceType); // 当前激活的设备类型

  // 分页状态
  const currentPage = ref(1);
  const pageSize = ref(12);
  const totalItems = ref(0);
  const totalPages = computed(() => Math.ceil(totalItems.value / pageSize.value));

  // 初始化模态框管理器
  const modalManager = useModalControl();
  const notification = useNotification();

  // 通知外部设备列表已变更
  const notifyDevicesChanged = async () => {
    if (onDevicesChanged) {
      await onDevicesChanged();
    }
  };

  // 轮询定时器
  let statusUpdateTimer: ReturnType<typeof setInterval> | null = null;

  // 自动批量健康检查
  async function autoHealthCheck() {
    try {
      // 只获取当前设备类型的设备ID
      let deviceIds: string[] = [];
      if (activeDeviceType.value === 'api') {
        // 只获取API设备
        deviceIds = devices.value
          .filter((d: DeviceUnion) => d.category === 'API设备' || d.vendor) // 简单判断是否是API设备
          .map((d: DeviceUnion) => String(d.id));
      } else if (activeDeviceType.value === 'test') {
        // 只获取测试设备
        deviceIds = devices.value
          .filter((d: DeviceUnion) => d.category === '测试设备') // 简单判断是否是测试设备
          .map((d: DeviceUnion) => String(d.id));
      } else if (activeDeviceType.value === 'playback') {
        // 只获取播放设备
        deviceIds = devices.value
          .filter((d: DeviceUnion) => d.type === 'dry' || d.type === 'noise') // 简单判断是否是播放设备
          .map((d: DeviceUnion) => String(d.id));
      }

      if (deviceIds.length > 0) {
        console.log(`执行${activeDeviceType.value}设备健康检查，设备ID:`, deviceIds);

        if (activeDeviceType.value === 'test') {
          const result = await devicesApi.healthCheck(deviceIds);
          result.forEach((item: { id: string | number; status: string; last_online_at?: string }) => {
            const deviceIndex = devices.value.findIndex((d: DeviceUnion) => String(d.id) === String(item.id));
            if (deviceIndex > -1) {
              const device = devices.value[deviceIndex] as TestDevice;
              device.status = item.status as any;
              if (item.last_online_at) {
                device.lastOnlineAt = item.last_online_at;
              }
            }
          });
        } else if (activeDeviceType.value === 'playback') {
          const result = await playbackApi.checkStatus();
          result.forEach((item: { id: string | number; status: string }) => {
            const deviceIndex = devices.value.findIndex((d: DeviceUnion) => String(d.id) === String(item.id));
            if (deviceIndex > -1) {
              devices.value[deviceIndex].status = (item.status || 'offline') as any;
            }
          });
        } else if (activeDeviceType.value === 'api') {
          for (const deviceId of deviceIds) {
            try {
              await apisApi.testConnection(deviceId);
              const deviceIndex = devices.value.findIndex((d: DeviceUnion) => String(d.id) === deviceId);
              if (deviceIndex > -1) {
                devices.value[deviceIndex].status = 'online';
              }
            } catch (error: any) {
              console.error(`API设备 ${deviceId} 健康检查失败:`, error);
              const deviceIndex = devices.value.findIndex((d: DeviceUnion) => String(d.id) === deviceId);
              if (deviceIndex > -1) {
                // 检查是否是404错误（设备不存在）
                if (error.response?.status === 404) {
                  // 从设备列表中移除不存在的设备
                  devices.value = devices.value.filter((d: DeviceUnion) => String(d.id) !== String(deviceId));
                  console.log(`API设备 ${deviceId} 不存在，已从列表中移除`);
                } else {
                  // 其他错误（如网络超时等），标记为离线
                  devices.value[deviceIndex].status = 'offline';
                }
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('自动健康检查失败:', error);
    }
  }

  const allFilteredDevices = computed(() => {
    let result = [...devices.value];
    if (selectedDeviceStatus.value !== 'all') {
      result = result.filter(device => device.status === selectedDeviceStatus.value);
    }
    if (deviceSearchQuery.value) {
      const query = deviceSearchQuery.value.toLowerCase();
      result = result.filter(device => {
        // 基础属性搜索 (所有设备共有)
        const nameMatch = device.name?.toLowerCase().includes(query);
        const descMatch = (device as any).description?.toLowerCase().includes(query);

        // 特定属性搜索
        const modelMatch = (device as any).model?.toLowerCase().includes(query);
        const serialMatch = (device as any).serialNumber?.toLowerCase().includes(query);
        const ipMatch = (device as any).ip?.toLowerCase().includes(query);
        const locationMatch = (device as any).location?.toLowerCase().includes(query);
        const typeMatch = (device as any).type?.toLowerCase().includes(query);
        const appNameMatch = (device as any).appName?.toLowerCase().includes(query);

        return nameMatch || descMatch || modelMatch || serialMatch || ipMatch || locationMatch || typeMatch || appNameMatch;
      });
    }
    return result;
  });

  // 分页后的设备列表
  const filteredDevices = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value;
    const end = start + pageSize.value;
    return allFilteredDevices.value.slice(start, end);
  });

  // 更新总数
  watch(allFilteredDevices, (newVal) => {
    totalItems.value = newVal.length;
    // 如果当前页超出范围，重置到第一页
    if (currentPage.value > totalPages.value && totalPages.value > 0) {
      currentPage.value = 1;
    }
  }, { immediate: true });

  // 分页方法
  const handlePageChange = (page: number) => {
    if (page >= 1 && page <= totalPages.value) {
      currentPage.value = page;
    }
  };

  const handlePageSizeChange = (size: number) => {
    pageSize.value = size;
    currentPage.value = 1; // 重置到第一页
  };

  const handlePrevPage = () => {
    if (currentPage.value > 1) {
      currentPage.value--;
    }
  };

  const handleNextPage = () => {
    if (currentPage.value < totalPages.value) {
      currentPage.value++;
    }
  };

  const fetchDevices = async () => {
    try {
      isLoading.value = true;
      let data: DeviceUnion[] = [];
      if (activeDeviceType.value === 'test') {
        const response = await devicesApi.getAll();
        data = (response.items || response) as TestDevice[];
      } else if (activeDeviceType.value === 'playback') {
        const response = await playbackApi.getAll();
        data = (response.items || response) as PlaybackDevice[];
      } else if (activeDeviceType.value === 'api') {
        const response = await apisApi.getAll();
        data = (response.items || response) as ApiDevice[];
      }
      devices.value = Array.isArray(data) ? data : [];
    } catch (error) {
      console.error('获取设备列表失败:', error);
      const errorMessage = error instanceof Error ? error.message : '获取设备列表失败';
      notification.error('获取设备列表失败', errorMessage);
      devices.value = [];
    } finally {
      isLoading.value = false;
    }
  };

  const deleteDevice = async (id: number | string, type?: string) => {
    const targetType = type || activeDeviceType.value;
    try {
      const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '确认删除',
        message: '确定要删除该设备吗？',
        type: 'danger',
        confirmText: '删除',
        cancelText: '取消'
      });
      if (confirmed) {
        if (targetType === 'test') {
          await devicesApi.delete(id);
        } else if (targetType === 'playback') {
          await playbackApi.delete(id);
        } else if (targetType === 'api') {
          await apisApi.delete(id);
        }
        await fetchDevices();
        await notifyDevicesChanged();
      }
    } catch (error) {
      console.error('删除设备失败:', error);
      // 向用户显示错误提示
      const errorMessage = error instanceof Error ? error.message : '删除设备失败，请重试';
      alert(errorMessage);
    }
  };

  const addDevice = (type?: string, initialData?: any) => {
    const targetType = type || activeDeviceType.value;
    console.log(`[useDeviceManagement] Opening add device modal for type: ${targetType}`, initialData);
    modalManager.open(MODAL_TYPES.ADD_DEVICE, {
      title: targetType === 'api' ? '添加 API' : '添加设备',
      mode: 'create',
      fields: generateDeviceFields(targetType),
      formData: initialData || {},
      onConfirm: async (result: any) => {
        try {
          const { data } = result;
          if (targetType === 'test') {
            await devicesApi.create(data);
          } else if (targetType === 'playback') {
            await playbackApi.create(data);
          } else if (targetType === 'api') {
            await apisApi.create(data);
          }
          await fetchDevices();
          await notifyDevicesChanged();
        } catch (error) {
          console.error('添加设备失败:', error);
          // 向用户显示错误提示
          const errorMessage = error instanceof Error ? error.message : '添加设备失败，请重试';
          alert(errorMessage);
        }
      }
    });
  };

  const editDevice = async (id: number | string, type?: string) => {
    const targetType = type || activeDeviceType.value;
    console.log(`[useDeviceManagement] Opening edit device modal for id: ${id}, type: ${targetType}`);
    try {
      let deviceData: any;
      if (targetType === 'test') {
        deviceData = await devicesApi.getOne(id);
      } else if (targetType === 'playback') {
        deviceData = await playbackApi.getOne(id);
      } else if (targetType === 'api') {
        deviceData = await apisApi.getOne(id);
      }

      modalManager.open(MODAL_TYPES.EDIT_DEVICE, {
        title: targetType === 'api' ? '编辑 API' : '编辑设备',
        mode: 'edit',
        fields: generateDeviceFields(targetType),
        formData: deviceData,
        onConfirm: async (result: any) => {
          try {
          const { data } = result;
          if (targetType === 'test') {
            await devicesApi.update(id, data);
          } else if (targetType === 'playback') {
            await playbackApi.update(id, data);
          } else if (targetType === 'api') {
            await apisApi.update(id, data);
          }
          await fetchDevices();
          await notifyDevicesChanged();
        } catch (error) {
          console.error('编辑设备失败:', error);
          // 向用户显示错误提示
          const errorMessage = error instanceof Error ? error.message : '编辑设备失败，请重试';
          alert(errorMessage);
        }
        }
      });
    } catch (error) {
      console.error('获取设备详情失败:', error);
    }
  };

  const batchDeleteDevices = async (ids: (number | string)[], type?: string) => {
    const targetType = type || activeDeviceType.value;
    if (!ids || ids.length === 0) return;
    try {
      const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '确认批量删除',
        message: `确定要删除选中的 ${ids.length} 个设备吗？`,
        type: 'danger',
        confirmText: '删除',
        cancelText: '取消'
      });
      if (confirmed) {
        isLoading.value = true;
        // 串行删除，确保稳定性（如果后端支持批量接口，应优先使用批量接口）
        for (const id of ids) {
          if (targetType === 'test') {
            await devicesApi.delete(id);
          } else if (targetType === 'playback') {
            await playbackApi.delete(id);
          } else if (targetType === 'api') {
            await apisApi.delete(id);
          }
        }
        await fetchDevices();
        await notifyDevicesChanged();
      }
    } catch (error) {
      console.error('批量删除设备失败:', error);
      // 向用户显示错误提示
      const errorMessage = error instanceof Error ? error.message : '批量删除设备失败，请重试';
      alert(errorMessage);
    } finally {
      isLoading.value = false;
    }
  };

  const importDevices = (type?: string) => {
    modalManager.open(MODAL_TYPES.IMPORT_EXPORT, {
      title: '导入设备',
      mode: 'import',
      deviceType: type || activeDeviceType.value,
      onConfirm: async () => {
        await fetchDevices();
        await notifyDevicesChanged();
      }
    });
  };

  const exportDevices = (type?: string) => {
    modalManager.open(MODAL_TYPES.IMPORT_EXPORT, {
      title: '导出设备',
      mode: 'export',
      deviceType: type || activeDeviceType.value
    });
  };

  const testDeviceConnection = async (id: number | string, type?: string) => {
    const targetType = type || activeDeviceType.value;
    try {
      if (targetType === 'test') {
        await healthCheckDevice(id);
      } else if (targetType === 'playback') {
        await playbackApi.test(id);
      } else if (targetType === 'api') {
        await apisApi.testConnection(id);
      }
    } catch (error) {
      console.error('测试设备连接失败:', error);
      const errorMessage = error instanceof Error ? error.message : '测试设备连接失败，请重试';
      alert(errorMessage);
      throw error;
    }
  };

  const scanDevices = (type?: string) => {
    const targetType = type || activeDeviceType.value;
    console.log(`[useDeviceManagement] Opening scan devices modal for type: ${targetType}`);

    modalManager.open(MODAL_TYPES.SCAN_DEVICES, {
      title: `扫描${targetType === 'test' ? '测试' : targetType === 'playback' ? '播放' : 'API'}设备`,
      deviceType: targetType,
      autoStartScan: true,
      onConfirm: (scannedDevice: any) => {
        console.log('[useDeviceManagement] Scanned device confirmed:', scannedDevice);

        // 将扫描到的数据转换为表单数据格式
        let formData: any = {};
        if (targetType === 'test') {
          // 归一化系统类型
          let system = (scannedDevice.system || 'android').toLowerCase();
          if (system.includes('harmony')) system = 'harmony';
          if (system.includes('ios')) system = 'ios';
          if (system.includes('android')) system = 'android';

          formData = {
            name: scannedDevice.name,
            model: scannedDevice.model,
            serialNumber: scannedDevice.serial || scannedDevice.serial_number,
            ip: scannedDevice.ip_address || scannedDevice.ip,
            system: system,
            systemVersion: scannedDevice.system_version || 'Unknown',
            appName: scannedDevice.app_name || 'Default App',
            appVersion: scannedDevice.app_version || '1.0.0',
            status: 'online'
          };
        } else if (targetType === 'playback') {
          formData = {
            name: scannedDevice.name,
            model: scannedDevice.model,
            deviceUniqueId: scannedDevice.device_unique_id,
            channelIndex: scannedDevice.channel_index !== undefined ? scannedDevice.channel_index : 0,
            sampleRate: scannedDevice.sample_rate || 48000,
            deviceType: scannedDevice.device_type || scannedDevice.type || 'dry',
            status: 'online'
          };
        } else if (targetType === 'api') {
          formData = {
            name: scannedDevice.name,
            endpoint: scannedDevice.endpoint,
            protocol: scannedDevice.protocol || 'http',
            status: 'online'
          };
        }

        // 关闭扫描模态窗并打开添加设备模态窗，预填扫描到的数据
        modalManager.close();
        addDevice(targetType, formData);
      }
    });
  };

  const startStatusPolling = (interval = 30000) => {
    stopStatusPolling();
    statusUpdateTimer = setInterval(autoHealthCheck, interval);
  };

  const stopStatusPolling = () => {
    if (statusUpdateTimer) {
      clearInterval(statusUpdateTimer);
      statusUpdateTimer = null;
    }
  };

  // 单个设备健康检查
  async function healthCheckDevice(id: string | number) {
    try {
      if (activeDeviceType.value === 'test') {
        const response = await devicesApi.healthCheck([String(id)]);
        const result = response?.data || response;
        console.log('[healthCheckDevice] API响应:', result);
        if (result && result.length > 0) {
          const item = result[0];
          console.log('[healthCheckDevice] 设备ID:', id, '返回状态:', item.status);
          const deviceIndex = devices.value.findIndex((d: DeviceUnion) => String(d.id) === String(item.id));
          console.log('[healthCheckDevice] 设备索引:', deviceIndex);
          if (deviceIndex > -1) {
            const newDevice = { ...devices.value[deviceIndex], status: item.status };
            console.log('[healthCheckDevice] 更新前:', devices.value[deviceIndex].status);
            console.log('[healthCheckDevice] 更新后:', newDevice.status);
            devices.value.splice(deviceIndex, 1, newDevice);
            console.log('[healthCheckDevice] 更新后实际值:', devices.value[deviceIndex].status);
          } else {
            console.log('[healthCheckDevice] 未找到匹配的设备');
          }
        }
      } else if (activeDeviceType.value === 'api') {
        await apisApi.testConnection(String(id));
        const deviceIndex = devices.value.findIndex((d: DeviceUnion) => String(d.id) === String(id));
        if (deviceIndex > -1) {
          devices.value.splice(deviceIndex, 1, { ...devices.value[deviceIndex], status: 'online' });
        }
      }
      return true;
    } catch (error) {
      console.error('设备健康检查失败:', error);
      const deviceIndex = devices.value.findIndex((d: DeviceUnion) => String(d.id) === String(id));
      if (deviceIndex > -1) {
        devices.value.splice(deviceIndex, 1, { ...devices.value[deviceIndex], status: 'offline' });
      }
      return false;
    }
  }

  onMounted(() => {
    fetchDevices();
    startStatusPolling();
  });

  onUnmounted(() => {
    stopStatusPolling();
  });

  // ===== 播放设备分页能力（兼容精简契约：audioImport.ts / useUploadModal.ts） =====
  // 原 useDeviceManagement 在重构拆分时移除了这些字段，但 audioImport.ts / useUploadModal.ts
  // 仍依赖它们，这里补齐以保持兼容。
  const playbackDevices = ref<PlaybackDevice[]>([]);
  const playbackDevicePage = ref(1);
  const playbackDevicePages = ref(1);
  const playbackDeviceLoading = ref(false);
  const playbackDeviceHasMore = ref(true);
  const deviceList = ref<{ value: string | number; name: string }[]>([]);

  async function fetchPlaybackDevices(reset = true) {
    if (reset) {
      playbackDevicePage.value = 1;
      playbackDevices.value = [];
      playbackDeviceHasMore.value = true;
    }
    if (playbackDeviceLoading.value || (!playbackDeviceHasMore.value && !reset)) return;
    playbackDeviceLoading.value = true;
    try {
      const response = await devicesApi.getPlaybackDevices({
        params: { page: playbackDevicePage.value, per_page: 50 },
        unwrapResponse: false,
      }) as APIResponse<{ items: PlaybackDevice[]; pages: number }>;
      if (response.success && response.data && Array.isArray(response.data.items)) {
        if (reset) {
          playbackDevices.value = response.data.items;
        } else {
          playbackDevices.value = [...playbackDevices.value, ...response.data.items];
        }
        playbackDevicePages.value = response.data.pages || 1;
        playbackDeviceHasMore.value = playbackDevicePage.value < playbackDevicePages.value;
        if (playbackDeviceHasMore.value) playbackDevicePage.value += 1;
      } else {
        if (reset) playbackDevices.value = [];
      }
    } catch (e) {
      console.error('Fetch playback devices failed:', e);
      if (reset) playbackDevices.value = [];
    } finally {
      playbackDeviceLoading.value = false;
    }
  }

  async function loadMorePlaybackDevices() {
    if (!playbackDeviceLoading.value && playbackDeviceHasMore.value) {
      await fetchPlaybackDevices(false);
    }
  }

  return {
    devices,
    deviceSearchQuery,
    selectedDeviceStatus,
    availableSerials,
    isLoading,
    filteredDevices,
    allFilteredDevices,
    fetchDevices,
    deleteDevice,
    addDevice,
    editDevice,
    batchDeleteDevices,
    importDevices,
    exportDevices,
    testDeviceConnection,
    scanDevices,
    autoHealthCheck,
    healthCheckDevice,
    modalManager,
    activeDeviceType,
    // 分页相关导出
    currentPage,
    pageSize,
    totalItems,
    totalPages,
    handlePageChange,
    handlePageSizeChange,
    handlePrevPage,
    handleNextPage,
    startHealthCheckPolling: startStatusPolling,
    stopHealthCheckPolling: stopStatusPolling,
    // ===== 精简播放设备契约（兼容 audioImport.ts / useUploadModal.ts） =====
    playbackDevices,
    playbackDevicePage,
    playbackDevicePages,
    playbackDeviceLoading,
    playbackDeviceHasMore,
    deviceList,
    fetchPlaybackDevices,
    loadMorePlaybackDevices,
  };
}
