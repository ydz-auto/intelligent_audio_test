import { devicesApi, playbackApi, apisApi } from '../../utils/api';
import { MODAL_TYPES } from '../../shared/types';
import type { DeviceUnion } from './deviceTypes';
import {
  activeTab,
  dropdowns,
  searchQuery,
  statusFilter,
  playbackTypeFilter,
  algorithmTypeFilter,
  algorithmFilter,
  selectedDevices,
  testDevices,
  playbackDevices,
  apiDevices,
  isScanning,
  scanProgress,
  scanStatus,
  scanResults,
  algorithmTypeOptions,
  getDeviceManagement
} from './deviceState';
import { fetchAllDevices } from './deviceFetching';

export function switchDeviceType(type: string) {
  activeTab.value = type;
  const deviceManagement = getDeviceManagement()!;
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

export function toggleDropdown(dropdownName: 'batchDropdown' | 'importExportDropdown') {
  dropdowns.value[dropdownName] = !dropdowns.value[dropdownName];
}

export async function handleAddDevice() {
  getDeviceManagement()!.addDevice(activeTab.value);
}

export async function openEditModal(deviceId: string) {
  await getDeviceManagement()!.editDevice(deviceId, activeTab.value);
}

export async function deleteDevice(deviceId: string) {
  getDeviceManagement()!.deleteDevice(deviceId, activeTab.value);
}

export function searchDevices() {
  // 搜索功能已通过计算属性实现
}

export function filterDevices() {
  // 过滤功能已通过计算属性实现
}

export function showDeviceDetails(deviceId: string) {
  getDeviceManagement()!.modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
    title: '设备详情',
    deviceId: deviceId,
    options: { closable: true, width: '800px' }
  });
}

export function batchEnableDevices() {
  getDeviceManagement()!.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
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

export function batchDisableDevices() {
  getDeviceManagement()!.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
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

export async function batchDeleteDevices() {
  getDeviceManagement()!.batchDeleteDevices(selectedDevices.value, activeTab.value);
}

export async function batchHealthCheck() {
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

export function importDevices() {
  getDeviceManagement()!.importDevices(activeTab.value as 'test' | 'playback' | 'api');
}

export function exportDevices() {
  getDeviceManagement()!.exportDevices(activeTab.value as 'test' | 'playback' | 'api');
}

export async function testDevice(deviceId: string | number) {
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
    getDeviceManagement()!.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
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
      await getDeviceManagement()!.testDeviceConnection(deviceId, activeTab.value as 'test' | 'playback' | 'api');
    } catch (error) {
      console.error('测试设备失败:', error);
      if (deviceIndex > -1 && originalStatus) {
        deviceList[deviceIndex].status = originalStatus;
      }
    }
  }
}

export async function stopTest(deviceId: string | number) {
  getDeviceManagement()!.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
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

export async function healthCheckDevice(deviceId: string | number) {
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

export function scanDevices(type?: string) {
  const targetType = (type || activeTab.value) as 'test' | 'playback' | 'api';
  getDeviceManagement()!.scanDevices(targetType);
}

export function startScanDevices() {
  scanDevices();
}

export function getDelayClass(delay: number) {
  if (delay < 50) return 'delay-good';
  if (delay < 100) return 'delay-warning';
  return 'delay-error';
}

export function toggleDeviceSelection(deviceId: string | number) {
  const index = selectedDevices.value.indexOf(deviceId);
  if (index > -1) {
    selectedDevices.value.splice(index, 1);
  } else {
    selectedDevices.value.push(deviceId);
  }
}

export function resetAllStates() {
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

export async function loadAlgorithmTypeOptions() {
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

export function getAlgorithmTypeName(algorithmType: string): string {
  if (!algorithmType) return '';
  const option = algorithmTypeOptions.value.find(opt => opt.value === algorithmType);
  return option ? option.label : algorithmType;
}
