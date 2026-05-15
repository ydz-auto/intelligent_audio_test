import { ref, type Ref } from 'vue';
import type { AudioUploadTask } from '../shared/types';

export type UploadStatus = 'idle' | 'preparing' | 'uploading' | 'paused' | 'completed' | 'failed' | 'stopped';

export interface UploadState {
  uploadProgress: Ref<number>;
  currentTask: Ref<AudioUploadTask | null>;
  currentUploadingFile: Ref<string | null>;
  isRetryingFailed: Ref<boolean>;
  uploadStatus: Ref<UploadStatus>;
}

const globalKey = '__upload_state_instance__';

declare global {
  interface Window {
    [globalKey]?: UploadState;
  }
}

let stateInstance: UploadState | null = null;

export function useUploadState(): UploadState {
  if (window[globalKey]) {
    return window[globalKey]!;
  }

  if (stateInstance) {
    return stateInstance;
  }

  const uploadProgress = ref(0);
  const currentTask = ref<AudioUploadTask | null>(null);
  const currentUploadingFile = ref<string | null>(null);
  const isRetryingFailed = ref(false);
  const uploadStatus = ref<UploadStatus>('idle');

  stateInstance = {
    uploadProgress,
    currentTask,
    currentUploadingFile,
    isRetryingFailed,
    uploadStatus
  };

  window[globalKey] = stateInstance;

  return stateInstance;
}
