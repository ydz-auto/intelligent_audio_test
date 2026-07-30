<template>
  <div class="group-form">
    <div class="form-row">
      <div class="form-group">
        <label for="groupName">组名称</label>
        <input type="text" id="groupName" v-model="localFormData.name" class="form-control">
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label for="groupDescription">描述</label>
        <textarea id="groupDescription" v-model="localFormData.description" class="form-control"></textarea>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label for="groupAlgorithmType">关联算法类型</label>
        <select id="groupAlgorithmType" v-model="localFormData.algorithmType" class="form-control">
          <option value="">不关联算法</option>
          <option v-for="algo in algorithmOptions" :key="algo.value" :value="algo.value">
            {{ algo.name || algo.value }}
          </option>
        </select>
        <small class="form-text text-muted">选择关联算法后，该分组下的用例将默认使用此算法类型</small>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { useAlgorithmConfig } from '../../../../composables/algorithm/useAlgorithmConfig';
import { useAlgorithmLabels } from '../../../../composables/algorithm/useAlgorithmLabels';
import type { GroupFormData } from './types';

const props = defineProps<{
  formData: Partial<GroupFormData>;
}>();

const emit = defineEmits<{
  (e: 'update', data: GroupFormData): void;
}>();

const { getAlgorithmOptions } = useAlgorithmConfig();
const { algorithmOptions: fallbackOptions, loadAlgorithms } = useAlgorithmLabels();

const localFormData = ref<GroupFormData>({
  name: '',
  description: '',
  algorithmType: ''
});

const algorithmOptions = ref<{ value: string; name: string }[]>([]);

async function loadAlgorithmOptions() {
  try {
    const options = await getAlgorithmOptions();
    algorithmOptions.value = (options || []).map((opt: any) => ({
      value: opt.value,
      name: opt.name || opt.label || opt.value
    }));
  } catch (error) {
    console.error('加载算法选项失败:', error);
    algorithmOptions.value = fallbackOptions.value.length > 0
      ? fallbackOptions.value.map((opt: any) => ({ value: opt.value, name: opt.label }))
      : [
          { value: 'translation', name: '翻译' },
          { value: 'asr', name: 'ASR识别' },
          { value: 'speaker_recognition', name: '说话人识别' },
          { value: 'tts', name: '语音合成' },
          { value: 'asr_eval', name: 'ASR评估' }
        ];
  }
}

function initFormData() {
  localFormData.value = {
    name: props.formData.name || '',
    description: props.formData.description || '',
    algorithmType: props.formData.algorithmType || ''
  };
}

watch(() => props.formData, () => {
  initFormData();
}, { immediate: true, deep: true });

watch(() => localFormData.value, (newVal) => {
  emit('update', { ...newVal });
}, { deep: true });

onMounted(async () => {
  await loadAlgorithms();
  await loadAlgorithmOptions();
  initFormData();
});
</script>

<style scoped>
.group-form {
  padding: 0;
}

.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.form-group {
  flex: 1;
  min-width: 200px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

.form-text {
  font-size: 12px;
  color: #6c757d;
  margin-top: 4px;
  display: block;
}
</style>
