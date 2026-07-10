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

export function useTestCaseCard() {
  const editingTestCase = ref<TestCase | null>(null);
  const editingGroup = ref<string | null>(null);
  const modalControl = useModalControl();
  
  const initialFormData: TestCaseFormData = {
    name: '',
    group: '默认分组',
    description: '',
    tags: [],
    tagsInput: '',
    test_type: 'e2e',
    config: {
      rounds: [{ roundNumber: 1, audios: [] }],
      dimensions: [],
    }
  };

  const formData = ref<TestCaseFormData>({ ...initialFormData });
  
  const groupFormData = ref<GroupFormData>({
    name: '',
    description: '',
    algorithmType: ''
  });

  const openAddTestCaseModal = async (group = '默认分组', options?: { algorithmType?: string; testType?: 'api' | 'e2e' }) => {
    console.log('[useTestCaseCard] 调用openAddTestCaseModal，分组:', group, '算法类型:', options?.algorithmType, '测试类型:', options?.testType);
    editingTestCase.value = null;
    const testType = options?.testType || 'e2e';
    formData.value = {
      ...initialFormData,
      group: group,
      algorithmType: options?.algorithmType || '',
      test_type: testType
    };
    
    try {
      const result = await modalControl.open(MODAL_TYPES.TEST_CASE_RELATED, {
        visible: true,
        mode: 'case',
        testType: testType,
        formData: formData.value,
        title: '新增测试用例',
        width: '1800px',
        maxWidth: '98vw'
      });
      
      if (result) {
        await handleModalSave(result);
      }
    } catch (error) {
      console.error('[useTestCaseCard] 打开新增用例模态窗失败:', error);
    }
  };

  const openEditTestCaseModal = async (testCase: TestCase) => {
    console.log('[useTestCaseCard] 调用openEditTestCaseModal，测试用例:', testCase.id);
    console.log('[useTestCaseCard] 测试用例完整数据:', JSON.stringify(testCase));
    editingTestCase.value = testCase;
    
    const normalized = normalizeTestCaseConfig(testCase.config || {});
    const testCaseType = (testCase as any).test_type || (testCase as any).testType || 'e2e';
    
    formData.value = {
      id: testCase.id,
      name: testCase.name || '',
      group: testCase.groupName || '',
      groupId: testCase.groupId || '',
      description: testCase.description || '',
      tags: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name),
      tagsInput: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name).join(','),
      config: normalized as TestCaseFormData['config'],
      algorithmType: (testCase as any).algorithmType || (testCase as any).algorithm_type || '',
      test_type: testCaseType as 'api' | 'e2e',
      // 新设计：algorithm_params 独立列（后端返回驼峰 algorithmParams）
      algorithm_params: Array.isArray((testCase as any).algorithmParams || (testCase as any).algorithm_params)
        ? ((testCase as any).algorithmParams || (testCase as any).algorithm_params)
        : [],
    } as TestCaseFormData;
    
    try {
      const result = await modalControl.open(MODAL_TYPES.TEST_CASE_RELATED, {
        visible: true,
        mode: 'case',
        testType: testCaseType,
        formData: formData.value,
        title: '编辑测试用例',
        width: '1800px',
        maxWidth: '98vw'
      });
      
      if (result) {
        await handleModalSave(result);
      }
    } catch (error) {
      console.error('[useTestCaseCard] 打开编辑用例模态窗失败:', error);
    }
  };

  const openEditGroupModal = async (groupName: string) => {
    editingGroup.value = groupName;
    groupFormData.value = {
      name: groupName,
      description: '',
      algorithmType: ''
    };

    // 从后端加载分组的完整信息（包括 algorithmType）
    try {
      const resp = await testcasesApi.getGroups({ page: 1, perPage: 1000 });
      const found = resp?.items?.find((g: any) => g.name === groupName);
      if (found) {
        groupFormData.value = {
          name: found.name || groupName,
          description: found.description || '',
          algorithmType: found.algorithmType || ''
        };
      }
    } catch (e) {
      console.warn('[useTestCaseCard] 加载分组信息失败:', e);
    }

    try {
      const result = await modalControl.open(MODAL_TYPES.TEST_GROUP, {
        visible: true,
        mode: 'group',
        formData: groupFormData.value,
        title: '编辑分组',
        width: '500px'
      });

      if (result) {
        await handleModalSave(result);
      }
    } catch (error) {
      console.error('[useTestCaseCard] 打开编辑分组模态窗失败:', error);
    }
  };

  const openCreateGroupModal = async () => {
    editingGroup.value = null;
    groupFormData.value = {
      name: '',
      description: '',
      algorithmType: ''
    };
    
    try {
      const result = await modalControl.open(MODAL_TYPES.TEST_GROUP, {
        visible: true,
        mode: 'group',
        formData: groupFormData.value,
        title: '创建分组',
        width: '500px'
      });
      
      if (result) {
        await handleModalSave(result);
      }
    } catch (error) {
      console.error('[useTestCaseCard] 打开创建分组模态窗失败:', error);
    }
  };

  const openImportTestCaseModal = async () => {
    try {
      const result = await modalControl.open(MODAL_TYPES.TEST_CASE_IMPORT, {
        visible: true,
        mode: 'import',
        title: '批量导入测试用例',
        width: '600px'
      });
      
      if (result) {
        await handleModalSave(result);
      }
    } catch (error) {
      console.error('[useTestCaseCard] 打开导入模态窗失败:', error);
    }
  };

  const openExportTestCaseModal = async () => {
    try {
      const result = await modalControl.open(MODAL_TYPES.TEST_CASE_EXPORT, {
        visible: true,
        mode: 'export',
        testType: 'e2e',
        title: '批量导出测试用例',
        width: '600px'
      });
      
      if (result) {
        await handleModalSave(result);
      }
    } catch (error) {
      console.error('[useTestCaseCard] 打开导出模态窗失败:', error);
    }
  };

  const handlePreviewAction = async (testCase: TestCase) => {
    const cfg: any = testCase.config || {};
    const hasAudioConfig = (cfg.rounds && Array.isArray(cfg.rounds) && cfg.rounds.some((r: any) => r.audios?.length > 0))
      || (cfg.audios && cfg.audios.length > 0);
    
    if (hasAudioConfig) {
      try {
        const playbackDevicesRes = await playbackApi.getAll();
        const playbackDevices = playbackDevicesRes.items || [];
        console.log('[useTestCaseCard] 可用播放设备:', playbackDevices.length);
        
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

  const deleteTestCase = async (id: string | number) => {
    try {
      const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
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

  const handleModalSave = async (saveData: ModalSaveData): Promise<ModalSaveResult> => {
    const store = useTestCaseStore();
    const { mode, isEdit, id, data } = saveData;
    let success = false;

    try {
      if (mode === 'case') {
        if (isEdit) {
          success = await store.updateTestCase(id!, data);
        } else {
          if (data.createNewGroup && data.group) {
            try {
              await store.addGroup({ name: data.group, description: '', algorithmType: data.algorithmType || '' });
            } catch (e) {
              console.warn('[useTestCaseCard] 创建新分组失败（可能已存在）:', e);
            }
          }
          success = await store.addTestCase(data);
        }
      } else if (mode === 'group') {
        if (isEdit) {
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
        console.log('执行导入逻辑:', data);
        const importFormData = new FormData();
        if (!data.file) {
          throw new Error('请选择要导入的文件');
        }
        importFormData.append('file', data.file);
        
        success = await store.importTestCases(importFormData);
      } else if (mode === 'export') {
        console.log('执行导出逻辑:', data);
        const format = data.format === 'xlsx' ? 'xlsx' : 'json';
        const res = await testcasesApi.export(data.ids || [], format);
        
        if (res instanceof Blob) {
          downloadBlob(res, `testcases_export_${Date.now()}.${format}`);
        } else if (format === 'json') {
          const jsonString = JSON.stringify(res, null, 2);
          const blob = new Blob([jsonString], { type: 'application/json;charset=utf-8' });
          downloadBlob(blob, `testcases_export_${Date.now()}.json`);
        } else if (format === 'xlsx') {
          if (typeof res === 'string') {
            try {
              const byteCharacters = atob(res);
              const byteNumbers = new Array(byteCharacters.length);
              for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
              }
              const byteArray = new Uint8Array(byteNumbers);
              const blob = new Blob([byteArray], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
              downloadBlob(blob, `testcases_export_${Date.now()}.xlsx`);
            } catch (error) {
              const blob = new Blob([res], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
              downloadBlob(blob, `testcases_export_${Date.now()}.xlsx`);
            }
          } else {
            const blob = new Blob([JSON.stringify(res)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
            downloadBlob(blob, `testcases_export_${Date.now()}.xlsx`);
          }
        } else {
          const blob = new Blob([JSON.stringify(res)], { type: 'application/octet-stream' });
          downloadBlob(blob, `testcases_export_${Date.now()}.bin`);
        }
        success = true;
      }

      if (success) {
        return { success: true, needRefresh: true };
      }
      return { success: false, needRefresh: false };
    } catch (error) {
      console.error('保存失败:', error);
      const errorMessage = error instanceof Error ? error.message : '保存失败，请重试';
      alert(errorMessage);
    }
    
    return { success: false, needRefresh: false };
  };

  return {
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
    handleModalSave
  };
}