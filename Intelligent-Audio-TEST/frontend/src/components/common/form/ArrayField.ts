import { ref, watch } from 'vue'

export interface Field {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  [key: string]: any;
}

export function useArrayField(
  props: { field: Field; value: any[]; modelValue: any[]; error: string },
  emit: (e: any, ...args: any[]) => void
) {
  const fieldId = `field-${props.field.key}`

  // 记录当前正在播放的索引
  const playingIndex = ref<number | null>(null);

  const getInitialValue = () => {
    if (props.modelValue !== undefined && Array.isArray(props.modelValue)) {
      return [...props.modelValue];
    }
    if (props.value !== undefined && Array.isArray(props.value)) {
      return [...props.value];
    }

    // 优先使用字段模板
    if (props.field && props.field.arrayItemTemplate) {
      return [{ ...props.field.arrayItemTemplate }];
    }

    // 根据类型返回默认模板
    if (props.field?.arrayItemType === 'apiEndpoint') {
      return [{
        endpoint: '',
        name: '',
        priority: 1,
        maxProcess: 5,
        maxTimeout: 30,
        maxAudioDuration: 60
      }];
    }

    // 默认返回一个最基本的模板项
    return [{ digital_gain: null, spl: null }];
  };

  const localValue = ref(getInitialValue())

  watch(() => props.modelValue, (newVal) => {
    if (Array.isArray(newVal)) {
      localValue.value = [...newVal]
    } else if (newVal === undefined && localValue.value.length === 0) {
      // 防止 modelValue 变为 undefined 时清空数组
      const template = props.field?.arrayItemTemplate || { digital_gain: null, spl: null };
      if (localValue.value.length === 0) {
        localValue.value = [{ ...template }];
      }
    }
  }, { deep: true })

  watch(() => props.value, (newVal) => {
    if (Array.isArray(newVal)) {
      localValue.value = [...newVal]
    } else if (newVal === undefined && localValue.value.length === 0) {
      // 防止 value 变为 undefined 时清空数组
      const template = props.field?.arrayItemTemplate || { digital_gain: null, spl: null };
      if (localValue.value.length === 0) {
        localValue.value = [{ ...template }];
      }
    }
  }, { deep: true })

  const handleInput = () => {
    emit('update:value', [...localValue.value])
    emit('update:modelValue', [...localValue.value])
    emit('input', [...localValue.value])
  }

  const addArrayItem = () => {
    let template = props.field.arrayItemTemplate || { digital_gain: null, spl: null };

    if (props.field.arrayItemType === 'apiEndpoint') {
      const defaultMaxProcess = 5;
      const defaultMaxTimeout = 30;
      const defaultMaxAudioDuration = 60;

      template = {...template, maxProcess: defaultMaxProcess, maxTimeout: defaultMaxTimeout, maxAudioDuration: defaultMaxAudioDuration};
    }

    localValue.value.push({ ...template });
    handleInput();
  };

  const removeArrayItem = (index: number) => {
    if (localValue.value.length > 1) {
      localValue.value.splice(index, 1)
      handleInput()
    }
  }

  const updateAPIUrl = (event: Event, index: number) => {
    const value = (event.target as HTMLInputElement).value;
    const newItem = { ...localValue.value[index] };
    newItem.endpoint = value;
    newItem.url = value;
    localValue.value.splice(index, 1, newItem);
    handleInput();
  }

  const updateSPLValue = (event: Event, index: number) => {
    const value = Number((event.target as HTMLInputElement).value);
    const newItem = { ...localValue.value[index] };
    newItem.spl = value;
    localValue.value.splice(index, 1, newItem);
    handleInput();
  }

  const updateGainOffset = (event: Event, index: number) => {
    const rawValue = (event.target as HTMLInputElement).value;
    const newItem = { ...localValue.value[index] };

    if (rawValue === '' || rawValue === '-') {
      newItem.gainOffset = null;
    } else {
      const value = Number(rawValue);
      newItem.gainOffset = isNaN(value) ? null : value;
    }

    localValue.value.splice(index, 1, newItem);
    handleInput();
  }

  const BASE_LEVEL_DBFS = -30;
  const MAX_FINAL_LEVEL_DBFS = -5;
  const MAX_GAIN_OFFSET = MAX_FINAL_LEVEL_DBFS - BASE_LEVEL_DBFS;

  const getGainOffset = (gainValue: number | null): string => {
    if (gainValue === null || gainValue === undefined) {
      return '0.00';
    }
    const offset = (gainValue - 50) * 0.24;
    return offset.toFixed(2);
  }

  const getFinalLevelDbfs = (item: any): number => {
    if (!item) {
      return BASE_LEVEL_DBFS;
    }
    let gainOffsetDb = 0;
    if (item.gainOffset !== undefined && item.gainOffset !== null) {
      const val = Number(item.gainOffset);
      if (!isNaN(val)) {
        gainOffsetDb = val;
      }
    } else if (item.digital_gain !== undefined && item.digital_gain !== null && item.digital_gain !== '') {
      const val = Number(item.digital_gain);
      if (!isNaN(val)) {
        gainOffsetDb = (val - 50) * 0.24;
      }
    } else if (item.gain !== undefined && item.gain !== null && item.gain !== '') {
      const val = Number(item.gain);
      if (!isNaN(val)) {
        gainOffsetDb = (val - 50) * 0.24;
      }
    }
    return BASE_LEVEL_DBFS + gainOffsetDb;
  }

  const getFinalLevel = (item: any): string => {
    const finalLevel = getFinalLevelDbfs(item);
    return `${finalLevel.toFixed(2)} dBFS`;
  }

  const canTestSPL = (index: number): boolean => {
    const item = localValue.value[index];
    if (!item) return false;

    // 检查 gainOffset 是否有值（包括 0）
    const hasGainOffset = item.gainOffset !== null && item.gainOffset !== undefined;
    if (hasGainOffset) return true;

    // 检查 digital_gain 或 gain 是否有值（兼容旧数据）
    const hasDigitalGain = (item.digital_gain !== null && item.digital_gain !== undefined && item.digital_gain !== '') ||
                           (item.gain !== null && item.gain !== undefined && item.gain !== '');
    return hasDigitalGain;
  }

  const testSPL = (index: number) => {
    // 如果当前有正在播放的其他测试音，先停止它
    if (playingIndex.value !== null && playingIndex.value !== index) {
      console.log(`[testSPL] 正在播放索引 ${playingIndex.value}，先停止它`);
      stopSPL(playingIndex.value);
    }

    let item = localValue.value[index];

    // 如果本地值不存在，尝试从 DOM 读取
    if (!item) {
      const arrayField = document.querySelector('.array-field');
      if (arrayField) {
        const arrayItems = arrayField.querySelectorAll('.array-item');
        if (arrayItems[index]) {
          const gainOffsetInput = arrayItems[index].querySelector('.gain-offset-wrapper input') as HTMLInputElement;
          const splInput = arrayItems[index].querySelector('.spl-input-wrapper input') as HTMLInputElement;

          if (gainOffsetInput) {
            item = {
              gainOffset: gainOffsetInput.value !== '' ? Number(gainOffsetInput.value) : null,
              spl: splInput && splInput.value !== '' ? Number(splInput.value) : null
            };
            console.log(`[testSPL] 从DOM读取数据:`, item);
          }
        }
      }
    }

    if (!item) {
      console.warn(`[testSPL] 未找到索引 ${index} 的校准点数据`);
      return;
    }

    // 确定 gainOffsetValue 和 gainValue
    let gainOffsetValue: number | null = null;
    let gainValue: number | null = null;

    if (item.gainOffset !== undefined && item.gainOffset !== null) {
      gainOffsetValue = Number(item.gainOffset);
      if (!isNaN(gainOffsetValue)) {
        gainValue = 50 + gainOffsetValue / 0.24;
      }
    } else {
      // 尝试从 digital_gain 或 gain 获取
      const digitalGain = item.digital_gain ?? item.gain;
      if (digitalGain !== undefined && digitalGain !== null && digitalGain !== '') {
        gainValue = Number(digitalGain);
        if (!isNaN(gainValue)) {
          gainOffsetValue = (gainValue - 50) * 0.24;
        }
      }
    }

    if (gainOffsetValue === null || isNaN(gainOffsetValue)) {
      console.warn(`[testSPL] 增益偏移无效:`, item.gainOffset);
      return;
    }

    const splValue = (item.spl !== undefined && item.spl !== null && item.spl !== '')
      ? Number(item.spl)
      : null;

    console.log(`[testSPL] 点击测试声压按钮: index=${index}, item=`, item, 'gainValue=', gainValue, 'gainOffset=', gainOffsetValue, 'splValue=', splValue);

    playingIndex.value = index;
    console.log(`[testSPL] 发送 test-spl 事件`);
    emit('test-spl', { index, gainValue: gainValue as number, splValue: splValue as any, gainOffset: gainOffsetValue });
  }

  const stopSPL = (index: number) => {
    console.log(`[stopSPL] 停止测试声压: index=${index}`);
    playingIndex.value = null;
    emit('stop-spl', { index });
  }

  const isPlaying = (index: number): boolean => {
    return playingIndex.value === index;
  }

  return {
    fieldId,
    localValue,
    playingIndex,
    handleInput,
    addArrayItem,
    removeArrayItem,
    updateAPIUrl,
    updateSPLValue,
    updateGainOffset,
    getGainOffset,
    getFinalLevelDbfs,
    getFinalLevel,
    canTestSPL,
    testSPL,
    stopSPL,
    isPlaying
  }
}
