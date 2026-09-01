<template>
  <div class="global-upload-progress">
    <div class="progress-header">
      <div class="progress-info">
        <div class="progress-text">{{ progressStatusText }} {{ uploadProgress }}%</div>
        <div class="progress-detail" v-if="currentTask">
          <span>已完成{{ currentTask.completedFiles }}/{{ currentTask.totalFiles }} 个文件</span>
          <span v-if="currentUploadingFile && uploadProgress < 100">当前上传{{ currentUploadingFile }}</span>
          <span v-else-if="currentTask.failedFiles > 0" class="error-text"> ({{ currentTask.failedFiles }} 个文件上传失败)</span>
        </div>
      </div>
      <div class="progress-actions">
        <button 
          class="btn btn-secondary" 
          v-if="uploadProgress === 100 || (currentTask && currentTask.failedFiles && currentTask.failedFiles > 0)" 
          @click="handleDismiss"
        >
          <i class="fas fa-times"></i>
          完成并关闭
        </button>
        <button 
          class="btn btn-danger" 
          v-else-if="uploadProgress > 0 && uploadProgress < 100" 
          @click="handlePause"
        >
          <i class="fas fa-pause"></i>
          取消上传
        </button>
      </div>
    </div>
    <div class="progress-container">
      <div class="progress-bar" :style="{ width: uploadProgress + '%' }"></div>
    </div>
    <div class="file-progress-detail" v-if="currentTask && currentTask.files.length > 0">
      <h4 class="detail-title">文件上传状态</h4>
      <div class="file-progress-list" ref="fileProgressList">
        <div class="file-progress-item" v-for="file in currentTask.files" :key="file.name" :data-file-name="file.name">
          <div class="file-info">
            <span class="file-name">{{ file.name }}</span>
            <span class="file-status" :class="file.status">
              <i class="fas" :class="{
                'fa-check-circle': file.status === UploadStatus.COMPLETED,
                'fa-exclamation-circle': file.status === UploadStatus.FAILED,
                'fa-spinner fa-spin': file.status === UploadStatus.UPLOADING,
                'fa-clock': file.status === UploadStatus.PENDING
              }"></i>
              {{ file.status === UploadStatus.COMPLETED ? '已完成' : file.status === UploadStatus.FAILED ? '失败' : file.status === UploadStatus.UPLOADING ? '上传中' : '待上传' }}
              <span class="error-message" v-if="file.errorMessage">({{ file.errorMessage }})</span>
            </span>
          </div>
          <div class="file-progress">
            <div class="file-progress-bar">
              <div class="file-progress-fill" :style="{ width: (file.uploadedSize / file.size * 100) + '%' }"></div>
            </div>
            <span class="file-progress-text">{{ Math.round((file.uploadedSize / file.size * 100)) }}%</span>
          </div>
        </div>
      </div>
      <div class="retry-section" v-if="currentTask.failedFiles > 0 || isRetryingFailed">
        <button class="btn btn-primary" @click="handleRetry" :disabled="isRetryingFailed">
          <i class="fas fa-redo"></i>
          <span v-if="isRetryingFailed">正在重试上传...</span>
          <span v-else>重试失败文件 ({{ currentTask.failedFiles }})</span>
        </button>
        <button class="btn btn-secondary" @click="handleDismiss" :disabled="isRetryingFailed">
          <i class="fas fa-times"></i>
          <span v-if="isRetryingFailed">正在处理...</span>
          <span v-else>忽略失败文件</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, type Ref } from 'vue';
import { UploadStatus } from '@/shared/types/enums';

interface AudioUploadFile {
  name: string;
  size: number;
  uploadedSize: number;
  status: UploadStatus[keyof UploadStatus];
  errorMessage?: string;
}

interface AudioUploadTask {
  id: string | number;
  totalFiles: number;
  completedFiles: number;
  failedFiles: number;
  files: AudioUploadFile[];
}

const props = defineProps<{
  uploadProgress: number;
  currentTask: AudioUploadTask | null;
  currentUploadingFile: string | null;
  isRetryingFailed: boolean;
}>();

const emit = defineEmits<{
  (e: 'dismiss', taskId: string): void;
  (e: 'pause', taskId: string): void;
  (e: 'retry', taskId: string): void;
}>();

const fileProgressList = ref<HTMLElement | null>(null);

const progressStatusText = computed(() => {
  if (props.uploadProgress <= 2) return '准备中...';
  if (props.uploadProgress <= 15) return '正在校验文件 (MD5)...';
  if (props.uploadProgress <= 20) return '正在同步上传状态...';
  if (props.uploadProgress < 95) return '正在上传文件...';
  if (props.uploadProgress < 100) return '正在完成导入...';
  return '导入完成';
});

const handleDismiss = () => {
  if (props.currentTask) {
    emit('dismiss', String(props.currentTask.id));
  }
};

const handlePause = () => {
  if (props.currentTask) {
    emit('pause', String(props.currentTask.id));
  }
};

const handleRetry = () => {
  if (props.currentTask) {
    emit('retry', String(props.currentTask.id));
  }
};
</script>

<style scoped>
.global-upload-progress {
  margin: 15px 0;
  padding: 10px;
  background-color: var(--background-secondary);
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-sm);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-sm);
}

.progress-info {
  flex: 1;
}

.progress-text {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: var(--font-weight-medium);
  margin-bottom: var(--spacing-xs);
}

.progress-detail {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
}

.progress-detail .error-text {
  color: var(--error-color);
}

.progress-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.progress-container {
  height: 8px;
  background-color: var(--secondary-color);
  border-radius: var(--border-radius-full);
  overflow: hidden;
  margin-bottom: var(--spacing-sm);
}

.progress-bar {
  height: 100%;
  background: var(--primary-gradient);
  border-radius: var(--border-radius-full);
  transition: width 0.3s ease;
}

.file-progress-detail {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background-color: var(--background-primary);
  border-radius: var(--border-radius-md);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
}

.detail-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-md) 0;
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color);
}

.file-progress-list {
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: var(--spacing-md);
  scroll-behavior: smooth;
}

.file-progress-item {
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm);
  background-color: var(--background-secondary);
  border-radius: var(--border-radius-sm);
  transition: all var(--transition-normal);
}

.file-progress-item:hover {
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.file-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xs);
}

.file-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: var(--spacing-sm);
}

.file-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  padding: 2px 8px;
  border-radius: var(--border-radius-full);
  white-space: nowrap;
}

.file-status.pending {
  color: var(--text-secondary);
  background-color: var(--background-tertiary);
}

.file-status.uploading {
  color: var(--primary-color);
  background-color: var(--primary-light);
}

.file-status.completed {
  color: var(--success-color);
  background-color: var(--success-light);
}

.file-status.failed {
  color: var(--error-color);
  background-color: var(--error-light);
}

.error-message {
  color: var(--error-color);
  font-size: var(--font-size-xs);
  margin-left: var(--spacing-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-progress {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.file-progress-bar {
  flex: 1;
  height: 6px;
  background-color: var(--secondary-color);
  border-radius: var(--border-radius-full);
  overflow: hidden;
}

.file-progress-fill {
  height: 100%;
  background: var(--primary-gradient);
  border-radius: var(--border-radius-full);
  transition: width 0.3s ease;
}

.file-progress-text {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  white-space: nowrap;
  width: 40px;
  text-align: right;
}

.retry-section {
  text-align: center;
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-color);
}

.retry-section .btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin: 0 var(--spacing-sm);
}
</style>
