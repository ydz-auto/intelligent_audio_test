import type { Ref } from 'vue';
import type { TestCase } from '../../shared/types';
import { useTestCaseStore } from '../../store/testCaseStore';
import { useModalControl, MODAL_TYPES } from '../modal/useModal';

/**
 * 测试用例列表批量操作 composable。
 *
 * 职责：
 * - resolveCaseIds：统一获取批量操作的目标用例ID（有勾选用勾选的，没勾选用筛选后的全量）
 * - 批量更新算法参数 / SPL / 播放设备 / 噪声 / 评价维度 / 标签
 * - 批量自动生成用例名 / 刷新参考参数
 * - 批量调整分组（移动/复制）
 * - 复制整组用例
 *
 * 依赖：
 * - filteredTestCases: 经过筛选后的分组用例映射，用于确定分组下可选的用例集合
 * - filteredTagCases: 标签视图下筛选后的用例映射
 * - selectedCases: 当前选中的用例 id 列表，批量操作优先作用于选中项
 * - algorithmTypeFilter: 当前算法类型筛选值，用于批量设置评价维度时透传
 */
export function useTestCaseBatchActions(
  filteredTestCases: Ref<Record<string, TestCase[]>>,
  selectedCases: Ref<(string | number)[]>,
  algorithmTypeFilter: Ref<string>,
  filteredTagCases?: Ref<Record<string, TestCase[]>>
) {
  const modalControl = useModalControl();
  const store = useTestCaseStore();

  // 本组件内部使用的批量操作上下文（保留原 let 变量语义）
  let currentBatchGroup = '';
  let currentBatchCaseIds: (string | number)[] = [];

  /**
   * 统一获取批量操作的目标用例ID
   * 规则：有勾选用勾选的，没勾选用筛选后的全量（从后端拉取）
   */
  const resolveCaseIds = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ): Promise<{ ids: (string | number)[]; isEmpty: boolean; emptyMsg: string; selectionMode: 'selected' | 'all' }> => {
    const groupCaseIds = new Set(filteredCases.map(tc => tc.id));
    const selectedInGroup = selection.filter(id => groupCaseIds.has(id));

    if (selectedInGroup.length > 0) {
      return { ids: selectedInGroup, isEmpty: false, emptyMsg: '', selectionMode: 'selected' };
    }

    // 没勾选 → 先用前端已加载的用例
    if (filteredCases.length > 0) {
      return { ids: filteredCases.map(tc => tc.id), isEmpty: false, emptyMsg: '', selectionMode: 'all' };
    }

    // 前端没有已加载用例 → 从后端拉取全量ID
    const allIds = await store.fetchCaseIdsByFilter({
      group: viewMode === 'group' ? group : undefined,
      tag: viewMode === 'tag' ? group : undefined,
    });

    if (allIds.length === 0) {
      return {
        ids: [],
        isEmpty: true,
        emptyMsg: viewMode === 'tag' ? `标签"${group}"下没有用例` : `分组"${group}"下没有用例`,
        selectionMode: 'all'
      };
    }

    return { ids: allIds, isEmpty: false, emptyMsg: '', selectionMode: 'all' };
  };

  /**
   * 复制分组用例
   */
  const handleCopyGroup = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    currentBatchGroup = group;
    currentBatchCaseIds = groupCases.map((tc: TestCase) => tc.id);

    try {
      const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '复制分组',
        content: `确定要复制分组 "${group}" 下的 ${groupCases.length} 个用例吗？\n\n复制后将成为新分组：${group}_copy`,
        confirmText: '复制',
        cancelText: '取消',
        danger: false
      });

      if (confirmed?.confirmed) {
        const result = await store.copyGroupCases(group);
        if (result) {
          alert(`分组复制成功！\n\n原分组：${group}\n新分组：${group}_copy`);
        }
      }
    } catch (error) {
      console.error('复制分组失败:', error);
    }
  };

  /**
   * 批量设置声压
   */
  const batchSetSPL = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ) => {
    const { ids, isEmpty, emptyMsg, selectionMode } = await resolveCaseIds(group, selection, filteredCases, viewMode);
    if (isEmpty) {
      alert(emptyMsg);
      return;
    }

    const result = await modalControl.open(MODAL_TYPES.BATCH_SPL, {
      title: '批量设置声压级',
      caseCount: ids.length,
      selectionMode,
      initialValue: 65
    });

    if (result?.value !== undefined) {
      const success = await store.batchUpdateSPL(ids, { value: result.value }, {
        targets: result.targets,
        roundMode: result.roundMode,
        roundNumbers: result.roundNumbers,
      });
      if (success) {
        alert(`已成功更新 ${ids.length} 个用例的声压`);
      }
    }
  };

  /**
   * 批量设置播放设备
   */
  const batchSetPlaybackDevice = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ) => {
    const { ids, isEmpty, emptyMsg, selectionMode } = await resolveCaseIds(group, selection, filteredCases, viewMode);
    if (isEmpty) {
      alert(emptyMsg);
      return;
    }

    const result = await modalControl.open(MODAL_TYPES.BATCH_PLAYBACK_DEVICE, {
      title: '批量设置播放设备',
      caseCount: ids.length,
      selectionMode
    });

    if (result?.deviceId) {
      const success = await store.batchUpdatePlaybackDevices(ids, { deviceId: result.deviceId }, {
        targets: result.targets,
        roundMode: result.roundMode,
        roundNumbers: result.roundNumbers,
      });
      if (success) {
        alert(`已成功更新 ${ids.length} 个用例的播放设备`);
      }
    }
  };

  /**
   * 批量设置噪声
   */
  const batchSetNoise = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ) => {
    const { ids, isEmpty, emptyMsg, selectionMode } = await resolveCaseIds(group, selection, filteredCases, viewMode);
    if (isEmpty) {
      alert(emptyMsg);
      return;
    }

    const result = await modalControl.open(MODAL_TYPES.BATCH_NOISE, {
      title: '批量设置噪声',
      caseCount: ids.length,
      selectionMode
    });

    if (result) {
      const success = await store.batchUpdateNoise(
        ids,
        result.audioId || '',
        result.spl || 0,
        result.deviceIds || [],
        {
          targets: result.targets,
          roundMode: result.roundMode,
          roundNumbers: result.roundNumbers,
        }
      );
      if (success) {
        alert(`已成功更新 ${ids.length} 个用例的噪声配置`);
      }
    }
  };

  /**
   * 批量设置用例专属参数
   */
  const batchSetAlgorithmParams = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ) => {
    const { ids, isEmpty, emptyMsg, selectionMode } = await resolveCaseIds(group, selection, filteredCases, viewMode);
    if (isEmpty) {
      alert(emptyMsg);
      return;
    }

    const result = await modalControl.open(MODAL_TYPES.BATCH_ALGORITHM_PARAMS, {
      title: '批量设置用例专属参数',
      caseCount: ids.length,
      selectionMode,
      algorithmType: filteredCases[0]?.algorithm_type || ''
    });

    if (result?.algorithmType && result?.params) {
      const success = await store.batchUpdateAlgorithmParams(ids, result.params, {
        roundMode: result.roundMode,
        roundNumbers: result.roundNumbers,
      });
      if (success) {
        alert(`已成功更新 ${ids.length} 个用例的专属参数`);
      }
    }
  };

  /**
   * 批量设置评价维度
   */
  const batchSetDimensions = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ) => {
    const { ids, isEmpty, emptyMsg, selectionMode } = await resolveCaseIds(group, selection, filteredCases, viewMode);
    if (isEmpty) {
      alert(emptyMsg);
      return;
    }

    const result = await modalControl.open(MODAL_TYPES.BATCH_DIMENSION, {
      title: '批量设置评价维度',
      caseCount: ids.length,
      selectionMode,
      testType: (filteredCases[0] as any)?.test_type || 'e2e',
      algorithmType: filteredCases[0]?.algorithm_type || ''
    });

    if (result?.dimensions) {
      const success = await store.batchUpdateDimensions(ids, result.dimensions, result.testType, {
        roundMode: result.roundMode,
        roundNumbers: result.roundNumbers,
        targets: result.targets,
      });
      if (success) {
        alert(`已成功更新 ${ids.length} 个用例的评价维度`);
      }
    }
  };

  /**
   * 批量调整分组
   */
  const batchAdjustGroup = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ) => {
    const { ids, isEmpty, emptyMsg, selectionMode } = await resolveCaseIds(group, selection, filteredCases, viewMode);
    if (isEmpty) {
      alert(emptyMsg);
      return;
    }

    const result = await modalControl.open(MODAL_TYPES.BATCH_ADJUST_GROUP, {
      title: '批量调整分组',
      caseCount: ids.length,
      selectionMode,
      currentGroupId: ''
    });

    if (result?.groupId) {
      let success = false;
      if (result.isCopy) {
        success = await store.batchCopyCases(ids, result.groupId);
      } else {
        success = await store.batchMoveCases(ids, result.groupId);
      }
      if (success) {
        alert(`已成功将 ${ids.length} 个用例${result.isCopy ? '复制' : '移动'}到目标分组`);
      }
    }
  };

  /**
   * 批量生成名称（从标签）
   */
  const batchGenerateName = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ) => {
    const { ids, isEmpty, emptyMsg, selectionMode } = await resolveCaseIds(group, selection, filteredCases, viewMode);
    if (isEmpty) {
      alert(emptyMsg);
      return;
    }

    const selectionText = selectionMode === 'selected' ? `您勾选了 ${ids.length} 个用例` : `将对 ${ids.length} 个用例`;
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '批量通过标签自动生成用例名',
      content: `${selectionText}自动生成名称（按标签长度排序，用"-"连接）\n\n是否继续？`,
      confirmText: '确定',
      cancelText: '取消',
      danger: false
    });

    if (confirmed?.confirmed) {
      const success = await store.batchAutoGenerateName(ids);
      if (success) {
        alert(`已成功为 ${ids.length} 个用例自动生成名称`);
      }
    }
  };

  /**
   * 批量管理标签
   */
  const batchManageTags = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ) => {
    const { ids, isEmpty, emptyMsg, selectionMode } = await resolveCaseIds(group, selection, filteredCases, viewMode);
    if (isEmpty) {
      alert(emptyMsg);
      return;
    }

    const result = await modalControl.open(MODAL_TYPES.BATCH_TAGS, {
      title: '批量管理用例标签',
      caseCount: ids.length,
      selectionMode
    });

    if (result) {
      let success = false;
      if (result.action === 'add' && result.tags) {
        success = await store.batchAddTags(ids, result.tags);
      } else if (result.action === 'remove' && result.tags) {
        success = await store.batchRemoveTags(ids, result.tags);
      } else if (result.action === 'rename' && result.oldTagName && result.newTagName) {
        success = await store.batchRenameTag(result.oldTagName, result.newTagName);
      }
      if (success) {
        const actionText = result.action === 'add' ? '添加' : result.action === 'remove' ? '移除' : '重命名';
        alert(`已成功${actionText}标签`);
      }
    }
  };

  /**
   * 用例参考更新
   */
  const batchRefreshReference = async (
    group: string,
    selection: (string | number)[],
    filteredCases: TestCase[],
    viewMode: 'group' | 'tag' = 'group'
  ) => {
    const { ids, isEmpty, emptyMsg, selectionMode } = await resolveCaseIds(group, selection, filteredCases, viewMode);
    if (isEmpty) {
      alert(emptyMsg);
      return;
    }

    const confirmed = await modalControl.open(MODAL_TYPES.BATCH_REFRESH_REFERENCE, {
      title: '用例参考更新',
      caseCount: ids.length,
      selectionMode
    });

    if (confirmed?.roundMode) {
      const result = await store.batchRefreshReference(ids);

      if (result && typeof result === 'object' && 'taskId' in result) {
        const status = await store.pollRefreshTaskStatus(result.taskId);

        if (status.success) {
          await store.fetchTestCases();
          alert(`用例参考更新完成！\n\n成功刷新: ${status.updated} 个\n失败: ${status.failed} 个`);
        } else {
          alert('用例参考更新任务执行失败，请稍后重试');
        }
      } else if (result === true) {
        alert(`已成功刷新 ${ids.length} 个用例的参考参数`);
      }
    }
  };

  // ===== 分组视图包装方法（兼容原接口签名） =====
  const handleUpdateAlgorithmParams = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    await batchSetAlgorithmParams(group, selectedCases.value, groupCases, 'group');
  };

  const handleUpdatePlaybackDevice = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    await batchSetPlaybackDevice(group, selectedCases.value, groupCases, 'group');
  };

  const handleUpdateSPL = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    await batchSetSPL(group, selectedCases.value, groupCases, 'group');
  };

  const handleAdjustGroup = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    await batchAdjustGroup(group, selectedCases.value, groupCases, 'group');
  };

  const handleUpdateDimensions = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    await batchSetDimensions(group, selectedCases.value, groupCases, 'group');
  };

  const handleUpdateNoise = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    await batchSetNoise(group, selectedCases.value, groupCases, 'group');
  };

  const handleAutoGenerateName = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    await batchGenerateName(group, selectedCases.value, groupCases, 'group');
  };

  const handleUpdateTags = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    await batchManageTags(group, selectedCases.value, groupCases, 'group');
  };

  const handleRefreshReference = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    await batchRefreshReference(group, selectedCases.value, groupCases, 'group');
  };

  // ===== 标签视图包装方法 =====
  const handleTagUpdateSPL = async (tagName: string) => {
    const tagCases = (filteredTagCases?.value || {})[tagName] || [];
    await batchSetSPL(tagName, selectedCases.value, tagCases, 'tag');
  };

  const handleTagUpdatePlaybackDevice = async (tagName: string) => {
    const tagCases = (filteredTagCases?.value || {})[tagName] || [];
    await batchSetPlaybackDevice(tagName, selectedCases.value, tagCases, 'tag');
  };

  const handleTagUpdateNoise = async (tagName: string) => {
    const tagCases = (filteredTagCases?.value || {})[tagName] || [];
    await batchSetNoise(tagName, selectedCases.value, tagCases, 'tag');
  };

  const handleTagUpdateAlgorithmParams = async (tagName: string) => {
    const tagCases = (filteredTagCases?.value || {})[tagName] || [];
    await batchSetAlgorithmParams(tagName, selectedCases.value, tagCases, 'tag');
  };

  const handleTagUpdateDimensions = async (tagName: string) => {
    const tagCases = (filteredTagCases?.value || {})[tagName] || [];
    await batchSetDimensions(tagName, selectedCases.value, tagCases, 'tag');
  };

  const handleTagAdjustGroup = async (tagName: string) => {
    const tagCases = (filteredTagCases?.value || {})[tagName] || [];
    await batchAdjustGroup(tagName, selectedCases.value, tagCases, 'tag');
  };

  const handleTagAutoGenerateName = async (tagName: string) => {
    const tagCases = (filteredTagCases?.value || {})[tagName] || [];
    await batchGenerateName(tagName, selectedCases.value, tagCases, 'tag');
  };

  const handleTagUpdateTags = async (tagName: string) => {
    const tagCases = (filteredTagCases?.value || {})[tagName] || [];
    await batchManageTags(tagName, selectedCases.value, tagCases, 'tag');
  };

  const handleTagRefreshReference = async (tagName: string) => {
    const tagCases = (filteredTagCases?.value || {})[tagName] || [];
    await batchRefreshReference(tagName, selectedCases.value, tagCases, 'tag');
  };

  return {
    resolveCaseIds,
    // 分组视图包装方法
    handleCopyGroup,
    handleUpdateAlgorithmParams,
    handleUpdatePlaybackDevice,
    handleUpdateSPL,
    handleAdjustGroup,
    handleUpdateDimensions,
    handleUpdateNoise,
    handleAutoGenerateName,
    handleUpdateTags,
    handleRefreshReference,
    // 标签视图包装方法
    handleTagUpdateSPL,
    handleTagUpdatePlaybackDevice,
    handleTagUpdateNoise,
    handleTagUpdateAlgorithmParams,
    handleTagUpdateDimensions,
    handleTagAdjustGroup,
    handleTagAutoGenerateName,
    handleTagUpdateTags,
    handleTagRefreshReference,
  };
}
