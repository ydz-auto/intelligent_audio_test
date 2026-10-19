import { onMounted, onUnmounted } from 'vue';
import { useDeviceManagement } from '../../composables/device/useDeviceManagement';

import { DEVICE_STATUS_TEXT } from '@/domain/constants/deviceLabels';
import { DeviceTabType } from '@/domain/enums';
import type { DeviceTabTypeType } from '@/domain/enums';

// 设备管理页 Tab 配置（组件级 UI 常量，页签类型走 DeviceTabType 枚举）
const tabs: { type: DeviceTabTypeType; label: string; icon: string }[] = [
  { type: DeviceTabType.TEST, label: '测试设备管理', icon: 'fas fa-microphone' },
  { type: DeviceTabType.API, label: '测试API管理', icon: 'fas fa-exchange-alt' },
  { type: DeviceTabType.PLAYBACK, label: '播放设备管理', icon: 'fas fa-headphones' }
];

import {
  activeTab,
  dropdowns,
  groupManagerVisible,
  searchQuery,
  statusFilter,
  playbackTypeFilter,
  algorithmFilter,
  algorithmTypeFilter,
  algorithmTypeOptions,
  laboratoryFilter,
  laboratories,
  playbackDevices,
  testDevices,
  apiDevices,
  selectedDevices,
  availableSerials,
  loading,
  error,
  isHealthChecking,
  isScanning,
  scanProgress,
  scanStatus,
  scanResults,
  playbackCurrentPage,
  playbackPageSize,
  playbackTotalItems,
  playbackTotalPages,
  testCurrentPage,
  testPageSize,
  testTotalItems,
  testTotalPages,
  apiCurrentPage,
  apiPageSize,
  apiTotalItems,
  apiTotalPages,
  setDeviceManagement,
  getDeviceManagement,
  getStatusUpdateTimer
} from './deviceState';

import { fetchAllDevices, loadLaboratories } from './deviceFetching';
import {
  switchDeviceType,
  toggleDropdown,
  handleAddDevice,
  searchDevices,
  filterDevices,
  showDeviceDetails,
  getDelayClass,
  toggleDeviceSelection,
  resetAllStates,
  openEditModal,
  deleteDevice,
  testDevice,
  stopTest,
  healthCheckDevice,
  batchEnableDevices,
  batchDisableDevices,
  batchRebootDevices,
  batchDeleteDevices,
  batchHealthCheck,
  importDevices,
  exportDevices,
  scanDevices,
  startScanDevices,
  loadAlgorithmTypeOptions,
  getAlgorithmTypeName,
  openGroupManager,
  handleDeviceOperate
} from './deviceActions';
import {
  addButtonText,
  stats,
  filteredPlaybackDevices,
  filteredTestDevices,
  filteredAPIDevices
} from './deviceComputed';
import {
  handlePlaybackPageChange,
  handlePlaybackPageSizeChange,
  handlePlaybackPrevPage,
  handlePlaybackNextPage,
  handleTestPageChange,
  handleTestPageSizeChange,
  handleTestPrevPage,
  handleTestNextPage,
  handleAPIPageChange,
  handleAPIPageSizeChange,
  handleAPIPrevPage,
  handleAPINextPage
} from './devicePagination';

export function useDevice() {
  // useDeviceManagement 已恢复完整能力：设备列表/弹窗/增删/扫描/健康轮询等。
  // 传入 fetchAllDevices 作为刷新回调，使增删改后同步合并设备列表。
  setDeviceManagement(useDeviceManagement(DeviceTabType.TEST, fetchAllDevices) as any);

  onMounted(() => {
    fetchAllDevices();
    loadLaboratories();
    loadAlgorithmTypeOptions();
    console.log('设备健康检查轮询已启动');
    getDeviceManagement()!.startHealthCheckPolling();
    document.addEventListener('click', handleClickOutsideEvent);
  });

  onUnmounted(() => {
    getDeviceManagement()!.stopHealthCheckPolling();
    const statusUpdateTimer = getStatusUpdateTimer();
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

  /** 实验室徽章筛选选中（INT-655：BadgeFilter value 为 labId 字符串，'all' = 全部） */
  function setLaboratoryFilter(value: string | number) {
    laboratoryFilter.value = String(value);
  }

  return {
    tabs,
    activeTab,
    dropdowns,
    groupManagerVisible,
    searchQuery,
    statusFilter,
    playbackTypeFilter,
    algorithmFilter,
    algorithmTypeFilter,
    algorithmTypeOptions,
    getAlgorithmTypeName,
    laboratoryFilter,
    laboratories,
    setLaboratoryFilter,
    deviceStatusText: DEVICE_STATUS_TEXT,
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
    batchRebootDevices,
    batchDeleteDevices,
    batchHealthCheck,
    importDevices,
    exportDevices,
    scanDevices,
    startScanDevices,
    availableSerials,
    openGroupManager,
    handleDeviceOperate,

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
