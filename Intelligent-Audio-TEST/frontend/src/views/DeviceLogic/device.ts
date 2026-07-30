import { ref, computed, onMounted, onUnmounted, watch, Ref } from 'vue';
import { devicesApi, playbackApi, apisApi, audiosApi } from '../../utils/api';
import { useModalControl } from '../../composables/useModal';
import { useDeviceManagement } from '../../composables/useDeviceManagement';
import { MODAL_TYPES } from '../../shared/types';
import type { PlaybackDevice, APIConfig, Audio } from '../../shared/types';

export interface TestDevice {
  id: string | number;
  name: string;
  model?: string;
  category?: string;
  keywords?: string;
  status: 'online' | 'offline' | 'testing' | 'busy' | 'error';
  lastOnlineAt?: string;
  needs_prompt_audio?: boolean;
  supportedAlgorithms?: string[];
  [key: string]: any;
}

export interface APIDevice {
  id: string | number;
  name: string;
  model?: string;
  category?: string;
  vendor?: string;
  status: 'online' | 'offline' | 'testing' | 'busy' | 'error';
  endpoints?: { endpoint: string; url?: string }[];
  algorithm_type?: string;
  algorithmType?: string;
  [key: string]: any;
}

export type DeviceUnion = TestDevice | APIDevice | PlaybackDevice;

const tabs = [
  { type: 'test', label: '测试设备管理', icon: 'fas fa-microphone' },
  { type: 'api', label: '测试API管理', icon: 'fas fa-exchange-alt' },
  { type: 'playback', label: '播放设备管理', icon: 'fas fa-headphones' }
];

const activeTab = ref('test');
const loading = ref(false);
const isHealthChecking = ref(false);
const error = ref<string | null>(null);
const isScanning = ref(false);
const scanProgress = ref(0);
const scanStatus = ref('准备扫描');
const scanResults = ref<any[]>([]);
const dropdowns = ref({
  batchDropdown: false,
  importExportDropdown: false
});
const searchQuery = ref('');
const statusFilter = ref('all');
const playbackTypeFilter = ref('all');
const algorithmFilter = ref('all');
const algorithmTypeFilter = ref('all');
const selectedDevices = ref<(string | number)[]>([]);
const deviceStatusText : Record<string, string> = { online: '在线', offline: '离线', testing: '测试中', busy: '忙碌', error: '错误' };
const playbackDevices = ref<PlaybackDevice[]>([]);
const testDevices = ref<TestDevice[]>([]);
const apiDevices = ref<APIDevice[]>([]);

// 分页状态
const playbackCurrentPage = ref(1);
const playbackPageSize = ref(6);
const playbackTotalItems = ref(0);
const playbackTotalPages = computed(() => Math.ceil(playbackTotalItems.value / playbackPageSize.value));

const testCurrentPage = ref(1);
const testPageSize = ref(12);
const testTotalItems = ref(0);
const testTotalPages = computed(() => Math.ceil(testTotalItems.value / testPageSize.value));

const apiCurrentPage = ref(1);
const apiPageSize = ref(12);
const apiTotalItems = ref(0);
const apiTotalPages = computed(() => Math.ceil(apiTotalItems.value / apiPageSize.value));

const promptAudios = ref<Audio[]>([]);
const availableSerials = ref<string[]>([]);
const algorithmTypeOptions = ref<{ value: string; label: string }[]>([]);
let statusUpdateTimer : ReturnType<typeof setInterval> | null = null;
let deviceManagement: {
  devices: ReturnType<typeof ref<DeviceUnion[]>>;
  activeDeviceType: ReturnType<typeof ref<'test' | 'playback' | 'api'>>;
  modalManager: ReturnType<typeof useModalControl>;
  addDevice: (type?: string, initialData?: any) => void;
  editDevice: (id: number | string, type?: string) => Promise<void>;
  deleteDevice: (id: number | string, type?: string) => Promise<void>;
  batchDeleteDevices: (ids: (number | string)[], type?: string) => Promise<void>;
  importDevices: (type?: string) => void;
  exportDevices: (type?: string) => void;
  testDeviceConnection: (id: number | string, type?: string) => Promise<void>;
  scanDevices: (type?: string) => void;
  startHealthCheckPolling: () => void;
  stopHealthCheckPolling: () => void;
} | undefined;

interface ListResponse<T> {
  items?: T[];
  pages?: number;
  total?: number;
}

async function fetchAllDevices() {
  loading.value = true;
  error.value = null;
  try {
    const basicResults = await Promise.allSettled([
      devicesApi.getAll() as Promise<ListResponse<TestDevice> | TestDevice[]>,
      apisApi.getAll() as Promise<ListResponse<APIDevice> | APIDevice[]>,
      audiosApi.getAll({ audioType: 'prompt' }) as Promise<ListResponse<Audio>>
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
      const audioRes = basicResults[2].value;
      promptAudios.value = (audioRes.items || []).filter(d => d);
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

async function autoHealthCheck() {
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
                deviceManagement.devices.value = deviceManagement.devices.value.filter(d => String(d.id) !== String(deviceId));
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

function switchDeviceType(type: string) {
  activeTab.value = type;
  if (deviceManagement.activeDeviceType) {
    deviceManagement.activeDeviceType.value = type as 'test' | 'playback' | 'api';
  }
  statusFilter.value = 'all';
  playbackTypeFilter.value = 'all';
  algorithmTypeFilter.value = 'all';
  searchQuery.value = '';
  selectedDevices.value = [];
  fetchAllDevices();
}

function toggleDropdown(dropdownName: 'batchDropdown' | 'importExportDropdown') {
  dropdowns.value[dropdownName] = !dropdowns.value[dropdownName];
}

async function handleAddDevice() {
  deviceManagement.addDevice(activeTab.value);
}

async function openEditModal(deviceId: string) {
  await deviceManagement.editDevice(deviceId, activeTab.value);
}

async function deleteDevice(deviceId: string) {
  deviceManagement.deleteDevice(deviceId, activeTab.value);
}

function searchDevices() {
  // 搜索功能已通过计算属性实现
}

function filterDevices() {
  // 过滤功能已通过计算属性实现
}

function showDeviceDetails(deviceId: string) {
  deviceManagement.modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
    title: '设备详情',
    deviceId: deviceId,
    options: { closable: true, width: '800px' }
  });
}

function batchEnableDevices() {
  deviceManagement.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: '确认批量启用',
    message: `确定要启用选中的 ${selectedDevices.value.length} 个设备吗？`,
    confirmText: '确认启用',
    cancelText: '取消',
    options: { closable: true },
    onConfirm: () => {
      console.log('批量启用设备:', selectedDevices.value);
      selectedDevices.value = [];
    }
  });
}

function batchDisableDevices() {
  deviceManagement.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: '确认批量禁用',
    message: `确定要禁用选中的 ${selectedDevices.value.length} 个设备吗？`,
    confirmText: '确认禁用',
    cancelText: '取消',
    options: { closable: true },
    onConfirm: () => {
      console.log('批量禁用设备:', selectedDevices.value);
      selectedDevices.value = [];
    }
  });
}

async function batchDeleteDevices() {
  deviceManagement.batchDeleteDevices(selectedDevices.value, activeTab.value);
}

async function batchHealthCheck() {
  if (selectedDevices.value.length === 0) {
    alert('请先选择要检查的设备');
    return;
  }
  
  try {
    for (const deviceId of selectedDevices.value) {
      let deviceList: DeviceUnion[] = [];
      if (activeTab.value === 'test') {
        deviceList = testDevices.value;
      } else if (activeTab.value === 'playback') {
        deviceList = playbackDevices.value;
      } else if (activeTab.value === 'api') {
        deviceList = apiDevices.value;
      } else {
        continue;
      }
      
      const deviceIndex = deviceList.findIndex(d => d.id === deviceId);
      if (deviceIndex > -1) {
        deviceList[deviceIndex].status = 'testing';
      }
      
      if (activeTab.value === 'test') {
        await devicesApi.healthCheck([deviceId]);
      } else if (activeTab.value === 'playback') {
        const result = await playbackApi.checkStatus() as { id: string | number; status: string }[];
        result.forEach(item => {
          const playbackDeviceIndex = playbackDevices.value.findIndex(d => d.id === item.id);
          if (playbackDeviceIndex > -1) {
            playbackDevices.value[playbackDeviceIndex].status = item.status as any;
          }
        });
      } else if (activeTab.value === 'api') {
        await apisApi.testConnection(deviceId as string | number);
      }
    }
    
    selectedDevices.value = [];
  } catch (error) {
    console.error('批量健康检查失败:', error);
    const errorMessage = error instanceof Error ? error.message : '未知错误';
    alert('批量健康检查失败: ' + errorMessage);
  }
}

function importDevices() {
  deviceManagement.importDevices(activeTab.value as 'test' | 'playback' | 'api');
}

function exportDevices() {
  deviceManagement.exportDevices(activeTab.value as 'test' | 'playback' | 'api');
}

async function testDevice(deviceId: string | number) {
  let deviceList: DeviceUnion[] = [];
  if (activeTab.value === 'test') {
    deviceList = testDevices.value;
  } else if (activeTab.value === 'playback') {
    deviceList = playbackDevices.value;
  } else if (activeTab.value === 'api') {
    deviceList = apiDevices.value;
  } else {
    return;
  }
  
  const deviceIndex = deviceList.findIndex(d => d.id === deviceId);
  const originalStatus = deviceIndex > -1 ? deviceList[deviceIndex].status : null;
  
  const result = await new Promise((resolve) => {
    deviceManagement.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认测试',
      message: '确定要开始测试该设备吗？',
      confirmText: '开始测试',
      cancelText: '取消',
      options: { closable: true },
      onConfirm: () => resolve(true),
      onCancel: () => resolve(false),
      onClose: () => resolve(false)
    });
  });
  
  if (result) {
    try {
      if (deviceIndex > -1) {
        deviceList[deviceIndex].status = 'testing';
      }
      await deviceManagement.testDeviceConnection(deviceId, activeTab.value as 'test' | 'playback' | 'api');
    } catch (error) {
      console.error('测试设备失败:', error);
      if (deviceIndex > -1 && originalStatus) {
        deviceList[deviceIndex].status = originalStatus;
      }
    }
  }
}

async function stopTest(deviceId: string | number) {
  deviceManagement.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: '确认停止测试',
    message: '确定要停止该设备的测试吗？',
    confirmText: '停止测试',
    cancelText: '取消',
    options: { closable: true },
    onConfirm: async () => {
      try {
        let deviceList: DeviceUnion[] = [];
        if (activeTab.value === 'playback') {
          deviceList = playbackDevices.value;
        } else if (activeTab.value === 'test') {
          deviceList = testDevices.value;
        } else if (activeTab.value === 'api') {
          deviceList = apiDevices.value;
        } else {
          return;
        }
        
        const deviceIndex = deviceList.findIndex(d => d.id === deviceId);
        if (deviceIndex > -1) {
          deviceList[deviceIndex].status = 'online';
        }
        
        if (activeTab.value === 'playback') {
          await (playbackApi as any).stopTest(deviceId);
        } else if (activeTab.value === 'test') {
          await (devicesApi as any).stopTest(deviceId);
        } else if (activeTab.value === 'api') {
          await (apisApi as any).stopTest(deviceId);
        }
      } catch (error) {
        console.error('停止测试失败:', error);
      }
    }
  });
}

async function healthCheckDevice(deviceId: string | number) {
  let deviceList: DeviceUnion[] = [];
  let deviceIndex = -1;
  
  try {
    if (activeTab.value === 'test') {
      deviceList = testDevices.value;
    } else if (activeTab.value === 'playback') {
      deviceList = playbackDevices.value;
    } else if (activeTab.value === 'api') {
      deviceList = apiDevices.value;
    }
    
    deviceIndex = deviceList.findIndex(d => d.id === deviceId);
    
    if (deviceIndex > -1) {
      deviceList[deviceIndex].status = 'testing';
    }
    
    if (activeTab.value === 'test') {
      const healthCheckResult = await devicesApi.healthCheck([deviceId]) as { id: string | number; status: string }[];
      if (healthCheckResult && Array.isArray(healthCheckResult)) {
        healthCheckResult.forEach(item => {
          const testDeviceIndex = testDevices.value.findIndex(d => d.id === item.id);
          if (testDeviceIndex > -1) {
            testDevices.value[testDeviceIndex].status = item.status as any;
          }
        });
      }
    } else if (activeTab.value === 'playback') {
      const healthCheckResult = await playbackApi.checkStatus() as { id: string | number; status: string }[];
      if (healthCheckResult && Array.isArray(healthCheckResult)) {
        healthCheckResult.forEach(item => {
          const playbackDeviceIndex = playbackDevices.value.findIndex(d => d.id === item.id);
          if (playbackDeviceIndex > -1) {
            playbackDevices.value[playbackDeviceIndex].status = item.status as any;
          }
        });
      }
    } else if (activeTab.value === 'api') {
      const healthCheckResult = await apisApi.testConnection(deviceId as string | number);
      if (healthCheckResult) {
        const apiDeviceIndex = apiDevices.value.findIndex(d => d.id === deviceId);
        if (apiDeviceIndex > -1) {
          apiDevices.value[apiDeviceIndex].status = 'online';
        }
      }
    }
    
    await fetchAllDevices();
  } catch (error) {
    console.error('健康检查失败:', error);
    if (deviceList && deviceIndex > -1) {
      deviceList[deviceIndex].status = 'offline';
    }
  }
}

function scanDevices(type?: string) {
  const targetType = (type || activeTab.value) as 'test' | 'playback' | 'api';
  deviceManagement.scanDevices(targetType);
}

function startScanDevices() {
  scanDevices();
}

function getDelayClass(delay: number) {
  if (delay < 50) return 'delay-good';
  if (delay < 100) return 'delay-warning';
  return 'delay-error';
}

function toggleDeviceSelection(deviceId: string | number) {
  const index = selectedDevices.value.indexOf(deviceId);
  if (index > -1) {
    selectedDevices.value.splice(index, 1);
  } else {
    selectedDevices.value.push(deviceId);
  }
}

const addButtonText = computed(() => {
  switch (activeTab.value) {
    case 'playback':
      return '添加播放设备';
    case 'api':
      return '添加测试API';
    default:
      return '添加测试设备';
  }
});

const stats = computed(() => {
  if (activeTab.value === 'playback') {
    return [
      { value: playbackDevices.value.filter(d => d && d.name).length, label: '总设备数', icon: 'fas fa-headphones', iconClass: 'device-icon' },
      { value: playbackDevices.value.filter(d => d && d.name && d.status === 'online').length, label: '在线设备', icon: 'fas fa-check-circle', iconClass: 'active-icon' },
      { value: playbackDevices.value.filter(d => d && d.name && d.status === 'offline').length, label: '离线设备', icon: 'fas fa-times-circle', iconClass: 'inactive-icon' },
      { value: playbackDevices.value.filter(d => d && d.name && d.status === 'testing').length, label: '测试中设备', icon: 'fas fa-play-circle', iconClass: 'test-icon' }
    ];
  } else if (activeTab.value === 'api') {
    return [
      { value: apiDevices.value.filter(d => d && d.name).length, label: '总测试API数', icon: 'fas fa-exchange-alt', iconClass: 'device-icon' },
      { value: apiDevices.value.filter(d => d && d.name && d.status === 'online').length, label: '可用API', icon: 'fas fa-check-circle', iconClass: 'active-icon' },
      { value: apiDevices.value.filter(d => d && d.name && d.status === 'offline').length, label: '不可用API', icon: 'fas fa-times-circle', iconClass: 'inactive-icon' },
      { value: apiDevices.value.filter(d => d && d.name && d.status === 'testing').length, label: '测试中API', icon: 'fas fa-play-circle', iconClass: 'test-icon' }
    ];
  } else {
    return [
      { value: testDevices.value.filter(d => d && d.name).length, label: '总测试设备数', icon: 'fas fa-microphone', iconClass: 'device-icon' },
      { value: testDevices.value.filter(d => d && d.name && d.status === 'online').length, label: '在线测试设备', icon: 'fas fa-check-circle', iconClass: 'active-icon' },
      { value: testDevices.value.filter(d => d && d.name && d.status === 'offline').length, label: '离线测试设备', icon: 'fas fa-times-circle', iconClass: 'inactive-icon' },
      { value: testDevices.value.filter(d => d && d.name && d.status === 'testing').length, label: '测试中设备', icon: 'fas fa-play-circle', iconClass: 'test-icon' }
    ];
  }
});

const allFilteredPlaybackDevices = computed(() => {
  return playbackDevices.value.filter(device => {
    if (!device) return false;
    const matchesSearch = !searchQuery.value || 
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) || 
      (device.model && device.model.toLowerCase().includes(searchQuery.value.toLowerCase()));
    
    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;
    
    const typeMapping: Record<string, string> = { '干声': 'dry', '噪声': 'noise' };
    const actualFilterType = playbackTypeFilter.value === 'all' ? 'all' : typeMapping[playbackTypeFilter.value] || playbackTypeFilter.value;
    const matchesPlaybackType = actualFilterType === 'all' || device.type === actualFilterType;

    return matchesSearch && matchesStatus && matchesPlaybackType;
  });
});

// 分页后的播放设备列表
const filteredPlaybackDevices = computed(() => {
  const start = (playbackCurrentPage.value - 1) * playbackPageSize.value;
  const end = start + playbackPageSize.value;
  return allFilteredPlaybackDevices.value.slice(start, end);
});

// 更新播放设备总数
watch(allFilteredPlaybackDevices, (newVal) => {
  playbackTotalItems.value = newVal.length;
  if (playbackCurrentPage.value > playbackTotalPages.value && playbackTotalPages.value > 0) {
    playbackCurrentPage.value = 1;
  }
}, { immediate: true });

const allFilteredTestDevices = computed(() => {
  return testDevices.value.filter(device => {
    if (!device) return false;
    const matchesSearch = !searchQuery.value || 
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) || 
      (device.model && device.model.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.category && device.category.toLowerCase().includes(searchQuery.value.toLowerCase()));
    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;
    const matchesAlgorithm = algorithmFilter.value === 'all' || 
      (device.supportedAlgorithms && device.supportedAlgorithms.includes(algorithmFilter.value));
    return matchesSearch && matchesStatus && matchesAlgorithm;
  });
});

// 分页后的测试设备列表
const filteredTestDevices = computed(() => {
  const start = (testCurrentPage.value - 1) * testPageSize.value;
  const end = start + testPageSize.value;
  return allFilteredTestDevices.value.slice(start, end);
});

// 更新测试设备总数
watch(allFilteredTestDevices, (newVal) => {
  testTotalItems.value = newVal.length;
  if (testCurrentPage.value > testTotalPages.value && testTotalPages.value > 0) {
    testCurrentPage.value = 1;
  }
}, { immediate: true });

const allFilteredAPIDevices = computed(() => {
  return apiDevices.value.filter(device => {
    if (!device) return false;
    const matchesSearch = !searchQuery.value || 
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) || 
      (device.model && device.model.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.category && device.category.toLowerCase().includes(searchQuery.value.toLowerCase()));
    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;
    const matchesAlgorithmType = algorithmTypeFilter.value === 'all' || 
      (device as any).algorithm_type === algorithmTypeFilter.value ||
      (device as any).algorithmType === algorithmTypeFilter.value;
    return matchesSearch && matchesStatus && matchesAlgorithmType;
  });
});

// 分页后的API设备列表
const filteredAPIDevices = computed(() => {
  const start = (apiCurrentPage.value - 1) * apiPageSize.value;
  const end = start + apiPageSize.value;
  return allFilteredAPIDevices.value.slice(start, end);
});

// 更新API设备总数
watch(allFilteredAPIDevices, (newVal) => {
  apiTotalItems.value = newVal.length;
  if (apiCurrentPage.value > apiTotalPages.value && apiTotalPages.value > 0) {
    apiCurrentPage.value = 1;
  }
}, { immediate: true });

// 分页方法
const handlePlaybackPageChange = (page: number) => {
  if (page >= 1 && page <= playbackTotalPages.value) {
    playbackCurrentPage.value = page;
  }
};

const handlePlaybackPageSizeChange = (size: number) => {
  playbackPageSize.value = size;
  playbackCurrentPage.value = 1;
};

const handlePlaybackPrevPage = () => {
  if (playbackCurrentPage.value > 1) {
    playbackCurrentPage.value--;
  }
};

const handlePlaybackNextPage = () => {
  if (playbackCurrentPage.value < playbackTotalPages.value) {
    playbackCurrentPage.value++;
  }
};

const handleTestPageChange = (page: number) => {
  if (page >= 1 && page <= testTotalPages.value) {
    testCurrentPage.value = page;
  }
};

const handleTestPageSizeChange = (size: number) => {
  testPageSize.value = size;
  testCurrentPage.value = 1;
};

const handleTestPrevPage = () => {
  if (testCurrentPage.value > 1) {
    testCurrentPage.value--;
  }
};

const handleTestNextPage = () => {
  if (testCurrentPage.value < testTotalPages.value) {
    testCurrentPage.value++;
  }
};

const handleAPIPageChange = (page: number) => {
  if (page >= 1 && page <= apiTotalPages.value) {
    apiCurrentPage.value = page;
  }
};

const handleAPIPageSizeChange = (size: number) => {
  apiPageSize.value = size;
  apiCurrentPage.value = 1;
};

const handleAPIPrevPage = () => {
  if (apiCurrentPage.value > 1) {
    apiCurrentPage.value--;
  }
};

const handleAPINextPage = () => {
  if (apiCurrentPage.value < apiTotalPages.value) {
    apiCurrentPage.value++;
  }
};

function resetAllStates() {
  activeTab.value = 'test';
  dropdowns.value = { batchDropdown: false, importExportDropdown: false };
  searchQuery.value = '';
  statusFilter.value = 'all';
  playbackTypeFilter.value = 'all';
  algorithmFilter.value = 'all';
  algorithmTypeFilter.value = 'all';
  selectedDevices.value = [];
  isScanning.value = false;
  scanProgress.value = 0;
  scanStatus.value = '准备扫描';
  scanResults.value = [];
}

async function loadAlgorithmTypeOptions() {
  try {
    const response = await fetch('/api/v1/algorithm/options');
    const result = await response.json();
    if (result.success && result.data && result.data.algorithms) {
      algorithmTypeOptions.value = result.data.algorithms.map((algo: any) => ({
        value: algo.value || algo.type,
        label: algo.name || algo.label || algo.value || algo.type
      }));
    }
  } catch (error) {
    console.error('加载算法类型选项失败:', error);
  }
}

function getAlgorithmTypeName(algorithmType: string): string {
  if (!algorithmType) return '';
  const option = algorithmTypeOptions.value.find(opt => opt.value === algorithmType);
  return option ? option.label : algorithmType;
}

export function useDevice() {
  // useDeviceManagement 已恢复完整能力：设备列表/弹窗/增删/扫描/健康轮询等。
  // 传入 fetchAllDevices 作为刷新回调，使增删改后同步合并设备列表。
  deviceManagement = useDeviceManagement('test', fetchAllDevices) as any;

  onMounted(() => {
    fetchAllDevices();
    loadAlgorithmTypeOptions();
    console.log('设备健康检查轮询已启动');
    deviceManagement.startHealthCheckPolling();
    document.addEventListener('click', handleClickOutsideEvent);
  });

  onUnmounted(() => {
    deviceManagement.stopHealthCheckPolling();
    if (statusUpdateTimer) {
      clearInterval(statusUpdateTimer);
    }

    document.removeEventListener('click', handleClickOutsideEvent);
  });
  
  function handleClickOutsideEvent(event: MouseEvent) {
    const target = event.target as HTMLElement;
    if (!target.closest('.dropdown-container')) {
      dropdowns.value.batchDropdown = false;
      dropdowns.value.importExportDropdown = false;
    }
  }

  return {
    tabs,
    activeTab,
    dropdowns,
    searchQuery,
    statusFilter,
    playbackTypeFilter,
    algorithmFilter,
    algorithmTypeFilter,
    algorithmTypeOptions,
    getAlgorithmTypeName,
    deviceStatusText,
    playbackDevices,
    testDevices,
    apiDevices,
    selectedDevices,
    addButtonText,
    stats,
    filteredPlaybackDevices,
    filteredTestDevices,
    filteredAPIDevices,
    switchDeviceType,
    toggleDropdown,
    handleAddDevice,
    searchDevices,
    filterDevices,
    showDeviceDetails,
    getDelayClass,
    toggleDeviceSelection,
    resetAllStates,
    loading,
    error,
    isHealthChecking,
    isScanning,
    scanProgress,
    scanStatus,
    scanResults,
    fetchAllDevices,
    openEditModal,
    deleteDevice,
    testDevice,
    stopTest,
    healthCheckDevice,
    batchEnableDevices,
    batchDisableDevices,
    batchDeleteDevices,
    batchHealthCheck,
    importDevices,
    exportDevices,
    scanDevices,
    startScanDevices,
    availableSerials,
    
    // 播放设备分页
    playbackCurrentPage,
    playbackPageSize,
    playbackTotalItems,
    playbackTotalPages,
    handlePlaybackPageChange,
    handlePlaybackPageSizeChange,
    handlePlaybackPrevPage,
    handlePlaybackNextPage,
    
    // 测试设备分页
    testCurrentPage,
    testPageSize,
    testTotalItems,
    testTotalPages,
    handleTestPageChange,
    handleTestPageSizeChange,
    handleTestPrevPage,
    handleTestNextPage,
    
    // API设备分页
    apiCurrentPage,
    apiPageSize,
    apiTotalItems,
    apiTotalPages,
    handleAPIPageChange,
    handleAPIPageSizeChange,
    handleAPIPrevPage,
    handleAPINextPage
  };
}


