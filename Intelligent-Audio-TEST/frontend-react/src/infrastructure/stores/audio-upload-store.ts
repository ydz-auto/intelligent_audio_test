/**
 * 音频上传任务 store（infrastructure 层；16_设备域.md §5.4 上传进度卡数据源）。
 * 多上传任务入队 + 暂停/继续/取消/优先级；进度/速率/预计剩余全部来自真实上传链路
 * （audio-upload-api 分片回调 → updateTask，INT-1512 移除本地模拟推进）；
 * localStorage 'audioUploadTasks' 持久化，刷新自动恢复（§5.4）。
 */
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type UploadFileStatus = 'pending' | 'uploading' | 'success' | 'failed'

export interface UploadFileItem {
  name: string
  size: number
  status: UploadFileStatus
}

export interface AudioUploadTask {
  id: string
  /** 任务名（示例「批量导入 {n} 个文件」） */
  name: string
  /** 总体进度 0-100（真实上传链路回调驱动） */
  progress: number
  paused: boolean
  /** 任务优先级（1 高 / 2 中 / 3 低） */
  priority: 1 | 2 | 3
  files: UploadFileItem[]
  /** 当前文件行（含导入速度/预计剩余时间） */
  currentFile: UploadFileItem | null
  /** 实测导入速度（MB/s；按已上传字节/耗时计算） */
  speed: number
  /** 预计剩余时间（秒；按剩余字节/实测速度推算） */
  etaSeconds: number
  createdAt: string
}

type AudioUploadState = {
  tasks: AudioUploadTask[]
  /** 入队新上传任务（upload-dialog 提交后调用；files 带真实文件大小） */
  enqueueTask: (input: {
    name: string
    files: Array<{ name: string; size: number }>
  }) => string
  /** 真实上传任务进度更新（audio-upload-api 驱动进度） */
  updateTask: (id: string, patch: Partial<AudioUploadTask>) => void
  setPaused: (id: string, paused: boolean) => void
  cancelTask: (id: string) => void
  setPriority: (id: string, priority: 1 | 2 | 3) => void
  retryFailed: (id: string) => void
  ignoreFailed: (id: string) => void
  clearTask: (id: string) => void
}

export const useAudioUploadStore = create<AudioUploadState>()(
  persist(
    (set, get) => ({
      tasks: [],

      enqueueTask: (input) => {
        // localStorage 恢复的任务保留原 id，故以现有任务最大序号为基准递增，避免刷新后撞号（P5）
        const nextSeq = get().tasks.reduce((max, task) => {
          const match = /^upload-(\d+)$/.exec(task.id)
          return match ? Math.max(max, Number(match[1])) : max
        }, 0) + 1
        const id = `upload-${nextSeq}`
        const files: UploadFileItem[] = input.files.map((file, index) => ({
          name: file.name,
          size: file.size,
          status: index === 0 ? 'uploading' : 'pending',
        }))
        const task: AudioUploadTask = {
          id,
          name: input.name,
          progress: 2,
          paused: false,
          priority: 2,
          files,
          currentFile: files[0] ?? null,
          // 速率/剩余时间由首片上传完成后的真实回调回填（不再预置估算值）
          speed: 0,
          etaSeconds: 0,
          createdAt: new Date().toISOString(),
        }
        set({ tasks: [task, ...get().tasks] })
        return id
      },

      updateTask: (id, patch) => {
        set({
          tasks: get().tasks.map((task) =>
            task.id === id ? { ...task, ...patch } : task
          ),
        })
      },

      setPaused: (id, paused) => {
        set({
          tasks: get().tasks.map((task) =>
            task.id === id ? { ...task, paused } : task
          ),
        })
      },

      cancelTask: (id) => {
        set({ tasks: get().tasks.filter((task) => task.id !== id) })
      },

      setPriority: (id, priority) => {
        set({
          tasks: get().tasks.map((task) =>
            task.id === id ? { ...task, priority } : task
          ),
        })
      },

      retryFailed: (id) => {
        set({
          tasks: get().tasks.map((task) =>
            task.id === id
              ? {
                  ...task,
                  paused: false,
                  progress: Math.max(task.progress, 5),
                  files: task.files.map((file) =>
                    file.status === 'failed'
                      ? { ...file, status: 'pending' }
                      : file
                  ),
                }
              : task
          ),
        })
      },

      ignoreFailed: (id) => {
        set({
          tasks: get().tasks.map((task) =>
            task.id === id
              ? {
                  ...task,
                  paused: false,
                  files: task.files.map((file) =>
                    file.status === 'failed'
                      ? { ...file, status: 'success' }
                      : file
                  ),
                }
              : task
          ),
        })
      },

      clearTask: (id) => {
        set({ tasks: get().tasks.filter((task) => task.id !== id) })
      },
    }),
    {
      name: 'audioUploadTasks',
      storage: createJSONStorage(() => localStorage),
      // 刷新后未完成任务的上传链路已中断、后端也无续传接口，旧百分比不再变化；
      // 只恢复已完成任务，避免恢复出一张永久停在中途的进度卡（INT-1512：不用假推进补齐）。
      onRehydrateStorage: () => (state) => {
        if (!state) return
        state.tasks = state.tasks.filter((task) => task.progress >= 100)
      },
    }
  )
)
