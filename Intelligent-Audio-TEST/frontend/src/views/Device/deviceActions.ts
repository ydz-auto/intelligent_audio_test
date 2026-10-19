import { devicesPort } from '../../composables/device/devicesPort';
import { playbackPort } from '../../composables/device/playbackPort';
import { apisPort } from '../../composables/apiTest/apisPort';
import { algorithmPort } from '../../composables/algorithm/algorithmPort';
import { MODAL_TYPES } from '../../composables/modal/constants';
import { DeviceStatus, DeviceTabType } from '../../domain/enums';
import type { DeviceTabTypeType } from '../../domain/enums';
import type { DeviceUnion } from '@/domain';
import type { DeviceBatchActionType } from '../../domain/model/device';
import {
  activeTab,
  dropdowns,
  groupManagerVisible,
  searchQuery,
  statusFilter,
  playbackTypeFilter,
  algorithmTypeFilter,
  algorithmFilter,
  laboratoryFilter,
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
import { useNotification } from '../../composables/modal/useNotification';

const notification = useNotification();

export function switchDeviceType(type: DeviceTabTypeType) {
  activeTab.value = type;
  const deviceManagement = getDeviceManagement()!;
  if (deviceManagement.activeDeviceType) {
    deviceManagement.activeDeviceType.value = type;
  }
  statusFilter.value = 'all';
  playbackTypeFilter.value = 'all';
  algorithmTypeFilter.value = 'all';
  laboratoryFilter.value = 'all';
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

export async function openEditModal(deviceId: string | number) {
  await getDeviceManagement()!.editDevice(deviceId, activeTab.value);
}

export async function deleteDevice(deviceId: string | number) {
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

/** 批量操作通用入口（INT-80：走 /test-devices/batch 幂等批量端点） */
async function runDeviceBatchAction(action: DeviceBatchActionType, title: string, params?: Record<string, unknown>) {
  if (selectedDevices.value.length === 0) {
    notification.warning('请先选择要操作的设备');
    return;
  }
  const ids = [...selectedDevices.value];
  getDeviceManagement()!.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: `确认${title}`,
    message: `确定要对选中的 ${ids.length} 个设备执行「${title}」吗？`,
    confirmText: '确认执行',
    cancelText: '取消',
    options: { closable: true },
    onConfirm: async () => {
      try {
        const result = await devicesPort.batchAction(action, ids, params);
        notification.success(result.idempotentReplay
          ? `${title}：命中幂等回放，未重复执行`
          : `${title}完成：成功 ${result.successCount ?? 0}/${result.total ?? ids.length}`);
        selectedDevices.value = [];
        await fetchAllDevices();
      } catch (error) {
        console.error(`${title}失败:`, error);
        notification.error(`${title}失败: ` + (error instanceof Error ? error.message : '未知错误'));
      }
    }
  });
}

export function batchEnableDevices() {
  // 批量启用 → 批量连接（INT-80 批量操作端点；原 console.log 占位实现替换）
  runDeviceBatchAction('connect', '批量连接');
}

export function batchDisableDevices() {
  // 批量禁用 → 批量断开（INT-80 批量操作端点）
  runDeviceBatchAction('disconnect', '批量断开');
}

export function batchRebootDevices() {
  runDeviceBatchAction('reboot', '批量重启');
}

/** 设备分组管理弹窗开关（INT-80） */
export function openGroupManager() {
  groupManagerVisible.value = true;
}

/** 设备卡操作菜单：单设备操作（INT-80 设备操作端点） */
export async function handleDeviceOperate(deviceId: string | number, operation: string) {
  const opLabels: Record<string, string> = {
    connect: '连接设备', disconnect: '断开连接', reboot: '重启设备',
    shutdown: '关闭设备', install_app: '安装应用', uninstall_app: '卸载应用',
  };
  const label = opLabels[operation] || operation;

  // INT-286：装卸应用参数改 INPUT_CONFIRM 表单模态收集（原 window.prompt 无校验、不可样式化），
  // 表单确认按钮即操作确认，不再二次弹 BASIC_CONFIRM
  let params: Record<string, unknown> | undefined;
  if (operation === 'install_app') {
    const filePath = await promptOperationValue({
      title: '安装应用',
      label: '服务器侧安装包路径（APK/HAP）',
      placeholder: '例如：/opt/packages/demo.apk',
      confirmText: '确认安装',
      validate: (v) => (/\s/.test(v) ? '路径不能包含空白字符' : null),
    });
    if (filePath == null) return;
    params = { file_path: filePath };
  } else if (operation === 'uninstall_app') {
    const pkg = await promptOperationValue({
      title: '卸载应用',
      label: '要卸载的应用包名',
      placeholder: '例如：com.example.app',
      confirmText: '确认卸载',
      danger: true,
      validate: (v) => (/\s/.test(v) ? '包名不能包含空白字符' : null),
    });
    if (pkg == null) return;
    params = { package_name: pkg };
  } else {
    const confirmed = await new Promise<boolean>((resolve) => {
      getDeviceManagement()!.modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: `确认${label}`,
        message: `确定要对设备执行「${label}」吗？`,
        confirmText: '确认执行',
        cancelText: '取消',
        options: { closable: true },
        onConfirm: () => resolve(true),
        onCancel: () => resolve(false),
        onClose: () => resolve(false),
      });
    });
    if (!confirmed) return;
  }

  try {
    await devicesPort.control(deviceId, operation as DeviceBatchActionType, params);
    notification.success(`${label}指令已下发`);
    await fetchAllDevices();
  } catch (error) {
    console.error(`${label}失败:`, error);
    notification.error(`${label}失败: ` + (error instanceof Error ? error.message : '未知错误'));
  }
}

/** INT-286：INPUT_CONFIRM 表单模态通用封装；用户取消返回 null，确认返回 trim 后的值 */
async function promptOperationValue(config: {
  title: string;
  label: string;
  placeholder?: string;
  confirmText?: string;
  danger?: boolean;
  validate?: (value: string) => string | null;
}): Promise<string | null> {
  try {
    const result = await getDeviceManagement()!.modalManager.open(MODAL_TYPES.INPUT_CONFIRM, config);
    const value = String(result?.value ?? '').trim();
    return value || null; // 空值视同取消（INPUT_CONFIRM 的 required 校验兜底）
  } catch {
    return null; // 用户取消
  }
}

export async function batchDeleteDevices() {
  getDeviceManagement()!.batchDeleteDevices(selectedDevices.value, activeTab.value);
}

export async function batchHealthCheck() {
  if (selectedDevices.value.length === 0) {
    notification.warning('请先选择要检查的设备');
    return;
  }

  // 单设备失败不中断循环：累计失败数，结束后一并提示
  let failedCount = 0;

  try {
    // PLAYBACK Tab：checkStatus() 为全量查询，循环内对 N 台设备重复调用 N 次×全量是浪费——
    // 先查一次并统一回写状态（INT-293）
    if (activeTab.value === DeviceTabType.PLAYBACK) {
      const result = await playbackPort.checkStatus() as { id: string | number; status: string }[];
      if (result && Array.isArray(result)) {
        result.forEach(item => {
          const playbackDeviceIndex = playbackDevices.value.findIndex(d => d.id === item.id);
          if (playbackDeviceIndex > -1) {
            playbackDevices.value[playbackDeviceIndex].status = item.status as any;
          }
        });
      }
    }

    for (const deviceId of selectedDevices.value) {
      if (activeTab.value === DeviceTabType.PLAYBACK) {
        continue; // 播放设备状态已在上方全量回写
      }

      let deviceList: DeviceUnion[] = [];
      if (activeTab.value === DeviceTabType.TEST) {
        deviceList = testDevices.value;
      } else if (activeTab.value === DeviceTabType.API) {
        deviceList = apiDevices.value;
      } else {
        continue;
      }

      const deviceIndex = deviceList.findIndex(d => d.id === deviceId);
      if (deviceIndex > -1) {
        deviceList[deviceIndex].status = DeviceStatus.TESTING;
      }

      try {
        if (activeTab.value === DeviceTabType.TEST) {
          await devicesPort.healthCheck([deviceId]);
        } else if (activeTab.value === DeviceTabType.API) {
          await apisPort.testConnection(deviceId as string | number);
        }
      } catch {
        // 单设备失败仅计数，不中断剩余设备的检查（INT-293）
        failedCount += 1;
        if (deviceIndex > -1) {
          deviceList[deviceIndex].status = DeviceStatus.OFFLINE;
        }
      }
    }

    selectedDevices.value = [];
    if (failedCount > 0) {
      notification.warning(`批量健康检查完成，${failedCount} 台设备检查失败`);
    }
  } catch (error) {
    console.error('批量健康检查失败:', error);
    const errorMessage = error instanceof Error ? error.message : '未知错误';
    notification.error('批量健康检查失败: ' + errorMessage);
  }
}

export function importDevices() {
  getDeviceManagement()!.importDevices(activeTab.value);
}

export function exportDevices() {
  getDeviceManagement()!.exportDevices(activeTab.value);
}

export async function testDevice(deviceId: string | number) {
  let deviceList: DeviceUnion[] = [];
  if (activeTab.value === DeviceTabType.TEST) {
    deviceList = testDevices.value;
  } else if (activeTab.value === DeviceTabType.PLAYBACK) {
    deviceList = playbackDevices.value;
  } else if (activeTab.value === DeviceTabType.API) {
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
        deviceList[deviceIndex].status = DeviceStatus.TESTING;
      }
      await getDeviceManagement()!.testDeviceConnection(deviceId, activeTab.value);
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
        if (activeTab.value === DeviceTabType.PLAYBACK) {
          deviceList = playbackDevices.value;
        } else if (activeTab.value === DeviceTabType.TEST) {
          deviceList = testDevices.value;
        } else if (activeTab.value === DeviceTabType.API) {
          deviceList = apiDevices.value;
        } else {
          return;
        }

        const deviceIndex = deviceList.findIndex(d => d.id === deviceId);
        if (deviceIndex > -1) {
          deviceList[deviceIndex].status = DeviceStatus.ONLINE;
        }

        if (activeTab.value === DeviceTabType.PLAYBACK) {
          await (playbackPort as any).stopTest(deviceId);
        } else if (activeTab.value === DeviceTabType.TEST) {
          await (devicesPort as any).stopTest(deviceId);
        } else if (activeTab.value === DeviceTabType.API) {
          await (apisPort as any).stopTest(deviceId);
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
    if (activeTab.value === DeviceTabType.TEST) {
      deviceList = testDevices.value;
    } else if (activeTab.value === DeviceTabType.PLAYBACK) {
      deviceList = playbackDevices.value;
    } else if (activeTab.value === DeviceTabType.API) {
      deviceList = apiDevices.value;
    }

    deviceIndex = deviceList.findIndex(d => d.id === deviceId);

    if (deviceIndex > -1) {
      deviceList[deviceIndex].status = DeviceStatus.TESTING;
    }

    if (activeTab.value === DeviceTabType.TEST) {
      const healthCheckResult = await devicesPort.healthCheck([deviceId]) as { id: string | number; status: string }[];
      if (healthCheckResult && Array.isArray(healthCheckResult)) {
        healthCheckResult.forEach(item => {
          const testDeviceIndex = testDevices.value.findIndex(d => d.id === item.id);
          if (testDeviceIndex > -1) {
            testDevices.value[testDeviceIndex].status = item.status as any;
          }
        });
      }
    } else if (activeTab.value === DeviceTabType.PLAYBACK) {
      const healthCheckResult = await playbackPort.checkStatus() as { id: string | number; status: string }[];
      if (healthCheckResult && Array.isArray(healthCheckResult)) {
        healthCheckResult.forEach(item => {
          const playbackDeviceIndex = playbackDevices.value.findIndex(d => d.id === item.id);
          if (playbackDeviceIndex > -1) {
            playbackDevices.value[playbackDeviceIndex].status = item.status as any;
          }
        });
      }
    } else if (activeTab.value === DeviceTabType.API) {
      const healthCheckResult = await apisPort.testConnection(deviceId as string | number);
      if (healthCheckResult) {
        const apiDeviceIndex = apiDevices.value.findIndex(d => d.id === deviceId);
        if (apiDeviceIndex > -1) {
          apiDevices.value[apiDeviceIndex].status = DeviceStatus.ONLINE;
        }
      }
    }

    await fetchAllDevices();
  } catch (error) {
    console.error('健康检查失败:', error);
    if (deviceList && deviceIndex > -1) {
      deviceList[deviceIndex].status = DeviceStatus.OFFLINE;
    }
  }
}

export function scanDevices(type?: string) {
  const targetType = (type || activeTab.value) as DeviceTabTypeType;
  getDeviceManagement()!.scanDevices(targetType);
}

export function startScanDevices() {
  scanDevices();
}

export function getDelayClass(delay?: number) {
  // delay 缺省（undefined < 50 为 false）时与原行为一致：返回 delay-error
  const d = delay ?? NaN;
  if (d < 50) return 'delay-good';
  if (d < 100) return 'delay-warning';
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
  activeTab.value = DeviceTabType.TEST;
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
    // 走 algorithmPort.getOptions（client unwrap 后返回 { algorithms: [...] }）
    const result = await algorithmPort.getOptions();
    if (result?.algorithms) {
      algorithmTypeOptions.value = result.algorithms.map((algo: any) => ({
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
