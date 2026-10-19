<template>
  <div class="api-edit-modal">
    <div class="modal-header">
      <h3>{{ title || 'API设置' }}</h3>
    </div>
    
    <div class="modal-body">
      <div class="form-group">
        <label class="form-label">API名称</label>
        <input 
          type="text" 
          v-model="editableData.name" 
          class="form-input"
          placeholder="请输入API名称"
        >
      </div>
      
      <div class="form-group">
        <label class="form-label">API密钥</label>
        <input 
          type="password" 
          v-model="editableData.apiKey" 
          class="form-input"
          placeholder="请输入API密钥"
        >
      </div>
      
      <div class="form-group">
        <label class="form-label">API端点</label>
        <input 
          type="text" 
          v-model="editableData.apiUrl" 
          class="form-input"
          placeholder="请输入API端点URL"
        >
      </div>
      
      <div class="form-group">
        <label class="form-label">模型</label>
        <input
          type="text"
          v-model="editableData.model"
          class="form-input"
          placeholder="请输入模型名称"
        >
      </div>

      <div class="form-group">
        <label class="form-label">代理类型</label>
        <select v-model="editableData.proxyType" class="form-input">
          <option value="">不使用代理</option>
          <option value="http">http</option>
          <option value="https">https</option>
          <option value="socks5">socks5</option>
          <option value="socks5h">socks5h</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">代理地址</label>
        <input
          type="text"
          v-model="editableData.proxyUrl"
          class="form-input"
          placeholder="user:pass@host:port"
        >
        <span class="form-hint">格式 user:pass@host:port，不含 scheme；选择代理类型时必填</span>
      </div>

      <div class="form-group">
        <label class="form-label">其他配置</label>
        <textarea 
          v-model="configJson" 
          class="form-textarea"
          placeholder="请输入JSON格式的其他配置"
          rows="4"
        ></textarea>
      </div>
    </div>
    
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleClose">
        取消
      </button>
      <button type="button" class="btn btn-primary" @click="handleSave">
        保存
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useNotification } from '@/composables/modal/useNotification';
import type { ProxyType } from '@/domain/model/apiConfig';

interface APIEditData {
  name?: string;
  apiKey?: string;
  apiUrl?: string;
  model?: string;
  /** 网络代理类型（http/https/socks5/socks5h；空 = 不使用代理） */
  proxyType?: ProxyType | '';
  /** 网络代理地址 [user:pass@]host:port（不含 scheme） */
  proxyUrl?: string;
  config?: Record<string, any>;
  [key: string]: any;
}

const props = defineProps<{
  title?: string;
  data?: APIEditData;
  onSave?: (settings: APIEditData) => void;
}>();

const emit = defineEmits(['close', 'save']);

const notification = useNotification();

const editableData = ref<APIEditData>({});
const configJson = ref('');

watch(() => props.data, (newData) => {
  if (newData) {
    editableData.value = { ...newData };
    configJson.value = newData.config ? JSON.stringify(newData.config, null, 2) : '';
  }
}, { immediate: true, deep: true });

const handleClose = () => {
  emit('close');
};

/**
 * 代理配置校验（与后端同规则，前后端双校验）：
 * proxy_type 非空 → proxy_url 必填且必须带 user:pass@ 前缀；
 * proxy_type 为空 → proxy_url 必须为空。
 */
const validateProxy = (): string | null => {
  const proxyType = editableData.value.proxyType;
  const proxyUrl = editableData.value.proxyUrl?.trim();
  if (proxyType) {
    if (!proxyUrl) {
      return '已选择代理类型时，代理地址必填（格式 user:pass@host:port）';
    }
    if (!/^[^:@]+:[^@]+@\S+$/.test(proxyUrl)) {
      return '代理地址必须以 user:pass@ 开头（格式 user:pass@host:port）';
    }
  } else if (proxyUrl) {
    return '未选择代理类型时，代理地址必须为空';
  }
  return null;
};

const handleSave = () => {
  const proxyError = validateProxy();
  if (proxyError) {
    notification.warning(proxyError);
    return;
  }
  try {
    const config = configJson.value ? JSON.parse(configJson.value) : {};
    const proxyUrl = editableData.value.proxyUrl?.trim();
    const settings: APIEditData = { ...editableData.value, config };
    if (proxyUrl) {
      settings.proxyUrl = proxyUrl;
    } else {
      delete settings.proxyUrl;
    }

    if (props.onSave) {
      props.onSave(settings);
    } else {
      emit('save', settings);
    }

    emit('close');
  } catch (e) {
    notification.warning('配置JSON格式不正确，请检查JSON语法');
  }
};
</script>

<style scoped>

.form-textarea{
    resize: vertical;
    min-height: 100px;
}




.api-edit-modal{
  padding: 20px;
}

.modal-header{
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-slate-200);
}

.modal-header h3{
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-slate-700);
}

.modal-body{
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group{
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label{
  font-size: 14px;
  font-weight: 500;
  color: var(--color-slate-600);
}

.form-hint{
  font-size: 12px;
  color: var(--color-slate-500);
}

.form-input,
.form-textarea{
  padding: 10px 12px;
  font-size: 14px;
  border: 1px solid var(--color-slate-200);
  border-radius: 6px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.form-input:focus,
.form-textarea:focus{
  outline: none;
  border-color: var(--color-blue-500);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-blue-500) 10%, transparent);
}



.modal-footer{
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--color-slate-200);
}

.btn{
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-secondary{
  background-color: var(--color-slate-100);
  border: 1px solid var(--color-slate-200);
  color: var(--color-slate-600);
}

.btn-secondary:hover{
  background-color: var(--color-slate-200);
}

.btn-primary{
  background-color: var(--color-blue-500);
  border: 1px solid var(--color-blue-500);
  color: white;
}

.btn-primary:hover{
  background-color: var(--color-blue-600);
  border-color: var(--color-blue-600);
}
</style>
