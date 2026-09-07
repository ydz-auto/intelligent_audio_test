import { ref, nextTick } from 'vue'
import { algorithmPort } from '../../composables/algorithm/algorithmPort'
import { PARAM_CODE_PRESETS } from './algorithmConstants'
import { getDefaultComponent, buildReferenceParamData } from './algorithmParamHelpers'
import { useNotification } from '../../composables/modal/useNotification'

export function useAlgorithmParamOps(
  formState: any,
  paramConfigType: any,
  effectiveMode: any,
  paramIdCounter: { value: number }
) {
  const notification = useNotification()
  let saveTimeout: any = null
  let caseParamSaveTimeout: any = null
  let referenceParamSaveTimeout: any = null

  function handleAddParam() {
    const isCase = paramConfigType.value === 'case'
    const tempId = `temp_${++paramIdCounter.value}`
    if (isCase) {
      formState.caseParams.push({
        tempId,
        paramCode: '',
        paramName: '',
        paramType: 'text',
        component: 'input',
        scope: 'common',
        required: false,
        defaultValue: '',
        minValue: null,
        maxValue: null,
        step: null,
        unit: '',
        helpText: '',
        annotationCode: null,
        fieldPath: null,
        uiOrder: formState.caseParams.length
      })
    } else {
      const params = paramConfigType.value === 'device' ? formState.deviceParams : formState.apiParams
      params.push({
        tempId,
        paramCode: '',
        paramName: '',
        direction: 'input',
        paramType: 'text',
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
    const param = formState.caseParams[index]
    if (param && param.id) {
      const backup = { ...param }
      formState.caseParams.splice(index, 1)
      algorithmPort.deleteCaseParam(param.id).catch(err => {
        console.error('删除用例参数失败:', err)
        formState.caseParams.splice(index, 0, backup)
        notification.error('删除用例参数失败，已恢复')
      })
    } else {
      formState.caseParams.splice(index, 1)
    }
  }

  function handleAddReferenceParam() {
    formState.referenceParams.push({
      tempId: `temp_ref_${++paramIdCounter.value}`,
      code: '',
      name: '',
      type: 'text',
      annotationCode: formState.type || '',
      annotationFormat: '',
      fieldPath: '',
      mergeMode: 'join',
      helpText: ''
    })
  }

  function handleRemoveReferenceParam(index: number) {
    const param = formState.referenceParams[index]
    if (param && param.id) {
      const backup = { ...param }
      formState.referenceParams.splice(index, 1)
      algorithmPort.deleteReferenceParam(param.id, formState.type).catch(err => {
        console.error('删除参考参数失败:', err)
        formState.referenceParams.splice(index, 0, backup)
        notification.error('删除参考参数失败，已恢复')
      })
    } else {
      formState.referenceParams.splice(index, 1)
    }
  }

  function handleCaseParamTypeChange(param: any, index: number) {
    param.component = getDefaultComponent(param.paramType)
    handleCaseParamBlur(param, index)
  }

  async function handleParamBlur(param: any, index: number, paramType: string) {
    if (!formState.type || !param.paramCode) return
    if (saveTimeout) clearTimeout(saveTimeout)
    saveTimeout = setTimeout(async () => {
      await autoSaveParams(param, paramType)
    }, 1500)
  }

  function handleParamCodeSelect(param: any, index: number) {
    const preset = PARAM_CODE_PRESETS[param.paramCode]
    if (preset && !param.paramName) {
      param.paramName = preset.paramName
      param.paramType = preset.paramType
      param.component = getDefaultComponent(preset.paramType)
      if (preset.defaultValue !== undefined) param.defaultValue = preset.defaultValue
      if (preset.helpText) param.helpText = preset.helpText
      if (preset.minValue !== undefined) param.minValue = preset.minValue
      if (preset.maxValue !== undefined) param.maxValue = preset.maxValue
      if (preset.step !== undefined) param.step = preset.step
      if (preset.unit) param.unit = preset.unit
    }
    handleCaseParamBlur(param, index)
  }

  async function handleCaseParamBlur(param: any, index: number) {
    if (!formState.type || !param.paramCode) return
    if (caseParamSaveTimeout) clearTimeout(caseParamSaveTimeout)
    caseParamSaveTimeout = setTimeout(async () => {
      await autoSaveCaseParams(param, index)
    }, 1000)
  }

  async function autoSaveParams(param: any, paramType: string) {
    if (!formState.type || !param.paramCode) return
    try {
      // 提交 bodyData 为 camelCase Domain 字段，algorithmPort 内部做 snake_case 转换
      const bodyData: any = {
        algorithmType: formState.type,
        paramTypeSource: paramType,
        paramCode: param.paramCode,
        paramName: param.paramName,
        paramType: param.paramType,
        direction: param.direction,
        required: param.required,
        defaultValue: param.defaultValue,
        validationRules: param.validationRules,
        helpText: param.helpText,
        uiOrder: param.uiOrder,
        hidden: param.hidden
      }
      let result
      if (param.id) {
        result = await algorithmPort.updateParam(param.id, bodyData)
      } else {
        result = await algorithmPort.createParam(bodyData)
        param.id = result.id
      }
    } catch (error) {
      console.error('自动保存参数失败:', error)
    }
  }

  async function autoSaveCaseParams(param: any, index: number) {
    if (!formState.type || !param.paramCode) return
    // 检查 paramCode 是否重复
    const duplicates = formState.caseParams.filter((p: any) => p.paramCode === param.paramCode)
    if (duplicates.length > 1) {
      console.warn(`参数代码 "${param.paramCode}" 重复，跳过自动保存`)
      return
    }
    try {
      const bodyData: any = {
        algorithmType: formState.type,
        paramCode: param.paramCode,
        paramName: param.paramName,
        paramType: param.paramType,
        required: param.required,
        defaultValue: param.defaultValue,
        helpText: param.helpText,
        component: param.component,
        uiOrder: param.uiOrder,
        hidden: param.hidden,
        scope: param.scope || 'common',
        minValue: param.minValue,
        maxValue: param.maxValue,
        step: param.step,
        unit: param.unit,
        annotationCode: param.annotationCode || null,
        fieldPath: param.fieldPath || null
      }
      let result
      if (param.id) {
        result = await algorithmPort.updateCaseParam(param.id, bodyData)
      } else {
        result = await algorithmPort.createCaseParam(bodyData)
        param.id = result.id
      }
    } catch (error) {
      console.error('自动保存用例参数失败:', error)
    }
  }

  async function handleReferenceParamBlur(param: any, index: number) {
    // 自动同步：annotationCode 为空时填充为 code
    if (!param.annotationCode && param.code) {
      param.annotationCode = param.code
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
        result = await algorithmPort.updateReferenceParam(param.id, formState.type, bodyData)
      } else {
        result = await algorithmPort.createReferenceParam({ ...bodyData, algorithmType: formState.type })
        param.id = result.id
      }
    } catch (error) {
      console.error('自动保存参考参数失败:', error)
    }
  }

  async function savePendingReferenceParams() {
    // 新建模式下，参考参数此前被跳过（算法定义未创建）；算法创建成功后统一补存
    for (const p of formState.referenceParams as any[]) {
      if (p.id || !p.code) continue
      try {
        const res = await algorithmPort.createReferenceParam({ ...buildReferenceParamData(p), algorithmType: formState.type })
        p.id = res.id
      } catch (e) {
        console.error('保存参考参数失败:', e)
      }
    }
  }

  function handleRemoveParam(index: number) {
    const params = paramConfigType.value === 'device' ? formState.deviceParams : formState.apiParams
    const param = params[index]
    if (param && param.id) {
      const backup = { ...param }
      params.splice(index, 1)
      algorithmPort.deleteParam(param.id).catch(err => {
        console.error('删除参数失败:', err)
        params.splice(index, 0, backup)
        notification.error('删除参数失败，已恢复')
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
