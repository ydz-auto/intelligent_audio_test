<template>
  <div class="import-form">
    <div class="form-section">
      <h5>
        导入配置
        <button type="button" class="btn btn-outline-primary btn-sm ml-2" @click="downloadTemplate">
          <i class="fas fa-download"></i> 下载模板
        </button>
      </h5>
      <div class="form-row">
        <div class="form-group">
          <label for="import-file">选择文件 <span class="required">*</span></label>
          <div
            class="file-upload"
            :class="{ 'is-dragging': isDragging }"
            @click="triggerFileSelect"
            @dragenter.prevent="isDragging = true"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="handleDrop"
          >
            <i class="fas fa-upload" style="font-size: 32px; color: var(--primary-color); margin-bottom: 12px;"></i>
            <p style="margin: 0 0 12px 0; color: var(--text-secondary);">点击或拖拽文件到此处上传</p>
            <p style="margin: 0; font-size: 12px; color: var(--text-tertiary);">支持 .xlsx/.xls, .json 格式文件，单个文件不超过10MB</p>
            <input ref="fileInputRef" type="file" id="import-file" accept=".xlsx,.xls,.json" style="display: none;" @change="handleFileChange">
            <div v-if="localFile" class="file-info mt-2">
              <i class="fas fa-file-alt"></i>
              <span>{{ localFile.name }}</span>
              <button type="button" class="btn btn-danger ml-2" @click.stop="clearFile">
                <i class="fas fa-times"></i> 移除
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="form-section mt-4" v-if="previewData">
      <h5>导入预览</h5>
      <div class="preview-stats">
        <span class="stat-item">用例数量：{{ previewData.total }} 条</span>
        <span class="stat-item" v-if="previewData.audioConfigsCount > 0">音频配置：{{ previewData.audioConfigsCount }} 条</span>
        <span class="stat-item" v-if="previewData.apiDimensionsCount > 0">API维度：{{ previewData.apiDimensionsCount }} 条</span>
        <span class="stat-item" v-if="previewData.e2eDimensionsCount > 0">E2E维度：{{ previewData.e2eDimensionsCount }} 条</span>
        <span class="stat-item" v-if="previewData.tagsCount > 0">标签：{{ previewData.tagsCount }} 个</span>
      </div>
      <div class="preview-table-container mt-3">
        <table class="table table-sm">
          <thead>
            <tr>
              <th>用例名称</th>
              <th>类型</th>
              <th>分组</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in previewData.items.slice(0, 10)" :key="index">
              <td>{{ item.name }}</td>
              <td>
                <span class="badge" :class="item.type === 'api' ? 'badge-api' : 'badge-e2e'">
                  {{ item.type === 'api' ? 'API' : 'E2E' }}
                </span>
              </td>
              <td>{{ item.group }}</td>
              <td>
                <span v-if="item.operation === 'update'" class="status-existing">更新</span>
                <span v-else class="status-new">新增</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="previewData.items.length > 10" class="preview-more">
          显示前10条，共 {{ previewData.items.length }} 条...
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { testcasesApi } from '../../../../utils/api';
import type { ImportPreviewData } from './types';

const emit = defineEmits<{
  (e: 'update', data: { file: File | null }): void;
  (e: 'submit'): void;
}>();

const localFile = ref<File | null>(null);
const isDragging = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);
const previewData = ref<ImportPreviewData | null>(null);

function triggerFileSelect() {
  fileInputRef.value?.click();
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement | null;
  const file = input?.files?.[0] || null;
  setFile(file);
  if (input) input.value = '';
}

function handleDrop(event: DragEvent) {
  isDragging.value = false;
  const file = event.dataTransfer?.files?.[0] || null;
  setFile(file);
  if (fileInputRef.value) fileInputRef.value.value = '';
}

function setFile(file: File | null) {
  if (!file) {
    localFile.value = null;
    previewData.value = null;
    emit('update', { file: null });
    return;
  }

  if (file.size > 10 * 1024 * 1024) {
    alert('文件大小不能超过10MB');
    return;
  }

  const validTypes = ['.json', '.xlsx', '.xls'];
  const fileName = file.name.toLowerCase();
  const isValidType = validTypes.some(type => fileName.endsWith(type));
  if (!isValidType) {
    alert('请选择 .json 或 .xlsx/.xls 格式的文件');
    return;
  }

  localFile.value = file;
  emit('update', { file });
  updatePreview();
}

function clearFile() {
  localFile.value = null;
  previewData.value = null;
  emit('update', { file: null });
  if (fileInputRef.value) fileInputRef.value.value = '';
}

async function updatePreview() {
  if (!localFile.value) {
    previewData.value = null;
    return;
  }

  try {
    const formData = new FormData();
    formData.append('file', localFile.value);

    const response = await testcasesApi.previewImport(formData);
    const data = (response && typeof response === 'object' && 'data' in response)
      ? (response as any).data
      : response;

    if (!data) {
      previewData.value = null;
      return;
    }

    const testCases = data.testCases || data.testcases || [];
    const previewErrors = Array.isArray(data.errors) ? data.errors : [];

    if (previewErrors.length > 0 && testCases.length === 0) {
      const maxLines = 50;
      const shown = previewErrors.slice(0, maxLines).map(String).join('\n');
      const more = previewErrors.length > maxLines ? `\n...（共${previewErrors.length}条）` : '';
      alert(`获取导入预览失败：${previewErrors.length} 个错误\n${shown}${more}`);
      previewData.value = null;
      return;
    }

    const audioConfigs = data.audioConfigs || data.audio_configs || [];
    const apiDimensions = data.apiDimensions || data.api_dimensions || [];
    const e2eDimensions = data.e2eDimensions || data.e2e_dimensions || [];

    previewData.value = {
      total: data.totalRows || data.total_rows || testCases.length,
      items: testCases.map((tc: Record<string, unknown>) => ({
        name: (tc.NAME || tc.name || '未命名') as string,
        type: (tc.TEST_TYPE || tc.testType || tc.type || 'api') as string,
        group: (tc.GROUP_NAME || tc.groupName || tc.group || '未分类') as string,
        operation: (tc.ID || tc.id) ? 'update' as const : 'insert' as const
      })),
      audioConfigsCount: audioConfigs.length,
      apiDimensionsCount: apiDimensions.length,
      e2eDimensionsCount: e2eDimensions.length,
      tagsCount: (data.tags || []).length,
      groupsCount: (data.groups || []).length,
      sheetNames: Object.keys(data).filter(key =>
        Array.isArray((data as any)[key]) && (data as any)[key].length > 0
      )
    };
  } catch (error: any) {
    console.error('获取导入预览失败:', error);
    alert('获取导入预览失败: ' + (error?.message || '未知错误'));
    previewData.value = null;
  }
}

async function downloadTemplate() {
  try {
    const response = await testcasesApi.downloadTemplate();
    const blob = response instanceof Blob ? response : new Blob([response]);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `测试用例导入模板_${new Date().toLocaleDateString()}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (error: unknown) {
    console.error('下载模板失败:', error);
    alert('下载模板失败: ' + ((error as Error).message || '未知错误'));
  }
}

function handleSubmit() {
  if (!localFile.value) {
    alert('请选择要导入的文件');
    return;
  }
  emit('submit');
}

defineExpose({
  handleSubmit,
  localFile
});
</script>

<style scoped>
.import-form {
  padding: 0;
}

.form-section {
  margin: 16px 0;
}

.form-section h5 {
  margin-bottom: 16px;
  font-weight: 600;
}

.form-row {
  margin-bottom: 16px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
}

.required {
  color: #dc3545;
  font-weight: bold;
}

.file-upload {
  border: 2px dashed var(--border-color, #ced4da);
  border-radius: 8px;
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.file-upload:hover {
  border-color: var(--primary-color, #007bff);
  background: rgba(0, 123, 255, 0.05);
}

.file-upload.is-dragging {
  border-color: var(--primary-color, #007bff);
  background: rgba(0, 123, 255, 0.1);
}

.file-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.preview-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 14px;
}

.stat-item {
  background: #e9ecef;
  padding: 4px 12px;
  border-radius: 4px;
}

.preview-table-container {
  max-height: 300px;
  overflow-y: auto;
}

.table {
  width: 100%;
  border-collapse: collapse;
}

.table th,
.table td {
  padding: 8px 12px;
  border: 1px solid #dee2e6;
  text-align: left;
}

.table th {
  background: #f8f9fa;
  font-weight: 600;
}

.badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.badge-api {
  background: #28a745;
  color: white;
}

.badge-e2e {
  background: #17a2b8;
  color: white;
}

.status-existing {
  color: #ffc107;
  font-weight: 500;
}

.status-new {
  color: #28a745;
  font-weight: 500;
}

.preview-more {
  text-align: center;
  padding: 8px;
  color: #6c757d;
  font-size: 12px;
}
</style>
