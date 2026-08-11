import { algorithmApi } from '../../utils/api'
import { PARAM_CODE_PRESETS, FEATURE_BUNDLES } from './algorithmConstants'

export function useAlgorithmFeatureBundles(
  formState: any,
  clearFormSchemaCache: () => void,
  autoSaveCaseParams: (param: any, index: number) => Promise<void>
) {
  function isBundleActive(bundleKey: string): boolean {
    const bundle = FEATURE_BUNDLES[bundleKey]
    if (!bundle) return false
    const codes = new Set(formState.case_params.map((p: any) => p.param_code))
    return bundle.params.every((code) => codes.has(code))
  }

  async function deleteCaseParams(params: any[]) {
    if (!formState.type) return
    for (const p of params) {
      if (p.id) {
        try {
          await algorithmApi.deleteCaseParam(p.id)
        } catch (e) {
          console.error('[toggleBundle] 删除参数失败:', p.param_code, e)
        }
      }
    }
    // 清除算法参数缓存，确保用例页面能获取最新参数
    clearFormSchemaCache()
  }

  async function saveCaseParams() {
    if (!formState.type) return
    try {
      // 只保存没有 id 的新参数（已存在的参数不需要重复保存）
      for (let i = 0; i < formState.case_params.length; i++) {
        const p = formState.case_params[i]
        if (!p.id && p.param_code) {
          await autoSaveCaseParams(p, i)
        }
      }
    } catch (e) {
      console.error('[toggleBundle] 保存失败:', e)
    }
  }

  async function toggleBundle(bundleKey: string) {
    const bundle = FEATURE_BUNDLES[bundleKey]
    if (!bundle) return
    const codes = new Set(formState.case_params.map((p: any) => p.param_code))
    const hasAll = bundle.params.every((code) => codes.has(code))
    if (hasAll) {
      // 取消勾选：从 DB 删除该 bundle 的所有参数，并从 formState 移除
      const removed = formState.case_params.filter((p: any) => bundle.params.includes(p.param_code))
      formState.case_params = formState.case_params.filter((p: any) => !bundle.params.includes(p.param_code))
      // 已入库的参数立即调用 DELETE，未入库的（无 id）无需处理
      await deleteCaseParams(removed)
    } else {
      // 添加缺失的参数
      for (const code of bundle.params) {
        if (!codes.has(code)) {
          const preset = PARAM_CODE_PRESETS[code]
          formState.case_params.push({
            param_code: code,
            param_name: preset?.param_name || code,
            param_type: preset?.param_type || 'text',
            scope: bundle.scope,
            required: false,
            default_value: preset?.default_value ?? '',
            help_text: preset?.help_text || '',
            min_value: preset?.min_value,
            max_value: preset?.max_value,
            step: preset?.step,
            unit: preset?.unit,
            annotation_code: null,
            field_path: null,
            hidden: false,
            deleted: false,
            tempId: `temp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          })
        }
      }
      // 触发保存（新建未入库的参数）
      await saveCaseParams()
    }
  }

  return {
    isBundleActive,
    toggleBundle,
  }
}
