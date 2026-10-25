/**
 * useEvaluationDimensions —— 维度保存/删除与 API 健康检查、权重更新
 *
 * 负责维度 CRUD 编排（saveDimension / deleteDimension，含结果提示模态框公共逻辑），
 * 以及 API 健康检查（testAPIHealth）与权重更新（updateWeight）。
 */
import { MODAL_TYPES } from '../modal/constants';
import { evaluationPort } from './evaluationPort';
import {
  EvaluationDimension,
} from '../../domain';
import type { APIHealthResultModalData } from '../../domain/model/apiConfig';
import { ApiEndpointStatus, Visibility } from '../../domain/enums';
import type { DimensionHealthCheckResult } from '../../domain/model/evaluationTypes';
import type { ModalManager } from '../modal/useModal';
import { SAVE_TYPE_ADD } from './useEvaluationDimensions.constants';
import { setVisibilityPref } from '../visibility/useVisibility';
import type { EvalDimensionState } from './useEvaluationDimensions.state';
import type { EvalDimensionNormalizers } from './useEvaluationDimensions.normalize';

/** 保存模块依赖（来自组合根的共享引用与相邻模块） */
interface SaveModuleDeps {
  /** 模态框管理器（组合根创建的共享实例） */
  modalManager: ModalManager;
  /** 数据刷新（保存/删除成功后重新拉取列表） */
  fetchData: () => Promise<void>;
  /** 必填字段校验（来自表单模块） */
  validateRequiredFields: (dimensionData: any) => string[];
  /** 保存前字段规范化处理链（来自规范化模块） */
  normalizers: EvalDimensionNormalizers;
}

/** 创建维度保存/删除与健康检查、权重更新模块 */
export function createEvalDimensionSave(state: EvalDimensionState, deps: SaveModuleDeps) {
  const { loading, error, dimensions, hierarchicalDimensions } = state;
  const {
    modalManager,
    fetchData,
    validateRequiredFields,
    normalizers,
  } = deps;

  const {
    normalizeRule,
    normalizeRequiredInputs,
    normalizeOutputFields,
    normalizeExcludeRounds,
    normalizeApiSettings,
    resolveCategory,
    inheritFromParentDimension,
    normalizeApiEndpoints,
    normalizeAssociatedAlgorithms,
  } = normalizers;

  // ========== 维度 CRUD ==========

  // 打开结果提示模态框（提取公共逻辑，消除重复）
  function showResultModal(title: string, content: string) {
    modalManager.open(MODAL_TYPES.BASIC_CONFIRM, { title, content, onConfirm: () => {} });
  }

  async function saveDimension(payload: any, type: 'add' | 'edit' = SAVE_TYPE_ADD): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const data = payload.data !== undefined ? payload.data : payload;
      const dimensionData = { ...data };

      // INT-423/467：可见性选择 → 记录 localStorage 偏好（新建默认沿用）
      if (dimensionData.visibility) setVisibilityPref(dimensionData.visibility);

      // 依次规范化各字段
      normalizeRule(dimensionData);
      normalizeRequiredInputs(dimensionData);
      normalizeOutputFields(dimensionData);
      normalizeExcludeRounds(dimensionData);
      normalizeApiSettings(dimensionData);
      // apiUrl 现在是字符串类型，只需修剪空格
      if (dimensionData.apiUrl !== undefined && typeof dimensionData.apiUrl === 'string') {
        dimensionData.apiUrl = dimensionData.apiUrl.trim();
      }
      await resolveCategory(dimensionData);
      inheritFromParentDimension(dimensionData);
      normalizeApiEndpoints(dimensionData);
      normalizeAssociatedAlgorithms(dimensionData);

      // 校验必填字段
      const missingFields = validateRequiredFields(dimensionData);
      if (missingFields.length > 0) {
        throw new Error(`以下必填字段缺失：${missingFields.join('、')}`);
      }

      // 调用 API 创建/更新
      if (type === SAVE_TYPE_ADD) {
        await evaluationPort.create(dimensionData);
        showResultModal('成功', '评估维度添加成功');
      } else {
        if (!dimensionData.id) throw new Error('维度 ID 缺失');
        await evaluationPort.update(dimensionData.id, dimensionData);
        showResultModal('成功', '评估维度更新成功');
      }
      await fetchData();
    } catch (err: any) {
      console.error('Failed to save dimension:', err);
      showResultModal('错误', err.message || '保存失败');
      error.value = err.message || '保存评估维度失败';
    } finally {
      loading.value = false;
    }
  }

  async function deleteDimension(id: number | string) {
    // 确认文案用维度名（对齐 V9.7.10），找不到时回退 ID
    const dimension = dimensions.value.find(dim => dim.id === id);
    const displayName = dimension?.name || String(id);
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '删除维度',
      content: `确定要删除维度「${displayName}」吗？`,
      onConfirm: async () => {
        loading.value = true;
        try {
          await evaluationPort.delete(id);
          showResultModal('成功', '维度已删除');
          await fetchData();
        } catch (err: any) {
          console.error('Failed to delete dimension:', err);
          showResultModal('错误', err.message || '删除维度失败');
        } finally {
          loading.value = false;
        }
      }
    });
  }

  // ========== 维度可见性切换（INT-536 D4） ==========

  /** 分享 / 设为私有：PATCH /evaluation/dimensions/{id}/visibility（需 evaluation:share + owner 校验），
   *  成功重取列表使徽标即时刷新（对齐任务/报告详情切换口径） */
  async function toggleDimensionVisibility(id: number | string) {
    const dimension = dimensions.value.find(dim => dim.id === id);
    if (!dimension) return;
    const current = (dimension.visibility || Visibility.SHARED) as string;
    const next = current === Visibility.PRIVATE ? Visibility.SHARED : Visibility.PRIVATE;
    loading.value = true;
    error.value = null;
    try {
      await evaluationPort.updateVisibility(id, next);
      showResultModal('成功', next === Visibility.SHARED ? '已改为共享' : '已设为私有');
      await fetchData();
    } catch (err: any) {
      console.error('Failed to toggle dimension visibility:', err);
      showResultModal('错误', err.message || '切换可见性失败，请确认您有该维度的分享权限');
    } finally {
      loading.value = false;
    }
  }

  // ========== API 健康检查 / 权重 ==========
  async function testAPIHealth(id: number | string) {
    loading.value = true;
    try {
      const result: DimensionHealthCheckResult = await evaluationPort.healthCheck(id);
      const dimension = dimensions.value.find(dim => dim.id === id) || {} as EvaluationDimension;

      const modalData: APIHealthResultModalData = {
        dimension,
        results: {
          success: result.overallStatus === ApiEndpointStatus.ONLINE || result.overallStatus === 'healthy',
          endpoints: result.results.map(r => ({
            url: r.url,
            name: r.url,
            success: r.status === ApiEndpointStatus.ONLINE || r.status === 'healthy', // healthy 为健康检查值，暂无对应枚举
            latency: r.responseTime ? parseFloat(r.responseTime) || 0 : 0,
            error: r.error
          }))
        }
      };

      modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
        title: 'API健康测试结果',
        data: modalData
      });
    } catch (err: any) {
      console.error('Failed to test API health:', err);
      showResultModal('错误', `API测试失败: ${err.message || '未知错误'}`);
    } finally {
      loading.value = false;
    }
  }

  async function updateWeight(id: number | string, weight: number) {
    loading.value = true;
    try {
      await evaluationPort.update(id, {
        weight: weight
      });

      const dimension = dimensions.value.find(dim => dim.id === id);
      if (dimension) {
        dimension.weight = weight;
      }

      showResultModal('成功', '权重更新成功');
    } catch (err: any) {
      console.error('Failed to update weight:', err);
      showResultModal('错误', `权重更新失败: ${err.message || '未知错误'}`);
    } finally {
      loading.value = false;
    }
  }

  // ========== 维度排序（上移/下移，调整报告页展示顺序） ==========

  // 是否可上移：主维度整体移动，子维度仅在同组内移动（不越过父维度或其它组）
  function canMoveUp(dim: any): boolean {
    const list = hierarchicalDimensions.value;
    const index = list.findIndex(d => d.id === dim.id);
    if (index <= 0) return false;
    // 子维度：上方必须是同一父维度的同级子维度，否则会跑到父维度上面
    if (dim._level === 1) {
      const prev = list[index - 1];
      return prev._level === 1 && prev.parentDimensionId === dim.parentDimensionId;
    }
    return true;
  }

  // 是否可下移：主维度整体移动，子维度仅在同组内移动（不越过父维度或其它组）
  function canMoveDown(dim: any): boolean {
    const list = hierarchicalDimensions.value;
    const index = list.findIndex(d => d.id === dim.id);
    if (index < 0 || index >= list.length - 1) return false;
    // 子维度：下方必须是同一父维度的同级子维度，否则会跑到其它主维度的组里
    if (dim._level === 1) {
      const next = list[index + 1];
      return next._level === 1 && next.parentDimensionId === dim.parentDimensionId;
    }
    return true;
  }

  // 上移/下移调整维度在报告页的展示顺序（主维度连同其子维度整块移动）
  async function moveDimension(id: number | string, direction: -1 | 1) {
    const list = hierarchicalDimensions.value;
    const index = list.findIndex(d => d.id === id);
    if (index < 0) return;
    if (direction === -1 ? !canMoveUp(list[index]) : !canMoveDown(list[index])) return;

    // 计算本次移动的块：主维度 = 自身 + 紧随其后的子维度；子维度 = 同一父维度的相邻同级片段
    const isMain = list[index]._level === 0;
    let blockStart = index;
    let blockEnd = index;
    if (isMain) {
      while (blockEnd < list.length - 1 && list[blockEnd + 1]._level === 1) blockEnd++;
    } else {
      const parentId = list[index].parentDimensionId;
      while (blockStart > 0 && list[blockStart - 1].parentDimensionId === parentId) blockStart--;
      while (blockEnd < list.length - 1 && list[blockEnd + 1].parentDimensionId === parentId) blockEnd++;
    }

    const ids = list.map(d => d.id);
    const block = ids.splice(blockStart, blockEnd - blockStart + 1);
    if (direction === -1) {
      ids.splice(blockStart - 1, 0, ...block);
    } else {
      // 注：V9.7.10 此处为 splice(blockStart, ...) 导致下移无效果，已修正为 blockStart + 1
      ids.splice(blockStart + 1, 0, ...block);
    }

    loading.value = true;
    error.value = null;
    try {
      await evaluationPort.reorder(ids);
      await fetchData();
    } catch (err: any) {
      console.error('Failed to reorder dimensions:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: `调整排序失败: ${err.message || '未知错误'}`,
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  return {
    saveDimension,
    deleteDimension,
    toggleDimensionVisibility,
    testAPIHealth,
    updateWeight,
    moveDimension,
    canMoveUp,
    canMoveDown,
  };
}

/** 保存/删除/健康检查/权重模块类型（由工厂推断） */
export type EvalDimensionSaveModule = ReturnType<typeof createEvalDimensionSave>;