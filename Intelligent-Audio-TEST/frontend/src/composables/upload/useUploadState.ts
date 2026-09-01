import { ref, type Ref } from 'vue';
import type { AudioUploadTask } from '../../shared/types';
import { UploadStatus as UploadStatusEnum } from '@/shared/types/enums';

/** 上传状态机：idle → preparing → uploading → completed/failed，可进入 paused/stopped */
export const UploadStatus = {
  IDLE: UploadStatusEnum.IDLE,
  PREPARING: UploadStatusEnum.PREPARING,
  UPLOADING: UploadStatusEnum.UPLOADING,
  PAUSED: UploadStatusEnum.PAUSED,
  COMPLETED: UploadStatusEnum.COMPLETED,
  FAILED: UploadStatusEnum.FAILED,
  STOPPED: UploadStatusEnum.STOPPED,
} as const;

export type UploadStatus = typeof UploadStatus[keyof typeof UploadStatus];

export type UploadAction = 'openUploadModal' | 'openFolderImport' | 'dismissTask' | 'pauseTask' | 'retryTask' | null;

export interface UploadActionPayload {
  action: UploadAction;
  taskId?: string;
}

export interface UploadState {
  uploadProgress: Ref<number>;
  currentTask: Ref<AudioUploadTask | null>;
  currentUploadingFile: Ref<string | null>;
  isRetryingFailed: Ref<boolean>;
  uploadStatus: Ref<UploadStatus>;
  pendingAction: Ref<UploadActionPayload>;
  requestAction: (action: UploadAction, taskId?: string) => void;
  consumeAction: () => UploadActionPayload;
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
  const uploadStatus = ref<UploadStatus>(UploadStatus.IDLE);
  const pendingAction = ref<UploadActionPayload>({ action: null });

  const requestAction = (action: UploadAction, taskId?: string) => {
    pendingAction.value = { action, taskId };
  };

  const consumeAction = (): UploadActionPayload => {
    const payload = { ...pendingAction.value };
    pendingAction.value = { action: null };
    return payload;
  };

  stateInstance = {
    uploadProgress,
    currentTask,
    currentUploadingFile,
    isRetryingFailed,
    uploadStatus,
    pendingAction,
    requestAction,
    consumeAction
  };

  window[globalKey] = stateInstance;

  return stateInstance;
}
