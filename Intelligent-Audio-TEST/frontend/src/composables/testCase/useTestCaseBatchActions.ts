import type { Ref } from 'vue';
import type { TestCase } from '../../shared/types';
import { useTestCaseStore } from '../../store/testCaseStore';
import { useModalControl, MODAL_TYPES } from '../modal/useModal';

/**
 * 测试用例列表批量操作 composable。
 *
 * 职责：
 * - 批量更新算法参数 / SPL / 播放设备 / 噪声 / 评价维度 / 标签
 * - 批量自动生成用例名 / 刷新参考参数
 * - 批量调整分组（移动/复制）
 * - 复制整组用例
 *
 * 依赖：
 * - filteredTestCases: 经过筛选后的分组用例映射，用于确定分组下可选的用例集合
 * - selectedCases: 当前选中的用例 id 列表，批量操作优先作用于选中项
 * - algorithmTypeFilter: 当前算法类型筛选值，用于批量设置评价维度时透传
 */
export function useTestCaseBatchActions(
  filteredTestCases: Ref<Record<string, TestCase[]>>,
  selectedCases: Ref<(string | number)[]>,
  algorithmTypeFilter: Ref<string>
) {
  const modalControl = useModalControl();

  // 本组件内部使用的批量操作上下文（保留原 let 变量语义）
  let currentBatchGroup = '';
  let currentBatchCaseIds: (string | number)[] = [];

  /**
   * 计算分组下待批量操作的用例 id 列表：
   * 优先使用分组内已勾选用例，否则回退到分组下全部用例。
   */
  const resolveBatchCaseIds = (group: string): (string | number)[] => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      return [];
    }

    const groupCaseIds = new Set(groupCases.map((tc: TestCase) => tc.id));
    const selectedInGroup = selectedCases.value.filter(id => groupCaseIds.has(id as string));

    currentBatchGroup = group;
    currentBatchCaseIds = selectedInGroup.length > 0
      ? selectedInGroup
      : Array.from(groupCaseIds);

    return currentBatchCaseIds;
  };

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
        const store = useTestCaseStore();
        const result = await store.copyGroupCases(group);
        if (result) {
          alert(`分组复制成功！\n\n原分组：${group}\n新分组：${group}_copy`);
        }
      }
    } catch (error) {
      console.error('复制分组失败:', error);
    }
  };

  const handleUpdateAlgorithmParams = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    const caseIds = resolveBatchCaseIds(group);
    if (caseIds.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    try {
      const result = await modalControl.open(MODAL_TYPES.BATCH_ALGORITHM_PARAMS, {
        title: '批量设置用例专属参数',
        caseCount: caseIds.length,
        algorithmType: groupCases[0]?.algorithmType || ''
      });

      if (result?.algorithmType && result?.params) {
        const store = useTestCaseStore();
        const updateResult = await store.batchUpdateAlgorithmParams(caseIds, result.params);
        if (updateResult) {
          alert(`已成功更新 ${caseIds.length} 个用例的专属参数`);
        }
      }
    } catch (error) {
      console.error('更新用例专属参数失败:', error);
    }
  };

  const handleUpdatePlaybackDevice = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    const caseIds = resolveBatchCaseIds(group);
    if (caseIds.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    try {
      const result = await modalControl.open(MODAL_TYPES.BATCH_PLAYBACK_DEVICE, {
        title: '批量设置播放设备',
        caseCount: caseIds.length
      });

      if (result?.deviceId) {
        const store = useTestCaseStore();
        const updateResult = await store.batchUpdatePlaybackDevices(caseIds, { deviceId: result.deviceId });
        if (updateResult) {
          alert(`已成功更新 ${caseIds.length} 个用例的播放设备`);
        }
      }
    } catch (error) {
      console.error('更新播放设备失败:', error);
    }
  };

  const handleUpdateSPL = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    const caseIds = resolveBatchCaseIds(group);
    if (caseIds.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    try {
      const result = await modalControl.open(MODAL_TYPES.BATCH_SPL, {
        title: '批量设置声压级',
        caseCount: caseIds.length,
        initialValue: 65
      });

      if (result?.value !== undefined) {
        const store = useTestCaseStore();
        const updateResult = await store.batchUpdateSPL(caseIds, { value: result.value });
        if (updateResult) {
          alert(`已成功更新 ${caseIds.length} 个用例的声压`);
        }
      }
    } catch (error) {
      console.error('更新声压失败:', error);
    }
  };

  const handleAdjustGroup = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    const caseIds = resolveBatchCaseIds(group);
    if (caseIds.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    try {
      const result = await modalControl.open(MODAL_TYPES.BATCH_ADJUST_GROUP, {
        title: '批量调整分组',
        caseCount: caseIds.length,
        currentGroupId: ''
      });

      if (result?.groupId) {
        const store = useTestCaseStore();
        let updateResult = false;
        if (result.isCopy) {
          updateResult = await store.batchCopyCases(caseIds, result.groupId);
        } else {
          updateResult = await store.batchMoveCases(caseIds, result.groupId);
        }
        if (updateResult) {
          alert(`已成功将 ${caseIds.length} 个用例${result.isCopy ? '复制' : '移动'}到目标分组`);
        }
      }
    } catch (error) {
      console.error('调整分组失败:', error);
    }
  };

  const handleUpdateDimensions = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    const caseIds = resolveBatchCaseIds(group);
    if (caseIds.length === 0) {
      alert('该分组下没有勾选用例');
      return;
    }

    try {
      const result = await modalControl.open(MODAL_TYPES.BATCH_DIMENSION, {
        title: '批量设置评价维度',
        caseCount: caseIds.length,
        algorithmType: algorithmTypeFilter.value !== 'all' ? algorithmTypeFilter.value : ''
      });

      if (result?.dimensions) {
        const store = useTestCaseStore();
        const updateResult = await store.batchUpdateDimensions(caseIds, result.dimensions, result.testType);
        if (updateResult) {
          alert(`已成功更新 ${caseIds.length} 个用例的评价维度`);
        }
      }
    } catch (error) {
      console.error('更新评价维度失败:', error);
    }
  };

  const handleUpdateNoise = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    const caseIds = resolveBatchCaseIds(group);
    if (caseIds.length === 0) {
      alert('该分组下没有勾选用例');
      return;
    }

    try {
      const result = await modalControl.open(MODAL_TYPES.BATCH_NOISE, {
        title: '批量设置噪声',
        caseCount: caseIds.length
      });

      if (result) {
        const store = useTestCaseStore();
        const updateResult = await store.batchUpdateNoise(
          caseIds,
          result.audioId || '',
          result.spl || 0,
          result.deviceIds || []
        );
        if (updateResult) {
          alert(`已成功更新 ${caseIds.length} 个用例的噪声配置`);
        }
      }
    } catch (error) {
      console.error('更新噪声配置失败:', error);
    }
  };

  const handleAutoGenerateName = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    const caseIds = resolveBatchCaseIds(group);
    if (caseIds.length === 0) {
      alert('该分组下没有勾选用例');
      return;
    }

    try {
      const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '批量通过标签自动生成用例名',
        content: `将为 ${caseIds.length} 个用例自动生成名称（按标签长度排序，用"-"连接）\n\n是否继续？`,
        confirmText: '确定',
        cancelText: '取消',
        danger: false
      });

      if (confirmed?.confirmed) {
        const store = useTestCaseStore();
        const updateResult = await store.batchAutoGenerateName(caseIds);
        if (updateResult) {
          alert(`已成功为 ${caseIds.length} 个用例自动生成名称`);
        }
      }
    } catch (error) {
      console.error('自动生成用例名失败:', error);
    }
  };

  const handleUpdateTags = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    const caseIds = resolveBatchCaseIds(group);
    if (caseIds.length === 0) {
      alert('该分组下没有勾选用例');
      return;
    }

    try {
      const result = await modalControl.open(MODAL_TYPES.BATCH_TAGS, {
        title: '批量管理用例标签',
        caseCount: caseIds.length
      });

      if (result) {
        const store = useTestCaseStore();
        let updateResult = false;
        if (result.action === 'add' && result.tags) {
          updateResult = await store.batchAddTags(caseIds, result.tags);
        } else if (result.action === 'remove' && result.tags) {
          updateResult = await store.batchRemoveTags(caseIds, result.tags);
        } else if (result.action === 'rename' && result.oldTagName && result.newTagName) {
          updateResult = await store.batchRenameTag(result.oldTagName, result.newTagName);
        }
        if (updateResult) {
          const actionText = result.action === 'add' ? '添加' : result.action === 'remove' ? '移除' : '重命名';
          alert(`已成功${actionText}标签`);
        }
      }
    } catch (error) {
      console.error('更新标签失败:', error);
    }
  };

  const handleRefreshReference = async (group: string) => {
    const groupCases = filteredTestCases.value[group] || [];
    if (groupCases.length === 0) {
      alert('该分组下没有用例');
      return;
    }

    const caseIds = resolveBatchCaseIds(group);
    if (caseIds.length === 0) {
      alert('该分组下没有勾选用例');
      return;
    }

    try {
      const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '用例参考更新',
        content: `确定要刷新 ${caseIds.length} 个用例的参考参数吗？\n\n这将从关联音频的标注数据重新生成参考参数。`,
        confirmText: '确定刷新',
        cancelText: '取消',
        danger: false
      });

      if (confirmed?.confirmed) {
        const store = useTestCaseStore();
        const result = await store.batchRefreshReference(caseIds);

        if (result && typeof result === 'object' && 'taskId' in result) {
          console.log(`[handleRefreshReference] 异步任务已提交: ${result.taskId}，开始轮询进度...`);

          const pollAndNotify = async () => {
            const status = await store.pollRefreshTaskStatus(result.taskId);

            if (status.success) {
              console.log(`[handleRefreshReference] 任务完成: 成功 ${status.updated} 个，失败 ${status.failed} 个`);
              await store.fetchTestCases();
              alert(`用例参考更新完成！\n\n成功刷新: ${status.updated} 个\n失败: ${status.failed} 个`);
            } else {
              console.error('[handleRefreshReference] 任务查询失败或任务不存在');
              alert('用例参考更新任务执行失败，请稍后重试');
            }
          };

          pollAndNotify();
        } else if (result === true) {
          alert(`已成功刷新 ${caseIds.length} 个用例的参考参数`);
        }
      }
    } catch (error) {
      console.error('刷新用例参考失败:', error);
    }
  };

  return {
    handleCopyGroup,
    handleUpdateAlgorithmParams,
    handleUpdatePlaybackDevice,
    handleUpdateSPL,
    handleAdjustGroup,
    handleUpdateDimensions,
    handleUpdateNoise,
    handleAutoGenerateName,
    handleUpdateTags,
    handleRefreshReference
  };
}
