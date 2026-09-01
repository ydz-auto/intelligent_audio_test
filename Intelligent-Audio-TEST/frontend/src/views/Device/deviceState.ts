import { ref, computed } from 'vue';
import { useModalControl } from '../../composables/modal/useModal';
import type { PlaybackDevice, Audio } from '../../shared/types';
import type { TestDevice, APIDevice, DeviceUnion } from './deviceTypes';
// 引入视图模式枚举，消除魔法字符串
import { ViewMode } from '@/shared/types/enums';

export const activeTab = ref('test');
export const loading = ref(false);
export const isHealthChecking = ref(false);
export const error = ref<string | null>(null);
export const isScanning = ref(false);
export const scanProgress = ref(0);
export const scanStatus = ref('准备扫描');
export const scanResults = ref<any[]>([]);
export const dropdowns = ref({
  batchDropdown: false,
  importExportDropdown: false
});
export const searchQuery = ref('');
export const statusFilter = ref(ViewMode.ALL);
export const playbackTypeFilter = ref(ViewMode.ALL);
export const algorithmFilter = ref(ViewMode.ALL);
export const algorithmTypeFilter = ref(ViewMode.ALL);
export const selectedDevices = ref<(string | number)[]>([]);
export const playbackDevices = ref<PlaybackDevice[]>([]);
export const testDevices = ref<TestDevice[]>([]);
export const apiDevices = ref<APIDevice[]>([]);

export const promptAudios = ref<Audio[]>([]);
export const availableSerials = ref<string[]>([]);
export const algorithmTypeOptions = ref<{ value: string; label: string }[]>([]);

export const playbackCurrentPage = ref(1);
export const playbackPageSize = ref(6);
export const playbackTotalItems = ref(0);
export const playbackTotalPages = computed(() => Math.ceil(playbackTotalItems.value / playbackPageSize.value));

export const testCurrentPage = ref(1);
export const testPageSize = ref(12);
export const testTotalItems = ref(0);
export const testTotalPages = computed(() => Math.ceil(testTotalItems.value / testPageSize.value));

export const apiCurrentPage = ref(1);
export const apiPageSize = ref(12);
export const apiTotalItems = ref(0);
export const apiTotalPages = computed(() => Math.ceil(apiTotalItems.value / apiPageSize.value));

export type DeviceManagementType = {
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

const moduleLevelState: {
  statusUpdateTimer: ReturnType<typeof setInterval> | null;
  deviceManagement: DeviceManagementType;
} = {
  statusUpdateTimer: null,
  deviceManagement: undefined
};

export function getDeviceManagement(): DeviceManagementType {
  return moduleLevelState.deviceManagement;
}

export function setDeviceManagement(dm: DeviceManagementType) {
  moduleLevelState.deviceManagement = dm;
}

export function getStatusUpdateTimer(): ReturnType<typeof setInterval> | null {
  return moduleLevelState.statusUpdateTimer;
}

export function setStatusUpdateTimer(timer: ReturnType<typeof setInterval> | null) {
  moduleLevelState.statusUpdateTimer = timer;
}
