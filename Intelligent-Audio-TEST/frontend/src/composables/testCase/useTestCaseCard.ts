import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { testcasesPort } from './testcasesPort';
import { playbackPort } from '../device/playbackPort';
import { useTestCaseStore } from '../../store/testCaseStore';
import { useModalControl } from '../modal/useModal';
import { useNotification } from '../modal/useNotification';
import { MODAL_TYPES } from '../modal/constants';
import { downloadBlob, normalizeTestCaseConfig } from '../../utils/utils';
import { ViewMode, TestType, Visibility } from '@/domain/enums';
import { getVisibilityPref } from '../visibility/useVisibility';
import { AUDIO_IMPORT_QUERY, AUDIO_IMPORT_AUTO_OPEN_VALUE } from '@/domain';
import type {
  TestCase,
  TestCaseFormData,
  GroupFormData,
  TestCaseAction
} from '../../domain';
import type {
  ModalSaveData,
  ModalSaveResult,
} from '../modal/types';

export function useTestCaseCard() {
  const router = useRouter();
  const editingTestCase = ref<TestCase | null>(null);
  const editingGroup = ref<string | null>(null);
  const modalControl = useModalControl();
  const notification = useNotification();
  
  const initialFormData: TestCaseFormData = {
    name: '',
    group: '',
    description: '',
    tags: [],
    tagsInput: '',
    testType: TestType.E2E,
    config: {
      rounds: [{ roundNumber: 1, audios: [] }],
      dimensions: [],
    },
    // INT-423/467：新建默认可见性（localStorage 偏好，缺省共享）
    visibility: getVisibilityPref(),
  };

  const formData = ref<TestCaseFormData>({ ...initialFormData });
  
  const groupFormData = ref<GroupFormData>({
    name: '',
    description: '',
    algorithmType: ''
  });

  const openAddTestCaseModal = async (group = '', options?: { algorithmType?: string; testType?: 'api' | 'e2e'; tags?: string[] }) => {
    editingTestCase.value = null;
    const testType = options?.testType || TestType.E2E;
    const presetTags = options?.tags || [];
    formData.value = {
      ...initialFormData,
      group: group,
      algorithmType: options?.algorithmType || '',
      testType: testType,
      // 标签作为预设（如从标签卡片「添加用例」进入时预填当前标签）
      tags: presetTags,
      tagsInput: presetTags.join(', ')
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
        return await handleModalSave(result);
      }
    } catch (error) {
      console.error('[useTestCaseCard] 打开新增用例模态窗失败:', error);
    }
  };

  const openEditTestCaseModal = async (testCase: TestCase) => {
    editingTestCase.value = testCase;
    
    const normalized = normalizeTestCaseConfig(testCase.config || {});
    // 编辑回填只信任域模型 testType（adapter 已从列表项 type 派生，INT-196）；
    // 不再 || TestType.E2E 兜底——API 用例曾被恒锁成 E2E 表单
    const testCaseType = testCase.testType;

    formData.value = {
      id: testCase.id,
      name: testCase.name || '',
      group: testCase.groupName || '',
      // INT-195：不回填 groupId——表单只绑分组名，groupId 由保存边界按所选分组名收敛
      // （残留编辑前旧值会在后端 group_id 优先语义下压住用户新选分组）
      description: testCase.description || '',
      tags: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name),
      tagsInput: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name).join(','),
      config: normalized as TestCaseFormData['config'],
      algorithmType: testCase.algorithmType || '',
      testType: testCaseType,
      // 新设计：algorithm_params 独立列（Domain 侧为 algorithmParams）
      algorithmParams: Array.isArray(testCase.algorithmParams)
        ? testCase.algorithmParams
        : [],
      // INT-423/467：编辑沿用资源现值；归属人用于非 owner 打开私有资源的 403 守卫
      visibility: (testCase.visibility || Visibility.SHARED) as TestCaseFormData['visibility'],
      createdByUserId: testCase.createdByUserId,
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
        return await handleModalSave(result);
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
      const resp = await testcasesPort.getGroups({ page: 1, perPage: 1000 });
      const found = resp?.items?.find((g: any) => g.name === groupName);
      if (found) {
        groupFormData.value = {
          name: found.name || groupName,
          description: found.description || '',
          // Domain 侧为 camelCase：algorithmType
          algorithmType: found.algorithmType || ''
        };
      }
    } catch (e) {
      console.warn('[useTestCaseCard] 加载分组信息失败:', e);
    }

    try {
      const result = await modalControl.open(MODAL_TYPES.TEST_GROUP, {
        visible: true,
        mode: ViewMode.GROUP,
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
        mode: ViewMode.GROUP,
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

  const openImportTestCaseModal = async (algorithmType?: string) => {
    // 对齐 V9.7.10：跳转音频导入页，由 query 参数自动打开上传音频模态窗并默认勾选生成用例
    router.push({
      path: '/AudioImport',
      query: {
        [AUDIO_IMPORT_QUERY.autoOpen]: AUDIO_IMPORT_AUTO_OPEN_VALUE,
        [AUDIO_IMPORT_QUERY.createTestCase]: 'true',
        ...(algorithmType ? { [AUDIO_IMPORT_QUERY.algorithmType]: algorithmType } : {})
      }
    });
  };

  const openExportTestCaseModal = async () => {
    try {
      const result = await modalControl.open(MODAL_TYPES.TEST_CASE_EXPORT, {
        visible: true,
        mode: 'export',
        testType: TestType.E2E,
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
        // playbackPort.getAll 已展平为 Domain 数组
        const playbackDevices = await playbackPort.getAll();

        await testcasesPort.preview(testCase.id);
      } catch (err: any) {
        console.error('[useTestCaseCard] 音频试听失败:', err);
        notification.error('音频试听失败: ' + (err.message || '未知错误'));
      }
    } else {
      notification.warning('该测试用例没有关联音频文件');
    }
  };

  const handleCopyAction = async (testCase: TestCase) => {
    try {
      const store = useTestCaseStore();
      const success = await store.copyTestCase(testCase.id);
      if (!success) {
        notification.error('复制测试用例失败');
      }
    } catch (error: any) {
      console.error('[useTestCaseCard] 复制测试用例失败:', error);
      notification.error('复制测试用例失败: ' + (error.message || '未知错误'));
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
      notification.error('删除测试用例失败: ' + (error instanceof Error ? error.message : '未知错误'));
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
        // 未支持的操作，忽略
        break;
    }
  };

  const handleModalSave = async (saveData: ModalSaveData): Promise<ModalSaveResult> => {
    const store = useTestCaseStore();
    const { mode, isEdit, id, data } = saveData;
    let success = false;

    try {
      if (mode === 'case') {
        if ((data as any)?.visibilityOnly) {
          // INT-423/467：分享/设为私有已由模态内 PATCH 完成，此处仅触发列表刷新
          return { success: true, needRefresh: true };
        }
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
      } else if (mode === ViewMode.GROUP) {
        if (isEdit) {
          const groupId = editingGroup.value || id;
          if (!groupId) {
            throw new Error('编辑分组时缺少分组标识符');
          }
          success = await store.updateGroup(groupId, data);
        } else {
          success = await store.addGroup(data);
        }
      } else if (mode === 'import') {
        const importFormData = new FormData();
        if (!data.file) {
          throw new Error('请选择要导入的文件');
        }
        importFormData.append('file', data.file);
        
        success = await store.importTestCases(importFormData);
      } else if (mode === 'export') {
        const format = data.format === 'xlsx' ? 'xlsx' : 'json';
        const res = await testcasesPort.export(data.ids || [], format);
        
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
      notification.error(errorMessage);
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