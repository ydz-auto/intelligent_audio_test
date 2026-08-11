import { onMounted, onUnmounted } from 'vue';
import { useDeviceManagement } from '../../composables/device/useDeviceManagement';

// Re-export types and shared constants for consumers of useDevice
export type { TestDevice, APIDevice, DeviceUnion } from './deviceTypes';
import { tabs, deviceStatusText } from './deviceTypes';

import {
  activeTab,
  dropdowns,
  searchQuery,
  statusFilter,
  playbackTypeFilter,
  algorithmFilter,
  algorithmTypeFilter,
  algorithmTypeOptions,
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

import { fetchAllDevices } from './deviceFetching';
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
  batchDeleteDevices,
  batchHealthCheck,
  importDevices,
  exportDevices,
  scanDevices,
  startScanDevices,
  loadAlgorithmTypeOptions,
  getAlgorithmTypeName
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
  setDeviceManagement(useDeviceManagement('test', fetchAllDevices) as any);

  onMounted(() => {
    fetchAllDevices();
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
