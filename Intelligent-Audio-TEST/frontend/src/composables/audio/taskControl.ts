import type { Ref } from 'vue';
import { audiosApi } from '../../utils/api';
import type { AudioUploadFile, AudioUploadTask, APIResponse } from '../../shared/types';
import { calculateMd5 } from './md5Utils';
import { getLocalTasks, saveLocalTask } from './taskPersistence';
import { updateOverallProgress, type UploadProcessContext } from './uploadProcess';

/**
 * 任务控制：暂停/恢复/重试/移除/检查未完成任务
 */

export interface TaskControlContext extends UploadProcessContext {
  isRetryingFailed: Ref<boolean>;
  uploadFileChunks: (
    ctx: UploadProcessContext,
    taskId: string,
    fileTask: AudioUploadFile,
    options: any,
    tcConfig?: any
  ) => Promise<void>;
}

export const pauseUploadTask = (
  ctx: TaskControlContext,
  taskId: string
) => {
  const { currentTask, uploadStatus, setAbortController } = ctx;
  if (currentTask.value?.id === taskId) {
    uploadStatus.value = 'paused';
    currentTask.value.status = 'paused';
    saveLocalTask(currentTask.value, ctx.uploadTasks);
    ctx.getAbortController()?.abort();
  }
};

export async function resumeUploadTask(
  ctx: TaskControlContext,
  taskId: string,
  isRetry = false,
  onUploadComplete?: () => void
) {
  const { uploadTasks, currentTask, uploadStatus, currentUploadingFile, setAbortController, isRetryingFailed, uploadFileChunks, uploadOptions } = ctx;

  const task = uploadTasks.value.find(t => t.id === taskId);
  if (!task) return;

  currentTask.value = task;
  uploadStatus.value = 'uploading';
  task.status = 'uploading';
  setAbortController(new AbortController());
  const taskOptions = task.options || uploadOptions;

  for (const fileTask of task.files) {
    if ((uploadStatus.value as string) === 'paused' || (uploadStatus.value as string) === 'stopped') break;
    if (fileTask.status !== 'completed') {
      try {
        fileTask.status = 'uploading';
        currentUploadingFile.value = fileTask.name;
        await uploadFileChunks(ctx, taskId, fileTask, taskOptions);
        fileTask.status = 'completed';
        fileTask.progress = 100;
        saveLocalTask(task, ctx.uploadTasks);
      } catch (err) {
        fileTask.status = 'failed';
        fileTask.error = err instanceof Error ? err.message : String(err);
        saveLocalTask(task, ctx.uploadTasks);
      }
      updateOverallProgress(ctx);
    }
  }

  task.completedFiles = task.files.filter(f => f.status === 'completed').length;
  task.failedFiles = task.files.filter(f => f.status === 'failed').length;

  uploadStatus.value = task.failedFiles > 0 ? 'failed' : 'completed';
  task.status = uploadStatus.value;
  task.endTime = new Date().toISOString();
  saveLocalTask(task, ctx.uploadTasks);

  isRetryingFailed.value = false;
  if (onUploadComplete) onUploadComplete();
}

export async function retryFailedFiles(
  ctx: TaskControlContext,
  taskId: string,
  autoSelectFiles = false,
  onUploadComplete?: () => void
) {
  const { uploadTasks, isRetryingFailed } = ctx;

  const task = uploadTasks.value.find(t => t.id === taskId);
  if (!task) return;

  isRetryingFailed.value = true;
  const previousFailedFiles = task.files.filter(f => f.status === 'failed');
  const fileData = [];
  let canReRegister = true;
  let needReSelectFiles = false;
  let failedFileNames: string[] = [];

  for (const fileTask of previousFailedFiles) {
    failedFileNames.push(fileTask.name);
    if (fileTask.file && typeof fileTask.file.slice === 'function') {
      try {
        const md5 = await calculateMd5(fileTask.file);
        fileData.push({
          name: fileTask.name,
          size: fileTask.size,
          md5
        });
      } catch (md5Err) {
        console.error('计算MD5失败:', fileTask.name, md5Err);
        canReRegister = false;
        needReSelectFiles = true;
      }
    } else {
      canReRegister = false;
      needReSelectFiles = true;
    }
  }

  if (needReSelectFiles || autoSelectFiles) {
    setTimeout(async () => {
      const input = document.createElement('input');
      input.type = 'file';
      input.multiple = true;
      input.accept = 'audio/*,.wav,.mp3,.m4a,.flac';
      input.onchange = async (e: any) => {
        const files = e.target.files;
        if (files && files.length > 0) {
          const selectedFiles = Array.from(files);
          const newFileTasks: typeof task.files = [];

          for (const file of selectedFiles) {
            if (failedFileNames.includes(file.name)) {
              const md5 = await calculateMd5(file);
              const fileId = `f_${Math.random().toString(36).substring(2, 11)}`;
              newFileTasks.push({
                id: fileId,
                fileId,
                file,
                name: file.name,
                size: file.size,
                md5,
                status: 'pending' as const,
                progress: 0,
                uploadedSize: 0,
                uploadedChunks: []
              });
            }
          }

          if (newFileTasks.length > 0) {
            task.files = task.files.filter(f => f.status !== 'failed');
            task.files.push(...newFileTasks);
            task.failedFiles = 0;
            task.completedFiles = task.files.filter(f => f.status === 'completed').length;
            task.totalFiles = task.files.length;
            saveLocalTask(task, ctx.uploadTasks);

            const newFileData = newFileTasks.map(ft => ({
              name: ft.name,
              size: ft.size,
              md5: ft.md5
            }));

            try {
              const regResponse = await audiosApi.registerUploadFiles(taskId, newFileData, {
                signal: ctx.getAbortController()?.signal,
                unwrapResponse: false
              }) as APIResponse<{ files: any[] }>;

              if (regResponse.data?.files) {
                newFileTasks.forEach((ft, idx) => {
                  const reg = regResponse.data.files[idx];
                  if (reg) {
                    ft.fileId = reg.fileId;
                    ft.totalChunks = reg.totalChunks;
                    ft.chunkSize = reg.chunkSize;
                  }
                });
              }
            } catch (regErr) {
              console.error('重新注册文件失败:', regErr);
            }

            await resumeUploadTask(ctx, taskId, false, onUploadComplete);
          }
        } else {
          isRetryingFailed.value = false;
        }
      };
      input.click();
    }, 100);
    return;
  }

  if (canReRegister && fileData.length > 0) {
    try {
      const regResponse = await audiosApi.registerUploadFiles(taskId, fileData, {
        signal: ctx.getAbortController()?.signal,
        unwrapResponse: false
      }) as APIResponse<{ files: any[] }>;

      if (regResponse.data?.files) {
        previousFailedFiles.forEach((fileTask, idx) => {
          const reg = regResponse.data.files[idx];
          if (reg) {
            fileTask.fileId = reg.fileId;
            fileTask.totalChunks = reg.totalChunks;
            fileTask.chunkSize = reg.chunkSize;
            fileTask.uploadedChunks = [];
            fileTask.progress = 0;
            fileTask.uploadedSize = 0;
            fileTask.status = 'pending';
            fileTask.error = undefined;
          }
        });
      }
    } catch (regErr) {
      console.error('重新注册文件失败:', regErr);
    }
  }

  task.files.forEach(f => {
    if (f.status === 'failed') f.status = 'pending';
  });

  task.failedFiles = 0;
  task.completedFiles = 0;
  saveLocalTask(task, ctx.uploadTasks);

  await resumeUploadTask(ctx, taskId, false, onUploadComplete);
}

export function removeLocalTask(
  ctx: TaskControlContext,
  taskId: string
) {
  const { uploadTasks, currentTask, uploadStatus, uploadProgress } = ctx;
  const tasks = getLocalTasks().filter(t => t.id !== taskId);
  localStorage.setItem('audioUploadTasks', JSON.stringify(tasks));
  uploadTasks.value = tasks;
  if (currentTask.value?.id === taskId) {
    currentTask.value = null;
    uploadStatus.value = 'idle';
    uploadProgress.value = 0;
  }
}

export function dismissTask(
  ctx: TaskControlContext,
  taskId: string,
  onUploadComplete?: () => void
) {
  removeLocalTask(ctx, taskId);
  if (onUploadComplete) onUploadComplete();
}

export function checkAndResumeTasks(
  ctx: TaskControlContext,
  onUploadComplete?: () => void
) {
  const tasks = getLocalTasks();
  const unfinished = tasks.find(t => t.status === 'uploading' || t.status === 'paused');
  if (unfinished && unfinished.id) {
    resumeUploadTask(ctx, unfinished.id, false, onUploadComplete);
  }
}
