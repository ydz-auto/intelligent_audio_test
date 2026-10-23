import { ref, computed } from 'vue';
import { useModalControl } from '../../composables/modal/useModal';
import type { PlaybackDevice, Audio, Laboratory } from '../../domain';
import type { TestDeviceView, ApiDeviceView, DeviceUnion } from '@/domain';
// 引入视图模式/页签枚举，消除魔法字符串
import { ViewMode, DeviceTabType } from '@/domain/enums';
import type { DeviceTabTypeType } from '@/domain/enums';

export const activeTab = ref<DeviceTabTypeType>(DeviceTabType.TEST);
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
// INT-80 设备分组管理弹窗
export const groupManagerVisible = ref(false);
export const searchQuery = ref('');
export const statusFilter = ref(ViewMode.ALL);
export const playbackTypeFilter = ref(ViewMode.ALL);
export const algorithmFilter = ref(ViewMode.ALL);
export const algorithmTypeFilter = ref(ViewMode.ALL);
/** 实验室筛选（INT-655：测试/播放设备页签按所属实验室过滤；值为 labId 字符串，ALL=全部） */
export const laboratoryFilter = ref<string | number>(ViewMode.ALL);
export const laboratories = ref<Laboratory[]>([]);
export const selectedDevices = ref<(string | number)[]>([]);
export const playbackDevices = ref<PlaybackDevice[]>([]);
export const testDevices = ref<TestDeviceView[]>([]);
export const apiDevices = ref<ApiDeviceView[]>([]);

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
  activeDeviceType: ReturnType<typeof ref<DeviceTabTypeType>>;
  modalManager: ReturnType<typeof useModalControl>;
  addDevice: (type?: string, initialData?: any) => void;
  editDevice: (id: number | string, type?: string) => Promise<void>;
  deleteDevice: (id: number | string, type?: string) => Promise<void>;
  batchDeleteDevices: (ids: (number | string)[], type?: string) => Promise<void>;
  importDevices: (type?: string) => Promise<void> | void;
  exportDevices: (type?: string, scope?: { selectedIds?: (string | number)[]; filteredIds?: (string | number)[] }) => Promise<void> | void;
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
