import { ref, type Ref } from 'vue';
import { getModalManager } from '../../utils/modalManager';
import { MODAL_TYPES } from '../../shared/types';
import type { AudioUploadOptions } from '../../shared/types';
import type { useDeviceManagement } from '../device/useDeviceManagement';
import type { useAlgorithmParams } from '../algorithm/useAlgorithmParams';
import type { useAudioUpload } from '../audio/useAudioUpload';
// 引入测试类型枚举，消除魔法字符串
import { TestType } from '@/shared/types/enums';

interface DeviceApi {
  playbackDevices: Ref<ReturnType<typeof useDeviceManagement>['playbackDevices']['value']>;
  deviceList: Ref<ReturnType<typeof useDeviceManagement>['deviceList']['value']>;
  fetchPlaybackDevices: () => Promise<void>;
  fetchDevices: () => Promise<void>;
}

interface AlgorithmApi {
  algorithmOptions: Ref<ReturnType<typeof useAlgorithmParams>['algorithmOptions']['value']>;
  fetchAlgorithmOptions: () => Promise<void>;
}

interface UploadApi {
  uploadOptions: ReturnType<typeof useAudioUpload>['uploadOptions'];
  updateUploadOptionsFromModal: (data: any) => void;
  startUploadProcess: (
    files: any[],
    folderGroupMappings?: Record<string, string>,
    unifiedRoundsByGroup?: Record<string, any>,
    testCaseGroupsData?: Record<string, any>,
    onUploadComplete?: () => void
  ) => Promise<void>;
  selectedFilesForUpload: Ref<File[]>;
}

/**
 * 上传模态框管理组合式函数
 *
 * 职责：
 * - 打开上传音频模态框
 * - 打开文件夹批量导入模态框
 * - 构建模态框配置项
 * - 处理模态框确认回调
 */
export function useUploadModal(
  deviceApi: DeviceApi,
  algorithmApi: AlgorithmApi,
  uploadApi: UploadApi,
  onUploadComplete: () => void
) {
  const modalManager = getModalManager();
  let isOpeningUploadModal = false;
  let isOpeningFolderImport = false;

  /**
   * 打开上传音频模态框
   */
  async function openUploadModal() {
    if (isOpeningUploadModal) return;
    isOpeningUploadModal = true;
    try {
      await deviceApi.fetchPlaybackDevices();
      await algorithmApi.fetchAlgorithmOptions();
      await deviceApi.fetchDevices();

      modalManager.open(MODAL_TYPES.AUDIO_IMPORT, {
        title: '上传音频',
        deviceOptions: deviceApi.deviceList.value,
        algorithmOptions: algorithmApi.algorithmOptions.value,
        uploadOptions: buildUploadOptionsConfig(uploadApi.uploadOptions, deviceApi, algorithmApi),
        supportedFormats: ['wav', 'mp3', 'm4a', 'flac'],
        acceptedFileTypes: '.wav,.mp3,.m4a,.flac',
        maxFileSize: 100 * 1024 * 1024,
        multiple: true,
        onConfirm: async (data: any) => {
          if (data.files && data.files.length > 0) {
            uploadApi.updateUploadOptionsFromModal(data);
            uploadApi.selectedFilesForUpload.value = data.files;
            await uploadApi.startUploadProcess(data.files, data.folderGroupMappings, data.unifiedRoundsByGroup, data.testCaseGroups, onUploadComplete);
          }
        }
      });
    } finally {
      isOpeningUploadModal = false;
    }
  }

  /**
   * 打开文件夹批量导入模态框
   */
  async function batchImportFromFolder() {
    if (isOpeningFolderImport) return;
    isOpeningFolderImport = true;
    try {
      await deviceApi.fetchPlaybackDevices();
      await algorithmApi.fetchAlgorithmOptions();

      modalManager.open(MODAL_TYPES.FOLDER_IMPORT, {
        title: '批量从文件夹导入',
        uploadOptions: buildFolderImportOptionsConfig(uploadApi.uploadOptions, deviceApi, algorithmApi),
        supportedFormats: ['wav', 'mp3', 'm4a', 'flac'],
        onConfirm: async (data: any) => {
          if (data.files && data.files.length > 0) {
            uploadApi.updateUploadOptionsFromModal(data);
            uploadApi.selectedFilesForUpload.value = data.files;
            await uploadApi.startUploadProcess(data.files, data.folderGroupMappings, data.unifiedRoundsByGroup, data.testCaseGroups, onUploadComplete);
          }
        }
      });
    } finally {
      isOpeningFolderImport = false;
    }
  }

  return {
    openUploadModal,
    batchImportFromFolder,
  };
}

/**
 * 构建上传音频模态框的配置项
 */
function buildUploadOptionsConfig(
  uploadOptions: AudioUploadOptions,
  deviceApi: DeviceApi,
  algorithmApi: AlgorithmApi
): any[] {
  return [
    {
      key: 'audioType',
      label: '音频类型',
      type: 'radio',
      options: [
        { label: '干声', value: 'dry' },
        { label: '噪声', value: 'noise' },
        { label: '提示词', value: 'prompt' },
        { label: '混合', value: 'mixed' }
      ],
      defaultValue: uploadOptions.audio_type
    },
    {
      key: 'createTestCase',
      label: '生成测试用例',
      type: 'boolean',
      defaultValue: uploadOptions.create_test_case
    },
    {
      key: 'algorithmType',
      label: '算法类型',
      type: 'select',
      options: [
        { label: '请选择算法', value: '' },
        ...(Array.isArray(algorithmApi.algorithmOptions.value) ? algorithmApi.algorithmOptions.value : []).map(a => ({ label: a.name, value: a.value }))
      ],
      defaultValue: uploadOptions.algorithm_type
    },
    {
      key: 'testTypes',
      label: '测试类型',
      type: 'checkbox',
      options: [
        { label: 'E2E测试', value: TestType.E2E },
        { label: 'API测试', value: TestType.API }
      ],
      defaultValue: uploadOptions.test_types
    },
    {
      key: 'dimensions',
      label: '评估维度',
      type: 'dimensions',
      defaultValue: uploadOptions.dimensions
    },
    {
      key: 'playbackDeviceId',
      label: '播放设备',
      type: 'select',
      options: (Array.isArray(deviceApi.playbackDevices.value) ? deviceApi.playbackDevices.value : []).map(d => ({ label: d.name, value: d.id })),
      defaultValue: uploadOptions.playback_device_id
    },
    {
      key: 'defaultSpl',
      label: '默认声压级(SPL)',
      type: 'number',
      min: 30,
      max: 120,
      step: 0.1,
      defaultValue: uploadOptions.spl
    },
    {
      key: 'groupNameType',
      label: '用例分组',
      type: 'radio',
      options: [
        { label: '根目录', value: 'root' },
        { label: '文件夹名', value: 'folder' },
        { label: '自定义', value: 'custom' }
      ],
      defaultValue: uploadOptions.group_name_type
    },
    {
      key: 'customGroupName',
      label: '自定义分组名称',
      type: 'text',
      placeholder: '请输入分组名称',
      defaultValue: uploadOptions.custom_group_name
    },
    {
      key: 'inheritTags',
      label: '继承音频标签',
      type: 'boolean',
      defaultValue: uploadOptions.inherit_tags
    }
  ];
}

/**
 * 构建文件夹导入模态框的配置项
 */
function buildFolderImportOptionsConfig(
  uploadOptions: AudioUploadOptions,
  deviceApi: DeviceApi,
  algorithmApi: AlgorithmApi
): any[] {
  return [
    {
      key: 'audioType',
      label: '音频类型',
      type: 'radio',
      options: [
        { label: '干声', value: 'dry' },
        { label: '噪声', value: 'noise' },
        { label: '混合', value: 'mixed' }
      ],
      defaultValue: uploadOptions.audio_type
    },
    {
      key: 'createTestCase',
      label: '生成测试用例',
      type: 'boolean',
      defaultValue: uploadOptions.create_test_case
    },
    {
      key: 'algorithmType',
      label: '算法类型',
      type: 'select',
      options: [
        { label: '请选择算法', value: '' },
        ...(Array.isArray(algorithmApi.algorithmOptions.value) ? algorithmApi.algorithmOptions.value : []).map(a => ({ label: a.name, value: a.value }))
      ],
      defaultValue: uploadOptions.algorithm_type
    },
    {
      key: 'testTypes',
      label: '测试类型',
      type: 'checkbox',
      options: [
        { label: 'E2E测试', value: TestType.E2E },
        { label: 'API测试', value: TestType.API }
      ],
      defaultValue: uploadOptions.test_types
    },
    {
      key: 'dimensions',
      label: '评估维度',
      type: 'dimensions',
      defaultValue: uploadOptions.dimensions
    },
    {
      key: 'playbackDeviceId',
      label: '播放设备',
      type: 'select',
      options: (Array.isArray(deviceApi.playbackDevices.value) ? deviceApi.playbackDevices.value : []).map(d => ({ label: d.name, value: d.id })),
      defaultValue: uploadOptions.playback_device_id
    },
    {
      key: 'defaultSpl',
      label: '默认声压级(SPL)',
      type: 'number',
      min: 30,
      max: 120,
      step: 0.1,
      defaultValue: uploadOptions.spl
    },
    {
      key: 'groupNameType',
      label: '用例分组',
      type: 'radio',
      options: [
        { label: '根目录', value: 'root' },
        { label: '文件夹名', value: 'folder' },
        { label: '自定义', value: 'custom' }
      ],
      defaultValue: uploadOptions.group_name_type
    },
    {
      key: 'customGroupName',
      label: '自定义分组名称',
      type: 'text',
      placeholder: '请输入分组名称',
      defaultValue: uploadOptions.custom_group_name
    },
    {
      key: 'inheritTags',
      label: '继承音频标签',
      type: 'boolean',
      defaultValue: uploadOptions.inherit_tags
    }
  ];
}
