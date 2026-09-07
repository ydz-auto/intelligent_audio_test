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
import { ApiEndpointStatus } from '../../domain/enums';
import type { DimensionHealthCheckResult } from '../../domain/model/evaluationTypes';
import type { ModalManager } from '../modal/useModal';
import { SAVE_TYPE_ADD } from './useEvaluationDimensions.constants';
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
  const { loading, error, dimensions } = state;
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
    normalizeApiSettings,
    resolveCategory,
    inheritFromParentDimension,
    normalizeApiEndpoints,
    normalizeAssociatedAlgorithms,
    normalizeLlmJudgeConfig,
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

      // 依次规范化各字段
      normalizeRule(dimensionData);
      normalizeRequiredInputs(dimensionData);
      normalizeOutputFields(dimensionData);
      normalizeApiSettings(dimensionData);
      // apiUrl 现在是字符串类型，只需修剪空格
      if (dimensionData.apiUrl !== undefined && typeof dimensionData.apiUrl === 'string') {
        dimensionData.apiUrl = dimensionData.apiUrl.trim();
      }
      await resolveCategory(dimensionData);
      inheritFromParentDimension(dimensionData);
      normalizeApiEndpoints(dimensionData);
      normalizeAssociatedAlgorithms(dimensionData);
      normalizeLlmJudgeConfig(dimensionData);

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
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '删除维度',
      content: `确定要删除维度 ${id} 吗？`,
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

  return {
    saveDimension,
    deleteDimension,
    testAPIHealth,
    updateWeight,
  };
}

/** 保存/删除/健康检查/权重模块类型（由工厂推断） */
export type EvalDimensionSaveModule = ReturnType<typeof createEvalDimensionSave>;