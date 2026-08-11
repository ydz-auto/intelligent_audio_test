import { ref, nextTick } from 'vue'
import { algorithmApi } from '../../utils/api'
import { PARAM_CODE_PRESETS } from './algorithmConstants'
import { getDefaultComponent, buildReferenceParamData } from './algorithmParamHelpers'

export function useAlgorithmParamOps(
  formState: any,
  paramConfigType: any,
  effectiveMode: any,
  paramIdCounter: { value: number }
) {
  let saveTimeout: any = null
  let caseParamSaveTimeout: any = null
  let referenceParamSaveTimeout: any = null

  function handleAddParam() {
    const isCase = paramConfigType.value === 'case'
    const tempId = `temp_${++paramIdCounter.value}`
    if (isCase) {
      formState.case_params.push({
        tempId,
        param_code: '',
        param_name: '',
        param_type: 'text',
        component: 'input',
        scope: 'common',
        required: false,
        default_value: '',
        min_value: null,
        max_value: null,
        step: null,
        unit: '',
        help_text: '',
        annotation_code: null,
        field_path: null,
        ui_order: formState.case_params.length
      })
    } else {
      const params = paramConfigType.value === 'device' ? formState.device_params : formState.api_params
      params.push({
        tempId,
        param_code: '',
        param_name: '',
        direction: 'input',
        param_type: 'text',
        required: false
      })
    }
    nextTick(() => {
      const inputs = document.querySelectorAll('.param-code-input')
      if (inputs.length > 0) {
        const lastInput = inputs[inputs.length - 1] as HTMLInputElement
        lastInput.focus()
      }
    })
  }

  function handleRemoveCaseParam(index: number) {
    const param = formState.case_params[index]
    if (param && param.id) {
      const backup = { ...param }
      formState.case_params.splice(index, 1)
      algorithmApi.deleteCaseParam(param.id).catch(err => {
        console.error('删除用例参数失败:', err)
        formState.case_params.splice(index, 0, backup)
        alert('删除用例参数失败，已恢复')
      })
    } else {
      formState.case_params.splice(index, 1)
    }
  }

  function handleAddReferenceParam() {
    formState.reference_params.push({
      tempId: `temp_ref_${++paramIdCounter.value}`,
      code: '',
      name: '',
      type: 'text',
      annotation_code: formState.type || '',
      annotation_format: '',
      field_path: '',
      merge_mode: 'join',
      help_text: ''
    })
  }

  function handleRemoveReferenceParam(index: number) {
    const param = formState.reference_params[index]
    if (param && param.id) {
      const backup = { ...param }
      formState.reference_params.splice(index, 1)
      algorithmApi.deleteReferenceParam(param.id, formState.type).catch(err => {
        console.error('删除参考参数失败:', err)
        formState.reference_params.splice(index, 0, backup)
        alert('删除参考参数失败，已恢复')
      })
    } else {
      formState.reference_params.splice(index, 1)
    }
  }

  function handleCaseParamTypeChange(param: any, index: number) {
    param.component = getDefaultComponent(param.param_type)
    handleCaseParamBlur(param, index)
  }

  async function handleParamBlur(param: any, index: number, paramType: string) {
    if (!formState.type || !param.param_code) return
    if (saveTimeout) clearTimeout(saveTimeout)
    saveTimeout = setTimeout(async () => {
      await autoSaveParams(param, paramType)
    }, 1500)
  }

  function handleParamCodeSelect(param: any, index: number) {
    const preset = PARAM_CODE_PRESETS[param.param_code]
    if (preset && !param.param_name) {
      param.param_name = preset.param_name
      param.param_type = preset.param_type
      param.component = getDefaultComponent(preset.param_type)
      if (preset.default_value !== undefined) param.default_value = preset.default_value
      if (preset.help_text) param.help_text = preset.help_text
      if (preset.min_value !== undefined) param.min_value = preset.min_value
      if (preset.max_value !== undefined) param.max_value = preset.max_value
      if (preset.step !== undefined) param.step = preset.step
      if (preset.unit) param.unit = preset.unit
    }
    handleCaseParamBlur(param, index)
  }

  async function handleCaseParamBlur(param: any, index: number) {
    if (!formState.type || !param.param_code) return
    if (caseParamSaveTimeout) clearTimeout(caseParamSaveTimeout)
    caseParamSaveTimeout = setTimeout(async () => {
      await autoSaveCaseParams(param, index)
    }, 1000)
  }

  async function autoSaveParams(param: any, paramType: string) {
    if (!formState.type || !param.param_code) return
    try {
      const bodyData: any = {
        algorithm_type: formState.type,
        param_type_source: paramType,
        param_code: param.param_code,
        param_name: param.param_name,
        param_type: param.param_type,
        direction: param.direction,
        required: param.required,
        default_value: param.default_value,
        validation_rules: param.validation_rules,
        help_text: param.help_text,
        ui_order: param.ui_order,
        hidden: param.hidden
      }
      let result
      if (param.id) {
        result = await algorithmApi.updateParam(param.id, bodyData)
      } else {
        result = await algorithmApi.createParam(bodyData)
        param.id = result.id
      }
    } catch (error) {
      console.error('自动保存参数失败:', error)
    }
  }

  async function autoSaveCaseParams(param: any, index: number) {
    if (!formState.type || !param.param_code) return
    // 检查 param_code 是否重复
    const duplicates = formState.case_params.filter((p: any) => p.param_code === param.param_code)
    if (duplicates.length > 1) {
      console.warn(`参数代码 "${param.param_code}" 重复，跳过自动保存`)
      return
    }
    try {
      const bodyData: any = {
        algorithm_type: formState.type,
        param_code: param.param_code,
        param_name: param.param_name,
        param_type: param.param_type,
        required: param.required,
        default_value: param.default_value,
        help_text: param.help_text,
        component: param.component,
        ui_order: param.ui_order,
        hidden: param.hidden,
        scope: param.scope || 'common',
        min_value: param.min_value,
        max_value: param.max_value,
        step: param.step,
        unit: param.unit,
        annotation_code: param.annotation_code || null,
        field_path: param.field_path || null
      }
      let result
      if (param.id) {
        result = await algorithmApi.updateCaseParam(param.id, bodyData)
      } else {
        result = await algorithmApi.createCaseParam(bodyData)
        param.id = result.id
      }
    } catch (error) {
      console.error('自动保存用例参数失败:', error)
    }
  }

  async function handleReferenceParamBlur(param: any, index: number) {
    // 自动同步：annotation_code 为空时填充为 code
    if (!param.annotation_code && param.code) {
      param.annotation_code = param.code
    }
    if (!formState.type || !param.code) return
    if (referenceParamSaveTimeout) clearTimeout(referenceParamSaveTimeout)
    referenceParamSaveTimeout = setTimeout(async () => {
      await autoSaveReferenceParams(param, index)
    }, 1000)
  }

  async function autoSaveReferenceParams(param: any, index: number) {
    // 新建模式下算法定义尚未创建，参考参数受外键约束无法提前自动保存，统一留待 saveAlgorithm 创建后补存
    if (effectiveMode.value !== 'edit') return
    if (!formState.type || !param.code) return
    try {
      const bodyData = buildReferenceParamData(param)
      let result
      if (param.id) {
        result = await algorithmApi.updateReferenceParam(param.id, formState.type, bodyData)
      } else {
        result = await algorithmApi.createReferenceParam({ ...bodyData, algorithm_type: formState.type })
        param.id = result.id
      }
    } catch (error) {
      console.error('自动保存参考参数失败:', error)
    }
  }

  async function savePendingReferenceParams() {
    // 新建模式下，参考参数此前被跳过（算法定义未创建）；算法创建成功后统一补存
    for (const p of formState.reference_params as any[]) {
      if (p.id || !p.code) continue
      try {
        const res = await algorithmApi.createReferenceParam({ ...buildReferenceParamData(p), algorithm_type: formState.type })
        p.id = res.id
      } catch (e) {
        console.error('保存参考参数失败:', e)
      }
    }
  }

  function handleRemoveParam(index: number) {
    const params = paramConfigType.value === 'device' ? formState.device_params : formState.api_params
    const param = params[index]
    if (param && param.id) {
      const backup = { ...param }
      params.splice(index, 1)
      algorithmApi.deleteParam(param.id).catch(err => {
        console.error('删除参数失败:', err)
        params.splice(index, 0, backup)
        alert('删除参数失败，已恢复')
      })
    } else {
      params.splice(index, 1)
    }
  }

  return {
    handleAddParam,
    handleRemoveCaseParam,
    handleAddReferenceParam,
    handleRemoveReferenceParam,
    handleCaseParamTypeChange,
    handleParamBlur,
    handleParamCodeSelect,
    handleCaseParamBlur,
    autoSaveCaseParams,
    handleReferenceParamBlur,
    autoSaveReferenceParams,
    savePendingReferenceParams,
    handleRemoveParam,
  }
}
