import { ref, watch, computed, onMounted } from 'vue'
import { useAlgorithmConfig } from '../../../composables/algorithm/useAlgorithmConfig'

export function useFormField(props: any, emit: any) {
  const fieldId = `field-${props.field.key}`
  const uploadedFile = ref(null)

  const isEmptySelect = computed(() => {
    if (props.field.type !== 'select' || !props.field.options) return false

    if (props.field.options.length === 0) return true

    if (props.field.options.length === 1) {
      const opt = props.field.options[0]
      return opt.value === '' && (opt.label.includes('无设备可用') || opt.label.includes('无可用设备'))
    }

    return false
  })

  const getInitialValue = () => {
    const val = props.modelValue !== undefined ? props.modelValue : props.value;

    switch (props.field.type) {
      case 'array':
        return Array.isArray(val) ? val : [props.field.arrayItemTemplate || { spl: null, digitalGain: null }];
      case 'checkbox':
        return Array.isArray(val) ? val : [];
      case 'number':
        return val !== undefined && val !== null ? val : 0;
      case 'switch':
        return val !== undefined && val !== null ? val : false;
      case 'apiMeta':
        return val !== undefined && val !== null && typeof val === 'object' ? val : {protocol: 'https', environment: 'development', version: 'v1', apiKey: ''};
      case 'algorithmMultiSelect':
        return Array.isArray(val) ? val : [];
      case 'algorithmSelect':
        if (Array.isArray(val) && val.length > 0) {
          return val[0]
        }
        return '';
      case 'algorithmConfigs':
        return val !== undefined && val !== null && typeof val === 'object' ? val : {};
      case 'requiredInputs':
        return Array.isArray(val) ? val : [];
      case 'multi-select-tags':
        return Array.isArray(val) ? val : [];
      case 'apiSettingsEditor':
        return val !== undefined && val !== null && typeof val === 'object' ? val : {method: 'POST', headers: {}, body_template: {}, timeout: 30000};
      case 'ruleEditor':
        return val !== undefined && val !== null && typeof val === 'object' ? val : {rules: [], defaultScore: 0};
      default:
        return val !== undefined && val !== null ? val : '';
    }
  };

  const localValue = ref(getInitialValue())
  const algorithmConfigsValue = ref({})
  const supportedAlgorithmsValue = ref([])

  const { algorithms, loadAlgorithms } = useAlgorithmConfig()

  const algorithmOptions = computed(() => {
    return (algorithms.value || []).map(algo => ({
      value: algo.type,
      label: algo.name
    }))
  })

  onMounted(async () => {
    if (algorithmOptions.value.length === 0) {
      await loadAlgorithms()
    }
  })

  watch(() => props.modelValue, (newVal) => {
    if (newVal !== undefined) {
      if (props.field.type === 'algorithmSelect' && Array.isArray(newVal) && newVal.length > 0) {
        localValue.value = newVal[0]
      } else {
        localValue.value = newVal
      }
    }
  })

  watch(() => props.value, (newVal) => {
    if (newVal !== undefined) {
      if (props.field.type === 'algorithmSelect' && Array.isArray(newVal) && newVal.length > 0) {
        localValue.value = newVal[0]
      } else {
        localValue.value = newVal
      }
    }
  })

  watch(() => props.field.options, (newOptions) => {
    console.log(`[FormField] ${props.field.key} options changed: ${newOptions ? newOptions.length : 0} items`);
  }, { deep: true })

  const handleInput = () => {
    let valueToEmit = localValue.value
    if (props.field.type === 'algorithmSelect' && localValue.value && !Array.isArray(localValue.value)) {
      valueToEmit = [localValue.value]
    }
    emit('update:value', valueToEmit)
    emit('update:modelValue', valueToEmit)
    emit('input', valueToEmit)

    console.log(`[FormField] ${props.field.key} value changed to:`, valueToEmit)
  }

  const handleAlgorithmChange = (value) => {
    localValue.value = value
    handleInput()
  }

  const handleAlgorithmConfigsChange = (value) => {
    localValue.value = value
    handleInput()
  }

  const toggleSwitch = (event) => {
    if (!props.field.disabled) {
      localValue.value = !localValue.value
      handleInput()
    }
    event.stopPropagation()
  }

  const isTagSelected = (value) => {
    if (!localValue.value || !Array.isArray(localValue.value)) return false
    return localValue.value.includes(value)
  }

  const toggleTag = (value) => {
    if (!localValue.value) {
      localValue.value = []
    }
    if (!Array.isArray(localValue.value)) {
      localValue.value = []
    }

    const index = localValue.value.indexOf(value)
    if (index === -1) {
      localValue.value.push(value)
    } else {
      localValue.value.splice(index, 1)
    }
    handleInput()
  }

  const addArrayItem = () => {
    const newItem = props.field.arrayItemTemplate || { spl: null, digitalGain: null };
    localValue.value.push({ ...newItem });
    handleInput();
  }

  const removeArrayItem = (index) => {
    if (localValue.value.length > 1) {
      localValue.value.splice(index, 1);
      handleInput();
    }
  }

  const updateGainValue = (event, item, index) => {
    const value = Number(event.target.value);
    if (props.field.arrayItemTemplate && 'gain' in props.field.arrayItemTemplate) {
      localValue.value[index].gain = value;
    } else {
      localValue.value[index].digitalGain = value;
    }
    handleInput();
  }

  const handleFileUpload = (event) => {
    const file = event.target.files[0]
    if (file) {
      uploadedFile.value = file
      emit('file-upload', { fieldKey: props.field.key, file })
      emit('update:value', file)
      emit('update:modelValue', file)
    }
  }

  const removeFile = () => {
    uploadedFile.value = null
    emit('file-upload', { fieldKey: props.field.key, file: null })
    emit('update:value', '')
    emit('update:modelValue', '')
    const input = document.getElementById(fieldId)
    if (input) {
      input.value = ''
    }
  }

  const getFileName = (file) => {
    if (!file) return ''
    return file.name
  }

  const handleButtonAction = () => {
    emit('button-action', { field: props.field, value: localValue.value })
  }

  const handleSelectClick = () => {
    if (props.field.action && !props.field.text) {
      emit('button-action', { field: props.field, value: localValue.value })
    }
  }

  // fieldKey 用于模板中 algorithmSelect 的 :id（与 fieldId 保持一致）
  const fieldKey = fieldId

  return {
    fieldId,
    fieldKey,
    uploadedFile,
    isEmptySelect,
    localValue,
    algorithmConfigsValue,
    supportedAlgorithmsValue,
    algorithmOptions,
    handleInput,
    handleAlgorithmChange,
    handleAlgorithmConfigsChange,
    toggleSwitch,
    isTagSelected,
    toggleTag,
    addArrayItem,
    removeArrayItem,
    updateGainValue,
    handleFileUpload,
    removeFile,
    getFileName,
    handleButtonAction,
    handleSelectClick
  }
}
