/**
 * 音频真实上传流程（application 层；INT-714 接线——导入音频 + 生成测试用例）。
 * 入队真实上传任务 → init/register/chunk/merge 逐文件驱动进度（audio-upload-api），
 * 完成后更新任务卡状态；返回生成用例数与失败清单供弹窗 toast。
 * 数据为「接线测试」语义的测试数据（devloop §3.1：常驻后端，run 结束前删测试用例）。
 */
import { useAudioUploadStore } from '@/infrastructure/stores/audio-upload-store'
import {
  initUploadTask,
  mergeChunks,
  registerUploadFiles,
  uploadChunk,
  type UploadTestCaseConfig,
} from '@/infrastructure/api/audio-upload-api'

export interface UploadBatchResult {
  successCount: number
  failedCount: number
  testCaseCount: number
  failed: Array<{ name: string; error: string }>
}

/** 每文件上传配置覆盖（文件夹导入/上传弹窗：per-folder 分组名 + 解析后的标注随 merge 落库） */
export interface PerFileUploadConfig {
  groupName?: string
  annotations?: unknown[]
}

/** 逐文件真实上传（每个文件独立 register/chunk/merge，merge 载荷 create_test_case 控制生成；用例类型由后端默认落库，INT-714 口径修订） */
export async function runAudioUpload(
  files: File[],
  config: UploadTestCaseConfig,
  onProgress?: (percent: number, currentFile: string) => void,
  perFile?: PerFileUploadConfig[]
): Promise<UploadBatchResult> {
  const result: UploadBatchResult = {
    successCount: 0,
    failedCount: 0,
    testCaseCount: 0,
    failed: [],
  }
  if (files.length === 0) return result

  // 初始化一次上传任务（多文件复用同一 task_id）
  let taskId: string
  try {
    taskId = await initUploadTask()
  } catch (err) {
    result.failed = files.map((f) => ({
      name: f.name,
      error: err instanceof Error ? err.message : '初始化上传任务失败',
    }))
    result.failedCount = files.length
    return result
  }

  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    onProgress?.(2, file.name)
    try {
      // 注册 → 分片上传 → 合并（生成测试用例由 merge 载荷 create_test_case 控制，test_types 不传）
      const [registered] = await registerUploadFiles(taskId, [
        { name: file.name, size: file.size },
      ])
      if (!registered?.fileId) throw new Error('注册文件失败')
      const chunkSize = registered.chunkSize > 0 ? registered.chunkSize : 5 * 1024 * 1024
      const totalChunks = Math.max(1, Math.ceil(file.size / chunkSize))
      for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
        const start = chunkIndex * chunkSize
        const end = Math.min(start + chunkSize, file.size)
        await uploadChunk(taskId, registered.fileId, chunkIndex, totalChunks, file.slice(start, end))
        onProgress?.(2 + Math.round(((chunkIndex + 1) / totalChunks) * 88), file.name)
      }
      const merged = await mergeChunks(taskId, registered.fileId, file.name, {
        ...config,
        // 每文件覆盖：分组名 / 标注（perFile 与 files 平行，缺省用 config 全局值）
        groupName: perFile?.[i]?.groupName ?? config.groupName,
        annotations: perFile?.[i]?.annotations ?? config.annotations ?? [],
      })
      onProgress?.(95, file.name)
      result.successCount += 1
      result.testCaseCount += merged.testCaseCount
    } catch (err) {
      result.failed.push({
        name: file.name,
        error: err instanceof Error ? err.message : String(err),
      })
      result.failedCount += 1
    }
  }
  onProgress?.(100, files[files.length - 1]?.name ?? '')
  return result
}

/** 弹窗层便捷入口：入队真实任务 + 执行上传（供 audio-upload-dialog「开始上传」调用） */
export async function startRealAudioUpload(
  files: File[],
  config: UploadTestCaseConfig,
  perFile?: PerFileUploadConfig[]
): Promise<UploadBatchResult> {
  const enqueueTask = useAudioUploadStore.getState().enqueueTask
  const updateTask = useAudioUploadStore.getState().updateTask
  const id = enqueueTask({
    name: `批量导入 ${files.length} 个文件`,
    fileNames: files.map((f) => f.name),
    real: true,
  })

  return runAudioUpload(files, config, (percent, currentFile) => {
    const fileIndex = files.findIndex((f) => f.name === currentFile)
    updateTask(id, {
      progress: percent,
      currentFile: {
        name: currentFile,
        size: 0,
        status: percent >= 100 ? 'success' : 'uploading',
      },
      files: files.map((f, i) => ({
        name: f.name,
        size: 0,
        status:
          i < fileIndex || percent >= 100 ? 'success' : i === fileIndex ? 'uploading' : 'pending',
      })),
      speed: percent > 2 && percent < 100 ? 5 + Math.random() * 3 : 0,
      etaSeconds: percent < 100 ? Math.max(1, Math.round((100 - percent) / 8)) : 0,
    })
  }, perFile)
}
