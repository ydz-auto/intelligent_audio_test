import { ref } from 'vue';
import { testcasesApi, playbackApi } from '../utils/api';
import { useTestCaseStore } from '../store/testCaseStore';
import { useModalControl } from './useModal';
import { MODAL_TYPES } from '../shared/types';
import { downloadBlob, normalizeTestCaseConfig } from '../utils/utils';
import type { 
  TestCase, 
  ModalSaveData, 
  ModalSaveResult, 
  TestCaseFormData, 
  GroupFormData, 
  TestCaseAction 
} from '../shared/types';

function normalizeAlgorithmParams(params: any[]): Record<string, any> {
  if (!Array.isArray(params)) return {};
  return params.reduce((acc: Record<string, any>, item: any) => {
    const code = item.fieldCode || item.field_code;
    const value = item.fieldValue || item.field_value;
    if (code) {
      acc[code] = value;
    }
    return acc;
  }, {});
}

export function useTestCaseCard() {
  const showTestCaseModal = ref(false);
  const showGroupModal = ref(false);
  const showImportModal = ref(false);
  const showExportModal = ref(false);
  const editingTestCase = ref<TestCase | null>(null);
  const editingGroup = ref<string | null>(null);
  
  const initialFormData: TestCaseFormData = {
    name: '',
    group: '默认分组',
    description: '',
    tags: [],
    tagsInput: '',
    config: {
      backgroundNoise: {
        audioId: null,
        spl: null,
        deviceId: null
      },
      audios: [
        {
          audioId: '',
          testType: 'api',
          playbackDeviceId: '',
          spl: 65,
          playOrder: 0
        }
      ],
      dimensions: {
        api: [],
        e2e: []
      }
    }
  };

  const formData = ref<TestCaseFormData>({ ...initialFormData });
  
  const groupFormData = ref<GroupFormData>({
    name: '',
    description: '',
    algorithmType: ''
  });

  // 打开新增测试用例模态框
  const openAddTestCaseModal = (group = '默认分组', options?: { algorithmType?: string }) => {
    console.log('[useTestCaseCard] 调用openAddTestCaseModal，分组:', group, '算法类型:', options?.algorithmType);
    editingTestCase.value = null;
    formData.value = {
      ...initialFormData,
      group: group,
      algorithmType: options?.algorithmType || ''
    };
    showTestCaseModal.value = true;
  };

  // 打开编辑测试用例模态框
  const openEditTestCaseModal = (testCase: TestCase) => {
    console.log('[useTestCaseCard] 调用openEditTestCaseModal，测试用例:', testCase.id);
    console.log('[useTestCaseCard] 测试用例完整数据:', JSON.stringify(testCase));
    editingTestCase.value = testCase;
    
    // 使用归一化函数处理配置，确保类型安全和兼容性
    const normalized = normalizeTestCaseConfig(testCase.config || {});
    const { apiAudios, dryAudios, ...config } = normalized;
    
    formData.value = {
      id: testCase.id,
      name: testCase.name || '',
      group: testCase.groupName || testCase.group || '',
      groupId: testCase.groupId || testCase.group_id || '',
      description: testCase.description || '',
      tags: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name),
      tagsInput: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name).join(','),
      config: config as TestCaseFormData['config'],
      translationDirectionId: testCase.translationDirectionId,
      algorithmType: (testCase as any).algorithmType || (testCase as any).algorithm_type || '',
      algorithmParams: normalizeAlgorithmParams((testCase as any).algorithmParams || (testCase as any).algorithm_params || []),
      referenceParams: normalizeAlgorithmParams((testCase as any).referenceParams || (testCase as any).reference_params || [])
    };
    
    showTestCaseModal.value = true;
  };

  // 打开编辑分组模态框
  const openEditGroupModal = (groupName: string) => {
    editingGroup.value = groupName;
    groupFormData.value = {
      name: groupName,
      description: '',
      algorithmType: ''
    };
    // 确保 formData 也被设置，这样 TestCaseModal 的 isEditMode 才能正确检测到编辑模式
    formData.value = {
      ...initialFormData,
      name: groupName,
      group: '默认分组'
    };
    showGroupModal.value = true;
  };

  // 打开创建分组模态框
  const openCreateGroupModal = () => {
    editingGroup.value = null;
    groupFormData.value = {
      name: '',
      description: '',
      algorithmType: ''
    };
    showGroupModal.value = true;
  };

  const openImportTestCaseModal = () => {
    showImportModal.value = true;
  };

  const openExportTestCaseModal = () => {
    showExportModal.value = true;
  };

  // 处理预览音频操作
  const handlePreviewAction = async (testCase: TestCase) => {
    // 检查音频配置
    const hasAudioConfig = testCase.config?.audios && testCase.config.audios.length > 0;
    // 检查旧格式的音频配置（向后兼容）
    const config: any = testCase.config || {};
    const hasOldAudioConfig = config.apiAudio || config.dryAudio || (config.dryAudios && config.dryAudios[0]?.file);
    
    if (hasAudioConfig || hasOldAudioConfig) {
      try {
        // 获取播放设备列表（可选，用于未来扩展设备选择）
        const playbackDevicesRes = await playbackApi.getAll();
        const playbackDevices = playbackDevicesRes.items || [];
        console.log('[useTestCaseCard] 可用播放设备:', playbackDevices.length);
        
        // 调用后端API预览
        await testcasesApi.preview(testCase.id);
        console.log(`[useTestCaseCard] 开始试听测试用例 ${testCase.id} 的音频`);
      } catch (err: any) {
        console.error('[useTestCaseCard] 音频试听失败:', err);
        alert('音频试听失败: ' + (err.message || '未知错误'));
      }
    } else {
      alert('该测试用例没有关联音频文件');
    }
  };

  // 处理复制测试用例操作
  const handleCopyAction = async (testCase: TestCase) => {
    try {
      const store = useTestCaseStore();
      const success = await store.copyTestCase(testCase.id);
      if (success) {
        console.log('[useTestCaseCard] 复制测试用例成功:', testCase.id);
      } else {
        alert('复制测试用例失败');
      }
    } catch (error: any) {
      console.error('[useTestCaseCard] 复制测试用例失败:', error);
      alert('复制测试用例失败: ' + (error.message || '未知错误'));
    }
  };

  // 删除测试用例
  const deleteTestCase = async (id: string | number) => {
    const { open } = useModalControl();
    try {
      // 修复：使用正确的属性名content而不是message
      const confirmed = await open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '确认删除',
        content: '确定要删除该测试用例吗？',
        danger: true,
        confirmText: '删除',
        cancelText: '取消'
      });
      if (confirmed) {
        const store = useTestCaseStore();
        return await store.deleteTestCase(id);
      }
    } catch (error) {
      console.error('删除测试用例失败:', error);
      alert('删除测试用例失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
    return false;
  };

  // 处理测试用例操作
  const handleTestCaseAction = (data: { action: { id: string }, testCase: TestCase }) => {
    const { action, testCase } = data;
    switch (action.id) {
      case 'preview':
        handlePreviewAction(testCase);
        break;
      case 'copy':
        handleCopyAction(testCase);
        break;
      case 'edit':
        openEditTestCaseModal(testCase);
        break;
      case 'delete':
        deleteTestCase(testCase.id);
        break;
      default:
        console.log('未处理的操作:', action.id);
    }
  };

  // 处理模态框关闭
  const handleModalClose = () => {
    showTestCaseModal.value = false;
    showGroupModal.value = false;
    showImportModal.value = false;
    showExportModal.value = false;
    editingTestCase.value = null;
    editingGroup.value = null;
  };

  // 处理模态框保存后的逻辑
  const handleModalSave = async (saveData: ModalSaveData): Promise<ModalSaveResult> => {
    const store = useTestCaseStore();
    const { mode, isEdit, id, data } = saveData;
    let success = false;

    try {
      if (mode === 'case') {
        if (isEdit) {
          success = await store.updateTestCase(id!, data);
        } else {
          success = await store.addTestCase(data);
        }
      } else if (mode === 'group') {
        if (isEdit) {
          // 对于分组编辑，使用 editingGroup.value 作为分组名称（标识符）
          const groupId = editingGroup.value || id;
          console.log('[useTestCaseCard] 编辑分组，editingGroup:', editingGroup.value, 'id:', id, '最终使用的groupId:', groupId);
          if (!groupId) {
            throw new Error('编辑分组时缺少分组标识符');
          }
          success = await store.updateGroup(groupId, data);
        } else {
          success = await store.addGroup(data);
        }
      } else if (mode === 'import') {
        // 处理导入逻辑，规范化 FormData 构建
        console.log('执行导入逻辑:', data);
        const importFormData = new FormData();
        if (!data.file) {
          throw new Error('请选择要导入的文件');
        }
        importFormData.append('file', data.file);
        
        success = await store.importTestCases(importFormData);
      } else if (mode === 'export') {
        // 处理导出逻辑
        console.log('执行导出逻辑:', data);
        const format = data.format === 'xlsx' ? 'xlsx' : 'json';
        const res = await testcasesApi.export(data.ids || [], format);
        
        // 使用通用下载工具函数处理 Blob
        if (res instanceof Blob) {
          downloadBlob(res, `testcases_export_${Date.now()}.${format}`);
        } else if (format === 'json') {
          const jsonString = JSON.stringify(res, null, 2);
          const blob = new Blob([jsonString], { type: 'application/json;charset=utf-8' });
          downloadBlob(blob, `testcases_export_${Date.now()}.json`);
        } else if (format === 'xlsx') {
          // 处理 XLSX 格式
          if (typeof res === 'string') {
            try {
              // 尝试解析 base64 字符串
              const byteCharacters = atob(res);
              const byteNumbers = new Array(byteCharacters.length);
              for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
              }
              const byteArray = new Uint8Array(byteNumbers);
              const blob = new Blob([byteArray], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
              downloadBlob(blob, `testcases_export_${Date.now()}.xlsx`);
            } catch (error) {
              // 如果解析失败，使用默认处理
              const blob = new Blob([res], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
              downloadBlob(blob, `testcases_export_${Date.now()}.xlsx`);
            }
          } else {
            // 对于其他类型的数据，尝试转换为 blob
            const blob = new Blob([JSON.stringify(res)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
            downloadBlob(blob, `testcases_export_${Date.now()}.xlsx`);
          }
        } else {
          // 处理其他格式
          const blob = new Blob([JSON.stringify(res)], { type: 'application/octet-stream' });
          downloadBlob(blob, `testcases_export_${Date.now()}.bin`);
        }
        success = true;
      }

      if (success) {
        handleModalClose();
        return { success: true, needRefresh: true };
      }
      return { success: false, needRefresh: false };
    } catch (error) {
      console.error('保存失败:', error);
      // 向用户显示错误提示
      const errorMessage = error instanceof Error ? error.message : '保存失败，请重试';
      alert(errorMessage);
    }
    
    return { success: false, needRefresh: false };
  };

  return {
    showTestCaseModal,
    showGroupModal,
    showImportModal,
    showExportModal,
    editingTestCase,
    editingGroup,
    formData,
    groupFormData,
    openAddTestCaseModal,
    openEditTestCaseModal,
    openEditGroupModal,
    openCreateGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    deleteTestCase,
    handleTestCaseAction,
    handleModalClose,
    handleModalSave
  };
}
