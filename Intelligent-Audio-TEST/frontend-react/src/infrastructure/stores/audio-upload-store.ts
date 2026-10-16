/**
 * 音频上传任务 store（infrastructure 层；16_设备域.md §5.4 上传进度卡数据源）。
 * 多上传任务入队 + 暂停/继续/取消/优先级；进度全本地计算（服务端 GET /audios/upload/progress
 * 前端未接，§11-18 缺口）；localStorage 'audioUploadTasks' 持久化，刷新自动恢复（§5.4）。
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
  /** 总体进度 0-100 */
  progress: number
  paused: boolean
  /** 任务优先级（1 高 / 2 中 / 3 低） */
  priority: 1 | 2 | 3
  files: UploadFileItem[]
  /** 当前文件行（含导入速度/预计剩余时间） */
  currentFile: UploadFileItem | null
  /** 导入速度（MB/s） */
  speed: number
  /** 预计剩余时间（秒） */
  etaSeconds: number
  createdAt: string
}

type AudioUploadState = {
  tasks: AudioUploadTask[]
  /** 入队新上传任务（upload-dialog 提交后调用） */
  enqueueTask: (input: {
    name: string
    fileNames: string[]
  }) => string
  advanceProgress: (id: string) => void
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
        const task: AudioUploadTask = {
          id,
          name: input.name,
          progress: 2,
          paused: false,
          priority: 2,
          files: input.fileNames.map((name, index) => ({
            name,
            size: 1_024_000 + index * 512_000,
            status: index === 0 ? 'uploading' : 'pending',
          })),
          currentFile: {
            name: input.fileNames[0] ?? '',
            size: 1_024_000,
            status: 'uploading',
          },
          speed: 6.4,
          etaSeconds: 42,
          createdAt: new Date().toISOString(),
        }
        set({ tasks: [task, ...get().tasks] })
        return id
      },

      advanceProgress: (id) => {
        set({
          tasks: get().tasks.map((task) => {
            if (task.id !== id || task.paused || task.progress >= 100) return task
            const next = Math.min(task.progress + 3, 100)
            const total = task.files.length
            const activeIndex = Math.min(
              Math.floor((next / 100) * total),
              total - 1
            )
            return {
              ...task,
              progress: next,
              speed: Number((task.speed + (Math.random() - 0.5) * 0.8).toFixed(1)),
              etaSeconds: Math.max(0, task.etaSeconds - 2),
              files: task.files.map((file, index) => {
                if (index < activeIndex) return { ...file, status: 'success' }
                if (index === activeIndex) return { ...file, status: 'uploading' }
                return file
              }),
              currentFile: {
                ...task.files[activeIndex],
                status: 'uploading',
              },
            }
          }),
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
    }
  )
)
