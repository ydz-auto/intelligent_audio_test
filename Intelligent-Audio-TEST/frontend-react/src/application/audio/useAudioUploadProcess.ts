/**
 * 音频真实上传流程（application 层；INT-714 接线——导入音频 + 生成测试用例）。
 * 入队真实上传任务 → init/register/chunk/merge 逐文件驱动进度（audio-upload-api），
 * 完成后更新任务卡状态；返回生成用例数与失败清单供弹窗 toast。
 * 进度/速率/预计剩余由真实分片上传链路计算（INT-1512：按已上传字节数与耗时推算，
 * 百分比随累计字节单调递增），不再做本地定时模拟推进。
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

/** 上传进度事件（真实链路：percent 由累计已上传字节占比推算；speed/eta 按实测耗时计算） */
export interface UploadProgressEvent {
  percent: number
  currentFile: string
  /** 实测速率（MB/s） */
  speed: number
  /** 预计剩余秒数（剩余字节 / 实测速率；无法估算时为 0） */
  etaSeconds: number
}

/** 每文件上传配置覆盖（文件夹导入/上传弹窗：per-folder 分组名 + 解析后的标注随 merge 落库） */
export interface PerFileUploadConfig {
  groupName?: string
  annotations?: unknown[]
}

/** 分片阶段在总进度中的占比：init/register 起于 2%，分片累计到 90%，合并 95%，完成 100% */
const PROGRESS_START = 2
const PROGRESS_CHUNK_SPAN = 88
const PROGRESS_MERGED = 95
const PROGRESS_DONE = 100
const BYTES_PER_MB = 1024 * 1024

/** 逐文件真实上传（每个文件独立 register/chunk/merge，merge 载荷 create_test_case 控制生成；用例类型由后端默认落库，INT-714 口径修订） */
export async function runAudioUpload(
  files: File[],
  config: UploadTestCaseConfig,
  onProgress?: (event: UploadProgressEvent) => void,
  perFile?: PerFileUploadConfig[]
): Promise<UploadBatchResult> {
  const result: UploadBatchResult = {
    successCount: 0,
    failedCount: 0,
    testCaseCount: 0,
    failed: [],
  }
  if (files.length === 0) return result

  const totalBytes = files.reduce((sum, file) => sum + file.size, 0)
  let uploadedBytes = 0
  const startedAt = performance.now()

  const emit = (percent: number, currentFile: string) => {
    if (!onProgress) return
    const elapsedSeconds = Math.max((performance.now() - startedAt) / 1000, 0.001)
    const speed = uploadedBytes / elapsedSeconds / BYTES_PER_MB
    const remainingBytes = Math.max(totalBytes - uploadedBytes, 0)
    const etaSeconds =
      speed > 0 ? Math.round(remainingBytes / (speed * BYTES_PER_MB)) : 0
    onProgress({ percent, currentFile, speed, etaSeconds })
  }

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
    const isLastFile = i === files.length - 1
    if (i === 0) emit(PROGRESS_START, file.name)
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
        uploadedBytes += end - start
        const ratio = totalBytes > 0 ? uploadedBytes / totalBytes : 1
        emit(PROGRESS_START + Math.round(ratio * PROGRESS_CHUNK_SPAN), file.name)
      }
      const merged = await mergeChunks(taskId, registered.fileId, file.name, {
        ...config,
        // 每文件覆盖：分组名 / 标注（perFile 与 files 平行，缺省用 config 全局值）
        groupName: perFile?.[i]?.groupName ?? config.groupName,
        annotations: perFile?.[i]?.annotations ?? config.annotations ?? [],
      })
      // 合并阶段只由最后一个文件推到最后档，避免中间文件合并时进度倒退（多文件整体进度单调）
      if (isLastFile) emit(PROGRESS_MERGED, file.name)
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
  emit(PROGRESS_DONE, files[files.length - 1]?.name ?? '')
  return result
}

/** 弹窗层便捷入口：入队真实任务 + 执行上传（供 audio-upload-dialog「开始上传」调用） */
export async function startRealAudioUpload(
  files: File[],
  config: UploadTestCaseConfig,
  perFile?: PerFileUploadConfig[]
): Promise<UploadBatchResult> {
  const { enqueueTask, updateTask } = useAudioUploadStore.getState()
  const id = enqueueTask({
    name: `批量导入 ${files.length} 个文件`,
    files: files.map((file) => ({ name: file.name, size: file.size })),
  })

  const result = await runAudioUpload(files, config, (event) => {
    const fileIndex = files.findIndex((f) => f.name === event.currentFile)
    updateTask(id, {
      progress: event.percent,
      currentFile:
        fileIndex >= 0
          ? {
              name: event.currentFile,
              size: files[fileIndex].size,
              status: 'uploading',
            }
          : null,
      files: files.map((f, i) => ({
        name: f.name,
        size: f.size,
        status:
          i < fileIndex || event.percent >= PROGRESS_DONE
            ? 'success'
            : i === fileIndex
              ? 'uploading'
              : 'pending',
      })),
      speed: event.speed,
      etaSeconds: event.etaSeconds,
    })
  }, perFile)

  // 结束态按真实成功/失败清单落每个文件状态（失败文件不显示为成功）
  const failedNames = new Set(result.failed.map((f) => f.name))
  updateTask(id, {
    progress: PROGRESS_DONE,
    currentFile: null,
    speed: 0,
    etaSeconds: 0,
    files: files.map((file) => ({
      name: file.name,
      size: file.size,
      status: failedNames.has(file.name) ? 'failed' : 'success',
    })),
  })
  return result
}
